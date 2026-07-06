# Agilink Fiches Suiveuses — Handoff

Snapshot date: 2026-06-29. Branch `data_extract`. **36 tracked files changed
(+2287/-561), plus new untracked source files (the `/operations` browse
feature §3.10, the unified-`operation_rows` DB restructure §3.11, the soft-UI
redesign §3.12, and the integrated chatbot copilot §3.13 from the `ChatBot`
branch), and 2 deleted model files — none of it committed yet** (see §1.1).
This doc covers that uncommitted work plus everything from the prior snapshot
(commit `285be99`).
Complements [README.md](README.md) (quickstart, VLM backend switch) and
[docs/Architecture_OpenSource_Fiches_Suiveuses.md](docs/Architecture_OpenSource_Fiches_Suiveuses.md)
(original design) — neither reflects the work below.

## 1. Urgent — do these first

1. **A whole session of work is sitting uncommitted.** `git status` shows 28
   modified tracked files (validation rules, ingest refactor, region-boundary
   fix, prompt tightening, the entire `FicheDetail.tsx` rework, the router
   migration, delete endpoint, audit-log wiring, the `/operations` browse
   feature, the unified-`operation_rows` DB restructure, and the BI dashboard)
   plus new untracked source files and 2 deleted model files —
   `+2034/-469` lines on tracked files alone, nothing staged or committed. If
   you want this preserved before anything risky happens to the working tree,
   commit it. I haven't, since you didn't ask.
   - **Untracked binaries in the repo root that must NOT be committed:**
     `Test_file_6948.pdf` (1.6 MB, looks like a real scan) and two videos
     `UNSPSC.mp4` / `mission_video_2025-06-11_06-12-35.mp4`. None are
     gitignored — they're only safe because nothing has run `git add -A`. Move
     them out of the repo (or gitignore them) before any commit, and confirm
     the PDF isn't real client data.
2. **A second API key got pasted into this chat and is now compromised.**
   The original leaked OpenRouter key was rotated out of `.env`, but the
   *replacement* key (`sk-or-v1-a11d55...`) was also typed directly into
   this conversation when topping up credits. Treat that one as exposed too
   — rotate it on openrouter.ai before this goes anywhere near production,
   and avoid pasting keys into chat going forward (paste into `.env`
   directly, or describe what changed without the literal value).
3. **`origin` (public) is still 1 commit behind `farness` (private).**
   `EmnaRaj/ocr_agilink` is public and only has `865b340`; all multi-page/
   durable-batch/orientation work (`285be99`) plus *all* of this session's
   uncommitted work currently only exist locally / on `farness`. Decide
   whether `origin` should get caught up and/or go private.
4. **Alembic is still out of sync with the live schema.** Still only one
   migration, [0bd9fd9ff567_baseline_schema.py](db/alembic/versions/0bd9fd9ff567_baseline_schema.py).
   `page_index`/`n_pages`/`uq_fiche_scan_page` were applied via raw `ALTER
   TABLE` months ago and still never got a real migration — a fresh
   `alembic upgrade head` elsewhere would build a schema missing them.

## 2. What this system does

Self-hosted pipeline turning scanned French paper traceability sheets
("Fiches Suiveuses" — cable/harness assembly QA forms) into structured,
human-validated data: scan → auto-orient → VLM extraction (per region) →
deterministic validation → editable human review → validated record → feeds
the dashboard, history, exports, and a chatbot.

Stack: FastAPI + SQLAlchemy/Postgres + MinIO + Redis/Celery (worker) +
React/Vite/TS/Tailwind, via `docker-compose`. All 6 services currently up
(`agilink-postgres`, `ocr_agilink-api-1`, `ocr_agilink-worker-1`,
`ocr_agilink-frontend-1`, `ocr_agilink-minio-1`, `ocr_agilink-redis-1`).

**VLM backend right now: `qwen/qwen3.7-plus` via OpenRouter** (see §3.7) —
closed-weight, cloud-only. This is a deliberate accuracy-over-architecture
tradeoff made this session; it does **not** match the README's "fully
open-source, self-hosted, data never leaves the premises" production goal.
Flag this explicitly before any real Agilink data goes through it.

## 3. This session's work (uncommitted)

1. **Validation rules made stricter and smarter**
   ([packages/fiche_schema/fiche_schema/validation.py](packages/fiche_schema/fiche_schema/validation.py)):
   - `qte_realisee` now flags *any* mismatch vs the header `qte`, not just
     over-reads (`qte_differente`, was `qte_superieure`) — catches misreads
     in either direction (a `20` read as `200`, or as `2`).
   - New **per-Partie majority-vote matricule outlier check**
     (`matricule_atypique`): one operator usually fills every row of a given
     Partie, so a row whose matricule breaks from that Partie's majority
     gets flagged — even though its format and registry membership both
     look fine alone. Deliberately scoped **per-Partie, not fiche-wide**
     (fixed after initially getting this wrong — see commit message style
     comment in the file) since Partie 1 and Partie 2 can legitimately be
     different operators; a fiche-wide vote let whichever Partie had more
     filled rows always "win" and falsely flag the other.
   - Tests: [test_validation.py](packages/fiche_schema/tests/test_validation.py),
     14 passing.

2. **Auto-grown operator registry — no manual list, by design.**
   `find_or_create_operator` in
   [api/app/services/matching.py](api/app/services/matching.py) registers a
   matricule into the `Operator` table **only when a human validates the
   fiche it's on** (never from a still-unverified VLM read — that would let
   misreads pollute the very registry meant to catch them). Wired through
   [api/app/services/ingest.py](api/app/services/ingest.py)'s new
   `resync_fiche` (validate path) / `save_correction` (save-without-validate
   path). User explicitly asked for this over a manually-supplied list:
   *"no we should keep it extracted from pdf files."* Registry has grown
   from 5 seed rows to 16 organically this session.

3. **Relational tables now actually sync on correction/validation.**
   Previously `PUT /fiches/{id}` only ever touched the JSONB
   `raw_extraction` blob — `Operation`/`Control`/`Item` rows (which
   analytics/exports read) never reflected a human's correction. Fixed via
   a shared `_sync_table_rows` helper in `ingest.py` that clears and rebuilds
   those rows from the (corrected) extraction. **Behavior change**: a
   validated fiche no longer wipes its `validation` issues to `[]` — flags
   persist through validation (statut still moves to `valide`, confidence
   still forced to 1.0) since a flag means "still worth a second look," not
   "wrong." Confirm this is the UX you want; it was inferred from the
   broader "stop silently trusting bad data" theme of this session, not
   explicitly requested.

4. **Render-resolution + prompt tightening for digit accuracy**
   ([api/app/services/ingest.py](api/app/services/ingest.py) `_TARGET_LONG_SIDE_PX`
   4000→5600, `_MAX_ZOOM` 4.0→5.5;
   [worker/worker/extract/prompt.py](worker/worker/extract/prompt.py) added
   explicit digit-confusion-pair guidance (0/6, 5/9, 4/9, 1/7, 2/8, 3/8) and
   a "one operator usually fills the whole Partie" self-check nudge;
   [worker/worker/extract/regional.py](worker/worker/extract/regional.py)
   now runs the header region **first** and feeds its `qte` into the
   operations-table prompts as a soft cross-check hint, not a value to blindly
   copy — softened after an early version caused the model to parrot a
   *wrong* header read into every row, masking the very inconsistency the
   qty rule is meant to catch).

5. **Region-boundary bug found and fixed**
   ([worker/worker/extract/regions.py](worker/worker/extract/regions.py)).
   Confirmed via direct OCR pixel-position analysis on a real scan: the
   printed "Qté:" label sometimes lands just past the header crop's old
   bottom edge (0.17) into the `operations_p1` crop instead, so the header
   call had literally no pixels to read it from (`qte` came back unread).
   Same root cause suspected for the last 1-2 rows of Partie 2 getting cut
   off. Widened header `0.04–0.17` → `0.04–0.20` and `operations_p2`
   `0.47–0.83` → `0.47–0.88`. Verified fixed on the exact page that
   surfaced it (header `qte` and the previously-blank last row both now
   extract correctly).

6. **Model A/B tested: switched default to `qwen/qwen3.7-plus`.**
   Tested `qwen3-vl-32b-instruct` (previous default) vs `qwen3-vl-235b-a22b-instruct`
   vs `qwen3.7-plus` on the exact real pages with known-wrong fields. The
   235B model showed **no improvement** over 32B on the hardest fields (both
   converged on the same wrong digits) — not worth ~2x the cost.
   `qwen3.7-plus` (~3x 32B's cost, ~$0.01–0.03/page) resolved both of the
   previously-stubborn cases cleanly (`ref_produit` exact match, a control
   matricule exact match, cross-confirmed against an already-validated value
   on a different fiche). Switched `VLLM_MODEL` in `.env`. **Architecture
   tradeoff**: closed-weight/cloud-only — see §2.

7. **`FicheDetail.tsx` — large UX rework** (the bulk of the diff, 609 lines).
   - **Alert ↔ field linking**: hovering/clicking a "Contrôle de cohérence"
     alert highlights (and scrolls to) the exact header/table cell it
     refers to.
   - **Bulk-correction prompt**: editing a `matricule_operateur`/`qte_realisee`
     cell that other rows on the fiche currently share offers to fix them
     together — a checklist of the other matching cells (old→new value shown
     inline), "Oui, corriger N" / "Non, juste cette cellule". Fires
     **on blur only** (not on every keystroke — an earlier version fired
     mid-edit while the user was still typing).
   - **Unsaved-changes guard**: leaving the page mid-edit (sidebar nav, the
     logo, browser back, tab close) now prompts
     Enregistrer-et-quitter/Quitter-sans-enregistrer/Rester. Required
     migrating the whole app from plain `<BrowserRouter>` to a **data
     router** (`createBrowserRouter`/`RouterProvider` in
     [App.tsx](frontend/src/App.tsx), `Layout.tsx` now renders `<Outlet/>`
     instead of `children`) since `useBlocker` only works with one. Tab
     close/refresh covered separately via `beforeunload` (the router can't
     see those).
   - **Cell editing model, after two corrections from the user**: clicking
     "Modifier" makes *every* cell an input at once (reverted back to this
     after an intermediate version gated each cell behind its own
     double-click, which the user explicitly didn't want). Double-clicking
     a value while just *viewing* (not yet in Modifier mode) now jumps
     straight into full edit mode and highlights that cell — an *additional*
     entry point, not a replacement for "Modifier."
   - **Delete fiche**: new button (top **and** bottom action bar — added
     per request so you're not forced to scroll back up after reviewing a
     long fiche) → confirm dialog → `DELETE /fiches/{id}` → back to
     `/historique`. Backend cascade-deletes Operation/Control/Item/AuditLog,
     leaves Scan/WorkOrder/Product/MinIO file untouched (other pages/fiches
     may still reference them). Verified end-to-end against a real fiche.
   - **NaN-stuck-cell bug fixed**: the `qte_realisee` input wrote `Number(badInput)`
     (`NaN`) straight to state; since `NaN ?? ""` is still `NaN` (`??` only
     catches null/undefined), the cell would permanently display literal
     `"NaN"` with no way to type past it. Fixed by never writing NaN to
     state — an invalid keystroke is now silently rejected instead.
   - **Date separator normalization**: `30/3`, `30.03`, `30-3` all
     canonicalize to `30.3` (`_normalize_date_raw` in
     [factory.py](packages/fiche_schema/fiche_schema/factory.py)) — applies
     at extraction time only; already-stored fiches keep their original
     text until re-extracted or manually edited.

8. **Fixed a 400 on every "Valider" click**, introduced earlier this same
   session by an over-strict save path. `update_fiche` had been validating
   the human-edited extraction via raw `FicheExtraction.model_validate`,
   which uses pydantic's strict ISO time parser — rejecting completely normal
   typed input like `"8:30"` (no leading zero) or `"13h30"` (this project's
   own French notation). Fixed by routing through `merge_extraction`
   instead, the same lenient parser (`_parse_time`/`_parse_date`) the VLM
   path already uses — handles "13h30" etc. and degrades a bad cell to
   null+raw_text instead of rejecting the whole save.

9. **`audit_log` is now actually written to, and Pilotage shows real KPIs
   from it.** The table existed since the baseline schema but nothing ever
   inserted into it — confirmed via grep (`AuditLog(` only in the model file)
   and a `count(*)` of 0. Two pieces:
   - **Field-level diff on every save** (`diff_extraction` in
     [api/app/services/ingest.py](api/app/services/ingest.py), called from
     `PUT /fiches/{id}` in
     [fiches_read.py](api/app/routers/fiches_read.py) before the new
     extraction overwrites the old one). Compares old vs. new header/
     operations/controls/items field-by-field and writes one `AuditLog` row
     per actually-changed value (old → new). Runs on **every** save —
     correction or direct-validate — not just validation, so the audit trail
     reflects every human touch, not just the final click. `changed_by` is
     hardcoded `"human"`: there's still no auth in this app, so that's the
     most honest value available — see "no auth/RBAC exists" below.
   - **"Taux d'automatisation" KPI** (`automation_pct` in
     [analytics.py](api/app/routers/analytics.py)): % of *validated* fiches
     with **zero** audit rows across their lifetime — i.e. accepted exactly
     as the VLM read them, no human correction ever applied, regardless of
     whether they went through "Modifier" or the direct "Valider" button.
     `null` (rendered as "—") when there are no validated fiches yet, rather
     than a misleading 0%.
   - **"Temps de cycle moyen" + bottleneck ranking**: average minutes
     between `heure_debut`/`heure_fin` per operation, only over rows with
     *both* times present, no `date_fin` (multi-day span — would need real
     date arithmetic, skipped rather than computed wrong), and `heure_fin >=
     heure_debut` (a negative gap is a misread, not a real duration — same
     "don't compute garbage stats from bad reads" stance as the validation
     layer). `cycle_time_coverage_pct` says what fraction of in-scope rows
     that average is actually based on. `cycle_time_by_operation` ranks the
     slowest operation names — new `CycleTimeList` panel
     ([Charts.tsx](frontend/src/components/Charts.tsx)) on the Dashboard.
   - **Deliberately NOT built**: literal Postgres materialized views (the
     pasted spec's assumption). At the current data scale (tens of fiches)
     a plain query-time aggregation in `/analytics` is just as correct with
     none of the refresh-staleness failure mode — a materialized view is an
     easy, obvious upgrade later if read load ever actually justifies it.
   - **Verified end-to-end against the live stack**, not a mocked unit test
     (no `api/` test infra exists yet to extend): a real `PUT` with a changed
     header field produced exactly one correct `audit_log` row and flipped
     `automation_pct`; a `PUT` with no changes produced zero rows. Both test
     fiches (and the one fabricated value) were reverted afterward — see the
     conversation for the exact revert steps if something there looks off.
   - **Still gated on two prerequisites that were explicitly flagged, not
     built**: there's no auth/RBAC anywhere in this app (confirmed via grep
     for keycloak/oauth/jwt/login — zero hits, `infra/keycloak/` is empty),
     so `changed_by` can't yet say *which* person made an edit, only that a
     person did. The rest of the pasted analytics spec (Traçabilité serial
     search, Performance opérateurs, Qualité & Conformité module, RBAC,
     WebSockets, scheduled reports, export API) was explicitly **not**
     started — this was only the "wire up audit_log + rebuild Pilotage"
     slice you picked.

10. **New `GET /operations` — flat, cross-fiche browse table.** You asked for
    "access to the full database" with every operation identifiable by its OF
    and item ref, then explicitly narrowed it: **only validated fiches**, not
    every fiche. Implementation:
    - [api/app/routers/operations.py](api/app/routers/operations.py) (new) —
      queries the unified `operation_rows` table (§3.11) joined to `Fiche` →
      `WorkOrder`/`Product` for `n_of`/`ref_produit`, filtered to
      `Fiche.statut == valide` unconditionally. It now returns **both
      operations and controls** (one table) and carries the verbatim
      outillage/matricule text + per-row confidence. This relies on §3.3's fix
      (relational rows sync on every save) — without it this table would have
      been reading stale data.
    - Why validated-only: a fiche still in `extrait`/`en_revue` may carry an
      unreviewed VLM misread; a cross-fiche "full database" view is only as
      trustworthy as its least-reviewed row, so it's scoped to the rows a
      human has actually confirmed.
    - Filters: `q` (free text on ref produit / N° OF), `n_of`, `ref_produit`,
      `matricule`, `partie`; paginated (`page`/`page_size`, default 50).
      Controls (the 3 `Control` rows per fiche) are **not** included — the
      request said "operations"; controls can be added the same way later if
      asked.
    - Frontend: new page [Operations.tsx](frontend/src/pages/Operations.tsx)
      at `/operations` ("Base de données" in the sidebar,
      [Layout.tsx](frontend/src/components/Layout.tsx)), same filter-bar +
      paginated-table pattern as [History.tsx](frontend/src/pages/History.tsx).
      No CSV export yet — wasn't asked for; easy to add to the existing
      `/{fiche_id}/export` exporters if wanted.
    - Verified end-to-end against the live stack: rebuilt api+frontend
      images, confirmed `total=50` (25 operations × the 2 currently-validated
      fiches 23/41), confirmed `n_of`/`matricule`/`partie` filters narrow
      correctly, confirmed a nonexistent filter value returns `total=0`, and
      confirmed the page renders through the nginx `/api` proxy at
      `localhost:3000/operations`.

11. **DB restructured: `operations` + `controls` → one `operation_rows` table,
    and the dashboard rebuilt as BI.** This was an explicit, approved
    architecture change ("act as a senior engineer, structure the DB
    properly"; "KPIs about the data inside the files, not file counts").

    **Why it was needed** — each fiche's data was stored *twice* and the copies
    disagreed: the JSONB `raw_extraction` blob held everything (incl. per-field
    confidence/raw text) and was what `/analytics` read; the relational
    `operations`/`controls` tables were a *lossy* projection (controls dropped
    dates/times/qty; per-field provenance was absent; resolved `tool_id` was
    null for most outillage so the raw text was lost) and were what
    `/operations` read. Two sources of truth, one of them incomplete.

    **What changed**
    - **New model [api/app/models/operation_row.py](api/app/models/operation_row.py)**:
      one `operation_rows` table holding **operations AND controls** (discriminated
      by `partie` = 1/2/controle). Lossless — every TableRow value as a typed
      column, control-only columns (`type_controle`/`methode`/`resultat`), the
      verbatim `outillage`/`matricule` strings **alongside** their resolved
      `tool_id`/`operator_id` FKs, and a `field_meta` JSONB carrying per-field
      `{confidence, raw_text, source}` so QA can query provenance directly.
      `Operation`/`Control` models + `models/operation.py`/`control.py` deleted;
      `Fiche.operations`/`.controls` relationships replaced by `Fiche.rows`.
    - **Single read path**: `_sync_table_rows`
      ([ingest.py](api/app/services/ingest.py)) now writes `operation_rows`;
      `/operations`, `/analytics`, `_to_list_item`, stats eager-load all read
      it. **The JSONB blob is now demoted to the UI edit-buffer + export/chat
      source + immutable provenance** — nothing *reports* off it anymore. (Full
      single-source-of-truth — i.e. the FicheDetail editor reading relational
      too — was deliberately NOT done: that's an ~800-line frontend rewrite for
      little gain; the editable working-copy + normalized read-model split is a
      legitimate pattern. Flag if you want it unified further.)
    - **Migration**: applied on the live volume via
      [app/scripts/backfill_operation_rows.py](api/app/scripts/backfill_operation_rows.py)
      (`docker compose run --rm api python -m app.scripts.backfill_operation_rows`)
      — it creates the table, **rebuilds every fiche's rows from its durable
      `raw_extraction`** (so nothing is lost even though the old relational
      tables were incomplete), then drops `operations`/`controls`. Ran clean:
      63 fiches → 1764 rows. An equivalent Alembic migration
      ([a1f2c3d4e5f6](db/alembic/versions/a1f2c3d4e5f6_unify_operation_rows.py))
      exists for fresh deploys but was **not** run on the live volume (it's
      ahead of the baseline — see §1.4); the script is the source of truth for
      what was applied. The script is idempotent (safe to re-run).
    - **One backfill caveat**: `merge_extraction`/`_ef` stamps every field's
      `source` as `"vlm"`, so `field_meta.*.source` is `"vlm"` for all
      backfilled rows even where a human had corrected the value. This is
      cosmetic (the audit_log is the real human-change record, and `source` is
      effectively always `"vlm"` in this codebase anyway since the live PUT path
      also routes through `merge_extraction`). Not worth special-casing.

    **BI dashboard** ([analytics.py](api/app/routers/analytics.py) +
    [Dashboard.tsx](frontend/src/pages/Dashboard.tsx) +
    [Charts.tsx](frontend/src/components/Charts.tsx)) — now analyses the
    *extracted content*, **scoped to validated fiches** (trustworthy data),
    across the four axes you picked, with a small process funnel as the only
    file-level figure kept:
    - **1 · Conformité & défauts**: control pass/fail donut, results stacked by
      control type, non-conformities per product, + KPI tiles (conformité %,
      non-conformités, `flagged_rows` "à revoir").
    - **2 · Flux opératoire & goulots**: gamme coverage donut, per-operation
      realisation rate, cycle-time bottleneck ranking, throughput timeline.
    - **3 · Performance opérateurs**: workload per matricule, avg cycle time
      per operator.
    - **4 · Quantité & traçabilité**: volume per product ref, serials traced
      per product, top outillages.
    - Gauges: Couverture / Conformité / Automatisation (each `null`→"—" when no
      data). Empty-state when 0 validated fiches, nudging the user to validate.
    - **Removed** the old file-centric tiles/charts (raw fiche count, "fiches
      validées N/M", "activité de numérisation" area) per "not the files info."
    - Verified live: `scope.validated` tracks as you validate (was 4 → 7 during
      testing), `/operations` total = validated × 28, KPIs all sane
      (conformité 100%, automatisation 86%, cycle ~54 min).

12. **Soft UI/UX redesign pass.** Senior-designer pass over the *design system*
    so polish cascades app-wide: softer/diffuse shadow tokens + refined brand
    gradients ([tailwind.config.js](frontend/tailwind.config.js)); a cohesive
    soft button family (`btn-primary/soft/ghost/danger/sm/icon`), ring-based
    cards, soft `badge-*` status pills, a `segmented` control, refined inputs
    ([index.css](frontend/src/index.css)); ring-based status/confidence badges
    with status dots ([ui.tsx](frontend/src/ui.tsx)); a grouped, premium sidebar
    + cleaner topbar ([Layout.tsx](frontend/src/components/Layout.tsx)); polished
    KPI tiles, gauges, and numbered BI section headers
    ([Dashboard.tsx](frontend/src/pages/Dashboard.tsx)); Operations view toggle
    unified to the segmented control. Build verified (CSS 42.8 kB → 7.3 kB gz).
    Not hand-tuned: FicheDetail (the big editor) and FloatingChat inherit the
    softened classes but weren't individually restyled.

13. **Chatbot copilot integrated from the `farness/ChatBot` branch** (a
    Pydantic AI **tool-calling** agent — replaces the old prompt-stuffing chat).
    The branch was one commit (`096b3c0`) off the OLD base `285be99`; I took its
    chatbot work and adapted only where my later restructure required.
    - **Brought in verbatim**: `api/app/agent/` (`agent.py`, `model.py`,
      `deps.py`, `queries.py`, `tools.py`, `service.py`), the agent-backed
      `routers/chat.py` (async streaming via `agent.service.run_stream`),
      `services/analytics.py` (the `compute_overview` the `get_overview` tool
      uses), and `api/tests/` (10 tests). Deleted the old
      `services/chat.py`. Merged `config.py` (`chat_model` =
      `qwen/qwen3-30b-a3b-instruct-2507`, `chat_base_url`/`chat_api_key`),
      `pyproject.toml` (`openai` → `pydantic-ai-slim[openai]`), `.env.example`,
      and 2 frontend comment tweaks.
    - **Schema-compatible by luck/design**: the agent reads each fiche's
      `raw_extraction` **JSONB** (`ex.get("operations")`/`controls`), NOT the
      relational tables I dropped — and its model imports all still exist. So no
      query rewrite was needed.
    - **Deliberately did NOT take** (would have clobbered my work / unrelated):
      the branch's slimmed `routers/analytics.py` (I kept my BI version §3.11 —
      the Dashboard depends on its contract), the docker-compose port change
      (3000→3100; kept 3000), and the baseline-migration edit.
    - **Provider**: the chat model reaches OpenRouter via the existing `VLLM_*`
      fallback (`chat_* or vllm_*` in `agent/model.py`), so no secret change was
      needed. To split chat onto its own endpoint later, set `CHAT_BASE_URL`/
      `CHAT_API_KEY` in `.env`.
    - **Verified**: 10/10 tests pass in-container
      (`docker compose cp api/tests api:/srv/api/tests && docker compose exec api
      python -m pytest tests`), and a live `POST /chat` returned a correct,
      language-matched grounded answer.
    - **Latent bug fixed along the way**: the `operation_rows` model used
      `create_type=False` on its enums (correct for the live DB, where the
      dropped tables had already made the types) — but on a FRESH DB
      (`create_all`, e.g. the test DB) nothing created `partie`/`statut_revue`/
      `type_controle`/`methode` anymore, so table creation failed
      (`type "partie" does not exist`). Fixed: the model now owns enum creation
      (plain `Enum(...)`, checkfirst skips existing); the Alembic migration keeps
      `create_type=False` (it runs after the baseline). See
      [operation_row.py](api/app/models/operation_row.py).

⚠️ **CRITICAL OPS LESSON — schema changes must rebuild BOTH `api` AND
`worker`.** The `worker` image **bundles its own copy of `api/app`** (see
[worker/Dockerfile](worker/Dockerfile): `COPY api/app /srv/api/app`). When I
dropped `operations`/`controls` and rebuilt only `api`, the stale worker kept
running old code that did `INSERT INTO controls` → **every new scan failed**
(`relation "controls" does not exist`) and was filed as an error fiche. Fixed
by `docker compose build worker && docker compose up -d worker`. **Any future
model/ingest change: rebuild api, worker, AND frontend.** (Scan #6's 20
"ERREUR · scan 6 pN" fiches are artifacts of this — safe to delete; offered.)

## 4. Known issues / open threads

- **Orientation on faint-logo pages is still borderline** (e.g. page 7 of
  one of the real scans) — logo match score sits near `_LOGO_FLOOR` and can
  pick the wrong rotation. Untouched this session; still needs widening the
  multi-scale search or tuning the floor in
  [worker/worker/preprocess/orient.py](worker/worker/preprocess/orient.py).
- **The "validated fiches keep their flags" behavior change (§3.3)** was an
  inferred design call, not an explicit request — revisit if it feels wrong
  in practice.
- **Closed-weight VLM in production** (§2, §3.6) — needs an explicit
  decision with Agilink before real client data flows through OpenRouter
  long-term, given the README's stated self-hosted/data-sovereignty goal.
- A few of the validated-fiche's bottom rows/controls (Test électrique,
  Potting, the 3 control checkboxes) still read blank on at least one real
  fiche — likely genuinely blank on the paper, not re-verified visually by
  a human yet (see §3.5).
- **`/operations` browse table (§3.10) has no CSV export and no date-range
  filter** — neither was explicitly asked for; add if requested. It also
  excludes `Control` rows entirely (the request said "operations") — revisit
  if controls need to show up in the same view.

## 5. Current state

```
branch:    data_extract — 36 tracked files modified + new untracked source files + 2 deleted models, uncommitted (+2287/-561 on tracked files)
origin:    https://github.com/EmnaRaj/ocr_agilink.git   — public  — at 865b340 (behind)
farness:   https://github.com/Farness-App/ocr_agilink.git — private — has data_extract + ChatBot branches; this session's work is NOT pushed anywhere

DB:        ~83 fiches (incl. 20 "ERREUR · scan 6" artifacts of the worker regression — safe to delete), operators grow organically.
           SCHEMA: operations + controls dropped, replaced by unified operation_rows (§3.11) — backfilled from raw_extraction. audit_log fills in on each human edit.
Services:  all 6 up (postgres, api, worker, frontend, minio, redis). api + worker + frontend images all rebuilt this session (restructure + BI dashboard + soft UI + chatbot). worker MUST be rebuilt on any schema change (§3.13 lesson).
VLM:       qwen/qwen3.7-plus via OpenRouter (vision). Chatbot copilot: qwen/qwen3-30b-a3b-instruct-2507 via OpenRouter (text, tool-calling) — §3.13.
```

## 6. How to pick this back up

```bash
cd /home/emna/Desktop/ocr_agilink
docker compose ps                       # confirm the 6 services are up
git status && git diff --stat           # see the uncommitted work from §3
python -m pytest packages/fiche_schema/tests/ -q   # 14 tests, all passing
```

Quickstart / env setup / VLM backend switch: see [README.md](README.md) —
its "Status" section is stale (still describes Phase 0/1); treat this
HANDOFF.md as current truth until the README gets updated.
