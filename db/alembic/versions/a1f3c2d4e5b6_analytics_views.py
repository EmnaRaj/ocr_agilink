"""analytics views derived from raw_extraction (specs/003)

Read-only SQL views that flatten each fiche's ``raw_extraction`` JSONB into clean,
queryable columns — the analytical copilot's query surface. The DDL lives in
``app.agent.views`` (single source of truth, shared with the test fixture) so prod
and test never drift. Because the views derive from ``raw_extraction`` (not the
relational tables, which go stale after corrections), they always reflect user edits.

Revision ID: a1f3c2d4e5b6
Revises: 0bd9fd9ff567
Create Date: 2026-06-30
"""
from typing import Sequence, Union

from alembic import op

from app.agent.views import ANALYTICS_VIEWS, VIEW_NAMES

# revision identifiers, used by Alembic.
revision: str = 'a1f3c2d4e5b6'
# Chained after the data_extract migrations (was '0bd9fd9ff567' on the ChatBot
# branch) so both lines form one linear history / a single alembic head. The
# views only derive from raw_extraction + referential tables, so ordering is safe.
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for ddl in ANALYTICS_VIEWS:
        op.execute(ddl)


def downgrade() -> None:
    for view in reversed(VIEW_NAMES):
        op.execute(f"DROP VIEW IF EXISTS {view};")
