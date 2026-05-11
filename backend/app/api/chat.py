"""
Chat router.

POST /api/chat/            — ask a question (batch or streaming)
GET  /api/chat/{doc_id}/timestamps — extract topic timestamps for audio/video
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.redis_client import rate_limit
from app.core.security import get_current_user
from app.models.document import Document
from app.models.schemas import ChatRequest, ChatResponse, TimestampResponse, TimestampEntry
from app.models.user import User
from app.services.chat_service import ChatService
from app.services.file_processor import FileProcessingService
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rl=Depends(rate_limit),
):
    doc = await _get_ready_doc(payload.document_id, current_user.id, db)

    svc = ChatService()

    if payload.stream:
        async def event_generator():
            async for chunk in svc.answer_stream(doc, payload.question):
                yield chunk

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return await svc.answer(doc, payload.question, db)


@router.get("/{doc_id}/timestamps", response_model=TimestampResponse)
async def get_timestamps(
    doc_id: int,
    topic: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await _get_ready_doc(doc_id, current_user.id, db)

    if doc.file_type not in ("audio", "video"):
        raise HTTPException(
            status_code=400, detail="Timestamps only available for audio/video files"
        )

    file_svc = FileProcessingService()
    segments = await file_svc.get_segments(doc.mongo_doc_id)

    entries: list[TimestampEntry] = []
    for seg in segments:
        text = seg.get("text", "")
        if topic and topic.lower() not in text.lower():
            continue
        entries.append(
            TimestampEntry(
                topic=topic or "segment",
                start_seconds=seg.get("start", 0),
                end_seconds=seg.get("end"),
                text_snippet=text[:200],
            )
        )

    return TimestampResponse(document_id=doc_id, timestamps=entries)


# ── Helpers ────────────────────────────────────────────────────────────────────
async def _get_ready_doc(doc_id: int, user_id: int, db: AsyncSession) -> Document:
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.owner_id == user_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.status != "done":
        raise HTTPException(
            status_code=202,
            detail=f"Document is still being processed (status: {doc.status})",
        )
    return doc