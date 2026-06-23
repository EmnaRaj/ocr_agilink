from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Scan(Base):
    __tablename__ = "scans"

    scan_id: Mapped[int] = mapped_column(primary_key=True)
    storage_url: Mapped[str] = mapped_column(String(512), nullable=False)
    dpi: Mapped[int | None] = mapped_column(Integer())
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    fiches: Mapped[list["Fiche"]] = relationship(back_populates="scan")
