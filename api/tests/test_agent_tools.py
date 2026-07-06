"""Unit tests for the copilot's deterministic data functions (no LLM)."""

from app.agent import queries
from app.models import StatutFiche

from .conftest import ctrl_row, extraction, op_row


def test_get_overview_counts_and_conformity(db, make_fiche):
    make_fiche(ref="100000", n_of="1111", statut=StatutFiche.extrait, ex=extraction(
        ref="100000", n_of="1111",
        ops=[op_row(1, "1", "Sertissage", applicable=True, matricule="390"),
             op_row(2, "1", "Soudure", applicable=True, matricule="332")],
        controls=[ctrl_row("Contrôle final", resultat=True, matricule="390")],
    ))
    make_fiche(ref="200000", n_of="2222", statut=StatutFiche.en_revue, ex=extraction(
        ref="200000", n_of="2222",
        ops=[op_row(1, "1", "Sertissage", applicable=True, matricule="390")],
        controls=[ctrl_row("Contrôle final", resultat=False, matricule="390")],
        confidence=0.4,
    ))

    ov = queries.overview(db)
    assert ov["kpis"]["fiches"] == 2
    assert ov["kpis"]["operations"] == 3
    assert ov["kpis"]["conformity_pct"] == 50  # 1 conforme / 2 controls
    by = {b["name"]: b["value"] for b in ov["by_statut"]}
    assert by["Extrait"] == 1 and by["En revue"] == 1
    workload = {w["matricule"]: w["operations"] for w in ov["operator_workload"]}
    assert workload["390"] == 2 and workload["332"] == 1


def test_search_fiches_filters(db, make_fiche):
    make_fiche(ref="100000", n_of="1111", statut=StatutFiche.extrait)
    make_fiche(ref="200000", n_of="2222", statut=StatutFiche.en_revue)

    review = queries.search_fiches(db, needs_review=True)
    assert [f["n_of"] for f in review] == ["2222"]

    by_q = queries.search_fiches(db, q="1111")
    assert [f["ref_produit"] for f in by_q] == ["100000"]

    extrait = queries.search_fiches(db, statut="extrait")
    assert {f["statut"] for f in extrait} == {"extrait"}

    assert queries.search_fiches(db, statut="not_a_statut")  # bad filter ignored, not error


def test_get_fiche_detail_and_missing(db, make_fiche):
    f = make_fiche(ref="123456", n_of="1554", ex=extraction(
        ref="123456", n_of="1554",
        ops=[op_row(1, "1", "Sertissage", applicable=True, matricule="390", date="12.03")],
        controls=[ctrl_row("Contrôle final", resultat=True)],
    ))
    detail = queries.get_fiche(db, f.fiche_id)
    assert detail is not None
    assert detail["ref_produit"] == "123456"
    assert detail["n_of"] == "1554"
    assert len(detail["operations"]) == 1
    assert detail["operations"][0]["matricule"] == "390"
    assert detail["controls"][0]["resultat"] == "Conforme"

    assert queries.get_fiche(db, 999999) is None  # AC3: missing → None


def test_review_queue_orders_by_confidence_with_issues(db, make_fiche):
    make_fiche(ref="300000", n_of="3333", statut=StatutFiche.en_revue, ex=extraction(
        ref="300000", n_of="3333", confidence=0.5,
        validation=[{"level": "warning", "field": "qte", "message": "Quantité douteuse"}],
    ))
    make_fiche(ref="400000", n_of="4444", statut=StatutFiche.en_revue, ex=extraction(
        ref="400000", n_of="4444", confidence=0.2,
        validation=[{"level": "error", "field": "ref_produit", "message": "Réf illisible"}],
    ))
    make_fiche(ref="500000", n_of="5555", statut=StatutFiche.extrait)  # excluded

    queue = queries.review_queue(db)
    assert [q["n_of"] for q in queue] == ["4444", "3333"]  # lowest confidence first
    assert queue[0]["issues"][0]["level"] == "error"


def test_referential_lists_operators_and_tools(db):
    from app.models import Operator, Tool
    db.add_all([Operator(matricule="390", nom="Dupont"), Tool(code_outillage="Pince 8", libelle="Pince")])
    db.flush()
    ref = queries.referential(db)
    assert {o["matricule"] for o in ref["operators"]} == {"390"}
    assert ref["operators"][0]["nom"] == "Dupont"
    assert {t["code"] for t in ref["tools"]} == {"Pince 8"}
