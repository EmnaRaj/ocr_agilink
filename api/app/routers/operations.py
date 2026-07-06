"""Flat, browsable listing of every operation/control row across the dataset.

Sourced from the unified `operation_rows` table — the single, complete source
of truth (see models/operation_row.py) — joined back to its work order /
product so each row carries its OF and item reference.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from fiche_schema import CONTROLE_ROWS, PARTIE_1_OPERATIONS, PARTIE_2_OPERATIONS

from ..db import get_db
from ..models import Fiche, OperationRow, Partie, Product, StatutFiche, WorkOrder
from ..schemas import (
    OperationListItem,
    OperationListResponse,
    OperationMatrixCell,
    OperationMatrixColumn,
    OperationMatrixResponse,
    OperationMatrixRow,
)

router = APIRouter(prefix="/operations", tags=["operations"])

# Fixed column order for the per-fiche matrix view: Partie 1 (12) → Partie 2
# (13) → Contrôles (3). Operation names repeat across P1/P2, so the column key
# carries the partie too. Derived from the template, not the data, so the
# columns are stable and complete even if a fiche is missing a row.
_MATRIX_COLUMNS = [
    OperationMatrixColumn(key=f"1-{i + 1}", partie="1", ordre=i + 1, nom_operation=name)
    for i, name in enumerate(PARTIE_1_OPERATIONS)
] + [
    OperationMatrixColumn(key=f"2-{i + 1}", partie="2", ordre=i + 1, nom_operation=name)
    for i, name in enumerate(PARTIE_2_OPERATIONS)
] + [
    OperationMatrixColumn(key=f"controle-{i + 1}", partie="controle", ordre=i + 1, nom_operation=name)
    for i, name in enumerate(CONTROLE_ROWS)
]


def _to_item(o: OperationRow) -> OperationListItem:
    f = o.fiche
    return OperationListItem(
        operation_id=o.row_id,
        fiche_id=f.fiche_id,
        n_of=f.work_order.n_of,
        ref_produit=f.work_order.product.ref_produit,
        designation=f.work_order.product.designation,
        partie=o.partie.value,
        nom_operation=o.nom_operation,
        ordre=o.ordre,
        applicable=o.applicable,
        date_op=o.date_op.isoformat() if o.date_op else None,
        date_fin=o.date_fin.isoformat() if o.date_fin else None,
        heure_debut=o.heure_debut.isoformat() if o.heure_debut else None,
        heure_fin=o.heure_fin.isoformat() if o.heure_fin else None,
        qte_realisee=o.qte_realisee,
        outillage=o.outillage or (o.tool.libelle if o.tool else None),
        matricule_operateur=o.matricule or (o.operator.matricule if o.operator else None),
        type_controle=o.type_controle.value if o.type_controle else None,
        resultat=o.resultat,
        confidence=float(o.confidence) if o.confidence is not None else None,
        statut_revue=o.statut_revue.value if o.statut_revue else None,
    )


@router.get("", response_model=OperationListResponse)
def list_operations(
    db: Session = Depends(get_db),
    q: str | None = Query(None, description="Free text — matches N° OF or réf. produit"),
    n_of: str | None = None,
    ref_produit: str | None = None,
    matricule: str | None = None,
    partie: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> OperationListResponse:
    """Every operation/control row across every VALIDATED fiche, one row each.

    Scoped to statut == valide only: a fiche still in extrait/en_revue may
    carry an unreviewed VLM misread, so it isn't trustworthy enough to surface
    in a cross-fiche "full database" view.
    """
    base = (
        select(OperationRow)
        .join(OperationRow.fiche)
        .join(Fiche.work_order)
        .join(WorkOrder.product)
        .where(Fiche.statut == StatutFiche.valide)
    )
    if q:
        like = f"%{q}%"
        base = base.where(or_(Product.ref_produit.ilike(like), WorkOrder.n_of.ilike(like)))
    if n_of:
        base = base.where(WorkOrder.n_of.ilike(f"%{n_of}%"))
    if ref_produit:
        base = base.where(Product.ref_produit.ilike(f"%{ref_produit}%"))
    if partie:
        base = base.where(OperationRow.partie == Partie(partie))
    if matricule:
        base = base.where(OperationRow.matricule == matricule)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (
        db.scalars(
            base.options(
                joinedload(OperationRow.fiche).joinedload(Fiche.work_order).joinedload(WorkOrder.product),
                joinedload(OperationRow.tool),
                joinedload(OperationRow.operator),
            )
            .order_by(Fiche.date_creation.desc(), OperationRow.partie, OperationRow.ordre)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .unique()
        .all()
    )

    return OperationListResponse(
        total=total, page=page, page_size=page_size, items=[_to_item(o) for o in rows]
    )


@router.get("/matrix", response_model=OperationMatrixResponse)
def operations_matrix(
    db: Session = Depends(get_db),
    q: str | None = Query(None, description="Free text — matches N° OF or réf. produit"),
    n_of: str | None = None,
    ref_produit: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> OperationMatrixResponse:
    """Traceability matrix: one row per VALIDATED fiche, one column per operation
    (Partie 1/2 + controls), each cell the operator matricule that performed it.

    Same validated-only scope as the list view — only human-confirmed data
    belongs in a cross-fiche overview.
    """
    base = (
        select(Fiche)
        .join(Fiche.work_order)
        .join(WorkOrder.product)
        .where(Fiche.statut == StatutFiche.valide)
    )
    if q:
        like = f"%{q}%"
        base = base.where(or_(Product.ref_produit.ilike(like), WorkOrder.n_of.ilike(like)))
    if n_of:
        base = base.where(WorkOrder.n_of.ilike(f"%{n_of}%"))
    if ref_produit:
        base = base.where(Product.ref_produit.ilike(f"%{ref_produit}%"))

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    fiches = (
        db.scalars(
            base.options(
                joinedload(Fiche.work_order).joinedload(WorkOrder.product),
                selectinload(Fiche.rows),
            )
            .order_by(Fiche.date_creation.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .unique()
        .all()
    )

    rows = []
    for f in fiches:
        cells = {}
        for r in f.rows:
            # Omit truly-empty cells to keep the payload small — the UI renders
            # a missing key as a blank cell.
            if r.applicable is None and not r.heure_debut and not r.matricule and r.qte_realisee is None:
                continue
            cells[f"{r.partie.value}-{r.ordre}"] = OperationMatrixCell(
                applicable=r.applicable,
                heure_debut=r.heure_debut.isoformat()[:5] if r.heure_debut else None,
                heure_fin=r.heure_fin.isoformat()[:5] if r.heure_fin else None,
                matricule=r.matricule or (r.operator.matricule if r.operator else None),
                qte_realisee=r.qte_realisee,
            )

        raw = f.raw_extraction or {}
        qte = ((raw.get("header") or {}).get("qte") or {}).get("value")
        rows.append(
            OperationMatrixRow(
                fiche_id=f.fiche_id,
                n_of=f.work_order.n_of,
                ref_produit=f.work_order.product.ref_produit,
                designation=f.work_order.product.designation,
                qte=qte if qte is not None else f.work_order.quantite,
                date_creation=f.date_creation,
                cells=cells,
            )
        )

    return OperationMatrixResponse(
        columns=_MATRIX_COLUMNS, total=total, page=page, page_size=page_size, rows=rows
    )
