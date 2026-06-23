from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import StatutFiche


class Fiche(Base):
    __tablename__ = "fiches"

    fiche_id: Mapped[int] = mapped_column(primary_key=True)
    of_id: Mapped[int] = mapped_column(ForeignKey("work_orders.of_id"), nullable=False)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.scan_id"))
    statut: Mapped[StatutFiche] = mapped_column(
        Enum(StatutFiche, name="statut_fiche"), nullable=False, default=StatutFiche.extrait
    )
    date_creation: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128))
    raw_extraction: Mapped[dict | None] = mapped_column(JSONB)

    work_order: Mapped["WorkOrder"] = relationship(back_populates="fiches")
    scan: Mapped["Scan"] = relationship(back_populates="fiches")
    items: Mapped[list["Item"]] = relationship(back_populates="fiche", cascade="all, delete-orphan")
    operations: Mapped[list["Operation"]] = relationship(
        back_populates="fiche", cascade="all, delete-orphan"
    )
    controls: Mapped[list["Control"]] = relationship(
        back_populates="fiche", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list["AuditLog"]] = relationship(
        back_populates="fiche", cascade="all, delete-orphan"
    )
