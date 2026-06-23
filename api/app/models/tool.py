from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Tool(Base):
    __tablename__ = "tools"

    tool_id: Mapped[int] = mapped_column(primary_key=True)
    code_outillage: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    libelle: Mapped[str | None] = mapped_column(String(128))
