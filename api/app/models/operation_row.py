from datetime import date as date_, time

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import Methode, Partie, StatutRevue, TypeControle

# Native PG enum types. These now live ONLY on this table (the former
# operations/controls tables that used to define them were dropped), so the
# model itself owns their creation — create_all creates them on a fresh DB,
# and SQLAlchemy's checkfirst skips them when they already exist (the live DB,
# where the dropped tables had created them). The Alembic migration keeps
# create_type=False since it runs after the baseline already made them.
_PARTIE = Enum(Partie, name="partie")
_STATUT_REVUE = Enum(StatutRevue, name="statut_revue")
_TYPE_CONTROLE = Enum(TypeControle, name="type_controle")
_METHODE = Enum(Methode, name="methode")


class OperationRow(Base):
    """One row of a fiche's traceability table — an operation (Partie 1/2) OR a
    control (partie == controle), unified into a single, complete, queryable
    table. This is the source of truth for all analytics / reporting / the
    cross-fiche browse view.

    Lossless by design: every value the form carries is a typed column, and the
    per-field OCR provenance (confidence / raw text / source) that used to live
    only in the JSONB blob is kept in `field_meta` so QA can query it directly
    (e.g. "every low-confidence Sertissage matricule"). The raw `outillage` /
    `matricule` strings are stored verbatim alongside their resolved FKs, since
    most free-text outillage never matches the controlled tools list and would
    otherwise be dropped.
    """

    __tablename__ = "operation_rows"

    row_id: Mapped[int] = mapped_column(primary_key=True)
    fiche_id: Mapped[int] = mapped_column(ForeignKey("fiches.fiche_id"), nullable=False, index=True)

    # Row identity (stable across re-extractions — form geometry never changes).
    partie: Mapped[Partie] = mapped_column(_PARTIE, nullable=False, index=True)
    nom_operation: Mapped[str] = mapped_column(String(255), nullable=False)
    ordre: Mapped[int] = mapped_column(Integer(), nullable=False)

    # Shared TableRow values (operations and controls both have these).
    applicable: Mapped[bool | None] = mapped_column(Boolean())
    date_op: Mapped[date_ | None] = mapped_column(Date())
    date_fin: Mapped[date_ | None] = mapped_column(Date())  # set only if finished a later day
    heure_debut: Mapped[time | None] = mapped_column(Time())
    heure_fin: Mapped[time | None] = mapped_column(Time())
    qte_realisee: Mapped[int | None] = mapped_column(Integer())

    # Outillage / operator: keep BOTH the verbatim read and the resolved FK.
    outillage: Mapped[str | None] = mapped_column(String(255))
    tool_id: Mapped[int | None] = mapped_column(ForeignKey("tools.tool_id"))
    matricule: Mapped[str | None] = mapped_column(String(32), index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("operators.operator_id"))

    # Control-only columns (null for operations).
    type_controle: Mapped[TypeControle | None] = mapped_column(_TYPE_CONTROLE)
    methode: Mapped[Methode | None] = mapped_column(_METHODE)
    resultat: Mapped[bool | None] = mapped_column(Boolean())

    # Per-field provenance: {field_name: {confidence, raw_text, source}}.
    field_meta: Mapped[dict | None] = mapped_column(JSONB)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    statut_revue: Mapped[StatutRevue | None] = mapped_column(_STATUT_REVUE)

    fiche: Mapped["Fiche"] = relationship(back_populates="rows")
    tool: Mapped["Tool | None"] = relationship()
    operator: Mapped["Operator | None"] = relationship()

    @property
    def is_control(self) -> bool:
        return self.partie == Partie.controle
