"""Analytical eval harness (specs/003 T7).

A small seeded dataset with KNOWN answers, queried through the analytical views the
way the agent's run_sql would. This catches view/SQL regressions deterministically
(no LLM): if a view's unnesting or a join breaks, an expected figure changes.
"""

from sqlalchemy import text

from app.models import StatutFiche
from .conftest import ctrl_row, extraction, op_row


def _seed(make_fiche, db):
    # 390 does 2 operations on A1; 412 does 1 on A2; A3 has a non-conform control by 390.
    make_fiche(ref="A1", n_of="of1", statut=StatutFiche.extrait,
               ex=extraction(ref="A1", n_of="of1", ops=[
                   op_row(ordre=1, applicable=True, matricule="390"),
                   op_row(ordre=2, applicable=True, matricule="390"),
               ]))
    make_fiche(ref="A2", n_of="of2", statut=StatutFiche.valide,
               ex=extraction(ref="A2", n_of="of2", ops=[
                   op_row(ordre=1, applicable=True, matricule="412"),
               ]))
    make_fiche(ref="A3", n_of="of3", statut=StatutFiche.en_revue,
               ex=extraction(ref="A3", n_of="of3", controls=[
                   ctrl_row(resultat=False, matricule="390"),
               ]))
    db.flush()


def test_eval_top_operator_by_operations(make_fiche, db):
    _seed(make_fiche, db)
    row = db.execute(text(
        "SELECT matricule_operateur, count(*) AS c FROM v_operations "
        "WHERE matricule_operateur IS NOT NULL GROUP BY 1 ORDER BY c DESC, 1 LIMIT 1"
    )).one()
    assert row.matricule_operateur == "390"
    assert row.c == 2


def test_eval_non_conform_control_count(make_fiche, db):
    _seed(make_fiche, db)
    n = db.execute(text("SELECT count(*) FROM v_controls WHERE resultat IS FALSE")).scalar_one()
    assert n == 1


def test_eval_statut_breakdown(make_fiche, db):
    _seed(make_fiche, db)
    rows = dict(db.execute(text("SELECT statut, count(*) FROM v_fiches GROUP BY statut")).all())
    assert rows == {"extrait": 1, "valide": 1, "en_revue": 1}


def test_eval_join_operator_name(make_fiche, db):
    # An operator row resolves its name via the v_operations -> operators join when the
    # matricule is known. (No operator seeded here, so operateur_nom is null — the LEFT
    # JOIN must still return the operation row, not drop it.)
    _seed(make_fiche, db)
    n = db.execute(text(
        "SELECT count(*) FROM v_operations WHERE matricule_operateur = '390'"
    )).scalar_one()
    assert n == 2
