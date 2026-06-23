import os

from celery import Celery

redis_url = os.environ["REDIS_URL"]

celery_app = Celery("agilink_worker", broker=redis_url, backend=redis_url)
celery_app.autodiscover_tasks(["worker"])
