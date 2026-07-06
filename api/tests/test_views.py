"""Analytical views reflect the JSONB truth, not the stale relational snapshot (specs/003 AC1).

The relational operations/controls/items tables are written once at ingest and never
updated; corrections land only in raw_extraction. These tests prove the views read the
JSONB, so a correction is visible immediately.
"""

from sqlalchemy import text

from .conftest import ctrl_row, extraction, op_row


def test_v_operations_unnests_and_resolves_operator(db, make_fiche):
    f = make_fiche(ex=extraction(ops=[
        op_row(ordre=1, nom="Soudure", applicable=True, matricule="390"),
        op_row(ordre=2, nom="Vissage", applicable=None, matricule=None),
    ]))
    db.flush()
    rows = db.execute(
        text("SELECT nom_operation, applicable, matricule_operateur "
             "FROM v_operations WHERE fiche_id = :id ORDER BY ordre"),
        {"id": f.fiche_id},
    ).all()
    assert [r.nom_operation for r in rows] == ["Soudure", "Vissage"]
    assert rows[0].applicable is True
    assert rows[0].matricule_operateur == "390"


def test_view_reflects_a_correction(db, make_fiche):
    # Original extraction says matricule 390 on the only operation.
    f = make_fiche(ex=extraction(ops=[op_row(ordre=1, nom="Soudure", matricule="390")]))
    db.flush()
    before = db.execute(
        text("SELECT matricule_operateur FROM v_operations WHERE fiche_id = :id"),
        {"id": f.fiche_id},
    ).scalar_one()
    assert before == "390"

    # User corrects it to 412 (write a NEW dict, as the real PUT path does).
    ex = dict(f.raw_extraction)
    ops = [dict(ex["operations"][0])]
    ops[0]["matricule_operateur"] = {"value": "412"}
    ex["operations"] = ops
    f.raw_extraction = ex
    db.flush()

    after = db.execute(
        text("SELECT matricule_operateur FROM v_operations WHERE fiche_id = :id"),
        {"id": f.fiche_id},
    ).scalar_one()
    assert after == "412"  # the view tracks the correction


def test_v_fiches_validated_flag_and_confidence(db, make_fiche):
    f = make_fiche(ex=extraction(ref="999000", qte=7, confidence=0.42))
    db.flush()
    row = db.execute(
        text("SELECT ref_produit, quantite, overall_confidence, validated, statut "
             "FROM v_fiches WHERE fiche_id = :id"),
        {"id": f.fiche_id},
    ).one()
    assert row.ref_produit == "999000"
    assert row.quantite == 7
    assert abs(row.overall_confidence - 0.42) < 1e-6
    assert row.validated is False


def test_v_controls_and_empty_extraction_degrades(db, make_fiche):
    f = make_fiche(ex=extraction(controls=[ctrl_row(nom="Contrôle final", resultat=False, matricule="390")]))
    db.flush()
    row = db.execute(
        text("SELECT type_controle, resultat FROM v_controls WHERE fiche_id = :id"),
        {"id": f.fiche_id},
    ).one()
    assert row.resultat is False

    # A fiche whose raw_extraction has no arrays must not error — just yield no rows.
    f2 = make_fiche(ref="888111", n_of="of-empty", ex={"header": {}, "meta": {"overall_confidence": 0.0}})
    db.flush()
    n = db.execute(
        text("SELECT count(*) FROM v_operations WHERE fiche_id = :id"),
        {"id": f2.fiche_id},
    ).scalar_one()
    assert n == 0
