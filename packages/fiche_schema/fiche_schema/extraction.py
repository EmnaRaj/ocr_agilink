"""Canonical extraction schema for the Fiche Suiveuse.

Imported by the worker (VLM prompt + guided JSON), the validation gate, and
the API (persistence + response payloads) — written once, used everywhere.
"""

from __future__ import annotations

from datetime import date, time
from enum import Enum
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ExtractedField(BaseModel, Generic[T]):
    """A single extracted value with provenance and confidence."""

    value: Optional[T] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    raw_text: Optional[str] = None
    source: Optional[str] = None  # vlm | doctr | opencv | human


class Partie(str, Enum):
    p1 = "1"
    p2 = "2"
    controle = "controle"


class Methode(str, Enum):
    manuel = "manuel"
    banc_de_test = "banc_de_test"


class TypeControle(str, Enum):
    electrique = "controle_electrique"
    final = "controle_final"
    correspondance_serie = "correspondance_serie"


class FicheHeader(BaseModel):
    ref_produit: ExtractedField[str]
    n_of: ExtractedField[str]
    qte: ExtractedField[int]
    # Free-form header note seen on real sheets (e.g. a serial range like
    # "2770 -> 2783") that isn't one of the three defined header fields.
    annotation_serie: Optional[ExtractedField[str]] = None


class Item(BaseModel):
    """One per physical part traced by the sheet (<= header qte)."""

    numero_serie: ExtractedField[str]


class TableRow(BaseModel):
    partie: Partie
    nom_operation: str
    ordre: int
    applicable: ExtractedField[Optional[bool]]  # Oui=True, blank=None
    date_op: ExtractedField[Optional[date]]
    date_fin: ExtractedField[Optional[date]]  # set only if finished a later day
    heure_debut: ExtractedField[Optional[time]]
    heure_fin: ExtractedField[Optional[time]]
    qte_realisee: ExtractedField[Optional[int]]
    outillage: ExtractedField[Optional[str]]
    matricule_operateur: ExtractedField[Optional[str]]


class OperationRow(TableRow):
    """partie in {p1, p2}."""


class ControlRow(TableRow):
    """partie == controle."""

    type_controle: TypeControle
    methode: ExtractedField[Optional[Methode]] = Field(
        default_factory=lambda: ExtractedField[Optional[Methode]]()
    )
    resultat: ExtractedField[Optional[bool]] = Field(
        default_factory=lambda: ExtractedField[Optional[bool]]()
    )


class ExtractionMeta(BaseModel):
    model_name: str
    schema_version: str = "1.0"
    overall_confidence: float = Field(0.0, ge=0.0, le=1.0)
    processing_ms: Optional[int] = None


class FicheExtraction(BaseModel):
    header: FicheHeader
    operations: list[OperationRow]  # 25 rows: Partie 1 (12) + Partie 2 (13)
    controls: list[ControlRow]  # 3 rows
    items: list[Item]
    meta: ExtractionMeta
