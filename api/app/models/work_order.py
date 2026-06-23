from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class WorkOrder(Base):
    __tablename__ = "work_orders"

    of_id: Mapped[int] = mapped_column(primary_key=True)
    n_of: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"), nullable=False)
    quantite: Mapped[int | None] = mapped_column()
    statut: Mapped[str | None] = mapped_column(String(32))

    product: Mapped["Product"] = relationship(back_populates="work_orders")
    fiches: Mapped[list["Fiche"]] = relationship(back_populates="work_order")
