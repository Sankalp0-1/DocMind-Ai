"""
VectorService — FAISS-backed semantic search using sentence-transformers.
"""

import os
import pickle
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_model = SentenceTransformer("all-MiniLM-L6-v2")


class VectorService:
    INDEX_FILE = Path(settings.FAISS_INDEX_PATH) / "index.faiss"
    META_FILE  = Path(settings.FAISS_INDEX_PATH) / "meta.pkl"

    def __init__(self):
        Path(settings.FAISS_INDEX_PATH).mkdir(parents=True, exist_ok=True)
        self._index: Optional[faiss.IndexFlatIP] = None
        self._meta: list[dict] = []
        self._load()

    def _load(self):
        if self.INDEX_FILE.exists() and self.META_FILE.exists():
            self._index = faiss.read_index(str(self.INDEX_FILE))
            with open(self.META_FILE, "rb") as f:
                self._meta = pickle.load(f)
            logger.info(f"FAISS index loaded: {self._index.ntotal} vectors")
        else:
            self._index = faiss.IndexFlatIP(384)
            self._meta = []

    def _save(self):
        faiss.write_index(self._index, str(self.INDEX_FILE))
        with open(self.META_FILE, "wb") as f:
            pickle.dump(self._meta, f)

    async def _embed(self, texts: list[str]) -> np.ndarray:
        arr = _model.encode(texts, normalize_embeddings=True).astype(np.float32)
        return arr

    async def index_document(self, doc_id: str, chunks: list[str]) -> None:
        if not chunks:
            return
        logger.info(f"Indexing {len(chunks)} chunks for doc {doc_id}...")
        vectors = await self._embed(chunks)
        self._index.add(vectors)
        for i, text in enumerate(chunks):
            self._meta.append({"doc_id": doc_id, "chunk_idx": i, "text": text})
        self._save()
        logger.info(f"FAISS now has {self._index.ntotal} total vectors")

    async def remove_document(self, doc_id: str) -> None:
        remaining = [(i, m) for i, m in enumerate(self._meta) if m["doc_id"] != doc_id]
        if not remaining:
            self._index = faiss.IndexFlatIP(384)
            self._meta = []
            self._save()
            return
        indices, metas = zip(*remaining)
        new_index = faiss.IndexFlatIP(384)
        texts = [m["text"] for m in metas]
        vectors = await self._embed(texts)
        new_index.add(vectors)
        self._index = new_index
        self._meta = list(metas)
        self._save()

    async def search(self, query: str, doc_id: str, top_k: int = 5) -> list[dict]:
        if self._index.ntotal == 0:
            return []
        q_vec = await self._embed([query])
        k = min(top_k * 10, self._index.ntotal)
        scores, indices = self._index.search(q_vec, k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._meta):
                continue
            meta = self._meta[idx]
            if meta["doc_id"] != doc_id:
                continue
            results.append({
                "text": meta["text"],
                "chunk_idx": meta["chunk_idx"],
                "score": float(score),
            })
            if len(results) >= top_k:
                break
        return results