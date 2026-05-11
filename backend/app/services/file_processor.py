"""
FileProcessingService:
  • PDF  → extract text per page with PyMuPDF
  • Audio/Video → transcribe with OpenAI Whisper (includes timestamps)
  • Chunks text → stores in MongoDB
  • Builds FAISS vector index for semantic search
"""

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import openai
from bson import ObjectId
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_mongo_db
from app.core.logger import get_logger
from app.models.document import Document
from app.services.vector_service import VectorService

logger = get_logger(__name__)
client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


class FileProcessingService:
    """Orchestrates extraction → chunking → embedding → indexing."""

    CHUNK_SIZE = 800       # characters per chunk
    CHUNK_OVERLAP = 100    # overlap to preserve context at boundaries

    # ── Public entry point ────────────────────────────────────────────────────
    async def process(self, document: Document, db: AsyncSession) -> None:
        """
        Called by the upload router (background task).
        Updates document status in PostgreSQL; stores data in MongoDB.
        """
        try:
            document.status = "processing"
            await db.commit()

            file_path = Path(settings.UPLOAD_DIR) / document.filename

            if document.file_type == "pdf":
                pages = await self._extract_pdf(file_path)
                chunks = self._chunk_pages(pages)
                mongo_id = await self._store_mongo(document, chunks, doc_type="pdf")

            else:  # audio or video
                transcript_segments = await self._transcribe(file_path)
                chunks = self._chunk_transcript(transcript_segments)
                mongo_id = await self._store_mongo(
                    document, chunks, doc_type=document.file_type,
                    segments=transcript_segments
                )
                # Total duration from last segment
                if transcript_segments:
                    document.duration_seconds = transcript_segments[-1].get("end", 0)

            # Build / update FAISS index
            await VectorService().index_document(
                doc_id=str(document.id),
                chunks=[c["text"] for c in chunks],
            )

            document.mongo_doc_id = mongo_id
            document.status = "done"
            document.processed_at = datetime.now(timezone.utc)

        except Exception as exc:
            logger.exception(f"Processing failed for document {document.id}: {exc}")
            document.status = "failed"
            document.error_message = str(exc)

        await db.commit()

    # ── PDF ───────────────────────────────────────────────────────────────────
    async def _extract_pdf(self, path: Path) -> list[dict]:
        """Return list of {page: int, text: str}."""
        pages = []
        with fitz.open(str(path)) as pdf:
            for i, page in enumerate(pdf):
                text = page.get_text("text").strip()
                if text:
                    pages.append({"page": i + 1, "text": text})
        logger.info(f"PDF extracted: {len(pages)} pages from {path.name}")
        return pages

    # ── Audio / Video ─────────────────────────────────────────────────────────
    async def _transcribe(self, path: Path) -> list[dict]:
        """
        Returns list of {start, end, text} segments via Whisper.
        Falls back gracefully if the file is audio-only from a video.
        """
        with open(path, "rb") as f:
            response = await client.audio.transcriptions.create(
                model=settings.OPENAI_WHISPER_MODEL,
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        segments = []
        for seg in (response.segments or []):
            segments.append({
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            })
        logger.info(f"Transcribed {len(segments)} segments from {path.name}")
        return segments

    # ── Chunking ──────────────────────────────────────────────────────────────
    def _chunk_pages(self, pages: list[dict]) -> list[dict]:
        """Split page text into overlapping chunks."""
        chunks = []
        for page_data in pages:
            text = page_data["text"]
            start = 0
            while start < len(text):
                end = start + self.CHUNK_SIZE
                chunk_text = text[start:end]
                chunks.append({
                    "text": chunk_text,
                    "page": page_data["page"],
                    "char_start": start,
                })
                start += self.CHUNK_SIZE - self.CHUNK_OVERLAP
        return chunks

    def _chunk_transcript(self, segments: list[dict]) -> list[dict]:
        """Group transcript segments into ~CHUNK_SIZE character chunks."""
        chunks = []
        buffer_text = ""
        buffer_start = 0.0
        buffer_end = 0.0

        for seg in segments:
            if len(buffer_text) + len(seg["text"]) > self.CHUNK_SIZE and buffer_text:
                chunks.append({
                    "text": buffer_text.strip(),
                    "start_seconds": buffer_start,
                    "end_seconds": buffer_end,
                })
                buffer_text = ""
                buffer_start = seg["start"]

            if not buffer_text:
                buffer_start = seg["start"]
            buffer_text += " " + seg["text"]
            buffer_end = seg["end"]

        if buffer_text.strip():
            chunks.append({
                "text": buffer_text.strip(),
                "start_seconds": buffer_start,
                "end_seconds": buffer_end,
            })
        return chunks

    # ── MongoDB storage ───────────────────────────────────────────────────────
    async def _store_mongo(
        self,
        document: Document,
        chunks: list[dict],
        doc_type: str,
        segments: list[dict] | None = None,
    ) -> str:
        db = get_mongo_db()
        doc = {
            "document_id": document.id,
            "original_name": document.original_name,
            "doc_type": doc_type,
            "chunks": chunks,
            "raw_segments": segments or [],
            "created_at": time.time(),
        }
        result = await db["documents"].insert_one(doc)
        return str(result.inserted_id)

    # ── Retrieval (used by chat service) ──────────────────────────────────────
    async def get_chunks(self, mongo_doc_id: str) -> list[dict]:
        db = get_mongo_db()
        doc = await db["documents"].find_one({"_id": ObjectId(mongo_doc_id)})
        return doc["chunks"] if doc else []

    async def get_segments(self, mongo_doc_id: str) -> list[dict]:
        db = get_mongo_db()
        doc = await db["documents"].find_one({"_id": ObjectId(mongo_doc_id)})
        return doc.get("raw_segments", []) if doc else []
