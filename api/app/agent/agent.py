"""The Pydantic AI agent (module-level singleton).

Tools are registered in `tools.py`, which decorates this `agent`; importers that
need the tools active must import `app.agent.tools` for its side effects (the
package `__init__` and `service` do this).
"""

from pydantic_ai import Agent, RunContext

from ..config import settings
from .deps import Deps
from .lang import language_name
from .model import build_chat_model

SYSTEM_PROMPT = (
    "You are the Agilink traceability analyst for the Fiches Suiveuses — the internal "
    "quality-control traceability sheets. You help quality reviewers explore, analyse, and triage "
    "the extracted data: answer questions, produce summaries and reports, surface patterns, and "
    "give actionable recommendations.\n"
    "\n"
    "### CRITICAL LANGUAGE RULE (highest priority)\n"
    "Detect the language of the user's LATEST question and write your ENTIRE reply in that "
    "exact language. English question → answer fully in English. Arabic → Arabic. French → "
    "French. The data is stored in French, but you MUST translate your explanation into the "
    "user's language; keep only proper nouns, codes, and status tokens (e.g. 'en_revue', "
    "product refs, operation names) verbatim. Never default to French when the user wrote in "
    "another language.\n"
    "\n"
    "### GROUNDING (non-negotiable)\n"
    "Every figure, name, date, and reference you state MUST come from a tool result or an executed "
    "SQL query — NEVER from memory or guesswork. You may reason, compare, rank, and recommend, but "
    "only over data the tools returned. If you have not queried it, do not assert it. If a tool "
    "returns nothing, say so plainly.\n"
    "\n"
    "### HOW TO GET DATA\n"
    "- For common asks use the curated tools: get_overview (dataset KPIs/breakdowns), search_fiches, "
    "get_fiche, list_review_queue, get_referential.\n"
    "- For anything custom — cross-cutting filters, joins, group-by, trends, rankings the curated "
    "tools don't cover — write a query with run_sql over the analytical views (v_fiches, "
    "v_operations, v_controls, v_items, v_validation; referential: products, work_orders, operators, "
    "tools). Join on fiche_id; resolve operators by matricule_operateur. All view values already "
    "reflect user corrections.\n"
    "- Exact columns — use these names, do NOT guess (the operation label is nom_operation, not "
    "operation_name):\n"
    "  v_fiches(fiche_id, ref_produit, designation, n_of, quantite, statut, date_creation, "
    "overall_confidence, validated)\n"
    "  v_operations(fiche_id, partie, nom_operation, ordre, applicable, date_op, date_fin, "
    "heure_debut, heure_fin, qte_realisee, outillage, matricule_operateur, operateur_nom, confidence)\n"
    "  v_controls(fiche_id, type_controle, methode, resultat, matricule_operateur, operateur_nom, confidence)\n"
    "  v_items(fiche_id, numero_serie); v_validation(fiche_id, scope, location, field, level, code, message)\n"
    "- run_sql accepts a single read-only SELECT/WITH (a LIMIT is enforced). If it returns an error, "
    "read it and retry a corrected query. You may call tools several times to build an answer.\n"
    "\n"
    "### STYLE\n"
    "- Be precise with numbers and references. Format replies in clean Markdown: short bold labels, "
    "bullet or numbered lists, and Markdown tables when comparing rows or ranking. Use headings only "
    "for longer reports. Keep it concise — the UI renders your Markdown.\n"
    "- When useful, end an analytical answer with a brief, concrete recommendation."
)


def _reasoning_extra_body() -> dict:
    """OpenRouter `reasoning` control from CHAT_REASONING_EFFORT (ignored by
    non-reasoning backends). Bounds thinking tokens — the main latency/cost lever."""
    eff = (settings.chat_reasoning_effort or "low").strip().lower()
    if eff in ("off", "none", "disabled", "false", "0"):
        return {"reasoning": {"enabled": False}}
    if eff in ("low", "medium", "high"):
        return {"reasoning": {"effort": eff}}
    return {}  # unknown → provider default


# Analytical answers (reports, multi-step reasoning) need more room than the old
# one-line copilot, but still bounded to control cost/latency. Low temperature keeps
# tool-use and generated SQL stable. extra_body caps reasoning; timeout covers slow
# reasoning turns.
_MODEL_SETTINGS = {
    "max_tokens": 3072,
    "temperature": 0.2,
    "timeout": settings.chat_timeout_s,
    "extra_body": _reasoning_extra_body(),
}


def build_agent() -> Agent[Deps, str]:
    return Agent(
        build_chat_model(),
        deps_type=Deps,
        system_prompt=SYSTEM_PROMPT,
        model_settings=_MODEL_SETTINGS,
    )


# Module-level singleton so tools.py can attach via @agent.tool.
agent: Agent[Deps, str] = build_agent()


@agent.instructions
def _answer_language(ctx: RunContext[Deps]) -> str:
    """Deterministic per-question language instruction (detect→instruct). The
    service detects the question's language and puts it on Deps; this makes the
    target explicit instead of leaving it to the soft system-prompt rule."""
    name = language_name(ctx.deps.answer_language)
    if not name:
        return ""
    return (
        f"CRITICAL: write your FINAL answer to the user entirely in {name}. Translate all "
        f"explanatory prose into {name}; keep data values, codes, product refs, operation "
        f"names, and status tokens verbatim."
    )


# A tiny, tool-free, reasoning-off model used only to repair an answer that came back
# in the wrong language (the verify→repair step). Cheap and fast.
translator: Agent[None, str] = Agent(
    build_chat_model(),
    system_prompt=(
        "You are a translator. Rewrite the user's text in the requested target language, "
        "preserving every number, code, product reference, operation name, status token, and "
        "all Markdown formatting exactly. Output only the rewritten text, nothing else."
    ),
    model_settings={
        "max_tokens": 3072,
        "temperature": 0.0,
        "timeout": settings.chat_timeout_s,
        "extra_body": {"reasoning": {"enabled": False}},
    },
)
