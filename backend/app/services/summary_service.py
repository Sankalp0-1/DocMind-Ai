"""
SummaryService — generates a structured summary using Groq API.
"""

import json
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.core.redis_client import cache_get, cache_set
from app.models.document import Document
from app.models.schemas import SummaryResponse
from app.services.file_processor import FileProcessingService

logger = get_logger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SUMMARY_SYSTEM = """You are a document summarization expert.
Given document excerpts, produce:
1. A clear, concise summary (3-5 paragraphs).
2. A JSON list of 5-10 key topics covered.

Respond ONLY in this JSON format with no extra text:
{
  "summary": "<summary text>",
  "key_topics": ["topic1", "topic2", ...]
}
"""


class SummaryService:

    def __init__(self):
        self.file_svc = FileProcessingService()

    async def summarize(self, document: Document, db: AsyncSession) -> SummaryResponse:
        cache_key = f"summary:{document.id}"
        cached = await cache_get(cache_key)
        if cached:
            logger.info(f"Summary cache hit for doc {document.id}")
            return SummaryResponse(**cached)

        if not document.mongo_doc_id:
            return SummaryResponse(
                document_id=document.id,
                summary="Document has not been processed yet.",
                key_topics=[],
                word_count=0,
            )

        chunks = await self.file_svc.get_chunks(document.mongo_doc_id)
        sample_text = "\n\n".join(c["text"] for c in chunks[:20])
        word_count = len(sample_text.split())

        try:
            async with httpx.AsyncClient() as http:
                resp = await http.post(
                    GROQ_URL,
                    headers={
                        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.GROQ_CHAT_MODEL,
                        "messages": [
                            {"role": "system", "content": SUMMARY_SYSTEM},
                            {"role": "user", "content": f"Document content:\n\n{sample_text}"},
                        ],
                        "stream": False,
                    },
                    timeout=60,
                )
                content = resp.json()["choices"][0]["message"]["content"]
                start = content.find("{")
                end = content.rfind("}") + 1
                data = json.loads(content[start:end])
                summary_text = data.get("summary", "No summary generated.")
                key_topics = data.get("key_topics", [])
        except Exception as exc:
            logger.error(f"Summary LLM call failed: {exc}")
            summary_text = "Summary generation failed."
            key_topics = []

        response = SummaryResponse(
            document_id=document.id,
            summary=summary_text,
            key_topics=key_topics,
            word_count=word_count,
        )

        await cache_set(cache_key, response.model_dump(), ttl=3600)
        return response