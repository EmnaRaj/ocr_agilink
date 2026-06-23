import hashlib
from datetime import datetime, timezone

import pymupdf
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fiche_schema import ExtractedField, FicheExtraction, validate_extraction
from sqlalchemy.orm import Session

from ..db import get_db
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
from ..services.extraction_client import run_extraction
from ..services.matching import (
    find_or_create_product,
    find_or_create_work_order,
    known_matricules,
    match_operator,
    match_tool,
)
from ..services.storage import upload_scan

router = APIRouter(prefix="/fiches", tags=["fiches"])

_PDF_CONTENT_TYPES = {"application/pdf"}

# Groq's vision API caps base64-encoded images at 4MB and 33 megapixels.
# Some scanner apps (e.g. TapScanner, the source of our sample fixture)
# export single-page PDFs whose MediaBox mirrors the source photo's pixel
# dimensions rather than a real paper size, so a fixed DPI can blow past
# that limit by 3x. Targeting a fixed long-side instead keeps every fiche's
# output size predictable regardless of what the source PDF claims.
# 4000px long-side (≈ 2800x4000 = 11MP, ~1.8MB JPEG) sits well under both
# Groq caps while giving the model enough resolution to read the cramped
# handwritten digit/matricule columns — at 3400px those digits fell below
# the model's effective resolution and were misread (see README known issue).
_TARGET_LONG_SIDE_PX = 4000
_MAX_ZOOM = 4.0
_JPEG_QUALITY = 92


def _to_raster(data: bytes, content_type: str | None, filename: str | None) -> tuple[bytes, str]:
    """Returns (raster_bytes, mime_type) for VLM input.

    Captures may arrive as PDF (e.g. phone scanner apps like TapScanner, the
    source of our sample fixture) rather than a plain image — render the
    first page to JPEG in that case. The original upload is still stored
    as-is in MinIO for fidelity.
    """
    is_pdf = content_type in _PDF_CONTENT_TYPES or (filename or "").lower().endswith(".pdf")
    if not is_pdf:
        return data, content_type or "image/jpeg"
    doc = pymupdf.open(stream=data, filetype="pdf")
    page = doc.load_page(0)
    zoom = min(_TARGET_LONG_SIDE_PX / max(page.rect.width, page.rect.height), _MAX_ZOOM)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    return pix.tobytes("jpeg", jpg_quality=_JPEG_QUALITY), "image/jpeg"


def _avg_confidence(fields: list[ExtractedField]) -> float:
    confidences = [f.confidence for f in fields]
    return round(sum(confidences) / len(confidences), 3) if confidences else 0.0


def _log_confidences(scan_id: int, extraction: FicheExtraction) -> None:
    print(f"--- field confidences: scan_id={scan_id} model={extraction.meta.model_name} ---")
    h = extraction.header
    print(f"  ref_produit={h.ref_produit.value!r} (conf={h.ref_produit.confidence:.2f})")
    print(f"  n_of={h.n_of.value!r} (conf={h.n_of.confidence:.2f})")
    print(f"  qte={h.qte.value!r} (conf={h.qte.confidence:.2f})")
    for row in extraction.operations:
        print(
            f"  [{row.partie.value}] {row.nom_operation}: "
            f"applicable={row.applicable.value} (conf={row.applicable.confidence:.2f}) "
            f"matricule={row.matricule_operateur.value} (conf={row.matricule_operateur.confidence:.2f}) "
            f"qte={row.qte_realisee.value} (conf={row.qte_realisee.confidence:.2f})"
        )
    for row in extraction.controls:
        print(
            f"  [controle] {row.nom_operation}: resultat={row.resultat.value} "
            f"(conf={row.resultat.confidence:.2f})"
        )
    print(f"  overall_confidence={extraction.meta.overall_confidence:.2f}")


@router.post("/scan")
def scan_fiche(file: UploadFile, db: Session = Depends(get_db)) -> dict:
    raw_bytes = file.file.read()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    existing = db.query(Scan).filter_by(sha256=sha256).first()
    if existing is not None:
        raise HTTPException(409, f"This exact file was already scanned (scan_id={existing.scan_id}).")

    ext = (file.filename or "").rsplit(".", 1)[-1].lower() or "bin"
    storage_url = upload_scan(f"{sha256}.{ext}", raw_bytes, file.content_type or "application/octet-stream")

    scan = Scan(storage_url=storage_url, uploaded_at=datetime.now(timezone.utc), sha256=sha256)
    db.add(scan)
    db.flush()

    image_bytes, mime_type = _to_raster(raw_bytes, file.content_type, file.filename)

    try:
        raw_result = run_extraction(image_bytes, mime_type)
    except Exception as exc:
        raise HTTPException(502, f"Extraction failed: {exc}") from exc

    extraction = FicheExtraction.model_validate(raw_result)
    _log_confidences(scan.scan_id, extraction)

    if extraction.header.ref_produit.value is None or extraction.header.n_of.value is None:
        raise HTTPException(422, "Could not read ref_produit/n_of from the header — cannot file this sheet.")

    # Deterministic validation gate: structural rules catch confident-but-wrong
    # values the model can't self-detect. Issues drive the review queue.
    issues = validate_extraction(extraction, known_matricules(db))
    flagged_rows = {i.location for i in issues if i.scope in ("operation", "control")}
    has_error = any(i.level == "error" for i in issues)
    needs_review = has_error or bool(flagged_rows) or extraction.meta.overall_confidence < 0.6

    product = find_or_create_product(db, extraction.header.ref_produit.value)
    work_order = find_or_create_work_order(
        db, extraction.header.n_of.value, product, extraction.header.qte.value
    )

    raw_payload = extraction.model_dump(mode="json")
    raw_payload["validation"] = [i.model_dump() for i in issues]

    fiche = Fiche(
        work_order=work_order,
        scan=scan,
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
                confidence=_avg_confidence(
                    [
                        row.applicable,
                        row.date_op,
                        row.heure_debut,
                        row.heure_fin,
                        row.qte_realisee,
                        row.outillage,
                        row.matricule_operateur,
                    ]
                ),
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

    db.commit()

    return {
        "scan_id": scan.scan_id,
        "fiche_id": fiche.fiche_id,
        "of_id": work_order.of_id,
        "product_id": product.product_id,
        "statut": fiche.statut.value,
        "overall_confidence": extraction.meta.overall_confidence,
        "needs_review": needs_review,
        "validation": [i.model_dump() for i in issues],
        "extraction": extraction.model_dump(mode="json"),
    }
