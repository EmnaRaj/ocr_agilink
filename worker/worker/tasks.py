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


_judge_client: VLMClient | None = None


def _get_judge_client() -> VLMClient | None:
    """A DIFFERENT model (JUDGE_MODEL) that independently re-extracts each sheet
    to VERIFY the primary read. Because the two models have different blind
    spots, a disagreement surfaces a real error (e.g. the 10108044→20208044
    misread the primary makes every time) and their agreement is a trustworthy
    confidence for the auto-validate gate. Runs over the same OpenRouter
    endpoint. Unset JUDGE_MODEL → no judge (single-model behaviour)."""
    global _judge_client
    judge_model = os.environ.get("JUDGE_MODEL")
    if not judge_model:
        return None
    if _judge_client is None:
        from .extract.vllm_client import VllmClient
        _judge_client = VllmClient(
            base_url=os.environ.get("VLLM_BASE_URL", "http://vllm:8000/v1"),
            model=judge_model,
            api_key=os.environ.get("VLLM_API_KEY", "EMPTY"),
        )
    return _judge_client


def _extract_verified(client: VLMClient, image_bytes: bytes, mime_type: str):
    """Extract, then cross-check against an independent judge model if one is
    configured. Agreement → high confidence (can auto-validate); disagreement →
    low confidence (routed to human review). A judge failure degrades safely to
    the primary extraction. Without a judge, falls back to EXTRACT_PASSES voting."""
    from fiche_schema import vote_extractions

    judge = _get_judge_client()
    if judge is None:
        passes = int(os.environ.get("EXTRACT_PASSES", "1"))
        return client.extract_voted(image_bytes, mime_type=mime_type, passes=passes)

    primary_ex = client.extract(image_bytes, mime_type=mime_type)
    try:
        judge_ex = judge.extract(image_bytes, mime_type=mime_type)
    except Exception as exc:  # noqa: BLE001 — judge unavailable → trust primary alone
        print(f"!!! judge model ({os.environ.get('JUDGE_MODEL')}) failed, using primary: {exc}")
        return primary_ex
    # Judge first so the stronger model's reading wins a disagreement; per-cell
    # agreement → confidence 1.0, disagreement → 0.5 (below the auto-validate floor).
    return vote_extractions([judge_ex, primary_ex])


@celery_app.task(name="worker.poll_sharepoint")
def poll_sharepoint() -> dict:
    """Celery-beat task: pull any NEW file from the watched SharePoint folder and
    push it into the same pipeline as a manual upload.

    Uses Graph's incremental `delta` feed (only changed items since last poll),
    and is idempotent three ways: by SharePoint driveItem id+eTag, by content
    sha256 (identical bytes are never re-ingested), and by the
    (scan_id, page_index) unique constraint downstream. App layer imported lazily
    so the worker still boots without SharePoint configured."""
    import hashlib
    from datetime import datetime, timezone

    import pymupdf

    from app.config import settings
    from app.db import SessionLocal
    from app.models import Scan
    from app.services import sharepoint
    from app.services.storage import upload_scan

    if not settings.sharepoint_enabled:
        return {"skipped": "disabled"}

    db = SessionLocal()
    enqueued: list[int] = []
    try:
        cursor = sharepoint.get_delta_cursor(db)
        changes, new_cursor = sharepoint.list_changed_files(cursor)
        for item in changes:
            if not item["name"].lower().endswith(".pdf"):
                continue
            if item["etag"] and db.query(Scan.scan_id).filter_by(
                external_id=item["id"], external_etag=item["etag"]
            ).first():
                continue  # this exact version already pulled
            data = sharepoint.download(item)
            sha256 = hashlib.sha256(data).hexdigest()
            if db.query(Scan.scan_id).filter_by(sha256=sha256).first():
                continue  # identical content already ingested (e.g. manual upload)
            try:
                n_pages = pymupdf.open(stream=data, filetype="pdf").page_count
            except Exception:  # noqa: BLE001 — non-pdf/corrupt still filed as 1 page
                n_pages = 1
            storage_url = upload_scan(f"{sha256}.pdf", data, "application/pdf")
            scan = Scan(
                storage_url=storage_url,
                uploaded_at=datetime.now(timezone.utc),
                sha256=sha256,
                n_pages=n_pages,
                source="sharepoint",
                status="processing",
                external_id=item["id"],
                external_etag=item["etag"],
                original_name=item["name"],
            )
            db.add(scan)
            db.commit()
            celery_app.send_task("worker.process_scan_batch", args=[scan.scan_id])
            enqueued.append(scan.scan_id)
        # Only advance the cursor once everything above committed, so a mid-poll
        # failure re-sees the same changes next time rather than skipping them.
        sharepoint.save_delta_cursor(db, new_cursor)
        return {"enqueued": enqueued, "count": len(enqueued)}
    finally:
        db.close()


@celery_app.task(name="worker.poll_local_inbox")
def poll_local_inbox() -> dict:
    """Beat task: ingest any new PDF/image dropped into the local inbox folder.

    A filesystem twin of the SharePoint poller for on-box / no-cloud use: watch
    a mounted directory, and for each new file upload it to storage, create a
    Scan, enqueue the batch, and move the file into <dir>/processed/. Deduped by
    content sha256 (a file already scanned is skipped, not re-run)."""
    import hashlib
    import shutil
    from datetime import datetime, timezone
    from pathlib import Path

    import pymupdf

    from app.config import settings
    from app.db import SessionLocal
    from app.models import Scan
    from app.services.storage import upload_scan

    if not settings.local_inbox_enabled:
        return {"skipped": "disabled"}

    inbox = Path(settings.local_inbox_dir)
    processed = inbox / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    enqueued: list[int] = []
    try:
        for path in sorted(inbox.iterdir()):
            if path.is_dir() or path.suffix.lower() not in (".pdf", ".jpg", ".jpeg", ".png"):
                continue
            data = path.read_bytes()
            sha256 = hashlib.sha256(data).hexdigest()
            if db.query(Scan.scan_id).filter_by(sha256=sha256).first():
                shutil.move(str(path), str(processed / path.name))  # already ingested
                continue
            ext = path.suffix.lower().lstrip(".") or "bin"
            ctype = "application/pdf" if ext == "pdf" else f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"
            try:
                n_pages = pymupdf.open(stream=data, filetype="pdf").page_count if ext == "pdf" else 1
            except Exception:  # noqa: BLE001
                n_pages = 1
            storage_url = upload_scan(f"{sha256}.{ext}", data, ctype)
            scan = Scan(
                storage_url=storage_url,
                uploaded_at=datetime.now(timezone.utc),
                sha256=sha256,
                n_pages=n_pages,
                source="local",
                status="processing",
                original_name=path.name,
            )
            db.add(scan)
            db.commit()
            scan.task_id = celery_app.send_task("worker.process_scan_batch", args=[scan.scan_id]).id
            db.commit()
            shutil.move(str(path), str(processed / path.name))
            enqueued.append(scan.scan_id)
        return {"enqueued": enqueued, "count": len(enqueued)}
    finally:
        db.close()


@celery_app.task(name="worker.extract_fiche")
def extract_fiche(image_b64: str, mime_type: str = "image/png") -> dict:
    from .preprocess.orient import correct_orientation

    image_bytes = base64.b64decode(image_b64)
    image_bytes, rotation = correct_orientation(image_bytes)
    client = _get_vlm_client()

    start = time.monotonic()
    extraction = _extract_verified(client, image_bytes, "image/jpeg" if rotation else mime_type)
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
    stopped = False
    try:
        scan = db.get(Scan, scan_id)
        if scan is None:
            return {"scan_id": scan_id, "error": "scan not found"}
        db.query(Scan).filter_by(scan_id=scan_id).update({"status": "processing"})
        db.commit()

        data, _ = download_scan(scan.storage_url)
        doc = pymupdf.open(stream=data, filetype="pdf")
        client = _get_vlm_client()

        for i in range(doc.page_count):
            # Cooperative stop/cancel: the API sets status to "stopped" (keep what's
            # filed) or deletes the scan entirely (status query returns None). Both
            # halt cleanly here — the task completes and is acked, no redelivery.
            st = db.query(Scan.status).filter_by(scan_id=scan_id).scalar()
            if st is None:
                return {"scan_id": scan_id, "canceled": True, "n_done": done}
            if st == "stopped":
                stopped = True
                break
            # Idempotent resume: skip pages already filed (retry / crash recovery).
            if db.query(Fiche.fiche_id).filter_by(scan_id=scan_id, page_index=i).first():
                done += 1
                continue
            from sqlalchemy.exc import IntegrityError

            try:
                image_bytes, mime = ingest.render_page(doc, i)
                image_bytes, rotation = correct_orientation(image_bytes)
                start = _t.monotonic()
                extraction = _extract_verified(client, image_bytes, "image/jpeg")
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
        # Batch finished: re-validate every page against the now-complete
        # operator roster so early pages (validated when the roster was still
        # empty) shed their cold-start "unknown operator" alerts and the real
        # cross-sheet catches fire.
        try:
            ingest.revalidate_scan(db, scan_id)
        except Exception as exc:  # noqa: BLE001 — never fail the batch on the finalize pass
            print(f"!!! revalidate_scan failed scan={scan_id}: {exc}")
        db.query(Scan).filter_by(scan_id=scan_id).update({"status": "stopped" if stopped else "done"})
        db.commit()
        return {"scan_id": scan_id, "n_done": done, "n_pages": doc.page_count, "stopped": stopped}
    except Exception:
        db.rollback()
        try:
            db.query(Scan).filter_by(scan_id=scan_id).update({"status": "error"})
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        raise
    finally:
        db.close()
