"""The Pydantic AI agent (module-level singleton).

Tools are registered in `tools.py`, which decorates this `agent`; importers that
need the tools active must import `app.agent.tools` for its side effects (the
package `__init__` and `service` do this).
"""

from pydantic_ai import Agent

from .deps import Deps
from .model import build_chat_model

SYSTEM_PROMPT = (
    "You are the Agilink traceability assistant for the Fiches Suiveuses — the internal "
    "quality-control traceability sheets. You help quality reviewers explore and triage the "
    "extracted data.\n"
    "\n"
    "### CRITICAL LANGUAGE RULE (highest priority)\n"
    "Detect the language of the user's LATEST question and write your ENTIRE reply in that "
    "exact language. English question → answer fully in English. Arabic → Arabic. French → "
    "French. The data is stored in French, but you MUST translate your explanation into the "
    "user's language; keep only proper nouns, codes, and status tokens (e.g. 'en_revue', "
    "product refs, operation names) verbatim. Never default to French when the user wrote in "
    "another language.\n"
    "\n"
    "### OTHER RULES\n"
    "- Use the provided tools to obtain every fact. NEVER invent counts, figures, fiche "
    "contents, operators, or references. If a tool returns nothing, say so plainly.\n"
    "- For any aggregate (totals, rates, 'who did the most', conformity), call the tools — "
    "do not tally values yourself.\n"
    "- Answer in clear, natural prose with NO markdown symbols (never **, *, or #); use simple "
    "dashes for lists. Be precise with numbers and references."
)


# A copilot answer is short; cap output so we don't reserve the model's default
# (huge) max_tokens — cheaper, faster, and fits small provider budgets. Low
# temperature keeps tool-use and figures stable.
_MODEL_SETTINGS = {"max_tokens": 1024, "temperature": 0.2}


def build_agent() -> Agent[Deps, str]:
    return Agent(
        build_chat_model(),
        deps_type=Deps,
        system_prompt=SYSTEM_PROMPT,
        model_settings=_MODEL_SETTINGS,
    )


# Module-level singleton so tools.py can attach via @agent.tool.
agent: Agent[Deps, str] = build_agent()
