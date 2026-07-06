"""Per-run dependencies injected into the agent and its tools.

Pydantic AI passes this to every tool via `RunContext[Deps]`. Tools open their
**own** short-lived session from `session_factory` — the model can emit several
tool calls in one turn and Pydantic AI runs sync tools in a threadpool, so a
single shared `Session` (not thread-safe) would race. Tools are read-only, so
independent sessions are safe.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session


@dataclass
class Deps:
    session_factory: Callable[[], Session]
    # ISO code of the language to answer in (detected from the question); drives the
    # dynamic language instruction. None → fall back to the system-prompt rule.
    answer_language: str | None = None
