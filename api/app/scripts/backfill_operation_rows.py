"""One-off migration: create `operation_rows`, backfill it from every fiche's
`raw_extraction`, then drop the legacy `operations` / `controls` tables.

The live DB volume is ahead of the Alembic baseline (page_index/rotation were
applied via raw ALTER), so this is applied directly rather than via Alembic.
Each fiche's `raw_extraction` JSONB is the durable source of truth, so the
relational rows are rebuilt from it (losslessly, including per-field
provenance) — the legacy tables are only dropped afterwards.

Run inside the (freshly built) api container, which holds the live DB
connection:

    docker compose run --rm api python -m app.scripts.backfill_operation_rows

Idempotent: re-creates the table if missing and rebuilds every fiche's rows
from scratch, so it's safe to re-run.
"""

from fiche_schema import merge_extraction, validate_extraction
from sqlalchemy import text

from ..db import SessionLocal, engine
from ..models import Fiche, OperationRow
from ..services.ingest import _sync_table_rows
from ..services.matching import known_matricules, match_operator


def run() -> None:
    # 1. Create the new table. The enum types it reuses (partie, statut_revue,
    #    type_controle, methode) already exist from the baseline schema.
    OperationRow.__table__.create(engine, checkfirst=True)

    db = SessionLocal()
    try:
        known = known_matricules(db)
        fiches = db.query(Fiche).all()
        rebuilt = skipped = 0
        for f in fiches:
            raw = f.raw_extraction or {}
            if not (raw.get("operations") or raw.get("controls")):
                # Error/placeholder fiche (unreadable page) — no table rows to
                # rebuild, same as the original extraction left it.
                f.rows = []
                skipped += 1
                continue
            meta = raw.get("meta") or {}
            extraction = merge_extraction(
                raw,
                model_name=meta.get("model_name") or "vlm",
                processing_ms=meta.get("processing_ms"),
            )
            issues = validate_extraction(extraction, known)
            flagged = {i.location for i in issues if i.scope in ("operation", "control")}
            # match_operator (lookup-only): backfill must not grow the
            # known-operator registry — it only mirrors the current data.
            _sync_table_rows(db, f, extraction, flagged, match_operator)
            rebuilt += 1
        db.commit()
        print(f"Backfilled operation_rows for {rebuilt} fiches ({skipped} empty/error skipped).")

        # 2. Everything now reads operation_rows — drop the legacy tables.
        db.execute(text("DROP TABLE IF EXISTS controls CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS operations CASCADE"))
        db.commit()
        print("Dropped legacy operations + controls tables.")

        total = db.query(OperationRow).count()
        print(f"operation_rows now holds {total} rows.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
