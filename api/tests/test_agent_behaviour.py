"""Agent behaviour tests with no real LLM (TestModel + monkeypatch).

The chat is stateless: `run_stream(question, history)` streams an answer grounded
via tools, with context from the client-supplied history and no persistence.
"""

import asyncio

from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.test import TestModel

from app.agent import agent
from app.agent.deps import Deps
from app.agent.service import run_stream


async def _collect(factory, question="test question", history=None) -> str:
    return "".join([c async for c in run_stream(question, history or [], tool_session_factory=factory)])


def _tool_names(result) -> list[str]:
    return [
        p.tool_name
        for m in result.all_messages()
        for p in getattr(m, "parts", [])
        if isinstance(p, ToolCallPart)
    ]


def test_agent_invokes_tools_via_testmodel(session_factory):
    with agent.override(model=TestModel()):
        result = agent.run_sync("Combien de fiches ?", deps=Deps(session_factory=session_factory))
    assert isinstance(result.output, str) and result.output
    called = set(_tool_names(result))
    assert called & {"get_overview", "search_fiches", "get_fiche", "list_review_queue", "get_referential"}


def test_run_stream_yields_text(session_factory):
    with agent.override(model=TestModel()):
        out = asyncio.run(_collect(session_factory))
    assert out  # non-empty streamed answer


def test_run_stream_accepts_history_context(session_factory):
    history = [
        {"role": "user", "content": "Combien de fiches en revue ?"},
        {"role": "assistant", "content": "Il y a 19 fiches en revue."},
    ]
    with agent.override(model=TestModel()):
        out = asyncio.run(_collect(session_factory, question="Et combien validées ?", history=history))
    assert out  # the client-supplied context is accepted and an answer is produced


def test_run_stream_degrades_on_provider_failure(session_factory, monkeypatch):
    class _Boom:
        def run_stream(self, *a, **k):
            raise RuntimeError("provider down")

    monkeypatch.setattr("app.agent.service.agent", _Boom())
    out = asyncio.run(_collect(session_factory))
    assert "indisponible" in out or "unavailable" in out  # friendly, no crash
