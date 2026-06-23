from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(primary_key=True)
    ref_produit: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    designation: Mapped[str | None] = mapped_column(String(255))

    work_orders: Mapped[list["WorkOrder"]] = relationship(back_populates="product")
