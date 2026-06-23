from datetime import date as date_, time

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import Partie, StatutRevue


class Operation(Base):
    __tablename__ = "operations"

    operation_id: Mapped[int] = mapped_column(primary_key=True)
    fiche_id: Mapped[int] = mapped_column(ForeignKey("fiches.fiche_id"), nullable=False)
    partie: Mapped[Partie] = mapped_column(Enum(Partie, name="partie"), nullable=False)
    nom_operation: Mapped[str] = mapped_column(String(255), nullable=False)
    ordre: Mapped[int] = mapped_column(Integer(), nullable=False)

    applicable: Mapped[bool | None] = mapped_column(Boolean())
    date_op: Mapped[date_ | None] = mapped_column(Date())
    # Set only when the operation finished on a later day than it started.
    date_fin: Mapped[date_ | None] = mapped_column(Date())
    heure_debut: Mapped[time | None] = mapped_column(Time())
    heure_fin: Mapped[time | None] = mapped_column(Time())
    qte_realisee: Mapped[int | None] = mapped_column(Integer())

    tool_id: Mapped[int | None] = mapped_column(ForeignKey("tools.tool_id"))
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("operators.operator_id"))

    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    statut_revue: Mapped[StatutRevue | None] = mapped_column(Enum(StatutRevue, name="statut_revue"))

    fiche: Mapped["Fiche"] = relationship(back_populates="operations")
    tool: Mapped["Tool | None"] = relationship()
    operator: Mapped["Operator | None"] = relationship()
