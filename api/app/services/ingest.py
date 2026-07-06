"""Framework-free fiche persistence shared by the API (single-page, synchronous)
and the worker (multi-page batch). No FastAPI imports here so the worker can
reuse it without pulling the web layer."""

import os
from datetime import datetime, timezone
from typing import Callable

import pymupdf
from fiche_schema import (
    ExtractedField,
    FicheExtraction,
    is_auto_validatable,
    split_matricules,
    validate_extraction,
)
from sqlalchemy.orm import Session

from ..models import (
    AuditLog,
    Fiche,
    Item,
    Methode,
    OperationRow,
    Operator,
    Partie,
    Scan,
    StatutFiche,
    StatutRevue,
    TypeControle,
)
from .matching import (
    find_or_create_operator,
    find_or_create_product,
    find_or_create_work_order,
    known_matricules,
    match_operator,
    match_tool,
)

# Render every page to a JPEG sized for the VLM. A fixed long-side keeps output
# size predictable regardless of the source PDF's claimed page size. Bumped
# from 4000: per-region crops (regions.py) inherit this resolution directly
# with no extra downsampling, and the dense operations table rows are only
# ~2-3% of page height each — extra source pixels there is what actually buys
# more legible handwritten digits. Re-check against Groq's image size caps if
# switching back to that backend for production.
_TARGET_LONG_SIDE_PX = 5600
_MAX_ZOOM = 5.5
_JPEG_QUALITY = 95

PLACEHOLDER_REF = "À IDENTIFIER"


def render_page(doc: "pymupdf.Document", idx: int) -> tuple[bytes, str]:
    page = doc.load_page(idx)
    zoom = min(_TARGET_LONG_SIDE_PX / max(page.rect.width, page.rect.height), _MAX_ZOOM)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    return pix.tobytes("jpeg", jpg_quality=_JPEG_QUALITY), "image/jpeg"


def empty_extraction(message: str) -> dict:
    """A minimal, UI-renderable extraction payload for a page we couldn't read."""
    f = {"value": None, "confidence": 0.0, "raw_text": None}
    return {
        "header": {"ref_produit": dict(f), "n_of": dict(f), "qte": dict(f), "annotation_serie": dict(f)},
        "operations": [],
        "controls": [],
        "items": [],
        "meta": {"model_name": "-", "overall_confidence": 0.0, "processing_ms": None},
        "validation": [
            {"scope": "fiche", "location": "", "field": "", "level": "error",
             "code": "extract_failed", "message": message}
        ],
    }


def _avg_confidence(fields: list[ExtractedField]) -> float:
    confidences = [f.confidence for f in fields]
    return round(sum(confidences) / len(confidences), 3) if confidences else 0.0


def persist_page(
    db: Session,
    scan: Scan,
    page_index: int,
    extraction: FicheExtraction | None,
    error: str | None = None,
    rotation: int = 0,
) -> Fiche:
    """Persist one page as a fiche. Pass extraction=None (with an error message)
    to file an unreadable page as a reviewable error fiche — no scan is ever
    silently dropped. `rotation` is the clockwise angle applied to upright the
    page, stored so the viewer shows it the same way up. The caller commits."""
    if extraction is None:
        product = find_or_create_product(db, PLACEHOLDER_REF)
        wo = find_or_create_work_order(db, f"ERREUR · scan {scan.scan_id} p{page_index + 1}", product, None)
        fiche = Fiche(
            work_order=wo, scan=scan, page_index=page_index, rotation=rotation,
            statut=StatutFiche.en_revue, date_creation=datetime.now(timezone.utc),
            raw_extraction=empty_extraction(error or "Extraction échouée."),
        )
        db.add(fiche)
        return fiche

    issues = validate_extraction(extraction, known_matricules(db))
    flagged_rows = {i.location for i in issues if i.scope in ("operation", "control")}
    has_error = any(i.level == "error" for i in issues)

    ref = extraction.header.ref_produit.value
    n_of = extraction.header.n_of.value
    incomplete = ref is None or n_of is None
    # Keep every page even when the header is unreadable — file it for review
    # with placeholders unique to this page (so distinct pages don't merge).
    ref = ref or PLACEHOLDER_REF
    n_of = n_of or f"{PLACEHOLDER_REF} · scan {scan.scan_id} p{page_index + 1}"

    needs_review = (
        incomplete or has_error or bool(flagged_rows) or extraction.meta.overall_confidence < 0.6
    )

    # Rule-based auto-validation: a sheet that passes EVERY deterministic check
    # (zero issues) is validated with no human review — statut goes straight to
    # `valide`. The gate is the rules, not the model's confidence (which we
    # proved unreliable on systematic misreads). Off via AUTO_VALIDATE=0.
    auto_validate = (
        os.environ.get("AUTO_VALIDATE", "1") != "0"
        and not incomplete
        and is_auto_validatable(
            extraction, issues, float(os.environ.get("AUTO_VALIDATE_MIN_CONF", "0.9"))
        )
    )
    if auto_validate:
        statut = StatutFiche.valide
        resolve_operator = find_or_create_operator  # human-grade trust: grow the registry
    elif needs_review:
        statut = StatutFiche.en_revue
        resolve_operator = match_operator
    else:
        statut = StatutFiche.extrait
        resolve_operator = match_operator

    product = find_or_create_product(db, ref)
    work_order = find_or_create_work_order(db, n_of, product, extraction.header.qte.value)

    raw_payload = extraction.model_dump(mode="json")
    raw_payload["validation"] = [i.model_dump() for i in issues]
    if auto_validate:
        # Distinguish machine-validated from human-confirmed, and mark it fully
        # confident for the review UI while keeping the audit trail honest.
        raw_payload.setdefault("meta", {})["auto_validated"] = True
        raw_payload["meta"]["overall_confidence"] = 1.0

    fiche = Fiche(
        work_order=work_order,
        scan=scan,
        page_index=page_index,
        rotation=rotation,
        statut=statut,
        date_creation=datetime.now(timezone.utc),
        raw_extraction=raw_payload,
    )
    db.add(fiche)
    _sync_table_rows(db, fiche, extraction, flagged_rows, resolve_operator)

    return fiche


def revalidate_scan(db: Session, scan_id: int) -> dict:
    """Re-validate every sheet of a finished batch against the now-complete
    operator roster.

    Per-page validation at ingest necessarily runs before the batch's other
    pages exist, so the cross-sheet checks (known-operator roster, systematic
    misread pruning) start blind: on the first pages every matricule looks
    "absent du référentiel" and fires a soft alert, even though it's a perfectly
    good read. This second pass — once all pages are filed and the roster is
    whole — recomputes each sheet's issues and status against the full roster,
    clearing that cold-start noise and letting the real cross-sheet catches
    (e.g. 164 -> 161) fire. A human-validated sheet is never touched.
    """
    roster = known_matricules(db)
    min_conf = float(os.environ.get("AUTO_VALIDATE_MIN_CONF", "0.9"))
    auto_on = os.environ.get("AUTO_VALIDATE", "1") != "0"
    changed = 0
    for fiche in db.query(Fiche).filter_by(scan_id=scan_id).all():
        raw = fiche.raw_extraction or {}
        meta = raw.get("meta") or {}
        if meta.get("validated") or not raw.get("header"):
            continue  # human-confirmed or an error page — leave as is
        try:
            extraction = FicheExtraction.model_validate(raw)
        except Exception:  # noqa: BLE001 — a malformed page stays as filed
            continue
        issues = validate_extraction(extraction, roster)
        raw["validation"] = [i.model_dump() for i in issues]
        incomplete = extraction.header.ref_produit.value is None or extraction.header.n_of.value is None
        auto = auto_on and not incomplete and is_auto_validatable(extraction, issues, min_conf)
        if auto:
            new_statut = StatutFiche.valide
            raw.setdefault("meta", {})["auto_validated"] = True
            raw["meta"]["overall_confidence"] = 1.0
        else:
            meta.pop("auto_validated", None)
            has_error = any(i.level == "error" for i in issues)
            flagged = any(i.scope in ("operation", "control") for i in issues)
            needs_review = incomplete or has_error or flagged or extraction.meta.overall_confidence < 0.6
            new_statut = StatutFiche.en_revue if needs_review else StatutFiche.extrait
        if fiche.statut != new_statut:
            changed += 1
        fiche.statut = new_statut
        fiche.raw_extraction = dict(raw)  # reassign so the JSONB column is marked dirty
    db.commit()
    return {"scan_id": scan_id, "revalidated": db.query(Fiche).filter_by(scan_id=scan_id).count(), "status_changed": changed}


def _meta(field: ExtractedField) -> dict:
    return {"confidence": field.confidence, "raw_text": field.raw_text, "source": field.source}


def _resolve_operators(db: Session, mat: str | None, resolve_operator) -> "Operator | None":
    """Resolve (and, at validation, register) EVERY operator on a row — a cell
    may hold two ("347/338"). Returns the first resolved one for the single FK;
    the verbatim string on the row keeps both for display/analytics."""
    first = None
    for part in split_matricules(mat):
        op = resolve_operator(db, part)
        if op is not None and first is None:
            first = op
    return first


def _sync_table_rows(
    db: Session,
    fiche: Fiche,
    extraction: FicheExtraction,
    flagged_rows: set[str],
    resolve_operator: Callable[[Session, str | None], "Operator | None"],
) -> None:
    """(Re)build the relational `operation_rows` + `items` for `fiche` from
    `extraction`. Clears any rows already on the fiche first (the relationship
    cascade deletes the orphaned ones), so this is safe both for a brand-new
    fiche and for re-syncing after a human correction.

    Operations (Partie 1/2) and controls (partie == controle) go into the same
    `operation_rows` table, discriminated by `partie`. Every value the form
    carries is stored as a typed column, the verbatim outillage/matricule
    strings are kept alongside their resolved FKs (most outillage text never
    matches the controlled tools list and would otherwise be lost), and the
    per-field OCR provenance is kept in `field_meta` so it's queryable.

    `resolve_operator` is `match_operator` (lookup-only) at first extraction —
    an unverified VLM read must never silently register a new "known"
    operator — and `find_or_create_operator` at validation time, when the
    matricule has been human-confirmed and the registry should grow from it.
    """
    fiche.rows = []
    fiche.items = []

    for row in (*extraction.operations, *extraction.controls):
        loc = f"{row.partie.value}·{row.nom_operation[:24]}"
        is_control = row.partie.value == "controle"

        field_meta = {
            "applicable": _meta(row.applicable),
            "date_op": _meta(row.date_op),
            "date_fin": _meta(row.date_fin),
            "heure_debut": _meta(row.heure_debut),
            "heure_fin": _meta(row.heure_fin),
            "qte_realisee": _meta(row.qte_realisee),
            "outillage": _meta(row.outillage),
            "matricule_operateur": _meta(row.matricule_operateur),
        }
        if is_control:
            field_meta["methode"] = _meta(row.methode)
            field_meta["resultat"] = _meta(row.resultat)

        fiche.rows.append(
            OperationRow(
                partie=Partie(row.partie.value),
                nom_operation=row.nom_operation,
                ordre=row.ordre,
                applicable=row.applicable.value,
                date_op=row.date_op.value,
                date_fin=row.date_fin.value,
                heure_debut=row.heure_debut.value,
                heure_fin=row.heure_fin.value,
                qte_realisee=row.qte_realisee.value,
                outillage=row.outillage.value,
                tool=match_tool(db, row.outillage.value),
                matricule=row.matricule_operateur.value,
                operator=_resolve_operators(db, row.matricule_operateur.value, resolve_operator),
                type_controle=TypeControle(row.type_controle.value) if is_control else None,
                methode=(
                    Methode(row.methode.value.value)
                    if is_control and row.methode.value is not None
                    else None
                ),
                resultat=row.resultat.value if is_control else None,
                field_meta=field_meta,
                confidence=_avg_confidence([
                    row.applicable, row.date_op, row.heure_debut, row.heure_fin,
                    row.qte_realisee, row.outillage, row.matricule_operateur,
                ]),
                statut_revue=StatutRevue.a_revoir if loc in flagged_rows else StatutRevue.auto,
            )
        )

    for item in extraction.items:
        if item.numero_serie.value:
            fiche.items.append(Item(numero_serie=item.numero_serie.value))


def _fv(field: object) -> object:
    return (field or {}).get("value") if isinstance(field, dict) else None


def _ev(field: ExtractedField | None) -> object:
    return field.value if field is not None else None


def diff_extraction(fiche: Fiche, old: dict, new: FicheExtraction) -> list[AuditLog]:
    """Field-level diff between a fiche's previous raw_extraction (`old`, the
    dict on the row before this save) and the extraction about to replace it
    (`new`), as `AuditLog` rows — one per actually-changed value.

    There's no auth in this app yet, so `changed_by` is always "human": every
    caller of this function is the PUT /fiches/{id} save path, which only a
    person clicking Enregistrer/Valider in the UI can reach (the worker's
    first-extraction path never touches this).

    This is the source of truth for the "automation rate" KPI: a validated
    fiche with zero audit rows across its lifetime was accepted exactly as
    the VLM read it, with no human correction ever applied.
    """
    rows: list[AuditLog] = []
    now = datetime.now(timezone.utc)

    def changed(scope: str, location: str, field: str, old_val: object, new_val: object) -> None:
        old_s = None if old_val is None else str(old_val)
        new_s = None if new_val is None else str(new_val)
        if old_s == new_s:
            return
        name = f"{scope}.{location}.{field}" if location else f"{scope}.{field}"
        rows.append(AuditLog(fiche=fiche, field=name, old_value=old_s, new_value=new_s, changed_by="human", changed_at=now))

    oh, nh = old.get("header") or {}, new.header
    changed("header", "", "ref_produit", _fv(oh.get("ref_produit")), nh.ref_produit.value)
    changed("header", "", "n_of", _fv(oh.get("n_of")), nh.n_of.value)
    changed("header", "", "qte", _fv(oh.get("qte")), nh.qte.value)
    changed("header", "", "annotation_serie", _fv(oh.get("annotation_serie")), _ev(nh.annotation_serie))

    old_ops = old.get("operations") or []
    for idx, row in enumerate(new.operations):
        old_row = old_ops[idx] if idx < len(old_ops) else {}
        loc = f"{row.partie.value}·{row.nom_operation[:24]}"
        for f in ("applicable", "date_op", "date_fin", "heure_debut", "heure_fin", "qte_realisee", "outillage", "matricule_operateur"):
            changed("operation", loc, f, _fv(old_row.get(f)), _ev(getattr(row, f)))

    old_ctrls = old.get("controls") or []
    for idx, row in enumerate(new.controls):
        old_row = old_ctrls[idx] if idx < len(old_ctrls) else {}
        loc = f"controle·{row.nom_operation[:24]}"
        changed("control", loc, "resultat", _fv(old_row.get("resultat")), _ev(row.resultat))
        new_methode = row.methode.value.value if row.methode.value is not None else None
        changed("control", loc, "methode", _fv(old_row.get("methode")), new_methode)
        changed("control", loc, "matricule_operateur", _fv(old_row.get("matricule_operateur")), _ev(row.matricule_operateur))

    old_items = old.get("items") or []
    for idx, item in enumerate(new.items):
        old_item = old_items[idx] if idx < len(old_items) else {}
        changed("item", f"#{idx + 1}", "numero_serie", _fv(old_item.get("numero_serie")), _ev(item.numero_serie))

    return rows


def _sync_work_order(db: Session, fiche: Fiche, extraction: FicheExtraction) -> None:
    """Re-point the fiche's WorkOrder/Product at the (corrected) header
    ref_produit / N° OF / qté, so the relational views (fiches list, operations
    list + matrix, analytics product volumes) match the corrected blob.

    Without this, a human fixing a misread header ref only updated the JSONB —
    the Product/WorkOrder kept the original wrong read, so the list/matrix showed
    a stale ref even though the fiche detail showed the corrected one.

    Skips when ref/OF are unreadable (placeholder/blank fiches) — never relinks
    to a junk product.
    """
    ref = extraction.header.ref_produit.value
    n_of = extraction.header.n_of.value
    if not ref or not n_of or ref == PLACEHOLDER_REF or PLACEHOLDER_REF in str(n_of):
        return
    product = find_or_create_product(db, ref)
    work_order = find_or_create_work_order(db, n_of, product, extraction.header.qte.value)
    # find_or_create_* only sets fields on CREATE — force the corrected values
    # onto an existing work order too.
    work_order.product = product
    if extraction.header.qte.value is not None:
        work_order.quantite = extraction.header.qte.value
    fiche.work_order = work_order


def _resync(db: Session, fiche: Fiche, extraction: FicheExtraction, resolve_operator) -> list:
    issues = validate_extraction(extraction, known_matricules(db))
    flagged_rows = {i.location for i in issues if i.scope in ("operation", "control")}
    _sync_work_order(db, fiche, extraction)
    _sync_table_rows(db, fiche, extraction, flagged_rows, resolve_operator)
    return issues


def save_correction(db: Session, fiche: Fiche, extraction: FicheExtraction) -> list:
    """Re-sync a fiche's relational rows after a human edits (but has not yet
    validated) its extraction — without this, corrections only ever lived in
    the JSONB `raw_extraction` blob and analytics/exports (which read the
    relational tables) would keep showing the pre-correction data.

    Operators are resolved lookup-only (`match_operator`): the edit hasn't
    been validated yet, so a matricule on it still isn't human-confirmed and
    must not be auto-registered into the known-operator registry.
    """
    return _resync(db, fiche, extraction, match_operator)


def resync_fiche(db: Session, fiche: Fiche, extraction: FicheExtraction) -> list:
    """Re-sync a fiche's relational rows on validation — see `save_correction`
    for why this matters. Resolves operators with `find_or_create_operator`:
    a human just confirmed these values, so this is how the known-operator
    registry grows from real, validated PDF data instead of a manually
    supplied list.
    """
    return _resync(db, fiche, extraction, find_or_create_operator)
