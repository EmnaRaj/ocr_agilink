from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Operator(Base):
    __tablename__ = "operators"

    operator_id: Mapped[int] = mapped_column(primary_key=True)
    matricule: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    nom: Mapped[str | None] = mapped_column(String(128))
