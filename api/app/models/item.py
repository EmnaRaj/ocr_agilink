from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Item(Base):
    __tablename__ = "items"

    item_id: Mapped[int] = mapped_column(primary_key=True)
    fiche_id: Mapped[int] = mapped_column(ForeignKey("fiches.fiche_id"), nullable=False)
    numero_serie: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    fiche: Mapped["Fiche"] = relationship(back_populates="items")
