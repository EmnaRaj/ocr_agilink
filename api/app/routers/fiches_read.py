from datetime import datetime, timezone

import pymupdf
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..db import get_db
from ..models import Fiche, Product, StatutFiche, WorkOrder
from ..schemas import (
    FicheDetail,
    FicheListItem,
    FicheListResponse,
    ProductRef,
    ScanRef,
    WorkOrderRef,
)
from ..services import export as export_svc
from ..services.storage import download_scan

router = APIRouter(prefix="/fiches", tags=["fiches"])

_EXPORTERS = {
    "xlsx": (export_svc.to_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "pdf": (export_svc.to_pdf, "application/pdf"),
    "csv": (export_svc.to_csv, "text/csv; charset=utf-8"),
}


def _overall_confidence(fiche: Fiche) -> float | None:
    meta = (fiche.raw_extraction or {}).get("meta") or {}
    return meta.get("overall_confidence")


def _header_ref(f: Fiche) -> str:
    """Prefer the (possibly user-corrected) ref in the extraction over the product."""
    hv = (((f.raw_extraction or {}).get("header") or {}).get("ref_produit") or {}).get("value")
    return hv or f.work_order.product.ref_produit


def _to_list_item(f: Fiche) -> FicheListItem:
    return FicheListItem(
        fiche_id=f.fiche_id,
        ref_produit=_header_ref(f),
        designation=f.work_order.product.designation,
        n_of=f.work_order.n_of,
        quantite=f.work_order.quantite,
        date_creation=f.date_creation,
        statut=f.statut.value,
        overall_confidence=_overall_confidence(f),
        n_items=len(f.items),
        n_operations=sum(1 for o in f.operations if o.applicable is not None),
        has_scan=f.scan_id is not None,
    )


def _loaded(stmt):
    return stmt.options(
        joinedload(Fiche.work_order).joinedload(WorkOrder.product),
        selectinload(Fiche.items),
        selectinload(Fiche.operations),
    )


@router.get("", response_model=FicheListResponse)
def list_fiches(
    db: Session = Depends(get_db),
    q: str | None = Query(None, description="Free text — matches ref produit or N° OF"),
    ref_produit: str | None = None,
    n_of: str | None = None,
    statut: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> FicheListResponse:
    base = select(Fiche).join(Fiche.work_order).join(WorkOrder.product)
    if q:
        like = f"%{q}%"
        base = base.where(or_(Product.ref_produit.ilike(like), WorkOrder.n_of.ilike(like)))
    if ref_produit:
        base = base.where(Product.ref_produit.ilike(f"%{ref_produit}%"))
    if n_of:
        base = base.where(WorkOrder.n_of.ilike(f"%{n_of}%"))
    if statut:
        base = base.where(Fiche.statut == StatutFiche(statut))
    if date_from:
        base = base.where(Fiche.date_creation >= date_from)
    if date_to:
        base = base.where(Fiche.date_creation <= date_to)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        _loaded(base).order_by(Fiche.date_creation.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()

    return FicheListResponse(
        total=total, page=page, page_size=page_size, items=[_to_list_item(f) for f in rows]
    )


@router.get("/{fiche_id}", response_model=FicheDetail)
def get_fiche(fiche_id: int, db: Session = Depends(get_db)) -> FicheDetail:
    fiche = db.scalars(_loaded(select(Fiche).where(Fiche.fiche_id == fiche_id))).unique().first()
    if fiche is None:
        raise HTTPException(404, f"Fiche {fiche_id} not found")
    wo = fiche.work_order
    return FicheDetail(
        fiche_id=fiche.fiche_id,
        statut=fiche.statut.value,
        date_creation=fiche.date_creation,
        created_by=fiche.created_by,
        overall_confidence=_overall_confidence(fiche),
        product=ProductRef(
            product_id=wo.product.product_id,
            ref_produit=wo.product.ref_produit,
            designation=wo.product.designation,
        ),
        work_order=WorkOrderRef(of_id=wo.of_id, n_of=wo.n_of, quantite=wo.quantite),
        scan=ScanRef(
            scan_id=fiche.scan.scan_id,
            uploaded_at=fiche.scan.uploaded_at,
            page_index=fiche.page_index,
            n_pages=fiche.scan.n_pages,
        )
        if fiche.scan
        else None,
        extraction=fiche.raw_extraction,
        validation=(fiche.raw_extraction or {}).get("validation", []),
    )


@router.get("/{fiche_id}/scan")
def get_fiche_scan(fiche_id: int, db: Session = Depends(get_db)) -> Response:
    """Serve the original scan as a browser-viewable image (PDF → first page JPEG)."""
    fiche = db.get(Fiche, fiche_id)
    if fiche is None or fiche.scan is None:
        raise HTTPException(404, "No scan for this fiche")
    data, ctype = download_scan(fiche.scan.storage_url)
    if ctype == "application/pdf" or fiche.scan.storage_url.lower().endswith(".pdf"):
        doc = pymupdf.open(stream=data, filetype="pdf")
        idx = min(max(fiche.page_index, 0), doc.page_count - 1)  # this fiche's own page
        page = doc.load_page(idx)
        if fiche.rotation:  # show it upright, same as the extractor saw it
            page.set_rotation((page.rotation + fiche.rotation) % 360)
        zoom = min(2200 / max(page.rect.width, page.rect.height), 4.0)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        data, ctype = pix.tobytes("jpeg", jpg_quality=85), "image/jpeg"
    return Response(content=data, media_type=ctype, headers={"Cache-Control": "private, max-age=3600"})


class FicheUpdate(BaseModel):
    extraction: dict
    validate: bool = False


@router.put("/{fiche_id}")
def update_fiche(fiche_id: int, payload: FicheUpdate, db: Session = Depends(get_db)) -> dict:
    """Save user corrections to the extracted data, and optionally validate the fiche.

    Validating clears the review flags, marks it human-validated (confidence 1.0)
    and moves it to statut 'valide' — the clean, confirmed record.
    """
    fiche = db.get(Fiche, fiche_id)
    if fiche is None:
        raise HTTPException(404, f"Fiche {fiche_id} not found")

    ex = dict(payload.extraction)
    meta = dict(ex.get("meta") or {})
    if payload.validate:
        ex["validation"] = []
        meta["validated"] = True
        meta["overall_confidence"] = 1.0
        fiche.statut = StatutFiche.valide
    else:
        fiche.statut = StatutFiche.en_revue
    ex["meta"] = meta
    fiche.raw_extraction = ex  # reassigning a new dict marks the JSONB column dirty
    db.commit()
    return {"ok": True, "fiche_id": fiche_id, "statut": fiche.statut.value}


@router.get("/{fiche_id}/export")
def export_fiche(fiche_id: int, format: str = "xlsx", db: Session = Depends(get_db)) -> Response:
    """Download the extracted fiche as Excel (xlsx), PDF, or CSV."""
    fmt = format.lower()
    if fmt not in _EXPORTERS:
        raise HTTPException(400, "format must be one of: xlsx, pdf, csv")
    fiche = db.scalars(_loaded(select(Fiche).where(Fiche.fiche_id == fiche_id))).unique().first()
    if fiche is None:
        raise HTTPException(404, f"Fiche {fiche_id} not found")
    build, media = _EXPORTERS[fmt]
    data = build(fiche)
    filename = f"{export_svc.file_stem(fiche)}.{fmt}"
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
