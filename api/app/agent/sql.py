"""Read-only SQL sandbox for the analytical copilot (specs/003).

The agent's ``run_sql`` tool lets the model write its own SELECTs over the analytical
views. This module is the guardrail layer that makes that safe:

1. a SELECT/WITH-only parser that rejects multi-statement, DDL/DML, and comments;
2. an injected ``LIMIT`` row cap;
3. a read-only transaction + statement timeout, always rolled back.

Facts still come from executed queries over the source-of-truth views — the model
composes the query, Postgres returns the numbers (constitution #1 preserved).
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, text

from ..config import settings

log = logging.getLogger("agent.sql")

# Whole-word tokens that must never appear in a query (writes / DDL / session control
# / multi-statement smuggling). The query must also *start* with SELECT or WITH.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|copy|merge|"
    r"call|do|vacuum|analyze|reindex|refresh|lock|into|set|attach|pragma|"
    r"begin|commit|rollback|savepoint)\b",
    re.IGNORECASE,
)
_STARTS_OK = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_HAS_LIMIT = re.compile(r"\blimit\b", re.IGNORECASE)

_ro_engine = None  # lazily built dedicated read-only engine, if configured


def _get_ro_engine():
    global _ro_engine
    if settings.readonly_database_url and _ro_engine is None:
        _ro_engine = create_engine(settings.readonly_database_url)
    return _ro_engine


def validate_select(query: str) -> str:
    """Return a cleaned single SELECT/WITH statement, or raise ValueError."""
    q = (query or "").strip()
    if not q:
        raise ValueError("empty query")
    if "--" in q or "/*" in q:
        raise ValueError("comments are not allowed")
    q = q.rstrip(";").strip()
    if ";" in q:
        raise ValueError("only a single statement is allowed")
    if not _STARTS_OK.match(q):
        raise ValueError("only SELECT/WITH queries are allowed")
    bad = _FORBIDDEN.search(q)
    if bad:
        raise ValueError(f"disallowed keyword: {bad.group(0).lower()}")
    return q


def _inject_limit(query: str, row_cap: int) -> str:
    if _HAS_LIMIT.search(query):
        return query
    return f"{query}\nLIMIT {int(row_cap)}"


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    return v


def _exec(executor, final_sql: str, timeout_ms: int, row_cap: int) -> dict:
    try:
        executor.rollback()  # ensure a clean transaction
        executor.execute(text("SET TRANSACTION READ ONLY"))
        executor.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
        result = executor.execute(text(final_sql))
        cols = list(result.keys())
        fetched = result.fetchmany(row_cap + 1)
        truncated = len(fetched) > row_cap
        rows = [[_jsonable(v) for v in row] for row in fetched[:row_cap]]
        return {"columns": cols, "rows": rows, "sql": final_sql, "truncated": truncated}
    except Exception as exc:  # malformed SQL, timeout, type-cast error, …
        log.warning("run_sql failed: %s", exc)
        return {"error": str(exc).strip().splitlines()[0][:300], "sql": final_sql}
    finally:
        try:
            executor.rollback()
        except Exception:
            pass


def run_readonly(query: str, *, fallback_session, timeout_ms: int | None = None,
                 row_cap: int | None = None) -> dict:
    """Validate and execute a read-only query; never raises.

    Uses the dedicated read-only engine if ``READONLY_DATABASE_URL`` is set, otherwise
    the caller's ``fallback_session`` (whose transaction we force read-only). Returns
    ``{columns, rows, sql, truncated}`` on success, or ``{error, sql}`` on rejection.
    """
    timeout_ms = settings.sql_timeout_ms if timeout_ms is None else timeout_ms
    row_cap = settings.sql_row_cap if row_cap is None else row_cap
    try:
        final_sql = _inject_limit(validate_select(query), row_cap)
    except ValueError as exc:
        return {"error": str(exc), "sql": query}

    ro = _get_ro_engine()
    if ro is not None:
        conn = ro.connect()
        try:
            return _exec(conn, final_sql, timeout_ms, row_cap)
        finally:
            conn.close()
    return _exec(fallback_session, final_sql, timeout_ms, row_cap)
