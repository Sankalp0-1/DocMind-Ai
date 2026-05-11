"""
Central configuration — reads from .env via pydantic-settings.
"""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "AI Q&A App"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production-please"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/aiqadb"
    MONGODB_URL: str = "mongodb://mongo:27017"
    MONGODB_DB: str = "aiqa"

    REDIS_URL: str = "redis://redis:6379/0"

    OPENAI_API_KEY: str = ""
    OPENAI_CHAT_MODEL: str = "gpt-4o"
    OPENAI_EMBED_MODEL: str = "text-embedding-3-small"
    OPENAI_WHISPER_MODEL: str = "whisper-1"

    # Groq
    GROQ_API_KEY: str = ""
    GROQ_CHAT_MODEL: str = "llama3-8b-8192"

    UPLOAD_DIR: str = "/tmp/uploads"
    MAX_FILE_SIZE_MB: int = 500

    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    FAISS_INDEX_PATH: str = "/tmp/faiss_index"
    VECTOR_DIM: int = 768


settings = Settings()