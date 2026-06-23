"""Deterministic validation + weighted confidence for an extracted fiche.

This is the structural-validation layer that runs after the VLM/OCR pass and
before persistence. It does NOT trust the model's self-reported confidence: it
applies hard rules (length/pattern/range/time-order/quantity-consistency/known
operator) that catch *confident-but-wrong* values — the failure mode a single
VLM pass can't catch on its own.

Pure Python, no model calls — cheap and deterministic.
"""

from __future__ import annotations

from pydantic import BaseModel

from .extraction import ControlRow, FicheExtraction, OperationRow

# --- Weighted confidence ----------------------------------------------------
#
# A flat average is dominated by the many blank cells and treats a critical
# ref_produit the same as a free-text outillage. We weight by business
# importance and only count *filled* table cells (a correctly-blank row should
# neither help nor hurt), while always counting the critical header fields so a
# missing ref/OF correctly tanks the score.
FIELD_WEIGHTS: dict[str, float] = {
    "ref_produit": 5.0,
    "n_of": 4.0,
    "qte": 3.0,
    "matricule_operateur": 3.0,
    "resultat": 3.0,
    "qte_realisee": 2.0,
    "numero_serie": 2.0,
    "applicable": 1.0,
    "heure_debut": 1.0,
    "heure_fin": 1.0,
    "date_op": 1.0,
    "date_fin": 1.0,
    "outillage": 1.0,
    "methode": 1.0,
    "annotation_serie": 1.0,
}


def weighted_overall_confidence(ex: FicheExtraction) -> float:
    """Importance-weighted confidence over the header + every filled table cell."""
    num = den = 0.0

    def add(name: str, field, *, always: bool = False) -> None:
        nonlocal num, den
        if field is None:
            return
        if not always and field.value is None:
            return
        w = FIELD_WEIGHTS.get(name, 1.0)
        num += w * float(field.confidence)
        den += w

    h = ex.header
    add("ref_produit", h.ref_produit, always=True)
    add("n_of", h.n_of, always=True)
    add("qte", h.qte, always=True)
    add("annotation_serie", h.annotation_serie)
    for row in (*ex.operations, *ex.controls):
        for name in ("applicable", "date_op", "heure_debut", "heure_fin", "qte_realisee", "outillage", "matricule_operateur"):
            add(name, getattr(row, name, None))
        add("resultat", getattr(row, "resultat", None))
        add("methode", getattr(row, "methode", None))
    for it in ex.items:
        add("numero_serie", it.numero_serie)

    return round(num / den, 3) if den else 0.0


# --- Validation rules -------------------------------------------------------


class ValidationIssue(BaseModel):
    scope: str  # "header" | "operation" | "control"
    location: str  # human label, e.g. "Réf. Produit" or "P1.3 Sertissage"
    field: str  # machine field name
    level: str  # "error" | "warning"
    code: str  # machine code, e.g. "ref_non_numerique"
    message: str  # French, operator-facing


def _digits(s: object) -> str:
    return "".join(ch for ch in str(s) if ch.isdigit())


def _has_data(row: OperationRow) -> bool:
    return (
        row.applicable.value is not None
        or bool(row.matricule_operateur.value)
        or row.qte_realisee.value is not None
        or bool(row.date_op.raw_text or row.date_op.value)
        or row.heure_debut.value is not None
    )


def validate_extraction(
    ex: FicheExtraction, known_matricules: set[str] | None = None
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    known = known_matricules or set()

    def add(scope, location, field, level, code, message):
        issues.append(ValidationIssue(scope=scope, location=location, field=field, level=level, code=code, message=message))

    h = ex.header
    # --- Header ---
    ref = h.ref_produit.value
    if not ref:
        add("header", "Réf. Produit", "ref_produit", "error", "ref_absent", "Réf. Produit non lue.")
    else:
        d = _digits(ref)
        if len(d) != len(str(ref).replace(" ", "")):
            add("header", "Réf. Produit", "ref_produit", "error", "ref_non_numerique", f"Réf. Produit contient des caractères non numériques: «{ref}».")
        if not (6 <= len(d) <= 12):
            add("header", "Réf. Produit", "ref_produit", "warning", "ref_longueur", f"Longueur de réf. inhabituelle ({len(d)} chiffres).")

    nof = h.n_of.value
    if not nof:
        add("header", "N° OF", "n_of", "error", "of_absent", "N° OF non lu.")
    elif not (2 <= len(_digits(nof)) <= 8):
        add("header", "N° OF", "n_of", "warning", "of_longueur", f"N° OF inhabituel: «{nof}».")

    qte = h.qte.value
    if qte is None:
        add("header", "Quantité", "qte", "warning", "qte_absente", "Quantité non lue.")
    elif not (0 < qte < 1000):
        add("header", "Quantité", "qte", "warning", "qte_hors_plage", f"Quantité hors plage attendue: {qte}.")

    # --- Operations + controls ---
    for row in (*ex.operations, *ex.controls):
        loc = f"{row.partie.value if hasattr(row.partie, 'value') else row.partie}·{row.nom_operation[:24]}"
        is_op = isinstance(row, OperationRow) and not isinstance(row, ControlRow)
        if is_op and not _has_data(row):
            continue

        hd, hf = row.heure_debut.value, row.heure_fin.value
        if hd is not None and hf is not None and row.date_fin.value is None and hf < hd:
            add("operation", loc, "heure_fin", "warning", "heure_incoherente", f"{loc}: heure de fin ({hf}) antérieure au début ({hd}).")

        qr = row.qte_realisee.value
        if qr is not None and qte is not None and qr > qte:
            add("operation", loc, "qte_realisee", "warning", "qte_superieure", f"{loc}: qté réalisée ({qr}) supérieure à la qté OF ({qte}).")

        mat = row.matricule_operateur.value
        if mat:
            digits = "".join(c for c in str(mat) if c.isdigit())
            if not (2 <= len(digits) <= 4):
                add("operation", loc, "matricule_operateur", "warning", "matricule_invalide", f"{loc}: matricule «{mat}» n'a pas un format plausible (2 à 4 chiffres).")
            elif known and str(mat) not in known:
                add("operation", loc, "matricule_operateur", "warning", "matricule_inconnu", f"{loc}: matricule «{mat}» absent du référentiel opérateurs.")

    return issues


def low_confidence_or_flagged(ex: FicheExtraction, issues: list[ValidationIssue], threshold: float = 0.6) -> bool:
    """True if the fiche should go to the human review queue rather than auto-accept."""
    if any(i.level == "error" for i in issues):
        return True
    if weighted_overall_confidence(ex) < threshold:
        return True
    return False
