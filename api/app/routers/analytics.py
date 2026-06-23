"""Aggregated analytics for the dashboard, computed from the (corrected) data.

Everything is derived from each fiche's raw_extraction so it reflects user
edits/validations, not the original relational snapshot.
"""

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..db import get_db
from ..models import Fiche, WorkOrder

router = APIRouter(tags=["analytics"])


def _fv(field: object) -> object:
    return (field or {}).get("value") if isinstance(field, dict) else None


@router.get("/analytics")
def analytics(db: Session = Depends(get_db)) -> dict:
    fiches = db.scalars(
        select(Fiche)
        .options(
            joinedload(Fiche.work_order).joinedload(WorkOrder.product),
            selectinload(Fiche.items),
        )
        .order_by(Fiche.date_creation)
    ).unique().all()

    op_applied = op_total = 0
    operators: Counter = Counter()
    conformity: Counter = Counter()
    timeline: Counter = Counter()       # operations per operation-date (DD.MM)
    products: Counter = Counter()       # qty per ref
    tools: Counter = Counter()
    by_day: Counter = Counter()         # fiches per scan-day
    statut: Counter = Counter()
    serial_count = 0

    for f in fiches:
        statut[f.statut.value] += 1
        by_day[f.date_creation.strftime("%d/%m")] += 1
        ex = f.raw_extraction or {}
        h = ex.get("header") or {}
        ref = _fv(h.get("ref_produit")) or f.work_order.product.ref_produit
        qte = _fv(h.get("qte")) or f.work_order.quantite or 0
        products[ref] += int(qte) if isinstance(qte, (int, float)) else 0

        for o in ex.get("operations") or []:
            mat = _fv(o.get("matricule_operateur"))
            appl = _fv(o.get("applicable"))
            date = (o.get("date_op") or {}).get("raw_text")
            op_total += 1
            if appl is True or mat:
                op_applied += 1
            if mat:
                operators[str(mat)] += 1
            if date:
                timeline[str(date)] += 1
            tool = _fv(o.get("outillage"))
            if tool:
                tools[str(tool)] += 1

        for c in ex.get("controls") or []:
            r = _fv(c.get("resultat"))
            conformity["Conforme" if r is True else ("Non conforme" if r is False else "Non renseigné")] += 1

        serial_count += len([1 for it in (ex.get("items") or []) if _fv(it.get("numero_serie"))])

    coverage = round(100 * op_applied / op_total) if op_total else 0
    conf_ok = conformity.get("Conforme", 0)
    conf_total = sum(conformity.values())
    conformity_rate = round(100 * conf_ok / conf_total) if conf_total else 0

    return {
        "kpis": {
            "fiches": len(fiches),
            "operations": op_total,
            "coverage_pct": coverage,
            "conformity_pct": conformity_rate,
            "operators": len(operators),
            "serials": serial_count,
            "validated": statut.get("valide", 0),
        },
        "operation_coverage": [
            {"name": "Réalisées", "value": op_applied},
            {"name": "Non renseignées", "value": max(op_total - op_applied, 0)},
        ],
        "operator_workload": [{"matricule": k, "operations": v} for k, v in operators.most_common(10)],
        "conformity": [{"name": k, "value": v} for k, v in conformity.items()],
        "timeline": [{"date": k, "operations": v} for k, v in sorted(timeline.items())],
        "product_volumes": [{"ref": k, "qty": v} for k, v in products.most_common(8)],
        "fiches_by_day": [{"date": k, "count": v} for k, v in by_day.items()],
        "by_statut": [
            {"name": "Extrait", "value": statut.get("extrait", 0)},
            {"name": "En revue", "value": statut.get("en_revue", 0)},
            {"name": "Validé", "value": statut.get("valide", 0)},
        ],
        "top_tools": [{"name": k, "count": v} for k, v in tools.most_common(6)],
    }
