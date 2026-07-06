"""Deterministic validation + weighted confidence for an extracted fiche.

This is the structural-validation layer that runs after the VLM/OCR pass and
before persistence. It does NOT trust the model's self-reported confidence: it
applies hard rules (length/pattern/range/time-order/quantity-consistency/known
operator) that catch *confident-but-wrong* values — the failure mode a single
VLM pass can't catch on its own.

Pure Python, no model calls — cheap and deterministic.
"""

from __future__ import annotations

import os
import re
from collections import Counter

from pydantic import BaseModel

from .extraction import ControlRow, FicheExtraction, OperationRow

# Agilink product refs are 8 digits and (observed 17/18 of the time) start with
# "10" — a ref that doesn't is almost certainly a leading-digit misread
# (e.g. 10108044 read as 20208044, 1→2). Flag it. Configurable via REF_PREFIX;
# set REF_PREFIX="" to disable the check.
_REF_PREFIX = os.environ.get("REF_PREFIX", "10")
_REF_LEN = int(os.environ.get("REF_LEN", "8"))  # Agilink product refs are 8 digits

# The learned operator roster is only authoritative once it holds at least this
# many operators. Below it (a freshly-cleaned DB, or a roster that simply can't
# be kept fully up to date) we DON'T gate auto-validation on operator-recognition
# signals (majority-unknown, near-miss-of-known) — everything looks unknown and
# real operators would be refused. Agilink runs ~20 operators, so ~12 means "most
# of the team is known"; below that, operator checks are advisory only.
_ROSTER_MATURE = int(os.environ.get("ROSTER_MATURE_MIN", "12"))

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


# Digit pairs that look alike in this handwriting (see worker/extract/prompt.py
# _DIGIT_NOTE, which asks the model to double-check these before settling).
_CONFUSION_PAIRS = (
    frozenset({"0", "6"}), frozenset({"5", "9"}), frozenset({"4", "9"}),
    frozenset({"1", "7"}), frozenset({"2", "8"}), frozenset({"3", "8"}),
    # 4 written with an angular open top reads as 1 (observed: 164 -> 161).
    frozenset({"1", "4"}),
)


def systematic_misreads(sheet_counts: dict[str, int], min_sheets: int = 2) -> set[str]:
    """Matricules that recur ONLY because a common operator is misread the same
    way every time (e.g. 164 -> 161), NOT because they're a real person.

    A random misread almost never repeats identically, so "seen on >= 2 sheets"
    normally means a real operator — but a *systematic* misread of a frequent
    operator does repeat. We detect it by shape + frequency: a value seen on a
    few sheets that is a single handwriting-confusion digit away from an operator
    seen VASTLY more often (>=6x, and >=8 sheets) is that operator misread, and
    must NOT be trusted as its own roster entry or the misread self-validates.
    The bar is deliberately high: two genuinely distinct operators can resemble
    each other (e.g. 339 and 389 both real), so only an overwhelming frequency
    gap — the fingerprint of one common operator misread on a few sheets (164 ->
    161, 18 vs 2) — counts, never a merely-more-common neighbour.
    """
    seen = {m for m, n in sheet_counts.items() if n >= min_sheets}
    misreads: set[str] = set()
    for x in seen:
        nx = sheet_counts[x]
        for y in seen:
            if y == x or sheet_counts[y] < max(8, 6 * nx) or len(x) != len(y):
                continue
            diffs = [frozenset((a, b)) for a, b in zip(x, y) if a != b]
            if len(diffs) == 1 and diffs[0] in _CONFUSION_PAIRS:
                misreads.add(x)
                break
    return misreads


def _confusable_known_match(mat: str, known: set[str]) -> str | None:
    """A *single* known matricule that differs from `mat` by exactly one
    digit, where that substitution is a common handwriting confusion pair.

    Catches the failure mode the per-Partie majority-vote check structurally
    can't: a digit misread the SAME way on every row of a fiche (no internal
    outlier to flag) is invisible to that check, but if the correct value has
    ever been registered (a human validated it elsewhere), this turns a
    generic "unknown operator" into a specific, actionable hint instead.
    Requires a unique match — two equally-plausible known candidates would
    make the suggestion a guess, not a signal.
    """
    matches = []
    for k in known:
        if len(k) != len(mat):
            continue
        diffs = [frozenset((a, b)) for a, b in zip(mat, k) if a != b]
        if len(diffs) == 1 and diffs[0] in _CONFUSION_PAIRS:
            matches.append(k)
    return matches[0] if len(matches) == 1 else None


def split_matricules(mat: object) -> list[str]:
    """A matricule cell can hold two operators ("347/338") — split into the
    individual operator tokens so each is validated / looked-up / counted on its
    own. A single-operator cell returns a one-element list."""
    if not mat:
        return []
    return [p.strip() for p in re.split(r"[/\-,;]+", str(mat)) if p.strip()]


def _day_month(text: object) -> tuple[int, int] | None:
    """A "DD/MM" (or ".", "-") reading -> (month, day) for ordering, else None."""
    if not text:
        return None
    parts = re.split(r"[./-]", str(text).strip())
    if len(parts) != 2:
        return None
    try:
        d, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return (m, d) if 1 <= d <= 31 and 1 <= m <= 12 else None


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
        # Agilink product refs are 8 digits. A ref more than one digit off (e.g.
        # "1010" = 4 digits, truncated at a space) is incomplete/misread and must
        # NOT auto-validate — this is a critical identity field.
        if d and abs(len(d) - _REF_LEN) > 1:
            add("header", "Réf. Produit", "ref_produit", "warning", "ref_longueur", f"Réf. «{ref}» a {len(d)} chiffres (attendu {_REF_LEN}) — probablement incomplète ou mal lue.")
        if _REF_PREFIX and d and not d.startswith(_REF_PREFIX):
            add("header", "Réf. Produit", "ref_produit", "warning", "ref_prefixe", f"Réf. «{ref}» ne commence pas par «{_REF_PREFIX}» (format produit attendu) — probable erreur de lecture (ex. 1 lu comme 2).")

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

    # Every matricule token present on THIS fiche, and how many rows use each —
    # context for telling a real operator (fills a Partie / co-appears with the
    # operator it resembles) from a one-off misread.
    fiche_mat_counts: Counter = Counter()
    for row in (*ex.operations, *ex.controls):
        for p in split_matricules(row.matricule_operateur.value):
            fiche_mat_counts[p] += 1

    # --- Operations + controls ---
    for row in (*ex.operations, *ex.controls):
        loc = f"{row.partie.value if hasattr(row.partie, 'value') else row.partie}·{row.nom_operation[:24]}"
        is_op = isinstance(row, OperationRow) and not isinstance(row, ControlRow)
        if is_op and not _has_data(row):
            continue

        hd, hf = row.heure_debut.value, row.heure_fin.value
        if hd is not None and hf is not None and row.date_fin.value is None and hf < hd:
            add("operation", loc, "heure_fin", "warning", "heure_incoherente", f"{loc}: heure de fin ({hf}) antérieure au début ({hd}).")

        # qte_realisee tracks the same batch through every operation row, so in
        # practice it's almost always equal to the header qte — not just "not
        # greater than" it. A mismatch in either direction (e.g. a misread "20"
        # as "200", or "49" as "219") is a strong misread signal, not a
        # legitimate partial-batch case on these sheets.
        qr = row.qte_realisee.value
        if qr is not None and qte is not None and qr != qte:
            lo, hi = sorted((qr, qte))
            # An extra/missing digit or a >=2x gap (20->200, 20->4) is the real
            # quantity MISREAD this check exists to catch -> hard signal. A small
            # slip (12 vs 13) is far more often a faithful read of an operator's
            # per-row partial count or a paper inconsistency than a bad read, so
            # it stays advisory and must not refuse an otherwise-correct sheet.
            if lo <= 0 or hi / lo >= 2:
                add("operation", loc, "qte_realisee", "warning", "qte_ecart_important", f"{loc}: qté réalisée ({qr}) très différente de la qté OF ({qte}) — probable erreur de lecture.")
            else:
                add("operation", loc, "qte_realisee", "warning", "qte_differente", f"{loc}: qté réalisée ({qr}) diffère légèrement de la qté OF ({qte}) — écart mineur, à vérifier.")

        mat = row.matricule_operateur.value
        # A row may carry two operators ("347/338") — validate each on its own.
        for part in split_matricules(mat):
            digits = "".join(c for c in part if c.isdigit())
            # Agilink matricules are 2-3 digits (all ~20 observed operators are);
            # a 4+ digit token (e.g. 1142) is a misread or two cells run together,
            # never a real operator -> hard block.
            if not (2 <= len(digits) <= 3):
                add("operation", loc, "matricule_operateur", "warning", "matricule_invalide", f"{loc}: matricule «{part}» n'a pas un format plausible (2 à 3 chiffres).")
            elif known and part not in known:
                suggestion = _confusable_known_match(part, known)
                # A near-miss is a MISREAD signal ONLY when the value is a stray
                # (a row or two) AND the operator it resembles isn't itself on
                # this sheet. If that operator also appears here, the two are
                # clearly distinct people (e.g. 329 in Partie 1 next to 389 in
                # Partie 2); if the value fills 3+ rows, it's the Partie's real
                # operator — not a one-off misread. In those cases it's just a
                # new operator (soft, self-registers), not a hard block.
                # Only trust the near-miss as a MISREAD once the roster is mature.
                # With an immature/incomplete roster a REAL operator (338) can
                # look like a "misread" of a known one (332) simply because it
                # isn't rostered yet — blocking it refuses correct sheets. Until
                # then it's just an unknown operator (soft), never a hard block.
                is_misread = (
                    suggestion is not None
                    and fiche_mat_counts[part] < 3
                    and len(known) >= _ROSTER_MATURE
                )
                if is_misread:
                    add(
                        "operation", loc, "matricule_operateur", "warning", "matricule_proche_connu",
                        f"{loc}: matricule «{part}» absent du référentiel, mais ressemble à l'opérateur connu «{suggestion}» (confusion d'écriture fréquente) — vérifier la lecture.",
                    )
                else:
                    add("operation", loc, "matricule_operateur", "warning", "matricule_inconnu", f"{loc}: matricule «{part}» absent du référentiel opérateurs.")

    # --- Auto-validation needs to actually RECOGNISE the operators ---
    # A single new operator among recognised ones is fine (stays soft). But if
    # the roster can't vouch for MOST of the sheet's operators it's either a bad
    # read (mostly strangers) or an immature roster — a human look is safer.
    # CRUCIAL: only judge "unknown" once the roster is mature enough to be
    # authoritative (>= _ROSTER_MATURE operators). On a freshly-cleaned DB the
    # roster is tiny and EVERY operator looks unknown, which would wrongly refuse
    # correct sheets; the per-batch re-validation rebuilds the roster and the
    # check then applies. This maximises auto-validation without gating on a
    # roster that can't yet tell a real operator from a misread.
    distinct_ops = {p for p in fiche_mat_counts if p.isdigit() and 2 <= len(p) <= 3}
    if distinct_ops and len(known) >= _ROSTER_MATURE:
        unknown_ops = {p for p in distinct_ops if p not in known}
        if len(unknown_ops) >= 2 and len(unknown_ops) > len(distinct_ops) - len(unknown_ops):
            add(
                "operation", "Opérateurs", "matricule_operateur", "warning",
                "operateurs_majoritairement_inconnus",
                f"La majorité des matricules ({len(unknown_ops)}/{len(distinct_ops)}) sont "
                f"absents du référentiel — lecture ou référentiel à confirmer avant validation.",
            )

    # --- Matricule majority-vote outlier (operations only, per Partie) ---
    # One operator typically runs every row of a given PARTIE, so the
    # matricule column is almost constant within Partie 1 and within Partie 2
    # — but the two Parties can legitimately be different operators, so the
    # vote must NOT span the whole fiche (that would let whichever Partie has
    # more filled rows always "win" and falsely flag the other Partie's
    # consistent-but-different value as the misread). A row that breaks from
    # its OWN Partie's majority is far more likely a misread digit than a
    # genuine mid-Partie operator handoff — flag it even though its format
    # and registry membership both look fine on their own.
    for partie_value in {row.partie.value for row in ex.operations}:
        partie_rows = [row for row in ex.operations if row.partie.value == partie_value]
        op_matricules = [row.matricule_operateur.value for row in partie_rows if row.matricule_operateur.value]
        if not op_matricules:
            continue
        majority_mat, majority_n = Counter(op_matricules).most_common(1)[0]
        if majority_n < 2 or majority_n <= len(op_matricules) / 2:
            continue
        for row in partie_rows:
            mat = row.matricule_operateur.value
            if mat and mat != majority_mat:
                loc = f"{row.partie.value if hasattr(row.partie, 'value') else row.partie}·{row.nom_operation[:24]}"
                add(
                    "operation", loc, "matricule_operateur", "warning", "matricule_atypique",
                    f"{loc}: matricule «{mat}» diffère de celui utilisé sur le reste de cette Partie («{majority_mat}») — vérifier la lecture.",
                )

    # --- Soft date-ordering check (operations run roughly in date order) ---
    # Operations are performed top-to-bottom, so a row's date is usually the same
    # as or later than the row above it. A date that goes BACKWARDS is more often
    # a misread digit than a real event — flag it (warning only; never corrected,
    # genuine out-of-order dates exist).
    prev_dm: tuple[int, int] | None = None
    prev_raw: str | None = None
    for row in ex.operations:
        raw = row.date_op.raw_text or (row.date_op.value.strftime("%d/%m") if row.date_op.value else None)
        dm = _day_month(raw)
        if dm is None:
            continue
        if prev_dm is not None and dm < prev_dm:
            loc = f"{row.partie.value if hasattr(row.partie, 'value') else row.partie}·{row.nom_operation[:24]}"
            add(
                "operation", loc, "date_op", "warning", "date_anterieure",
                f"{loc}: date «{raw}» antérieure à «{prev_raw}» plus haut dans la gamme — "
                f"l'ordre des opérations est habituellement croissant, vérifier la lecture.",
            )
        prev_dm, prev_raw = dm, raw

    return issues


def low_confidence_or_flagged(ex: FicheExtraction, issues: list[ValidationIssue], threshold: float = 0.6) -> bool:
    """True if the fiche should go to the human review queue rather than auto-accept."""
    if any(i.level == "error" for i in issues):
        return True
    if weighted_overall_confidence(ex) < threshold:
        return True
    return False


# Warning codes that are HARD misread signals — any of these blocks
# auto-validation (routes the sheet to a human). Deliberately EXCLUDES:
#  - `date_anterieure` (dates are genuinely often out of order) and
#    `matricule_atypique` (a lone different matricule is often a real operator
#    handoff) — measured to fire on almost every *correct* sheet.
#  - `matricule_inconnu` — a well-formed matricule that's simply not in the
#    (learned) roster yet is far more often a NEW operator than a misread
#    (Agilink onboards people continuously), so blocking it refuses correct
#    sheets. It self-registers once it recurs. We still HARD-block
#    `matricule_proche_connu` (a one-off that looks exactly like a common known
#    operator with one confused digit — the fingerprint of an actual misread).
#  - `heure_incoherente` — a fin-before-début time is a low-importance cell
#    (weight 1.0) that doesn't change the sheet's traceability identity
#    (product / OF / quantity / operators / operation sequence). It's usually a
#    paper-entry slip by the operator or a one-digit misread; refusing an
#    otherwise-perfect sheet over one time is the wrong trade-off. Stays a
#    visible warning so an auditor can correct the time, but it no longer gates.
# All remain warnings surfaced to the reviewer.
_AUTOVALIDATE_BLOCKING = frozenset({
    "ref_absent", "ref_non_numerique", "ref_prefixe", "ref_longueur", "of_absent",
    "matricule_invalide", "matricule_proche_connu",
    "operateurs_majoritairement_inconnus",
    "qte_ecart_important",
})


def is_auto_validatable(
    ex: FicheExtraction, issues: list[ValidationIssue], min_confidence: float = 0.5
) -> bool:
    """Can this sheet be validated with NO human review?

    RULE-BASED gate (reliable once an operator roster is loaded — which is what
    makes `matricule_inconnu` meaningful): a sheet auto-validates when no ERROR
    and no HARD misread signal fired (`_AUTOVALIDATE_BLOCKING`): ref/OF present &
    well-formed, **every matricule is a real known operator**, times ordered,
    qté = header, no time-shaped outillage. A misread number that isn't a real
    operator (e.g. 207→601) trips `matricule_inconnu` → routed to a human;
    correct sheets (all-real matricules) pass regardless of the model's
    confidence. Soft warnings (out-of-order date, atypical-but-known matricule)
    stay advisory. `min_confidence` is only a low garbage backstop — the RULES
    are the gate, not the (uncalibrated) confidence.
    """
    if any(i.level == "error" or i.code in _AUTOVALIDATE_BLOCKING for i in issues):
        return False
    if ex.header.ref_produit.value is None or ex.header.n_of.value is None:
        return False
    return ex.meta.overall_confidence >= min_confidence
