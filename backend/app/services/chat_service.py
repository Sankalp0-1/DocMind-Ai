"""
ChatService — RAG pipeline using Groq API.
"""

import json
import asyncio
from typing import AsyncGenerator

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.core.redis_client import cache_get, cache_set
from app.models.document import Document
from app.models.schemas import ChatSource, ChatResponse
from app.services.vector_service import VectorService
from app.services.file_processor import FileProcessingService

logger = get_logger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """You are a helpful AI assistant that answers questions strictly 
based on the provided document context. 

Rules:
- Only use information from the CONTEXT section below.
- If the answer is not in the context, say "I couldn't find that in the document."
- Be concise and cite which part of the document supports your answer.
- For audio/video transcripts, reference approximate timestamps when useful.
"""


class ChatService:

    def __init__(self):
        self.vector_svc = VectorService()
        self.file_svc = FileProcessingService()

    async def answer(
        self,
        document: Document,
        question: str,
        db: AsyncSession,
    ) -> ChatResponse:
        cache_key = f"chat:{document.id}:{hash(question)}"
        cached = await cache_get(cache_key)
        if cached:
            logger.info("Cache hit for chat query")
            return ChatResponse(**cached)

        hits = await self.vector_svc.search(
            query=question, doc_id=str(document.id), top_k=5
        )

        if not hits and document.mongo_doc_id:
            raw_chunks = await self.file_svc.get_chunks(document.mongo_doc_id)
            hits = [
                {"text": c["text"], "chunk_idx": i, "score": 1.0}
                for i, c in enumerate(raw_chunks[:5])
            ]

        context = "\n\n".join(f"[Chunk {i+1}]: {h['text']}" for i, h in enumerate(hits))

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\nAnswer based only on the context above:",
            },
        ]

        async with httpx.AsyncClient() as http:
            resp = await http.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": settings.GROQ_CHAT_MODEL, "messages": messages, "stream": False},
                timeout=60,
            )
            resp_json = resp.json()
            logger.error(f"Groq response: {resp_json}")
            if "choices" not in resp_json:
                answer_text = f"API Error: {resp_json.get('error', {}).get('message', 'Unknown error')}"
            else:
                answer_text = resp_json["choices"][0]["message"]["content"]

        sources = self._build_sources(hits, document)
        timestamp_hint = await self._find_timestamp(document, hits)

        response = ChatResponse(
            answer=answer_text,
            sources=sources,
            timestamp_hint=timestamp_hint,
        )

        await cache_set(cache_key, response.model_dump(), ttl=600)
        return response

    async def answer_stream(
        self,
        document: Document,
        question: str,
    ) -> AsyncGenerator[str, None]:
        hits = await self.vector_svc.search(
            query=question, doc_id=str(document.id), top_k=5
        )
        context = "\n\n".join(f"[Chunk {i+1}]: {h['text']}" for i, h in enumerate(hits))

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\nAnswer:",
            },
        ]

        async with httpx.AsyncClient() as http:
            async with http.stream(
                "POST",
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": settings.GROQ_CHAT_MODEL, "messages": messages, "stream": True},
                timeout=60,
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        payload = line[6:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            data = json.loads(payload)
                            token = data["choices"][0]["delta"].get("content", "")
                            if token:
                                yield f"data: {json.dumps({'token': token})}\n\n"
                        except Exception:
                            pass

        sources = self._build_sources(hits, document)
        timestamp_hint = await self._find_timestamp(document, hits)
        meta = {
            "sources": [s.model_dump() for s in sources],
            "timestamp_hint": timestamp_hint,
        }
        yield f"data: {json.dumps({'meta': meta})}\n\n"
        yield "data: [DONE]\n\n"

    def _build_sources(self, hits: list[dict], document: Document) -> list[ChatSource]:
        sources = []
        for h in hits:
            page_ts = None
            if "page" in h:
                page_ts = f"Page {h['page']}"
            elif "start_seconds" in h:
                s = int(h.get("start_seconds", 0))
                page_ts = f"{s // 60}:{s % 60:02d}"
            sources.append(
                ChatSource(
                    chunk_text=h["text"][:300],
                    page_or_timestamp=page_ts,
                    score=round(h["score"], 4),
                )
            )
        return sources

    async def _find_timestamp(
        self, document: Document, hits: list[dict]
    ) -> float | None:
        if document.file_type not in ("audio", "video"):
            return None
        if not document.mongo_doc_id or not hits:
            return None
        chunks = await self.file_svc.get_chunks(document.mongo_doc_id)
        best_idx = hits[0].get("chunk_idx", 0)
        if best_idx < len(chunks):
            return chunks[best_idx].get("start_seconds")
        return None