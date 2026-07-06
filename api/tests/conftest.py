"""Postgres-backed test fixtures for the api package.

The models use Postgres-specific types (JSONB, native ENUMs), so tests run
against a real Postgres — a throwaway database created from `DATABASE_URL`'s
server, with one transaction per test rolled back for isolation.

Run inside the api container (which has DATABASE_URL → postgres:5432):
    docker compose exec api sh -c 'pip install pytest && pytest /srv/api/tests'
"""

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import Base, Fiche, Product, StatutFiche, WorkOrder

_TEST_DB = "fiches_copilot_test"


def _server_url(db_name: str) -> str:
    base = os.environ["DATABASE_URL"]
    return base.rsplit("/", 1)[0] + "/" + db_name


@pytest.fixture(scope="session")
def engine():
    # (Re)create a clean test database from the server's default db.
    admin = create_engine(_server_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {_TEST_DB}"))
    admin.dispose()

    eng = create_engine(_server_url(_TEST_DB))
    Base.metadata.create_all(eng)
    # The analytical views (specs/003) are created by an Alembic migration, not by
    # the models; create them here from the same canonical DDL so tests match prod.
    from app.agent.views import ANALYTICS_VIEWS

    with eng.begin() as c:
        for ddl in ANALYTICS_VIEWS:
            c.execute(text(ddl))
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Session:
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn)
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


@pytest.fixture
def session_factory(engine):
    """A `Deps.session_factory` bound to the test engine (for agent tools)."""
    return lambda: Session(bind=engine)


# --- builders ---------------------------------------------------------------

def op_row(ordre=1, partie="1", nom="Opération", applicable=None, matricule=None,
           date=None, qte=None, outillage=None, debut=None, fin=None) -> dict:
    def f(v):
        return {"value": v}
    return {
        "partie": partie, "ordre": ordre, "nom_operation": nom,
        "applicable": f(applicable),
        "date_op": {"value": None, "raw_text": date},
        "date_fin": f(None),
        "heure_debut": f(debut), "heure_fin": f(fin),
        "qte_realisee": f(qte), "outillage": f(outillage),
        "matricule_operateur": f(matricule),
    }


def ctrl_row(nom="Contrôle", resultat=None, matricule=None) -> dict:
    return {
        "partie": "controle", "ordre": 1, "nom_operation": nom,
        "type_controle": "controle_final",
        "applicable": {"value": None}, "date_op": {"value": None, "raw_text": None},
        "date_fin": {"value": None}, "heure_debut": {"value": None}, "heure_fin": {"value": None},
        "qte_realisee": {"value": None}, "outillage": {"value": None},
        "matricule_operateur": {"value": matricule},
        "methode": {"value": None}, "resultat": {"value": resultat},
    }


def extraction(ref="123456", n_of="1554", qte=10, ops=(), controls=(),
               confidence=0.9, validation=()) -> dict:
    return {
        "header": {
            "ref_produit": {"value": ref}, "n_of": {"value": n_of},
            "qte": {"value": qte}, "annotation_serie": {"value": None},
        },
        "operations": list(ops),
        "controls": list(controls),
        "items": [],
        "meta": {"model_name": "test", "overall_confidence": confidence},
        "validation": list(validation),
    }


@pytest.fixture
def make_fiche(db):
    """Factory: create a persisted fiche with the given extraction/statut."""
    def _make(ref="123456", n_of="1554", statut=StatutFiche.extrait, quantite=10, ex=None) -> Fiche:
        product = Product(ref_produit=ref)
        wo = WorkOrder(n_of=n_of, product=product, quantite=quantite)
        fiche = Fiche(
            work_order=wo, statut=statut, date_creation=datetime.now(timezone.utc),
            raw_extraction=ex if ex is not None else extraction(ref=ref, n_of=n_of, qte=quantite),
        )
        db.add_all([product, wo, fiche])
        db.flush()
        return fiche
    return _make
