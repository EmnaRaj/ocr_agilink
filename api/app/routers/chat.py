import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..agent.service import run_events

router = APIRouter(tags=["chat"])


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatTurn] = []


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    """Stream the copilot's turn as NDJSON events, grounded via tools.

    Each line is a JSON event: reason (thinking), step (a tool/SQL the agent used),
    text (answer tokens), or error. Stateless: context comes from the client-sent
    `history`; nothing is persisted, so the chat resets on relaunch. Tools open their
    own per-call sessions, so the route needs no DB session of its own.
    """
    history = [t.model_dump() for t in req.history]

    async def gen():
        async for ev in run_events(req.question, history):
            yield json.dumps(ev, ensure_ascii=False) + "\n"

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
