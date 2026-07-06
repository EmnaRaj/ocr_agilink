"""Run the agent and stream its answer — stateless.

Context comes only from the client-supplied history (the SPA keeps the live
conversation in React state and sends it each turn); there is no server-side
persistence — the chat resets on relaunch. Tools get their own per-call session
via the factory (concurrency safety). Failures degrade to a friendly streamed
message rather than a 500 mid-stream.
"""

import logging
import time
from collections.abc import AsyncIterator, Callable

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from sqlalchemy.orm import Session

from . import tools  # noqa: F401 — ensure @agent.tool functions are registered
from ..db import SessionLocal
from .agent import agent
from .deps import Deps

logger = logging.getLogger("app.agent")
logger.setLevel(logging.INFO)  # surface per-turn observability (tools, latency, tokens)

_MAX_HISTORY_MESSAGES = 16  # ~8 turns; bounds context so it can't grow unbounded
_FRIENDLY_ERROR = (
    "\n\n[assistant momentanément indisponible — réessayez dans un instant / "
    "assistant temporarily unavailable, please retry]"
)


def _msgs_from_turns(turns: list[dict]) -> list[ModelMessage]:
    """Client [{role, content}] history → Pydantic AI message history."""
    msgs: list[ModelMessage] = []
    for t in turns[-_MAX_HISTORY_MESSAGES:]:
        content = (t.get("content") or "")[:2000]
        if not content:
            continue
        if t.get("role") == "user":
            msgs.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif t.get("role") == "assistant":
            msgs.append(ModelResponse(parts=[TextPart(content=content)]))
    return msgs


async def run_stream(
    question: str,
    history: list[dict] | None = None,
    tool_session_factory: Callable[[], Session] = SessionLocal,
) -> AsyncIterator[str]:
    """Stream the agent's answer token by token, grounded via tools."""
    deps = Deps(session_factory=tool_session_factory)
    start = time.monotonic()
    try:
        async with agent.run_stream(
            question, deps=deps, message_history=_msgs_from_turns(history or [])
        ) as result:
            async for chunk in result.stream_text(delta=True):
                yield chunk
        _log_turn(question, result, start)
    except Exception as exc:  # noqa: BLE001 — provider error → friendly message, no 500
        logger.warning("chat turn failed: %s", exc)
        yield _FRIENDLY_ERROR


def _log_turn(question: str, result, start: float) -> None:
    ms = int((time.monotonic() - start) * 1000)
    try:
        from pydantic_ai.messages import ToolCallPart

        tools_called = [
            p.tool_name
            for m in result.all_messages()
            for p in getattr(m, "parts", [])
            if isinstance(p, ToolCallPart)
        ]
        usage = result.usage()
        logger.info(
            "chat ok in %dms | tools=%s | tokens=%s",
            ms, tools_called, getattr(usage, "total_tokens", None),
        )
    except Exception:  # noqa: BLE001 — logging must never break a successful turn
        logger.info("chat ok in %dms", ms)
