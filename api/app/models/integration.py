from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class IntegrationState(Base):
    """Tiny key/value store for external-integration cursors — e.g. the
    SharePoint Graph `delta` link, so each poll only fetches what changed since
    the last one. One row per key."""

    __tablename__ = "integration_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
