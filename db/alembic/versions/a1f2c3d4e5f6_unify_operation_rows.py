"""unify operations + controls into operation_rows

Replaces the separate `operations` and `controls` tables with a single,
complete `operation_rows` table (the source of truth for analytics / reporting
/ the cross-fiche browse view). It keeps every value the form carries, the
verbatim outillage/matricule strings alongside their resolved FKs, and the
per-field OCR provenance in `field_meta`.

NOTE: on the existing dev volume this was applied via
`app.scripts.backfill_operation_rows` (which also backfills from each fiche's
raw_extraction), because that volume is ahead of the baseline. This migration
is the equivalent for a fresh deploy; it does NOT backfill data.

Revision ID: a1f2c3d4e5f6
Revises: 0bd9fd9ff567
Create Date: 2026-06-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1f2c3d4e5f6"
down_revision: Union[str, None] = "0bd9fd9ff567"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reuse the existing native enum types (created by the baseline) — never
# re-CREATE TYPE, or the migration fails on an already-populated DB.
_partie = postgresql.ENUM("p1", "p2", "controle", name="partie", create_type=False)
_statut_revue = postgresql.ENUM("auto", "a_revoir", "corrige", name="statut_revue", create_type=False)
_type_controle = postgresql.ENUM(
    "controle_electrique", "controle_final", "correspondance_serie", name="type_controle", create_type=False
)
_methode = postgresql.ENUM("manuel", "banc_de_test", name="methode", create_type=False)


def upgrade() -> None:
    op.create_table(
        "operation_rows",
        sa.Column("row_id", sa.Integer(), nullable=False),
        sa.Column("fiche_id", sa.Integer(), nullable=False),
        sa.Column("partie", _partie, nullable=False),
        sa.Column("nom_operation", sa.String(length=255), nullable=False),
        sa.Column("ordre", sa.Integer(), nullable=False),
        sa.Column("applicable", sa.Boolean(), nullable=True),
        sa.Column("date_op", sa.Date(), nullable=True),
        sa.Column("date_fin", sa.Date(), nullable=True),
        sa.Column("heure_debut", sa.Time(), nullable=True),
        sa.Column("heure_fin", sa.Time(), nullable=True),
        sa.Column("qte_realisee", sa.Integer(), nullable=True),
        sa.Column("outillage", sa.String(length=255), nullable=True),
        sa.Column("tool_id", sa.Integer(), nullable=True),
        sa.Column("matricule", sa.String(length=32), nullable=True),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column("type_controle", _type_controle, nullable=True),
        sa.Column("methode", _methode, nullable=True),
        sa.Column("resultat", sa.Boolean(), nullable=True),
        sa.Column("field_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("statut_revue", _statut_revue, nullable=True),
        sa.ForeignKeyConstraint(["fiche_id"], ["fiches.fiche_id"]),
        sa.ForeignKeyConstraint(["operator_id"], ["operators.operator_id"]),
        sa.ForeignKeyConstraint(["tool_id"], ["tools.tool_id"]),
        sa.PrimaryKeyConstraint("row_id"),
    )
    op.create_index(op.f("ix_operation_rows_fiche_id"), "operation_rows", ["fiche_id"])
    op.create_index(op.f("ix_operation_rows_partie"), "operation_rows", ["partie"])
    op.create_index(op.f("ix_operation_rows_matricule"), "operation_rows", ["matricule"])

    op.drop_table("controls")
    op.drop_table("operations")


def downgrade() -> None:
    op.create_table(
        "operations",
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("fiche_id", sa.Integer(), nullable=False),
        sa.Column("partie", _partie, nullable=False),
        sa.Column("nom_operation", sa.String(length=255), nullable=False),
        sa.Column("ordre", sa.Integer(), nullable=False),
        sa.Column("applicable", sa.Boolean(), nullable=True),
        sa.Column("date_op", sa.Date(), nullable=True),
        sa.Column("date_fin", sa.Date(), nullable=True),
        sa.Column("heure_debut", sa.Time(), nullable=True),
        sa.Column("heure_fin", sa.Time(), nullable=True),
        sa.Column("qte_realisee", sa.Integer(), nullable=True),
        sa.Column("tool_id", sa.Integer(), nullable=True),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("statut_revue", _statut_revue, nullable=True),
        sa.ForeignKeyConstraint(["fiche_id"], ["fiches.fiche_id"]),
        sa.ForeignKeyConstraint(["operator_id"], ["operators.operator_id"]),
        sa.ForeignKeyConstraint(["tool_id"], ["tools.tool_id"]),
        sa.PrimaryKeyConstraint("operation_id"),
    )
    op.create_table(
        "controls",
        sa.Column("control_id", sa.Integer(), nullable=False),
        sa.Column("fiche_id", sa.Integer(), nullable=False),
        sa.Column("type_controle", _type_controle, nullable=False),
        sa.Column("methode", _methode, nullable=True),
        sa.Column("resultat", sa.Boolean(), nullable=True),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["fiche_id"], ["fiches.fiche_id"]),
        sa.ForeignKeyConstraint(["operator_id"], ["operators.operator_id"]),
        sa.PrimaryKeyConstraint("control_id"),
    )
    op.drop_index(op.f("ix_operation_rows_matricule"), table_name="operation_rows")
    op.drop_index(op.f("ix_operation_rows_partie"), table_name="operation_rows")
    op.drop_index(op.f("ix_operation_rows_fiche_id"), table_name="operation_rows")
    op.drop_table("operation_rows")
