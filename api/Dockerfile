FROM python:3.11-slim

WORKDIR /srv

COPY packages/fiche_schema /srv/packages/fiche_schema
COPY api/pyproject.toml /srv/api/pyproject.toml
COPY api/app /srv/api/app

RUN pip install --no-cache-dir -e /srv/packages/fiche_schema -e /srv/api

WORKDIR /srv/api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
