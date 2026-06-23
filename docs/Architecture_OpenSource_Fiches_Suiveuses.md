# Open-Source Architecture — Agilink Traceability Sheet Automation

*Prepared by Farness · June 2026 · 100% self-hostable, no per-page fees, data stays on-premises*

---

## Design goals

- **Fully open-source and self-hosted** — runs on Agilink's own server (or a private VM in Tunisia). No data leaves the building, no per-page API bill.
- **Reliable handwriting reading** on a fixed-template French form with printed labels, handwriting, checkboxes, dates and times.
- **Human-in-the-loop** so the data is trustworthy from day one and the models *improve over time*.
- **Each record linked to its product reference and OF number**, with full audit trail.

The whole system is a controlled pipeline: **capture → preprocess → extract → validate → store → analyse**, with a feedback loop that turns human corrections into better models.

---

## The stack at a glance

| Layer | Component | Role | Licence |
|---|---|---|---|
| Capture | **React PWA** + **OpenCV.js** (jscanify) | Camera/scanner capture, edge-detect, deskew, upload | MIT |
| API | **FastAPI** (Python) | REST endpoints, orchestration | MIT |
| Queue | **Redis** + **Celery** | Async document processing | BSD / MIT |
| Preprocess | **OpenCV** + **Pillow** | Deskew, denoise, crop, binarise | Apache/BSD |
| Layout / OCR | **docTR** (Mindee) or **PaddleOCR PP-OCRv5** | Text detection + printed-field recognition, French | Apache 2.0 |
| Handwriting / extraction | **Qwen2.5-VL** served via **vLLM**, with **Outlines** for guaranteed JSON | Read handwriting, output structured fields, checkboxes | Apache 2.0 |
| Validation | Python rules + confidence routing | Business rules, route low-confidence to review | — |
| Human review | **Label Studio** | Review/correct flagged fields; doubles as annotation tool | Apache 2.0 |
| Database | **PostgreSQL** | Structured records, JSONB raw output | PostgreSQL licence |
| Object storage | **MinIO** | Original scanned images (S3-compatible) | AGPL/commercial |
| Analytics | **Metabase** (or **Apache Superset**) | Dashboards, KPIs | AGPL / Apache 2.0 |
| Auth | **Keycloak** | SSO, role-based access (operator/supervisor/admin) | Apache 2.0 |
| Reverse proxy | **Caddy** or **Traefik** | TLS, routing | Apache 2.0 |
| MLOps | **MLflow** | Track fine-tuning runs, model registry | Apache 2.0 |
| Deployment | **Docker Compose** (→ **k3s** if scaling) | One-command self-host | Apache 2.0 |
| Monitoring | **Prometheus** + **Grafana** | Health, throughput, latency | Apache 2.0 |

Everything above is free to self-host. The only licence to read carefully is **MinIO (AGPL)** — fine for internal use; if that's a concern, swap it for **SeaweedFS** (Apache 2.0) or just store scans on the filesystem.

---

## The extraction strategy (the part that matters)

Because the form layout is **always identical**, we exploit that instead of fighting it. Two stages working together:

**1. Template-anchored field cropping.** A one-time config maps each cell of the Fiche Suiveuse to a bounding box (header fields, and every operation row's columns: Applicable, Date, Heure début, Heure fin, Outillage, Matricule). On each scan we detect the form's anchors with OpenCV, align the image, and crop each field. This gives clean, isolated images per field and a natural **per-field confidence**.

**2. Per-field recognition + a VLM reader.**
- Printed labels and structured fields → **docTR / PaddleOCR** (fast, French-capable).
- Handwritten cells and the whole-form structured pass → **Qwen2.5-VL**, prompted with a strict JSON schema (the exact field list). **Outlines** (or vLLM's guided-JSON) forces the model to return schema-valid JSON, so you never get malformed output.
- Checkboxes ("Applicable Oui/Non", "Contrôle: manuel / banc de test") → the VLM reads these reliably; OpenCV pixel-density on the cropped box is a cheap cross-check.

**Why a VLM and not just classic OCR?** Open classic engines (Tesseract, PaddleOCR) are excellent on printed text but weaker on cursive handwriting. A self-hosted VLM reasons about context — it uses the field type and neighbours to disambiguate a messy digit — and returns structured data directly. Qwen2.5-VL is the strongest open VLM you can run on your own GPU.

**Accuracy lever — fine-tuning.** Out of the box the VLM will be good; fine-tuned on a few hundred real Agilink sheets it gets very good on Agilink's specific handwriting. The human-review corrections (below) are exactly the labelled data you need, so accuracy **compounds** with use. Keep TrOCR/Qwen LoRA fine-tuning as a phase-2 improvement, not a prerequisite.

---

## The validation gate (how the data earns trust)

Every extracted field carries a confidence score. The gate does three things:

1. **Confidence routing** — fields above a threshold (start around **90%** for critical fields like matricule, dates, OF number; tune on real data) auto-post. Anything below routes to human review.
2. **Business rules** — independent of confidence:
   - required fields present (Réf produit, N° OF, Qté),
   - `heure_fin > heure_début`,
   - quantity consistent with the OF,
   - matricule is a known operator,
   - serial numbers unique.
   Any rule failure flags the sheet regardless of confidence.
3. **Human-in-the-loop** — flagged sheets open in **Label Studio**, showing the scan beside the extracted fields with low-confidence cells highlighted. The supervisor corrects in seconds. Corrections are (a) written to the database, (b) logged in the audit trail, and (c) saved as labelled training data.

This is the difference between "an AI that's right most of the time" and "a system you can run production traceability on." With this gate, real IDP systems reach 90–95%+ accuracy, approaching 99% in narrow, well-defined cases like this one.

---

## Data model (PostgreSQL)

Normalised, with the reference/OF link threaded through everything and a JSONB column holding the raw model output.

```
products      (product_id PK, ref_produit, designation)
work_orders   (of_id PK, n_of, product_id FK→products, quantite, statut)
operators     (operator_id PK, matricule, nom)
tools         (tool_id PK, code_outillage, libelle)

fiches        (fiche_id PK, of_id FK→work_orders, scan_id FK→scans,
               statut [extrait|en_revue|valide], date_creation,
               created_by, raw_extraction JSONB)

items         (item_id PK, fiche_id FK→fiches, numero_serie)   -- one per part

operations    (operation_id PK, fiche_id FK→fiches,
               partie [1|2|controle], nom_operation, ordre,
               applicable BOOL, date_op DATE,
               heure_debut TIME, heure_fin TIME,
               tool_id FK→tools, operator_id FK→operators,
               confidence NUMERIC, statut_revue)

controls      (control_id PK, fiche_id FK→fiches, type_controle,
               methode [manuel|banc_de_test], resultat, operator_id FK)

scans         (scan_id PK, storage_url, dpi, uploaded_at, sha256)
audit_log     (event_id PK, fiche_id FK, field, old_value, new_value,
               changed_by, changed_at)
```

Key points: `raw_extraction JSONB` lets you reprocess without rescanning; `confidence` per operation drives review and quality reporting; `audit_log` records every correction (audits + training signal); scans live in MinIO, the DB keeps the link + hash for integrity.

---

## Analytics — what the data unlocks

All of these are SQL over the schema above, surfaced in Metabase/Superset:

- **Cycle time per operation** (`heure_fin − heure_début`) → bottlenecks.
- **Operator productivity & workload** by matricule.
- **Lead time per OF and per product** (first operation → final control).
- **Operation completion / skip rates** (Applicable Oui/Non).
- **Tooling usage** by `outillage`.
- **Instant serial-number traceability** — full history of any part in seconds (audits, recalls, certifications).
- **Production volumes** by period/product, and **quality indicators** (electrical/final control pass rates).

For live operational views (throughput today, queue depth, review backlog), point **Grafana** at the same database.

---

## Continuous improvement loop (MLOps)

1. Human corrections in Label Studio accumulate as labelled examples.
2. Periodically export them and run a **LoRA fine-tune** of Qwen2.5-VL (or TrOCR) on Agilink's real handwriting.
3. Track each run in **MLflow** (metrics, artifacts, model registry); promote a new model only if field-level accuracy improves on a held-out test set.
4. Swap the model behind the extraction service. Accuracy climbs over time, the review burden shrinks.

---

## Hardware

- **One GPU server** for the VLM — an NVIDIA card with **16–24 GB VRAM** comfortably runs a quantised Qwen2.5-VL 7B via vLLM for this volume (e.g. RTX 4090 / A5000; an A100 if you later fine-tune heavily). docTR/PaddleOCR also benefit from the GPU.
- **One application server** (8–16 vCPU, 32 GB RAM) for FastAPI, Celery workers, PostgreSQL, MinIO, Metabase, Keycloak — all in Docker. PostgreSQL can move to its own box later.
- Both can be the **same physical machine** for a pilot. The architecture scales out (k3s, separate DB, multiple workers) only when volume demands it.

CPU-only is possible (docTR/PaddleOCR on CPU, or a smaller VLM) but handwriting accuracy and speed drop — a modest GPU is the single best value investment here.

---

## Deployment shape (Docker Compose)

A single `docker-compose.yml` brings up the whole system:

```
services:
  caddy          # TLS + reverse proxy (entry point)
  keycloak       # auth / RBAC
  api            # FastAPI
  worker         # Celery workers (preprocess + extraction)
  vllm           # Qwen2.5-VL inference server (GPU)
  redis          # queue/broker
  postgres       # database
  minio          # scan storage
  labelstudio    # human review
  metabase       # dashboards
  mlflow         # experiment tracking
  prometheus     # metrics
  grafana        # ops dashboards
```

Operators reach only the PWA (through Caddy); everything else is internal. One command to stand up a pilot; the same compose file (or a k3s manifest) scales to production.

---

## Security & compliance (build in from day one)

- TLS everywhere (Caddy auto-certs); all services on a private network, only the PWA exposed.
- **Keycloak** roles: operator (capture only), supervisor (review/validate), admin.
- **Encryption at rest** for PostgreSQL and MinIO; scan integrity via SHA-256 hash.
- **Full audit trail** (`audit_log`) of every extraction and every manual edit — exactly what quality audits and certifications expect.
- Automated **backups** of PostgreSQL + MinIO; retention policy per Agilink's record-keeping rules.

---

## Build plan

1. **Scoping (½–1 day):** gather 20–50 real sheets; lock the JSON schema, the field bounding-box map, and the business rules.
2. **POC (1–2 weeks):** stand up capture → docTR/PaddleOCR + Qwen2.5-VL → JSON; measure field-level accuracy on the real sheets; set confidence thresholds.
3. **Core build:** PWA, FastAPI + Celery, validation gate, Label Studio review, PostgreSQL + MinIO, Keycloak, Caddy — all in Docker Compose.
4. **Analytics:** Metabase dashboards once data is flowing; Grafana for ops.
5. **Improvement loop:** wire corrections → MLflow-tracked fine-tuning; deploy improved models.
6. **Deploy on Agilink's server, train supervisors, support.**

**Two things decide success more than model choice:** scan quality at the source (≥300 DPI, flat, well-lit) and a fast, well-designed review screen. Get those right and the open-source stack runs production traceability with confidence.

---

### Alternative component swaps (all open-source)

- VLM: **Qwen2.5-VL** ↔ **PaddleOCR-VL 1.5** ↔ **MiniCPM-V** — benchmark on your sheets and pick the best French-handwriting performer.
- Serving: **vLLM** ↔ **Ollama** (simpler) ↔ **Triton** (heavier, production).
- Object storage: **MinIO** ↔ **SeaweedFS** (Apache 2.0) ↔ filesystem.
- BI: **Metabase** (fast to start) ↔ **Apache Superset** (more powerful).
- Backend: **FastAPI** (Python, ML-native) ↔ **NestJS** (if the team prefers Node).
