from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Scan(Base):
    __tablename__ = "scans"

    scan_id: Mapped[int] = mapped_column(primary_key=True)
    storage_url: Mapped[str] = mapped_column(String(512), nullable=False)
    dpi: Mapped[int | None] = mapped_column(Integer())
    # A single uploaded file can hold many fiches (one per page).
    n_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # Provenance: "manual" (API upload), "sharepoint" or "local" (auto-ingest).
    # external_id/external_etag are the SharePoint driveItem id + eTag, used to
    # skip a file we've already pulled even if the delta feed replays it.
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual", server_default="manual")
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    external_etag: Mapped[str | None] = mapped_column(String(255))

    # Batch lifecycle: "processing" -> "done" | "error" | "stopped". Lets the UI
    # show progress and offer stop/cancel, and lets a failed/partial scan be
    # retried instead of being blocked as a duplicate. task_id is the Celery id
    # of the batch job, so it can be revoked on stop.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing", server_default="processing")
    task_id: Mapped[str | None] = mapped_column(String(64))
    # Original file name (for the monitoring view — the storage key is a hash).
    original_name: Mapped[str | None] = mapped_column(String(255))

    fiches: Mapped[list["Fiche"]] = relationship(back_populates="scan")
