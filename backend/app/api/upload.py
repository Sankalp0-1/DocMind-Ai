"""
Upload router.

POST /api/upload/          — upload a file (PDF/audio/video)
GET  /api/upload/          — list user's documents
GET  /api/upload/{id}      — document detail + status
DELETE /api/upload/{id}    — delete document
"""

import os
import shutil
import uuid
from pathlib import Path

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, HTTPException,
    UploadFile, status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.core.redis_client import rate_limit
from app.core.security import get_current_user
from app.models.document import Document
from app.models.schemas import DocumentOut
from app.models.user import User
from app.services.file_processor import FileProcessingService
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

ALLOWED_MIMES = {
    "application/pdf": "pdf",
    "audio/mpeg": "audio",
    "audio/wav": "audio",
    "audio/ogg": "audio",
    "audio/mp4": "audio",
    "video/mp4": "video",
    "video/webm": "video",
    "video/ogg": "video",
    "video/quicktime": "video",
}

Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


@router.post("/", response_model=DocumentOut, status_code=201)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rl=Depends(rate_limit),
):
    # Validate MIME type
    content_type = file.content_type or ""
    file_type = ALLOWED_MIMES.get(content_type)
    if not file_type:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. "
                   "Allowed: PDF, MP3, WAV, OGG, MP4, WebM, MOV",
        )

    # Validate file size
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Max: {settings.MAX_FILE_SIZE_MB} MB",
        )

    # Save to disk
    ext = Path(file.filename or "file").suffix
    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = Path(settings.UPLOAD_DIR) / unique_name
    with open(dest_path, "wb") as f:
        f.write(contents)

    # DB record
    doc = Document(
        owner_id=current_user.id,
        filename=unique_name,
        original_name=file.filename or unique_name,
        file_type=file_type,
        file_size_bytes=len(contents),
        mime_type=content_type,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Kick off processing in the background
    background_tasks.add_task(_process_in_background, doc.id)
    logger.info(f"Uploaded {doc.original_name} ({size_mb:.2f} MB) — queued for processing")
    return doc


async def _process_in_background(doc_id: int):
    """Separate DB session for the background task."""
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if doc:
            await FileProcessingService().process(doc, db)


@router.get("/", response_model=list[DocumentOut])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Document)
        .where(Document.owner_id == current_user.id)
        .order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await _get_owned_doc(doc_id, current_user.id, db)
    return doc


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await _get_owned_doc(doc_id, current_user.id, db)
    # Remove file from disk
    file_path = Path(settings.UPLOAD_DIR) / doc.filename
    if file_path.exists():
        file_path.unlink()
    await db.delete(doc)
    await db.commit()


# ── Helpers ────────────────────────────────────────────────────────────────────
async def _get_owned_doc(doc_id: int, user_id: int, db: AsyncSession) -> Document:
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.owner_id == user_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
