import base64

from celery import Celery

from ..config import settings

_celery_client = Celery(broker=settings.redis_url, backend=settings.redis_url)

# Row-anchored + self-consistency voting makes many small parallel calls
# (~25 rows × N votes), so allow generous headroom.
EXTRACTION_TIMEOUT_S = 300


def run_extraction(image_bytes: bytes, mime_type: str = "image/png") -> dict:
    """Submits the image to the worker's Celery task and blocks for the result.

    Phase 1 simplification: the API waits synchronously on the extraction
    (a few seconds for a single VLM call). A polling/job-status endpoint can
    replace this once there's a UI that needs it (Phase 4/5).
    """
    image_b64 = base64.b64encode(image_bytes).decode()
    async_result = _celery_client.send_task("worker.extract_fiche", args=[image_b64, mime_type])
    return async_result.get(timeout=EXTRACTION_TIMEOUT_S)
