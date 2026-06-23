from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..db import get_db
from ..models import Fiche, Product, StatutFiche, WorkOrder
from ..schemas import StatsResponse, StatutBreakdown
from .fiches_read import _to_list_item

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
    total_fiches = db.scalar(select(func.count()).select_from(Fiche)) or 0
    total_products = db.scalar(select(func.count()).select_from(Product)) or 0
    total_work_orders = db.scalar(select(func.count()).select_from(WorkOrder)) or 0

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    scanned_today = (
        db.scalar(select(func.count()).select_from(Fiche).where(Fiche.date_creation >= today)) or 0
    )

    by = dict(
        db.execute(select(Fiche.statut, func.count()).group_by(Fiche.statut)).all()
    )
    breakdown = StatutBreakdown(
        extrait=by.get(StatutFiche.extrait, 0),
        en_revue=by.get(StatutFiche.en_revue, 0),
        valide=by.get(StatutFiche.valide, 0),
    )

    recent = db.scalars(
        select(Fiche)
        .options(
            joinedload(Fiche.work_order).joinedload(WorkOrder.product),
            selectinload(Fiche.items),
            selectinload(Fiche.operations),
        )
        .order_by(Fiche.date_creation.desc())
        .limit(8)
    ).unique().all()

    confidences = [
        c
        for f in recent
        if (c := (f.raw_extraction or {}).get("meta", {}).get("overall_confidence")) is not None
    ]
    avg_conf = round(sum(confidences) / len(confidences), 3) if confidences else None

    return StatsResponse(
        total_fiches=total_fiches,
        total_products=total_products,
        total_work_orders=total_work_orders,
        scanned_today=scanned_today,
        avg_confidence=avg_conf,
        by_statut=breakdown,
        recent=[_to_list_item(f) for f in recent],
    )
