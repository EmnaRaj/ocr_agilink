"""The run_sql sandbox guard + executor (specs/003 AC2)."""

import pytest

from app.agent import sql


@pytest.mark.parametrize("bad", [
    "UPDATE fiches SET statut = 'valide'",
    "DELETE FROM fiches",
    "DROP VIEW v_fiches",
    "SELECT 1; DROP TABLE fiches",          # multi-statement
    "SELECT 1 -- comment",                   # comment smuggling
    "SELECT * FROM v_fiches /* x */",        # block comment
    "INSERT INTO operators VALUES (1,'x','y')",
    "SELECT * INTO tmp FROM v_fiches",       # SELECT INTO is a write
    "SET ROLE postgres",
    "",                                       # empty
])
def test_guard_rejects_non_select(bad):
    with pytest.raises(ValueError):
        sql.validate_select(bad)


@pytest.mark.parametrize("ok", [
    "SELECT count(*) FROM v_fiches",
    "select ref_produit from v_fiches where statut = 'valide'",
    "WITH x AS (SELECT 1 AS n) SELECT n FROM x",
    "SELECT * FROM v_fiches;",                # trailing semicolon is stripped
])
def test_guard_accepts_select(ok):
    assert sql.validate_select(ok)


def test_inject_limit_added_when_absent():
    assert "LIMIT 500" in sql._inject_limit("SELECT * FROM v_fiches", 500)


def test_inject_limit_not_doubled():
    out = sql._inject_limit("SELECT * FROM v_fiches LIMIT 5", 500)
    assert out.count("LIMIT") == 1


def test_run_readonly_executes_and_caps(session_factory):
    with session_factory() as s:
        out = sql.run_readonly("SELECT 1 AS n", fallback_session=s, row_cap=10)
    assert "error" not in out
    assert out["columns"] == ["n"]
    assert out["rows"] == [[1]]
    assert "LIMIT 10" in out["sql"]


def test_run_readonly_queries_a_view(session_factory):
    with session_factory() as s:
        out = sql.run_readonly("SELECT fiche_id, ref_produit FROM v_fiches", fallback_session=s)
    assert "error" not in out  # the view is reachable through the sandbox
    assert out["columns"] == ["fiche_id", "ref_produit"]


def test_run_readonly_rejects_write_gracefully(session_factory):
    with session_factory() as s:
        out = sql.run_readonly("DELETE FROM fiches", fallback_session=s)
    assert "error" in out and "rows" not in out


def test_run_readonly_blocks_write_at_transaction_level(session_factory):
    # Even a query that slipped past the parser cannot write: the transaction is
    # read-only. (We call the executor directly with a write to prove the layer.)
    with session_factory() as s:
        out = sql._exec(s, "UPDATE fiches SET created_by = 'x'", 5000, 100)
    assert "error" in out  # read-only transaction rejects the write
