from sqlalchemy import Boolean, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .enums import Methode, TypeControle


class Control(Base):
    __tablename__ = "controls"

    control_id: Mapped[int] = mapped_column(primary_key=True)
    fiche_id: Mapped[int] = mapped_column(ForeignKey("fiches.fiche_id"), nullable=False)
    type_controle: Mapped[TypeControle] = mapped_column(
        Enum(TypeControle, name="type_controle"), nullable=False
    )
    # Only meaningful for type_controle == controle_electrique.
    methode: Mapped[Methode | None] = mapped_column(Enum(Methode, name="methode"))
    resultat: Mapped[bool | None] = mapped_column(Boolean())
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("operators.operator_id"))

    fiche: Mapped["Fiche"] = relationship(back_populates="controls")
    operator: Mapped["Operator | None"] = relationship()
