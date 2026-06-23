# Agilink — Fiches Suiveuses Automation

Open-source, self-hosted system to scan, read (printed + handwritten French),
validate, and store Agilink's "Fiche Suiveuse" traceability sheets.
See [docs/Architecture_OpenSource_Fiches_Suiveuses.md](docs/Architecture_OpenSource_Fiches_Suiveuses.md)
for the full design and [docs/fixtures/](docs/fixtures/) for the reference
blank template and a sample filled sheet.

## Status

**Phase 0** — repo scaffold, Postgres/MinIO/Redis infra, Alembic baseline
schema, seed data.

**Phase 1** — vertical slice working end-to-end: `POST /fiches/scan` accepts
a scan (image or PDF), stores it in MinIO, runs a VLM extraction pass, and
persists scans/fiches/operations/controls/items with per-field confidence.
Verified against `docs/fixtures/sample_filled_sheet.pdf`.

### Extraction approach (region-based)

A single full-page A4 scan downsamples the dense 25-row operations table
below the VLM's effective resolution, so cramped handwritten digits get
misread and rows near blank stretches get misaligned. Instead, the Groq POC
backend crops the page into focused vertical bands — header, Partie 1
operations, Partie 2 operations, controls + serials — and extracts each in
its own short, focused call, then assembles the partial results onto the
canonical skeleton (`worker/worker/extract/regions.py`,
`packages/fiche_schema` `merge_extraction`). This gives the model ~2x the
effective resolution per row and a much shorter output to keep aligned. On
the sample fixture it reads `ref_produit`, the Finition/control matricules
(390, 332), the dates, and the blank-vs-marked control rows correctly and
stably across runs.

Residual limits on this small POC model (`llama-4-scout-17b`): a couple of
genuinely ambiguous handwritten digits still flip occasionally (e.g. `n_of`
1554↔1559) and a few middle operation-row matricules aren't perfect. These
are OCR-accuracy ceilings of the POC model on hard handwriting, not pipeline
bugs — re-evaluate once production switches to self-hosted Qwen2.5-VL
(`VLM_BACKEND=vllm`). Every field carries a confidence score and the raw
text it was read from, so Phase 3's validation gate can flag low-confidence
cells for human review rather than trusting them blindly.

Reliability properties worth noting: a single malformed cell value degrades
to null (keeping its raw text for review) instead of aborting the sheet, and
a single failed region degrades to blank rather than failing the whole scan
(`packages/fiche_schema` `_ef`, `GroqClient.extract`). Dates are never given
a fabricated year — the form prints none, so `date_*` values are null with
the `DD.MM` text kept in `raw_text` for a future frontend to assign the year.

## Quickstart

```bash
cp .env.example .env   # fill in real secrets; never commit .env
docker compose up -d --build
```

This brings up Postgres, Redis, MinIO (+ auto-creates the scans bucket), and
builds/starts the `api` (FastAPI, http://localhost:8000/health) and `worker`
(Celery) stub services.

Apply database migrations and seed reference data (run from a Python env with
`api` and `fiche_schema` installed — see below):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e packages/fiche_schema -e api
set -a; source .env; set +a
DATABASE_URL=postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5434/${POSTGRES_DB} \
  alembic -c db/alembic.ini upgrade head
python db/seed/seed.py
```

(`localhost:5434` because migrations run from the host against the port
published by `docker-compose.yml` — 5434, not the default 5432, since this
dev machine already runs a native Postgres on 5432; inside a container it
would be `postgres:5432`.)

## Switching to the self-hosted production VLM (Qwen2.5-VL)

The extraction backend is swappable by config — no code change. The POC uses
Groq (cloud, data leaves the premises); production uses a **fully open-source,
self-hosted** stack so scans never leave the client's network:

- **vLLM** (Apache-2.0) serves the model over an OpenAI-compatible API.
- **Qwen2.5-VL** (Apache-2.0 weights) is the open vision-language model.
- The worker talks to it with the **openai** Python client — same code path as
  Groq, since both speak the OpenAI chat-completions API
  (`worker/worker/extract/regional.py` holds the shared region logic;
  `groq_client.py` / `vllm_client.py` differ only in the one request call).

To enable it in the client environment (needs an NVIDIA GPU +
`nvidia-container-toolkit` on the host):

```bash
# .env
VLM_BACKEND=vllm
VLLM_MODEL=Qwen/Qwen2.5-VL-7B-Instruct   # 3B (~10GB VRAM) / 7B (~18GB) / 32B / 72B

# start the stack including the vLLM container (gated behind the "gpu" profile)
docker compose --profile gpu up -d
```

First start downloads the weights into the `hf_cache` volume (a few minutes);
after that the worker routes every extraction to the on-prem model. No other
change is needed — the API, schema, and DB are backend-agnostic. To go back to
the POC backend, set `VLM_BACKEND=groq` and `docker compose up -d` (without the
profile). A larger Qwen2.5-VL (32B/72B) is the expected fix for the residual
handwriting-alignment limits noted above.

## Monorepo layout

```
packages/fiche_schema/  canonical Pydantic extraction schema (single source of truth)
api/                    FastAPI app, SQLAlchemy ORM
worker/                 Celery worker (extraction pipeline lands here in Phase 1+)
db/                     Alembic migrations + seed data
frontend/               React PWA capture app (Phase 5)
infra/                  Caddy/Keycloak/Prometheus/Grafana configs (later phases)
docs/                   architecture doc + reference fixtures
```

## Notes

- `VLM_BACKEND=groq` is the POC default — scans are sent to Groq's API, which
  means **data leaves the premises**. This is acceptable for development only;
  production on Agilink's server must use `VLM_BACKEND=vllm` (self-hosted
  Qwen2.5-VL). The worker's extraction layer is built behind a shared
  interface so this is a config switch, not a code change.
- Rotate `GROQ_API_KEY` after the POC phase.
