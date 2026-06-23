import base64
import os
import time

from .celery_app import celery_app
from .extract import VLMClient
from .extract.groq_client import GroqClient


@celery_app.task(name="worker.ping")
def ping() -> str:
    """Phase 0 smoke-test task — confirms the Celery/Redis wiring works."""
    return "pong"


_vlm_client: VLMClient | None = None


def _get_vlm_client() -> VLMClient:
    global _vlm_client
    if _vlm_client is None:
        backend = os.environ.get("VLM_BACKEND", "groq")
        if backend == "groq":
            _vlm_client = GroqClient(
                api_key=os.environ["GROQ_API_KEY"],
                model=os.environ.get("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
            )
        elif backend == "vllm":
            # On-prem production: self-hosted Qwen2.5-VL via vLLM. Imported
            # lazily so a Groq-only deploy doesn't pay for the openai import.
            from .extract.vllm_client import VllmClient

            _vlm_client = VllmClient(
                base_url=os.environ.get("VLLM_BASE_URL", "http://vllm:8000/v1"),
                model=os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct"),
                api_key=os.environ.get("VLLM_API_KEY", "EMPTY"),
            )
        else:
            raise ValueError(f"Unknown VLM_BACKEND={backend!r} (expected 'groq' or 'vllm')")
    return _vlm_client


@celery_app.task(name="worker.extract_fiche")
def extract_fiche(image_b64: str, mime_type: str = "image/png") -> dict:
    from .preprocess.orient import correct_orientation

    image_bytes = base64.b64decode(image_b64)
    image_bytes, rotation = correct_orientation(image_bytes)
    client = _get_vlm_client()

    start = time.monotonic()
    extraction = client.extract(image_bytes, mime_type="image/jpeg" if rotation else mime_type)
    extraction.meta.processing_ms = int((time.monotonic() - start) * 1000)

    payload = extraction.model_dump(mode="json")
    payload["_rotation"] = rotation  # caller pops this before validating the schema
    return payload


@celery_app.task(name="worker.process_scan_batch", acks_late=True)
def process_scan_batch(scan_id: int) -> dict:
    """Durably extract every page of a multi-fiche scan, one fiche per page.

    The worker owns the full pipeline (download → render → extract → persist),
    committing one fiche at a time. `acks_late` + idempotent resume mean a
    worker crash redelivers the task and it picks up at the first unfiled page
    instead of restarting or duplicating. App layer is imported lazily so the
    worker boots even without DB connectivity.
    """
    import time as _t

    import pymupdf

    from app.db import SessionLocal
    from app.models import Fiche, Scan
    from app.services import ingest
    from app.services.storage import download_scan

    from .preprocess.orient import correct_orientation

    db = SessionLocal()
    done = 0
    try:
        scan = db.get(Scan, scan_id)
        if scan is None:
            return {"scan_id": scan_id, "error": "scan not found"}

        data, _ = download_scan(scan.storage_url)
        doc = pymupdf.open(stream=data, filetype="pdf")
        client = _get_vlm_client()

        for i in range(doc.page_count):
            # Idempotent resume: skip pages already filed (retry / crash recovery).
            if db.query(Fiche.fiche_id).filter_by(scan_id=scan_id, page_index=i).first():
                done += 1
                continue
            from sqlalchemy.exc import IntegrityError

            try:
                image_bytes, mime = ingest.render_page(doc, i)
                image_bytes, rotation = correct_orientation(image_bytes)
                start = _t.monotonic()
                extraction = client.extract(image_bytes, mime_type="image/jpeg")
                extraction.meta.processing_ms = int((_t.monotonic() - start) * 1000)
                ingest.persist_page(db, scan, i, extraction, rotation=rotation)
                db.commit()
            except IntegrityError:
                db.rollback()  # another (redelivered) run already filed this page
            except Exception as exc:  # noqa: BLE001 — isolate a bad page from the batch
                db.rollback()
                print(f"!!! batch page {i} failed scan={scan_id}: {exc}")
                try:
                    ingest.persist_page(db, scan, i, None, error=str(exc))
                    db.commit()
                except IntegrityError:
                    db.rollback()
            done += 1
        return {"scan_id": scan_id, "n_done": done, "n_pages": doc.page_count}
    finally:
        db.close()
