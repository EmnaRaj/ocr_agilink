"""Run the agent and stream its answer as structured events — stateless.

Context comes only from the client-supplied history (the SPA keeps the live
conversation in React state and sends it each turn); there is no server-side
persistence — the chat resets on relaunch. Tools get their own per-call session
via the factory (concurrency safety). Failures degrade to a friendly event
rather than a 500 mid-stream.

The stream is a sequence of small dict events (serialised to NDJSON by the
router):
  {"t": "reason", "d": "..."}  reasoning/thinking tokens (reasoning models)
  {"t": "step",   "tool": "run_sql", "sql": "...", "rows": 3}  a tool the agent used
  {"t": "text",   "d": "..."}  answer tokens
  {"t": "error",  "d": "..."}  friendly degrade message
`run_stream` remains a text-only view over the same events (used by tests).
"""

import json
import logging
import time
from collections.abc import AsyncIterator, Callable

from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    UserPromptPart,
)
from sqlalchemy.orm import Session

from . import tools  # noqa: F401 — ensure @agent.tool functions are registered
from ..db import SessionLocal
from .agent import agent, translator
from .deps import Deps
from .lang import detect_language, language_name

logger = logging.getLogger("app.agent")
logger.setLevel(logging.INFO)  # surface per-turn observability (tools, latency)

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


def _return_value(event: FunctionToolResultEvent):
    """The tool's return value as a dict, wherever the framework stashed it.

    Across pydantic-ai versions the return payload may live on event.content, on a
    nested ToolReturnPart (event.content.content / event.part.content), and may be a
    dict or a JSON string. Try the candidates and return the first dict."""
    candidates = [
        getattr(event, "content", None),
        getattr(getattr(event, "content", None), "content", None),
        getattr(getattr(event, "part", None), "content", None),
    ]
    for c in candidates:
        if isinstance(c, dict):
            return c
        if isinstance(c, str):
            try:
                j = json.loads(c)
                if isinstance(j, dict):
                    return j
            except (ValueError, TypeError):
                pass
    return None


def _tool_step(event: FunctionToolResultEvent) -> dict:
    """Translate a tool-result event into a 'step' (source) event: which tool, with
    what arguments (filters / fiche id), the executed SQL, and how many rows."""
    call = getattr(event, "part", None)  # ToolCallPart (tool_name, args)
    value = _return_value(event)
    tool = (
        getattr(call, "tool_name", None)
        or getattr(getattr(event, "content", None), "tool_name", None)
        or (value or {}).get("_tool")
    )
    step = {"t": "step", "tool": tool or "tool"}
    # Non-empty call args give the "what" (e.g. fiche_id, filters). run_sql's args are
    # redundant with its executed SQL, so skip them there.
    args = getattr(call, "args", None)
    if args and tool != "run_sql":
        if isinstance(args, str):
            step["args"] = args[:200]
        elif isinstance(args, dict):
            step["args"] = {k: v for k, v in args.items() if v not in (None, "", False)}
    if isinstance(value, dict):
        if value.get("sql"):
            step["sql"] = value["sql"]
        if value.get("error"):
            step["error"] = value["error"]
        elif isinstance(value.get("rows"), list):
            step["rows"] = len(value["rows"])
    return step


async def _ensure_language(text: str, target: str | None) -> str:
    """Verify → repair: if the final answer isn't in the question's language, rewrite
    it with the translator. Best-effort — any failure returns the original text.
    Works because the answer is buffered (not token-streamed), so we fix before send."""
    if not target or len(text) < 20:
        return text
    got = detect_language(text)
    if not got or got == target:
        return text
    try:
        res = await translator.run(f"Target language: {language_name(target)}.\n\n{text}")
        return (res.output or "").strip() or text
    except Exception as exc:  # noqa: BLE001 — repair is best-effort, never break the turn
        logger.warning("language repair failed: %s", exc)
        return text


async def run_events(
    question: str,
    history: list[dict] | None = None,
    tool_session_factory: Callable[[], Session] = SessionLocal,
) -> AsyncIterator[dict]:
    """Stream the agent's turn as structured events (reason / step / text)."""
    target_lang = detect_language(question)  # detect → instruct (via Deps) → verify → repair
    deps = Deps(session_factory=tool_session_factory, answer_language=target_lang)
    start = time.monotonic()
    tools_called: list[str] = []
    try:
        async with agent.iter(
            question, deps=deps, message_history=_msgs_from_turns(history or [])
        ) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    # Reasoning streams live. A model turn's plain text is buffered and
                    # classified at the end: if the turn ALSO called tools it was step
                    # narration → reasoning; only the final turn (no tool calls) is the
                    # answer. This stops interstitial narration polluting the answer.
                    text_buf: list[str] = []
                    turn_called_tool = False
                    async with node.stream(run.ctx) as request_stream:
                        async for event in request_stream:
                            if isinstance(event, PartStartEvent):
                                part = event.part
                                if isinstance(part, ThinkingPart) and part.content:
                                    yield {"t": "reason", "d": part.content}
                                elif isinstance(part, TextPart) and part.content:
                                    text_buf.append(part.content)
                                elif isinstance(part, ToolCallPart):
                                    turn_called_tool = True
                            elif isinstance(event, PartDeltaEvent):
                                d = event.delta
                                if isinstance(d, ThinkingPartDelta) and getattr(d, "content_delta", None):
                                    yield {"t": "reason", "d": d.content_delta}
                                elif isinstance(d, TextPartDelta) and getattr(d, "content_delta", None):
                                    text_buf.append(d.content_delta)
                    text = "".join(text_buf).strip()
                    if text:
                        if turn_called_tool:
                            yield {"t": "reason", "d": "\n\n" + text}
                        else:
                            yield {"t": "text", "d": await _ensure_language(text, target_lang)}
                elif Agent.is_call_tools_node(node):
                    async with node.stream(run.ctx) as handle_stream:
                        async for event in handle_stream:
                            if isinstance(event, FunctionToolResultEvent):
                                step = _tool_step(event)
                                tools_called.append(step["tool"])
                                yield step
        ms = int((time.monotonic() - start) * 1000)
        logger.info("chat ok in %dms | tools=%s", ms, tools_called)
    except Exception as exc:  # noqa: BLE001 — provider error → friendly event, no 500
        logger.warning("chat turn failed: %s", exc)
        yield {"t": "error", "d": _FRIENDLY_ERROR}


async def run_stream(
    question: str,
    history: list[dict] | None = None,
    tool_session_factory: Callable[[], Session] = SessionLocal,
) -> AsyncIterator[str]:
    """Text-only view over `run_events` (answer + degrade message)."""
    async for ev in run_events(question, history, tool_session_factory):
        if ev.get("t") in ("text", "error"):
            yield ev["d"]
