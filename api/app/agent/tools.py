"""Agent-facing tool bindings — thin adapters over `queries.py`.

The deterministic data logic lives in `queries.py` (unit-tested directly); these
wrappers attach it to the agent, carry the docstrings the model uses to pick a
tool, and open a **fresh per-call session** (see `deps.Deps`). Tools are
read-only. Future write-tools (validate / correct / flag / export) go below the
marker, each behind confirmation + an audit_log row.
"""

from pydantic_ai import RunContext

from . import queries, sql
from .agent import agent
from .deps import Deps

# The columns the model may query via run_sql. All values reflect user corrections
# (the views derive from raw_extraction). Returned by describe_schema and summarized
# in the system prompt. Join key: fiche_id; operator link: matricule_operateur.
SCHEMA: dict = {
    "views": {
        "v_fiches": ["fiche_id", "ref_produit", "designation", "n_of", "quantite",
                     "statut", "date_creation", "overall_confidence", "validated", "page_index"],
        "v_operations": ["fiche_id", "partie", "nom_operation", "ordre", "applicable",
                         "date_op", "date_fin", "heure_debut", "heure_fin", "qte_realisee",
                         "outillage", "matricule_operateur", "operateur_nom", "confidence"],
        "v_controls": ["fiche_id", "type_controle", "methode", "resultat",
                       "matricule_operateur", "operateur_nom", "confidence"],
        "v_items": ["fiche_id", "numero_serie"],
        "v_validation": ["fiche_id", "scope", "location", "field", "level", "code", "message"],
    },
    "referential": {
        "products": ["product_id", "ref_produit", "designation"],
        "work_orders": ["of_id", "n_of", "quantite", "product_id"],
        "operators": ["operator_id", "matricule", "nom"],
        "tools": ["tool_id", "code_outillage", "libelle"],
    },
    "notes": (
        "statut in (extrait, en_revue, valide). v_controls.resultat=true means Conforme. "
        "Dates are DD.MM text (no year). All values reflect user corrections."
    ),
}

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


@agent.tool
def describe_schema(ctx: RunContext[Deps]) -> dict:
    """List the queryable views and their columns for use with run_sql. Call this
    before writing SQL when unsure which columns exist. All values reflect user
    corrections (the views derive from the live extraction record)."""
    return SCHEMA


@agent.tool
def run_sql(ctx: RunContext[Deps], query: str) -> dict:
    """Run a read-only SQL SELECT over the analytical views to answer open-ended
    analytical questions the other tools don't cover (cross-cutting filters, joins,
    group-by, trends, rankings). Prefer the curated tools for common asks; use this
    for anything custom.

    Queryable views: v_fiches, v_operations, v_controls, v_items, v_validation, plus
    referential tables products, work_orders, operators, tools. Join on fiche_id;
    resolve operators by matricule_operateur. Call describe_schema first if unsure of
    columns. Rules: a single SELECT/WITH statement only (no writes, no semicolons, no
    comments); a LIMIT is enforced automatically. Returns {columns, rows, sql,
    truncated}, or {error, sql} if the query is rejected or fails — read the error and
    retry a corrected query. Base every figure you report on the returned rows."""
    with ctx.deps.session_factory() as db:
        return sql.run_readonly(query, fallback_session=db)


# --- Deferred: operational write-tools (specs/004) -------------------------
# validate_fiche / correct_field / flag_fiche / export_fiche go here, each
# behind explicit confirmation and writing an audit_log row. Not implemented in
# this milestone (read-only analytical copilot).
