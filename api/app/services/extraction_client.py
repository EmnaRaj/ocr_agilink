import base64

from celery import Celery

from ..config import settings

_celery_client = Celery(broker=settings.redis_url, backend=settings.redis_url)

# Row-anchored + self-consistency voting makes many small parallel calls
# (~25 rows × N votes), so allow generous headroom.
EXTRACTION_TIMEOUT_S = 300


def run_extraction(image_bytes: bytes, mime_type: str = "image/png") -> dict:
    """Submits a single image to the worker's Celery task and blocks for the
    result. Used for single-page uploads where an instant response matters."""
    image_b64 = base64.b64encode(image_bytes).decode()
    async_result = _celery_client.send_task("worker.extract_fiche", args=[image_b64, mime_type])
    return async_result.get(timeout=EXTRACTION_TIMEOUT_S)


def enqueue_scan_batch(scan_id: int) -> str:
    """Fire-and-forget a durable multi-page batch. The worker owns the whole
    job (download → render → extract → persist per page) so it survives an
    API/worker restart and resumes from the last unfinished page. Returns the
    Celery task id so the caller can store it (for stop/revoke)."""
    return _celery_client.send_task("worker.process_scan_batch", args=[scan_id]).id


def revoke_task(task_id: str | None) -> None:
    """Stop a running/queued batch task. terminate=True interrupts the page in
    flight; the cooperative status check makes any redelivery exit cleanly."""
    if task_id:
        _celery_client.control.revoke(task_id, terminate=True)
