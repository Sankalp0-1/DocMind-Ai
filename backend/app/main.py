"""
AI-Powered Document & Multimedia Q&A — FastAPI Backend
Entry point: all routers, middleware, lifespan events
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.api import upload, chat, summary, auth
from app.core.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("🚀 Starting AI Q&A App...")
    await init_db()
    yield
    logger.info("🛑 Shutting down AI Q&A App...")


app = FastAPI(
    title="AI Document & Multimedia Q&A",
    description="Upload PDFs, audio, and video — then chat with your content.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router,   prefix="/api/auth",    tags=["Auth"])
app.include_router(upload.router, prefix="/api/upload",  tags=["Upload"])
app.include_router(chat.router,   prefix="/api/chat",    tags=["Chat"])
app.include_router(summary.router,prefix="/api/summary", tags=["Summary"])


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
