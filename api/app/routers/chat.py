from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.chat import stream_answer

router = APIRouter(tags=["chat"])


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatTurn] = []


@router.post("/chat")
def chat(req: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    """Stream the assistant's answer (plain-text chunks) grounded in all the data."""

    def gen():
        try:
            for piece in stream_answer(req.question, [t.model_dump() for t in req.history], db):
                yield piece
        except Exception as exc:  # surface a readable error in the stream
            yield f"\n\n[erreur] {exc}"

    return StreamingResponse(
        gen(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
