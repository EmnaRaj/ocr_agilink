FROM python:3.11-slim

WORKDIR /srv

COPY packages/fiche_schema /srv/packages/fiche_schema
COPY worker/pyproject.toml /srv/worker/pyproject.toml
COPY worker/worker /srv/worker/worker

RUN pip install --no-cache-dir -e /srv/packages/fiche_schema -e /srv/worker

WORKDIR /srv/worker
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info"]
