"""Deterministic data functions behind the copilot's tools.

Plain functions over a SQLAlchemy `Session` — no agent/LLM coupling, so they are
unit-tested directly (see api/tests/test_agent_tools.py). The `@agent.tool`
wrappers in tools.py are thin adapters over these. All aggregate facts are
computed here in SQL/Python; the model never tallies values itself.
"""

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Fiche, Operator, Product, StatutFiche, Tool, WorkOrder
from ..routers.fiches_read import (
    _header_ref,
    _loaded,
    _overall_confidence,
    _to_list_item,
)
from ..services.analytics import _fv, compute_overview


def overview(db: Session) -> dict:
    return compute_overview(db)


def search_fiches(
    db: Session,
    q: str | None = None,
    ref_produit: str | None = None,
    n_of: str | None = None,
    statut: str | None = None,
    needs_review: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
) -> list[dict]:
    base = select(Fiche).join(Fiche.work_order).join(WorkOrder.product)
    if q:
        like = f"%{q}%"
        base = base.where(or_(Product.ref_produit.ilike(like), WorkOrder.n_of.ilike(like)))
    if ref_produit:
        base = base.where(Product.ref_produit.ilike(f"%{ref_produit}%"))
    if n_of:
        base = base.where(WorkOrder.n_of.ilike(f"%{n_of}%"))
    if needs_review:
        statut = "en_revue"
    if statut:
        try:
            base = base.where(Fiche.statut == StatutFiche(statut))
        except ValueError:
            pass  # unknown statut → ignore the filter rather than error
    for raw, lower in ((date_from, True), (date_to, False)):
        if raw:
            try:
                dt = datetime.fromisoformat(raw)
                base = base.where(Fiche.date_creation >= dt if lower else Fiche.date_creation <= dt)
            except ValueError:
                pass
    rows = db.scalars(
        _loaded(base).order_by(Fiche.date_creation.desc()).limit(max(1, min(limit, 100)))
    ).unique().all()
    return [_to_list_item(f).model_dump(mode="json") for f in rows]


def _compact_operations(ex: dict) -> list[dict]:
    """Only operation rows that actually carry data (keeps the payload bounded)."""
    out = []
    for o in ex.get("operations") or []:
        ov = lambda k: _fv(o.get(k))  # noqa: E731
        date = (o.get("date_op") or {}).get("raw_text") or ov("date_op")
        if not (ov("applicable") is not None or ov("matricule_operateur") or ov("qte_realisee") is not None or date):
            continue
        out.append({
            "ordre": o.get("ordre"),
            "partie": o.get("partie"),
            "operation": o.get("nom_operation"),
            "applicable": ov("applicable"),
            "date": date,
            "qte_realisee": ov("qte_realisee"),
            "heure_debut": str(ov("heure_debut"))[:5] if ov("heure_debut") else None,
            "heure_fin": str(ov("heure_fin"))[:5] if ov("heure_fin") else None,
            "outillage": ov("outillage"),
            "matricule": ov("matricule_operateur"),
        })
    return out


def get_fiche(db: Session, fiche_id: int) -> dict | None:
    fiche = db.scalars(_loaded(select(Fiche).where(Fiche.fiche_id == fiche_id))).unique().first()
    if fiche is None:
        return None
    ex = fiche.raw_extraction or {}
    h = ex.get("header") or {}
    controls = []
    for c in ex.get("controls") or []:
        res = _fv(c.get("resultat"))
        controls.append({
            "controle": c.get("nom_operation"),
            "resultat": "Conforme" if res is True else ("Non conforme" if res is False else None),
            "matricule": _fv(c.get("matricule_operateur")),
        })
    serials = [_fv(it.get("numero_serie")) for it in (ex.get("items") or [])]
    return {
        "fiche_id": fiche.fiche_id,
        "statut": fiche.statut.value,
        "ref_produit": _header_ref(fiche),
        "n_of": fiche.work_order.n_of,
        "quantite": _fv(h.get("qte")) or fiche.work_order.quantite,
        "overall_confidence": _overall_confidence(fiche),
        "operations": _compact_operations(ex),
        "controls": controls,
        "serials": [s for s in serials if s],
        "validation": ex.get("validation") or [],
    }


def review_queue(db: Session, limit: int = 20) -> list[dict]:
    # Order + limit in SQL (lowest confidence first, missing confidence last) so
    # we never load the whole en_revue table just to take the worst N.
    confidence = Fiche.raw_extraction["meta"]["overall_confidence"].as_float()
    stmt = (
        _loaded(select(Fiche).where(Fiche.statut == StatutFiche.en_revue))
        .order_by(confidence.asc().nulls_last())
        .limit(max(1, min(limit, 100)))
    )
    fiches = db.scalars(stmt).unique().all()
    items = []
    for f in fiches:
        ex = f.raw_extraction or {}
        items.append({
            "fiche_id": f.fiche_id,
            "ref_produit": _header_ref(f),
            "n_of": f.work_order.n_of,
            "overall_confidence": _overall_confidence(f) or 0.0,
            "issues": [
                {"level": i.get("level"), "field": i.get("field"), "message": i.get("message")}
                for i in (ex.get("validation") or [])
            ],
        })
    return items


def referential(db: Session) -> dict:
    operators = db.scalars(select(Operator)).all()
    tools = db.scalars(select(Tool)).all()
    return {
        "operators": [{"matricule": o.matricule, "nom": o.nom} for o in operators],
        "tools": [{"code": t.code_outillage, "libelle": t.libelle} for t in tools],
    }
