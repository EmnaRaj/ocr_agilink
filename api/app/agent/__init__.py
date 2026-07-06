"""Traceability Review Copilot — a Pydantic AI tool-calling agent.

A TEXT (not vision) tool-calling LLM that answers questions over the already-
extracted, corrected traceability data. Aggregate facts come from deterministic
tools (SQL/Python), never from the model tallying text. See
specs/001-traceability-copilot/ for the full spec.
"""

from .agent import agent
from . import tools  # noqa: F401 — side-effect: registers @agent.tool functions

__all__ = ["agent"]
