"""review_queue ordering + limit happen in SQL (AC3)."""

from app.agent import queries
from app.models import StatutFiche

from .conftest import extraction


def test_review_queue_orders_by_confidence_and_limits(db, make_fiche):
    make_fiche(ref="100000", n_of="1111", statut=StatutFiche.en_revue, ex=extraction(n_of="1111", confidence=0.8))
    make_fiche(ref="200000", n_of="2222", statut=StatutFiche.en_revue, ex=extraction(n_of="2222", confidence=0.2))
    make_fiche(ref="300000", n_of="3333", statut=StatutFiche.en_revue, ex=extraction(n_of="3333", confidence=0.5))
    make_fiche(ref="400000", n_of="4444", statut=StatutFiche.extrait)  # excluded (not en_revue)

    q = queries.review_queue(db, limit=2)
    assert [r["n_of"] for r in q] == ["2222", "3333"]  # lowest confidence first, limited to 2
