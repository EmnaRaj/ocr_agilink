import hashlib
from datetime import datetime, timezone

import pymupdf
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fiche_schema import FicheExtraction
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Fiche, Scan
from ..services import ingest
from ..services.extraction_client import enqueue_scan_batch, revoke_task, run_extraction
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
        n_filed = db.query(Fiche.fiche_id).filter_by(scan_id=existing.scan_id).count()
        complete = existing.status == "done" and n_filed >= existing.n_pages
        if complete:
            raise HTTPException(409, f"This exact file was already scanned (scan_id={existing.scan_id}).")
        # A prior scan of this file errored / was stopped / never finished — don't
        # block it as a duplicate. Re-run the durable batch: it resumes at the
        # first unfiled page and finalises, so the retry the user expects works.
        existing.status = "processing"
        existing.task_id = enqueue_scan_batch(existing.scan_id)
        db.commit()
        return {"mode": "batch", "scan_id": existing.scan_id, "n_pages": existing.n_pages, "resumed": True}

    ext = (file.filename or "").rsplit(".", 1)[-1].lower() or "bin"
    storage_url = upload_scan(f"{sha256}.{ext}", raw_bytes, file.content_type or "application/octet-stream")

    is_pdf = _is_pdf(file.content_type, file.filename)
    doc = pymupdf.open(stream=raw_bytes, filetype="pdf") if is_pdf else None
    n_pages = doc.page_count if doc is not None else 1

    scan = Scan(
        storage_url=storage_url, uploaded_at=datetime.now(timezone.utc), sha256=sha256,
        n_pages=n_pages, original_name=file.filename,
    )
    db.add(scan)
    db.commit()  # persist the scan before any (possibly long) extraction

    # Any PDF (even a single page) goes to the durable Celery batch: it survives
    # an API/worker restart, resumes per page, and — crucially — is trackable and
    # stop/cancellable from the UI. (A plain image can't be opened as a PDF batch,
    # so it stays on the instant synchronous path below.)
    if is_pdf:
        scan.task_id = enqueue_scan_batch(scan.scan_id)
        db.commit()
        return {"mode": "batch", "scan_id": scan.scan_id, "n_pages": n_pages}

    # Plain image (jpg/png) → extract synchronously for an instant result.
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
    scan.status = "done"
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
        # "done" for the UI = the batch is no longer running (finished, stopped,
        # or errored) — not merely that every page happened to be filed.
        "done": scan.status in ("done", "stopped", "error") or n_done >= scan.n_pages,
        "status": scan.status,
        "source": scan.source,
        "fiche_ids": [f[0] for f in fiches],
    }


@router.get("/scans")
def list_scans(limit: int = 100, db: Session = Depends(get_db)) -> list[dict]:
    """Every scan with its live status, progress and source — for the monitoring
    view. Newest first."""
    from sqlalchemy import func

    counts = dict(db.query(Fiche.scan_id, func.count()).group_by(Fiche.scan_id).all())
    rows = db.query(Scan).order_by(Scan.uploaded_at.desc()).limit(limit).all()
    out = []
    for s in rows:
        n_done = counts.get(s.scan_id, 0)
        out.append({
            "scan_id": s.scan_id,
            "original_name": s.original_name or f"Scan #{s.scan_id}",
            "uploaded_at": s.uploaded_at.isoformat(),
            "n_pages": s.n_pages,
            "n_done": n_done,
            "status": s.status,
            "source": s.source,
            "done": s.status in ("done", "stopped", "error"),
        })
    return out


@router.post("/scan/{scan_id}/retry")
def retry_scan(scan_id: int, db: Session = Depends(get_db)) -> dict:
    """Re-run a stopped/errored/incomplete scan. The durable batch resumes at the
    first unfiled page, so nothing already extracted is redone."""
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(404, f"Scan {scan_id} not found")
    scan.status = "processing"
    scan.task_id = enqueue_scan_batch(scan_id)
    db.commit()
    return {"ok": True, "scan_id": scan_id, "status": "processing"}


@router.post("/scan/{scan_id}/stop")
def stop_scan(scan_id: int, db: Session = Depends(get_db)) -> dict:
    """Halt a running batch but KEEP the pages already extracted. The worker
    checks this status between pages and exits cleanly; we also revoke the task
    to interrupt the page in flight."""
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(404, f"Scan {scan_id} not found")
    scan.status = "stopped"
    db.commit()
    revoke_task(scan.task_id)
    n_done = db.query(Fiche.fiche_id).filter_by(scan_id=scan_id).count()
    return {"ok": True, "scan_id": scan_id, "status": "stopped", "n_done": n_done}


@router.delete("/scan/{scan_id}")
def cancel_scan(scan_id: int, db: Session = Depends(get_db)) -> dict:
    """Cancel a scan entirely: stop processing and DELETE the scan + all its
    fiches (and the stored file). Frees the sha256 so the file can be scanned
    fresh. The worker sees the scan vanish mid-batch and aborts."""
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(404, f"Scan {scan_id} not found")
    task_id, storage_url = scan.task_id, scan.storage_url
    for fiche in db.query(Fiche).filter_by(scan_id=scan_id).all():
        db.delete(fiche)
    db.delete(scan)
    db.commit()
    revoke_task(task_id)
    try:
        from ..services.storage import delete_scan
        delete_scan(storage_url)
    except Exception:  # noqa: BLE001 — object may already be gone / shared
        pass
    return {"ok": True, "scan_id": scan_id, "canceled": True}
