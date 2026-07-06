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
    auto_validated: bool = False
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


class OperationListItem(BaseModel):
    operation_id: int
    fiche_id: int
    n_of: str
    ref_produit: str
    designation: str | None
    partie: str
    nom_operation: str
    ordre: int
    applicable: bool | None
    date_op: str | None
    date_fin: str | None
    heure_debut: str | None
    heure_fin: str | None
    qte_realisee: int | None
    outillage: str | None
    matricule_operateur: str | None
    type_controle: str | None
    resultat: bool | None
    confidence: float | None
    statut_revue: str | None


class OperationListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[OperationListItem]


class OperationMatrixColumn(BaseModel):
    key: str            # "{partie}-{ordre}", e.g. "1-4"
    partie: str         # "1" | "2" | "controle"
    ordre: int
    nom_operation: str


class OperationMatrixCell(BaseModel):
    applicable: bool | None = None
    heure_debut: str | None = None   # "HH:MM"
    heure_fin: str | None = None     # "HH:MM"
    matricule: str | None = None
    qte_realisee: int | None = None


class OperationMatrixRow(BaseModel):
    fiche_id: int
    n_of: str
    ref_produit: str
    designation: str | None
    qte: int | None
    date_creation: datetime
    # column key -> what happened for that operation on this fiche. Empty
    # operations are omitted (treated as blank by the UI).
    cells: dict[str, OperationMatrixCell]


class OperationMatrixResponse(BaseModel):
    columns: list[OperationMatrixColumn]
    total: int
    page: int
    page_size: int
    rows: list[OperationMatrixRow]


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
