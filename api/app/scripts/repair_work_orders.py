"""One-off repair: re-point each validated fiche's WorkOrder/Product at its
(corrected) header ref/OF/qté, fixing fiches whose header was corrected after
the original misread created the Product (e.g. fiche read 20208044, corrected to
10108044, but the list/matrix still showed 20208044).

Going forward this is handled automatically on every save (_sync_work_order in
ingest.py); this repairs the already-validated rows. Then prunes the orphaned
products/work_orders left behind by the relink.

    docker compose exec -T api python -m app.scripts.repair_work_orders
"""

from fiche_schema import merge_extraction

from ..db import SessionLocal
from ..models import Fiche, Product, StatutFiche, WorkOrder
from ..services.ingest import _sync_work_order


def run() -> None:
    db = SessionLocal()
    try:
        fixed = 0
        for f in db.query(Fiche).filter(Fiche.statut == StatutFiche.valide).all():
            raw = f.raw_extraction or {}
            meta = raw.get("meta") or {}
            extraction = merge_extraction(
                raw, model_name=meta.get("model_name") or "human", processing_ms=meta.get("processing_ms")
            )
            before = f.work_order.product.ref_produit
            _sync_work_order(db, f, extraction)
            db.flush()
            after = f.work_order.product.ref_produit
            if before != after:
                print(f"  fiche {f.fiche_id}: {before} -> {after}")
                fixed += 1
        db.commit()

        # Prune what the relink orphaned.
        wo_orphans = (
            db.query(WorkOrder)
            .filter(~WorkOrder.of_id.in_(db.query(Fiche.of_id)))
            .delete(synchronize_session=False)
        )
        db.commit()
        p_orphans = (
            db.query(Product)
            .filter(~Product.product_id.in_(db.query(WorkOrder.product_id)))
            .delete(synchronize_session=False)
        )
        db.commit()
        print(f"Relinked {fixed} fiches; pruned {wo_orphans} orphan work_orders, {p_orphans} orphan products.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
