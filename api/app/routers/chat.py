from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..agent.service import run_stream

router = APIRouter(tags=["chat"])


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatTurn] = []


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    """Stream the copilot's answer (plain-text chunks), grounded via tools.

    Stateless: context comes from the client-sent `history`; nothing is persisted,
    so the chat resets on relaunch. Tools open their own per-call sessions, so the
    route needs no DB session of its own.
    """
    history = [t.model_dump() for t in req.history]

    async def gen():
        async for piece in run_stream(req.question, history):
            yield piece

    return StreamingResponse(
        gen(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
