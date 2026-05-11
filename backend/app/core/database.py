"""
Database connections:
  • PostgreSQL (SQLAlchemy async) — structured metadata, users, sessions
  • MongoDB (Motor async)        — raw extracted text, chunk embeddings metadata
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# ── PostgreSQL ────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI dependency — yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── MongoDB ───────────────────────────────────────────────────────────────────
_mongo_client: AsyncIOMotorClient | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(settings.MONGODB_URL)
    return _mongo_client


def get_mongo_db():
    return get_mongo_client()[settings.MONGODB_DB]


# ── Init ──────────────────────────────────────────────────────────────────────
async def init_db():
    """Create all PostgreSQL tables on startup."""
    from app.models import user, document  # noqa: F401
    async with engine.begin() as conn:
        await conn.execute(text(
            "DO $$ BEGIN "
            "CREATE TYPE filetype AS ENUM ('pdf', 'audio', 'video'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        ))
        await conn.execute(text(
            "DO $$ BEGIN "
            "CREATE TYPE processingstatus AS ENUM ('pending', 'processing', 'done', 'failed'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        ))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ PostgreSQL tables ready")
