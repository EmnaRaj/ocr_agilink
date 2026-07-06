"""SharePoint auto-ingest: scan provenance + delta-cursor store

Adds `source`/`external_id`/`external_etag` to `scans` (so a SharePoint-pulled
file is deduped by its driveItem id+eTag and marked distinct from a manual
upload), and an `integration_state` key/value table holding the Graph `delta`
cursor so each poll is incremental.

Revision ID: b2c3d4e5f6a7
Revises: a1f2c3d4e5f6
Create Date: 2026-07-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1f2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scans",
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
    )
    op.add_column("scans", sa.Column("external_id", sa.String(255), nullable=True))
    op.add_column("scans", sa.Column("external_etag", sa.String(255), nullable=True))
    op.create_index("ix_scans_external_id", "scans", ["external_id"])
    # Batch lifecycle (progress + stop/cancel + retry-of-failed).
    op.add_column(
        "scans",
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
    )
    op.add_column("scans", sa.Column("task_id", sa.String(64), nullable=True))
    op.add_column("scans", sa.Column("original_name", sa.String(255), nullable=True))

    op.create_table(
        "integration_state",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("integration_state")
    op.drop_column("scans", "original_name")
    op.drop_column("scans", "task_id")
    op.drop_column("scans", "status")
    op.drop_index("ix_scans_external_id", table_name="scans")
    op.drop_column("scans", "external_etag")
    op.drop_column("scans", "external_id")
    op.drop_column("scans", "source")
