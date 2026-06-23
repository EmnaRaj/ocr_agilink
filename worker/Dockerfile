FROM python:3.11-slim

# tesseract-ocr provides the OSD model used to auto-rotate sideways scans.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY packages/fiche_schema /srv/packages/fiche_schema
COPY worker/pyproject.toml /srv/worker/pyproject.toml
COPY worker/worker /srv/worker/worker
# The multi-page batch task reuses the API's persistence layer (models, db,
# services). Install the `app` package without its deps — the worker declares
# the runtime ones (sqlalchemy/psycopg/boto3/pymupdf) itself, keeping FastAPI
# and the rest of the web layer out of the worker image.
COPY api/pyproject.toml /srv/api/pyproject.toml
COPY api/app /srv/api/app

RUN pip install --no-cache-dir -e /srv/packages/fiche_schema -e /srv/worker \
 && pip install --no-cache-dir --no-deps -e /srv/api

WORKDIR /srv/worker
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info"]
