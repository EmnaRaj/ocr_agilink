from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create the full schema + analytical views if they're missing.

    Idempotent and safe on an already-populated DB (existing tables/views are
    skipped). Runs at API startup so a FRESH deploy — e.g. the local test
    package a client unzips and runs — boots with a complete, current schema
    with no manual migration step. Disable with AUTO_INIT_DB=0.
    """
    import logging
    import os

    if os.environ.get("AUTO_INIT_DB", "1") == "0":
        return
    log = logging.getLogger("app.db")
    from sqlalchemy import text

    from . import models  # noqa: F401 — registers every table on Base.metadata
    from .models.base import Base

    try:
        Base.metadata.create_all(bind=engine, checkfirst=True)
    except Exception as exc:  # noqa: BLE001 — existing DB / enum race: schema is already there
        log.warning("create_all skipped (schema likely already present): %s", exc)
    try:
        from .agent.views import ANALYTICS_VIEWS

        with engine.begin() as conn:
            for ddl in ANALYTICS_VIEWS:
                conn.execute(text(ddl))
    except Exception as exc:  # noqa: BLE001 — views are best-effort at startup
        log.warning("analytics view init skipped: %s", exc)
