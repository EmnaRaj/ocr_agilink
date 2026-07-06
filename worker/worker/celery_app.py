import os

from celery import Celery

redis_url = os.environ["REDIS_URL"]

celery_app = Celery("agilink_worker", broker=redis_url, backend=redis_url)
celery_app.autodiscover_tasks(["worker"])

# Durability for long multi-page batches: if a worker is lost mid-task, requeue
# it (combined with acks_late on the batch task + idempotent per-page resume).
# prefetch=1 keeps a long batch from hogging other queued work.
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.worker_prefetch_multiplier = 1
# Redis redelivers an unacked task only after this window — so it's also the
# worst-case crash-recovery delay for an in-flight batch. 30 min comfortably
# exceeds a normal batch (~20 pages × ~1 min) yet recovers a crash reasonably
# fast. The (scan_id, page_index) unique constraint makes any redelivery safe
# even if it overlaps the original run.
celery_app.conf.broker_transport_options = {"visibility_timeout": 30 * 60}

# SharePoint auto-ingest: when enabled, a beat schedule fires the poller every
# SHAREPOINT_POLL_SECONDS. Only registered when enabled so a default deploy runs
# no extra timer. Requires a running `celery beat` (the compose `beat` service).
def _on(flag: str) -> bool:
    return os.environ.get(flag, "0") not in ("0", "false", "False", "")


_schedule: dict = {}
if _on("SHAREPOINT_ENABLED"):
    _schedule["poll-sharepoint"] = {
        "task": "worker.poll_sharepoint",
        "schedule": float(os.environ.get("SHAREPOINT_POLL_SECONDS", "180")),
    }
if _on("LOCAL_INBOX_ENABLED"):
    _schedule["poll-local-inbox"] = {
        "task": "worker.poll_local_inbox",
        "schedule": float(os.environ.get("LOCAL_INBOX_POLL_SECONDS", "30")),
    }
if _schedule:
    celery_app.conf.beat_schedule = _schedule
