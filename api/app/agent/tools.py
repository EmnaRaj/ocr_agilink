"""Agent-facing tool bindings — thin adapters over `queries.py`.

The deterministic data logic lives in `queries.py` (unit-tested directly); these
wrappers attach it to the agent, carry the docstrings the model uses to pick a
tool, and open a **fresh per-call session** (see `deps.Deps`). Tools are
read-only. Future write-tools (validate / correct / flag / export) go below the
marker, each behind confirmation + an audit_log row.
"""

from pydantic_ai import RunContext

from . import queries
from .agent import agent
from .deps import Deps

# Keys of compute_overview() the agent actually needs — keep the tool payload
# bounded (the full dict's timeline/by_day/product_volumes grow with the data).
_OVERVIEW_KEYS = ("kpis", "by_statut", "operator_workload", "conformity")


@agent.tool
def get_overview(ctx: RunContext[Deps]) -> dict:
    """Dataset-wide KPIs and breakdowns: total fiches, operations, coverage %,
    conformity %, distinct operators, serials, validated count, the statut
    breakdown (extrait / en_revue / valide), per-operator workload and the
    conformity split. Use for any aggregate or "how many" / "which operator did
    the most" / "conformity rate" question."""
    with ctx.deps.session_factory() as db:
        ov = queries.overview(db)
    return {k: ov[k] for k in _OVERVIEW_KEYS if k in ov}


@agent.tool
def search_fiches(
    ctx: RunContext[Deps],
    q: str | None = None,
    ref_produit: str | None = None,
    n_of: str | None = None,
    statut: str | None = None,
    needs_review: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search fiches with optional filters, most recent first.

    q: free text matching product ref or N° OF. statut: one of 'extrait',
    'en_revue', 'valide'. needs_review=True restricts to fiches in review.
    date_from/date_to: ISO dates (YYYY-MM-DD) on the scan date. Returns compact
    summaries (id, ref, N° OF, quantity, statut, confidence, counts)."""
    with ctx.deps.session_factory() as db:
        return queries.search_fiches(
            db, q=q, ref_produit=ref_produit, n_of=n_of, statut=statut,
            needs_review=needs_review, date_from=date_from, date_to=date_to, limit=limit,
        )


@agent.tool
def get_fiche(ctx: RunContext[Deps], fiche_id: int) -> dict | None:
    """Full detail of one fiche by id: header (ref, N° OF, quantity), the filled
    operation rows, controls (with conformity), serial numbers, overall
    confidence, and any validation issues. Returns null if the fiche does not
    exist — say so plainly rather than guessing."""
    with ctx.deps.session_factory() as db:
        return queries.get_fiche(db, fiche_id)


@agent.tool
def list_review_queue(ctx: RunContext[Deps], limit: int = 20) -> list[dict]:
    """The review queue: fiches needing human attention (statut 'en_revue'),
    LOWEST confidence first, each annotated with WHY — its validation issues
    (level, field, message). Use for "what needs my attention / review"."""
    with ctx.deps.session_factory() as db:
        return queries.review_queue(db, limit=limit)


@agent.tool
def get_referential(ctx: RunContext[Deps]) -> dict:
    """Reference data for grounding: known operators (matricule → name) and
    tools (code → label). Use to resolve "who is matricule 390" or to list the
    referenced operators/tools."""
    with ctx.deps.session_factory() as db:
        return queries.referential(db)


# --- Deferred: write-tools (Phase 2 / specs/003) ---------------------------
# validate_fiche / correct_field / flag_fiche / export_fiche go here, each
# behind explicit confirmation and writing an audit_log row. Not implemented in
# this milestone (read-only copilot).
