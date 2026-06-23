import hashlib
from datetime import datetime, timezone

import pymupdf
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fiche_schema import FicheExtraction
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Fiche, Scan
from ..services import ingest
from ..services.extraction_client import enqueue_scan_batch, run_extraction
from ..services.storage import upload_scan

router = APIRouter(prefix="/fiches", tags=["fiches"])

_PDF_CONTENT_TYPES = {"application/pdf"}


def _is_pdf(content_type: str | None, filename: str | None) -> bool:
    return content_type in _PDF_CONTENT_TYPES or (filename or "").lower().endswith(".pdf")


@router.post("/scan")
def scan_fiche(file: UploadFile, db: Session = Depends(get_db)) -> dict:
    raw_bytes = file.file.read()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    existing = db.query(Scan).filter_by(sha256=sha256).first()
    if existing is not None:
        raise HTTPException(409, f"This exact file was already scanned (scan_id={existing.scan_id}).")

    ext = (file.filename or "").rsplit(".", 1)[-1].lower() or "bin"
    storage_url = upload_scan(f"{sha256}.{ext}", raw_bytes, file.content_type or "application/octet-stream")

    is_pdf = _is_pdf(file.content_type, file.filename)
    doc = pymupdf.open(stream=raw_bytes, filetype="pdf") if is_pdf else None
    n_pages = doc.page_count if doc is not None else 1

    scan = Scan(
        storage_url=storage_url, uploaded_at=datetime.now(timezone.utc), sha256=sha256, n_pages=n_pages
    )
    db.add(scan)
    db.commit()  # persist the scan before any (possibly long) extraction

    # Multi-page file → one fiche per page. Hand the whole batch to a durable
    # Celery task: it survives an API/worker restart and resumes where it left
    # off (each page is idempotent on scan_id+page_index).
    if n_pages > 1:
        enqueue_scan_batch(scan.scan_id)
        return {"mode": "batch", "scan_id": scan.scan_id, "n_pages": n_pages}

    # Single page (or plain image) → extract synchronously for an instant result.
    image_bytes, mime = (
        ingest.render_page(doc, 0) if doc is not None else (raw_bytes, file.content_type or "image/jpeg")
    )
    try:
        result = run_extraction(image_bytes, mime)
        rotation = result.pop("_rotation", 0)
        extraction = FicheExtraction.model_validate(result)
        fiche = ingest.persist_page(db, scan, 0, extraction, rotation=rotation)
    except Exception as exc:  # noqa: BLE001 — never lose the scan; file it for review
        db.rollback()
        scan = db.get(Scan, scan.scan_id)
        fiche = ingest.persist_page(db, scan, 0, None, error=str(exc))
    db.commit()
    return {
        "mode": "single",
        "scan_id": scan.scan_id,
        "fiche_id": fiche.fiche_id,
        "n_pages": 1,
        "statut": fiche.statut.value,
    }


@router.get("/scan/{scan_id}/status")
def scan_status(scan_id: int, db: Session = Depends(get_db)) -> dict:
    """Progress of a multi-page batch: how many pages have been filed so far."""
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(404, f"Scan {scan_id} not found")
    fiches = (
        db.query(Fiche.fiche_id)
        .filter_by(scan_id=scan_id)
        .order_by(Fiche.page_index)
        .all()
    )
    n_done = len(fiches)
    return {
        "scan_id": scan_id,
        "n_pages": scan.n_pages,
        "n_done": n_done,
        "done": n_done >= scan.n_pages,
        "fiche_ids": [f[0] for f in fiches],
    }
