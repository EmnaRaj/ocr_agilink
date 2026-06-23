"""API response schemas for the Fiches Suiveuses UI."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class FicheListItem(BaseModel):
    fiche_id: int
    ref_produit: str
    designation: str | None
    n_of: str
    quantite: int | None
    date_creation: datetime
    statut: str
    overall_confidence: float | None
    n_items: int
    n_operations: int
    has_scan: bool


class FicheListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[FicheListItem]


class ProductRef(BaseModel):
    product_id: int
    ref_produit: str
    designation: str | None


class WorkOrderRef(BaseModel):
    of_id: int
    n_of: str
    quantite: int | None


class ScanRef(BaseModel):
    scan_id: int
    uploaded_at: datetime
    page_index: int = 0
    n_pages: int = 1


class ValidationIssueOut(BaseModel):
    scope: str
    location: str
    field: str
    level: str
    code: str
    message: str


class FicheDetail(BaseModel):
    fiche_id: int
    statut: str
    date_creation: datetime
    created_by: str | None
    overall_confidence: float | None
    product: ProductRef
    work_order: WorkOrderRef
    scan: ScanRef | None
    # Full extraction payload (header / operations / controls / items / meta),
    # exactly as produced by the pipeline — the UI renders it field by field.
    extraction: dict[str, Any] | None
    validation: list[ValidationIssueOut]


class StatutBreakdown(BaseModel):
    extrait: int = 0
    en_revue: int = 0
    valide: int = 0


class StatsResponse(BaseModel):
    total_fiches: int
    total_products: int
    total_work_orders: int
    scanned_today: int
    avg_confidence: float | None
    by_statut: StatutBreakdown
    recent: list[FicheListItem]
