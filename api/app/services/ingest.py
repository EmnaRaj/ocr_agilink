"""Framework-free fiche persistence shared by the API (single-page, synchronous)
and the worker (multi-page batch). No FastAPI imports here so the worker can
reuse it without pulling the web layer."""

from datetime import datetime, timezone

import pymupdf
from fiche_schema import ExtractedField, FicheExtraction, validate_extraction
from sqlalchemy.orm import Session

from ..models import (
    Control,
    Fiche,
    Item,
    Methode,
    Operation,
    Partie,
    Scan,
    StatutFiche,
    StatutRevue,
    TypeControle,
)
from .matching import (
    find_or_create_product,
    find_or_create_work_order,
    known_matricules,
    match_operator,
    match_tool,
)

# Render every page to a JPEG sized for the VLM. A fixed long-side keeps output
# size predictable regardless of the source PDF's claimed page size, and stays
# under Groq's 4MB/33MP caps while preserving handwritten-digit resolution.
_TARGET_LONG_SIDE_PX = 4000
_MAX_ZOOM = 4.0
_JPEG_QUALITY = 92

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

    product = find_or_create_product(db, ref)
    work_order = find_or_create_work_order(db, n_of, product, extraction.header.qte.value)

    raw_payload = extraction.model_dump(mode="json")
    raw_payload["validation"] = [i.model_dump() for i in issues]

    fiche = Fiche(
        work_order=work_order,
        scan=scan,
        page_index=page_index,
        rotation=rotation,
        statut=StatutFiche.en_revue if needs_review else StatutFiche.extrait,
        date_creation=datetime.now(timezone.utc),
        raw_extraction=raw_payload,
    )
    db.add(fiche)

    for row in extraction.operations:
        loc = f"{row.partie.value}·{row.nom_operation[:24]}"
        db.add(
            Operation(
                fiche=fiche,
                partie=Partie(row.partie.value),
                nom_operation=row.nom_operation,
                ordre=row.ordre,
                applicable=row.applicable.value,
                date_op=row.date_op.value,
                date_fin=row.date_fin.value,
                heure_debut=row.heure_debut.value,
                heure_fin=row.heure_fin.value,
                qte_realisee=row.qte_realisee.value,
                tool=match_tool(db, row.outillage.value),
                operator=match_operator(db, row.matricule_operateur.value),
                confidence=_avg_confidence([
                    row.applicable, row.date_op, row.heure_debut, row.heure_fin,
                    row.qte_realisee, row.outillage, row.matricule_operateur,
                ]),
                statut_revue=StatutRevue.a_revoir if loc in flagged_rows else StatutRevue.auto,
            )
        )

    for row in extraction.controls:
        db.add(
            Control(
                fiche=fiche,
                type_controle=TypeControle(row.type_controle.value),
                methode=Methode(row.methode.value.value) if row.methode.value is not None else None,
                resultat=row.resultat.value,
                operator=match_operator(db, row.matricule_operateur.value),
            )
        )

    for item in extraction.items:
        if item.numero_serie.value:
            db.add(Item(fiche=fiche, numero_serie=item.numero_serie.value))

    return fiche
