from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import StatutFiche


class Fiche(Base):
    __tablename__ = "fiches"
    # One fiche per page of a scan — guards against duplicate inserts if a
    # durable batch task is redelivered (crash recovery / at-least-once).
    __table_args__ = (UniqueConstraint("scan_id", "page_index", name="uq_fiche_scan_page"),)

    fiche_id: Mapped[int] = mapped_column(primary_key=True)
    of_id: Mapped[int] = mapped_column(ForeignKey("work_orders.of_id"), nullable=False)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.scan_id"))
    # Which page of the (possibly multi-fiche) source scan this fiche came from.
    page_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Clockwise degrees (0/90/180/270) applied to upright the scan before
    # extraction; the viewer re-applies it so the page is shown the right way up.
    rotation: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    statut: Mapped[StatutFiche] = mapped_column(
        Enum(StatutFiche, name="statut_fiche"), nullable=False, default=StatutFiche.extrait
    )
    date_creation: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128))
    raw_extraction: Mapped[dict | None] = mapped_column(JSONB)
    # Soft-archive: hidden from the default history list but not deleted.
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    work_order: Mapped["WorkOrder"] = relationship(back_populates="fiches")
    scan: Mapped["Scan"] = relationship(back_populates="fiches")
    items: Mapped[list["Item"]] = relationship(back_populates="fiche", cascade="all, delete-orphan")
    # Unified operation + control rows (see models/operation_row.py). This is the
    # source of truth for analytics / reporting / the cross-fiche browse view.
    rows: Mapped[list["OperationRow"]] = relationship(
        back_populates="fiche", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list["AuditLog"]] = relationship(
        back_populates="fiche", cascade="all, delete-orphan"
    )
