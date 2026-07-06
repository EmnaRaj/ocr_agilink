from datetime import datetime, timezone

import pymupdf
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from fiche_schema import is_auto_validatable, merge_extraction

from ..db import get_db
from ..models import Fiche, Partie, Product, StatutFiche, WorkOrder
from ..schemas import (
    FicheDetail,
    FicheListItem,
    FicheListResponse,
    ProductRef,
    ScanRef,
    WorkOrderRef,
)
from ..services import export as export_svc
from ..services.ingest import diff_extraction, resync_fiche, save_correction
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
        auto_validated=bool(((f.raw_extraction or {}).get("meta") or {}).get("auto_validated")),
        overall_confidence=_overall_confidence(f),
        n_items=len(f.items),
        n_operations=sum(
            1 for o in f.rows if o.partie != Partie.controle and o.applicable is not None
        ),
        has_scan=f.scan_id is not None,
    )


def _loaded(stmt):
    return stmt.options(
        joinedload(Fiche.work_order).joinedload(WorkOrder.product),
        selectinload(Fiche.items),
        selectinload(Fiche.rows),
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
    archived: bool = Query(False, description="False = active fiches (default), True = archived only"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> FicheListResponse:
    base = select(Fiche).join(Fiche.work_order).join(WorkOrder.product).where(Fiche.archived == archived)
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

    Both paths re-run the deterministic checks against the corrected data and
    re-sync the relational Operation/Control/Item rows (so analytics/exports
    reflect the correction, not the original misread). Validating sets
    overall_confidence to 1.0 and moves the fiche to statut 'valide', but
    deliberately does NOT blank out remaining structural flags (e.g. a
    matricule outlier the human didn't actually change) — a flag on a
    validated fiche means "confirmed, but still worth a second look", not
    "definitely wrong". Validating also promotes any matricule on the fiche
    into the known-operator registry (find_or_create_operator), since it's
    now human-confirmed.
    """
    fiche = db.get(Fiche, fiche_id)
    if fiche is None:
        raise HTTPException(404, f"Fiche {fiche_id} not found")
    old_extraction = fiche.raw_extraction or {}

    ex = dict(payload.extraction)
    meta = dict(ex.get("meta") or {})
    # merge_extraction (not a strict FicheExtraction.model_validate) so a
    # human-typed correction gets the same lenient parsing as a VLM read —
    # pydantic's native time/date parser rejects perfectly normal input like
    # "8:30" (no leading zero) or "13h30"; a single bad cell degrades to
    # null+raw_text instead of rejecting the whole save.
    try:
        extraction = merge_extraction(ex, model_name=meta.get("model_name") or "human", processing_ms=meta.get("processing_ms"))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(400, f"Extraction invalide: {exc}") from exc

    # Audited regardless of validate: an "automation rate" KPI needs to know
    # whether ANY save on this fiche ever touched a value, not just whether
    # the final validate click did.
    db.add_all(diff_extraction(fiche, old_extraction, extraction))

    if payload.validate:
        meta["validated"] = True
        meta["overall_confidence"] = 1.0
        fiche.statut = StatutFiche.valide
        issues = resync_fiche(db, fiche, extraction)
    else:
        issues = save_correction(db, fiche, extraction)
        # Dynamic re-check: a correction that clears every BLOCKING alert (e.g.
        # the reviewer just typed in the N° OF that was the lone error) validates
        # the fiche on the spot — no separate "Valider" click needed. Remaining
        # soft/advisory flags never block. If blockers remain, stay in review.
        if is_auto_validatable(extraction, issues, 0.0):
            meta["validated"] = True
            meta["validated_via"] = "edit"
            meta["overall_confidence"] = 1.0
            fiche.statut = StatutFiche.valide
        else:
            fiche.statut = StatutFiche.en_revue

    ex["validation"] = [i.model_dump() for i in issues]
    ex["meta"] = meta
    fiche.raw_extraction = ex  # reassigning a new dict marks the JSONB column dirty
    db.commit()
    return {"ok": True, "fiche_id": fiche_id, "statut": fiche.statut.value}


@router.delete("/{fiche_id}")
def delete_fiche(fiche_id: int, db: Session = Depends(get_db)) -> dict:
    """Permanently delete a fiche and its operations/controls/items (cascade).

    Leaves the WorkOrder/Product and the underlying Scan/MinIO file alone —
    other fiches (other pages of the same multi-page scan, or sharing the
    same work order) may still reference them. Deleting frees up this page's
    (scan_id, page_index) slot, so re-running a batch on that scan will
    re-extract it instead of skipping it as already-filed.
    """
    fiche = db.get(Fiche, fiche_id)
    if fiche is None:
        raise HTTPException(404, f"Fiche {fiche_id} not found")
    db.delete(fiche)
    db.commit()
    return {"ok": True, "fiche_id": fiche_id}


class FicheIds(BaseModel):
    ids: list[int]


class ArchiveRequest(FicheIds):
    archived: bool = True


class ResolveAlert(BaseModel):
    key: str
    resolved: bool = True


def _alert_key(i: dict) -> str:
    """Stable identifier for one coherence alert (must match the frontend's)."""
    return "|".join(str(i.get(k, "")) for k in ("scope", "location", "field", "code"))


@router.post("/{fiche_id}/resolve-alert")
def resolve_alert(fiche_id: int, payload: ResolveAlert, db: Session = Depends(get_db)) -> dict:
    """Mark one coherence alert as reviewed (confirmed/ignored) by a human, or
    un-mark it. When EVERY alert on the fiche is resolved, the fiche is validated
    (human-confirmed). Re-opening an alert on such a fiche sends it back to review.
    This lets a reviewer clear false-positives one by one straight from the sheet.
    """
    fiche = db.get(Fiche, fiche_id)
    if fiche is None:
        raise HTTPException(404, f"Fiche {fiche_id} not found")
    raw = dict(fiche.raw_extraction or {})
    meta = dict(raw.get("meta") or {})
    alerts = raw.get("validation") or []
    all_keys = {_alert_key(i) for i in alerts}
    # ERROR-level alerts (missing/invalid OF, ref…) are structural — they can't be
    # dismissed by confirm/ignore, only fixed by editing the data. Only WARNING
    # alerts are "resolvable" here.
    errors_present = any(i.get("level") == "error" for i in alerts)
    warning_keys = {_alert_key(i) for i in alerts if i.get("level") != "error"}
    resolved = set(meta.get("resolved_alerts") or [])
    if payload.resolved:
        resolved.add(payload.key)
    else:
        resolved.discard(payload.key)
    resolved &= all_keys  # drop stale keys from older validation runs
    meta["resolved_alerts"] = sorted(resolved)

    all_resolved = (not errors_present) and (warning_keys <= resolved)
    if all_resolved:
        fiche.statut = StatutFiche.valide
        meta["validated"] = True
        meta["validated_via"] = "alerts"
        meta.pop("auto_validated", None)
        meta["overall_confidence"] = 1.0
    elif meta.get("validated_via") == "alerts" and fiche.statut == StatutFiche.valide:
        # a previously alert-validated fiche had an alert re-opened → back to review
        fiche.statut = StatutFiche.en_revue
        meta.pop("validated", None)
        meta.pop("validated_via", None)
    raw["meta"] = meta
    fiche.raw_extraction = raw
    db.commit()
    return {
        "ok": True,
        "resolved": len(resolved),
        "total": len(warning_keys),
        "all_resolved": all_resolved,
        "statut": fiche.statut.value,
    }


@router.post("/bulk-delete")
def bulk_delete(payload: FicheIds, db: Session = Depends(get_db)) -> dict:
    """Permanently delete several fiches at once (same cascade as single delete)."""
    n = 0
    for fiche in db.query(Fiche).filter(Fiche.fiche_id.in_(payload.ids)).all():
        db.delete(fiche)
        n += 1
    db.commit()
    return {"ok": True, "deleted": n}


@router.post("/bulk-archive")
def bulk_archive(payload: ArchiveRequest, db: Session = Depends(get_db)) -> dict:
    """Archive (or restore) several fiches — soft-hide from the default history
    without deleting the data."""
    n = (
        db.query(Fiche)
        .filter(Fiche.fiche_id.in_(payload.ids))
        .update({Fiche.archived: payload.archived}, synchronize_session=False)
    )
    db.commit()
    return {"ok": True, "archived": payload.archived, "count": n}


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
