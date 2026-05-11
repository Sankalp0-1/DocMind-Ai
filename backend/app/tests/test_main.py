"""
Test suite — targets 95%+ coverage.

Run with:
  pytest --cov=app --cov-report=term-missing -v

Uses pytest-asyncio for async tests + httpx AsyncClient for API tests.
External calls (OpenAI, MongoDB, FAISS) are mocked.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.security import hash_password, create_access_token
from app.models.user import User
from app.models.document import Document, FileType, ProcessingStatus

# ── Test database (in-memory SQLite) ──────────────────────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session
        await session.commit()


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
def auth_headers(test_user: User) -> dict:
    token = create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_document(db: AsyncSession, test_user: User) -> Document:
    doc = Document(
        owner_id=test_user.id,
        filename="test_doc.pdf",
        original_name="Sample.pdf",
        file_type=FileType.PDF,
        file_size_bytes=1024,
        mime_type="application/pdf",
        status=ProcessingStatus.DONE,
        mongo_doc_id="507f1f77bcf86cd799439011",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


# ═══════════════════════════════════════════════════════════════════════════════
# Auth Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuth:

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient):
        resp = await client.post("/api/auth/register", json={
            "email": "new@example.com",
            "username": "newuser",
            "password": "securepass123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "new@example.com"
        assert "hashed_password" not in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient, test_user: User):
        resp = await client.post("/api/auth/register", json={
            "email": "test@example.com",
            "username": "another",
            "password": "password123",
        })
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_register_short_password(self, client: AsyncClient):
        resp = await client.post("/api/auth/register", json={
            "email": "short@example.com",
            "username": "shortpass",
            "password": "123",
        })
        assert resp.status_code == 422  # validation error

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_user: User):
        resp = await client.post(
            "/api/auth/token",
            data={"username": "test@example.com", "password": "password123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, test_user: User):
        resp = await client.post(
            "/api/auth/token",
            data={"username": "test@example.com", "password": "wrong"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_authenticated(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_me_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# Upload Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpload:

    @pytest.mark.asyncio
    async def test_upload_pdf(self, client: AsyncClient, auth_headers: dict, tmp_path):
        with patch("app.api.upload._process_in_background", new_callable=AsyncMock):
            with patch("app.core.redis_client.get_redis") as mock_redis:
                mock_r = AsyncMock()
                mock_r.zremrangebyscore = AsyncMock(return_value=0)
                mock_r.zadd = AsyncMock(return_value=1)
                mock_r.zcard = AsyncMock(return_value=1)
                mock_r.expire = AsyncMock(return_value=1)
                mock_r.pipeline.return_value.__aenter__ = AsyncMock(return_value=mock_r)
                mock_r.pipeline.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_r.pipeline.return_value.execute = AsyncMock(return_value=[0, 1, 1, 1])
                mock_redis.return_value = mock_r

                pdf_content = b"%PDF-1.4 test content"
                resp = await client.post(
                    "/api/upload/",
                    files={"file": ("test.pdf", pdf_content, "application/pdf")},
                    headers=auth_headers,
                )
        assert resp.status_code == 201
        data = resp.json()
        assert data["original_name"] == "test.pdf"
        assert data["file_type"] == "pdf"

    @pytest.mark.asyncio
    async def test_upload_unsupported_type(self, client: AsyncClient, auth_headers: dict):
        with patch("app.core.redis_client.get_redis") as mock_redis:
            mock_r = AsyncMock()
            mock_r.pipeline.return_value.execute = AsyncMock(return_value=[0, 1, 1, 1])
            mock_redis.return_value = mock_r

            resp = await client.post(
                "/api/upload/",
                files={"file": ("test.txt", b"hello", "text/plain")},
                headers=auth_headers,
            )
        assert resp.status_code == 415

    @pytest.mark.asyncio
    async def test_list_documents(self, client: AsyncClient, auth_headers: dict, test_document: Document):
        resp = await client.get("/api/upload/", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_get_document_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/upload/99999", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_document(self, client: AsyncClient, auth_headers: dict, test_document: Document):
        with patch("pathlib.Path.exists", return_value=False):
            resp = await client.delete(f"/api/upload/{test_document.id}", headers=auth_headers)
        assert resp.status_code == 204


# ═══════════════════════════════════════════════════════════════════════════════
# Chat Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestChat:

    @pytest.mark.asyncio
    async def test_chat_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/chat/",
            json={"document_id": 99999, "question": "What is this about?"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_chat_success(
        self, client: AsyncClient, auth_headers: dict, test_document: Document
    ):
        mock_response = MagicMock()
        mock_response.answer = "This document covers AI topics."
        mock_response.sources = []
        mock_response.timestamp_hint = None
        mock_response.model_dump.return_value = {
            "answer": "This document covers AI topics.",
            "sources": [],
            "timestamp_hint": None,
        }

        with patch("app.api.chat.ChatService") as MockSvc:
            instance = MockSvc.return_value
            instance.answer = AsyncMock(return_value=mock_response)

            with patch("app.core.redis_client.get_redis") as mock_redis:
                mock_r = AsyncMock()
                mock_r.pipeline.return_value.execute = AsyncMock(return_value=[0, 1, 1, 1])
                mock_redis.return_value = mock_r

                resp = await client.post(
                    "/api/chat/",
                    json={"document_id": test_document.id, "question": "What is this about?"},
                    headers=auth_headers,
                )
        assert resp.status_code == 200
        assert "answer" in resp.json()


# ═══════════════════════════════════════════════════════════════════════════════
# Summary Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSummary:

    @pytest.mark.asyncio
    async def test_summary_success(
        self, client: AsyncClient, auth_headers: dict, test_document: Document
    ):
        from app.models.schemas import SummaryResponse
        mock_resp = SummaryResponse(
            document_id=test_document.id,
            summary="A comprehensive document about AI.",
            key_topics=["Machine Learning", "NLP"],
            word_count=500,
        )
        with patch("app.api.summary.SummaryService") as MockSvc:
            instance = MockSvc.return_value
            instance.summarize = AsyncMock(return_value=mock_resp)
            resp = await client.get(f"/api/summary/{test_document.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "A comprehensive document about AI."
        assert "Machine Learning" in data["key_topics"]

    @pytest.mark.asyncio
    async def test_summary_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/summary/99999", headers=auth_headers)
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Security Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecurity:

    def test_hash_and_verify(self):
        from app.core.security import hash_password, verify_password
        hashed = hash_password("mysecretpassword")
        assert verify_password("mysecretpassword", hashed)
        assert not verify_password("wrongpassword", hashed)

    def test_token_creation_and_decoding(self):
        from app.core.security import create_access_token, decode_token
        token = create_access_token({"sub": "42"})
        payload = decode_token(token)
        assert payload["sub"] == "42"

    def test_invalid_token_raises(self):
        from app.core.security import decode_token
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_token("not.a.real.token")
        assert exc_info.value.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# Vector Service Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestVectorService:

    @pytest.mark.asyncio
    async def test_embed_and_search(self, tmp_path):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.FAISS_INDEX_PATH = str(tmp_path)
            mock_settings.VECTOR_DIM = 4
            mock_settings.OPENAI_API_KEY = "test"
            mock_settings.OPENAI_EMBED_MODEL = "text-embedding-3-small"

            import numpy as np
            from app.services.vector_service import VectorService

            svc = VectorService.__new__(VectorService)
            import faiss
            svc._index = faiss.IndexFlatIP(4)
            svc._meta = []
            svc.INDEX_FILE = tmp_path / "index.faiss"
            svc.META_FILE = tmp_path / "meta.pkl"

            # Mock _embed
            async def fake_embed(texts):
                arr = np.ones((len(texts), 4), dtype=np.float32)
                return arr / np.linalg.norm(arr, axis=1, keepdims=True)

            svc._embed = fake_embed
            svc._save = lambda: None

            await svc.index_document("doc1", ["chunk one", "chunk two"])
            results = await svc.search("query", "doc1", top_k=2)
            assert len(results) <= 2


# ═══════════════════════════════════════════════════════════════════════════════
# Health Check
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealth:

    @pytest.mark.asyncio
    async def test_health(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
