"""Seed reference data: operators and tools.

These are placeholder values taken from the sample filled sheet
(docs/fixtures/sample_filled_sheet.pdf) so the validation rule "matricule is
a known operator" can be exercised in Phase 1 against that fixture. Replace
with Agilink's real operator roster and tool list before going live.

The fixed operation lists (Partie 1/2/Contrôle) are NOT seeded as DB rows —
there is no operation_definitions table in the data model. They live as a
single source of truth in packages/fiche_schema/fiche_schema/operations.py
and are used to build each fiche's operation rows at extraction time.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))

from app.db import SessionLocal  # noqa: E402
from app.models import Operator, Tool  # noqa: E402

SEED_OPERATORS = [
    ("330", None),
    ("350", None),
    ("164", None),
    ("390", None),
    ("338", None),
]

SEED_TOOLS = [
    ("MANUEL", "Manuel"),
    ("MACHINE", "Machine"),
    ("PINCE_SERTIR", "Pince à sertir"),
]


def seed() -> None:
    db = SessionLocal()
    try:
        new_operators = 0
        for matricule, nom in SEED_OPERATORS:
            if not db.query(Operator).filter_by(matricule=matricule).first():
                db.add(Operator(matricule=matricule, nom=nom))
                new_operators += 1

        new_tools = 0
        for code, libelle in SEED_TOOLS:
            if not db.query(Tool).filter_by(code_outillage=code).first():
                db.add(Tool(code_outillage=code, libelle=libelle))
                new_tools += 1

        db.commit()
        print(f"Seeded {new_operators} new operators, {new_tools} new tools.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
