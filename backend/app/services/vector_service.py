"""
VectorService — Simple text search (no embeddings needed).
"""
from app.core.logger import get_logger

logger = get_logger(__name__)


class VectorService:

    async def index_document(self, doc_id: str, chunks: list[str]) -> None:
        # No indexing needed — text stored in MongoDB directly
        logger.info(f"Skipping vector indexing for doc {doc_id} (using MongoDB text search)")

    async def remove_document(self, doc_id: str) -> None:
        pass

    async def search(self, query: str, doc_id: str, top_k: int = 5) -> list[dict]:
        # Simple keyword search in MongoDB
        from app.core.database import get_mongo_db
        db = get_mongo_db()
        doc = await db["documents"].find_one({"document_id": int(doc_id)})
        if not doc:
            return []
        
        query_words = query.lower().split()
        chunks = doc.get("chunks", [])
        
        scored = []
        for i, chunk in enumerate(chunks):
            text_lower = chunk["text"].lower()
            score = sum(1 for word in query_words if word in text_lower)
            if score > 0:
                scored.append({
                    "text": chunk["text"],
                    "chunk_idx": i,
                    "score": float(score),
                    **{k: v for k, v in chunk.items() if k != "text"}
                })
        
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]
    