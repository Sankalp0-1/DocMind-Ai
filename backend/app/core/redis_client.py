"""
Redis client wrapper:
  • Simple get/set/delete with JSON serialization
  • Rate limiting via sliding-window counter
  • FastAPI dependency for easy injection
"""

import json
import time
from typing import Any

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            ssl_cert_reqs=None,
        )
    return _redis


# ── Cache helpers ─────────────────────────────────────────────────────────────
async def cache_get(key: str) -> Any | None:
    r = await get_redis()
    val = await r.get(key)
    return json.loads(val) if val else None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    r = await get_redis()
    await r.setex(key, ttl, json.dumps(value))


async def cache_delete(key: str) -> None:
    r = await get_redis()
    await r.delete(key)


# ── Rate limiter dependency ───────────────────────────────────────────────────
async def rate_limit(request: Request):
    """
    Sliding-window rate limiter.
    Keyed by IP; raises 429 if limit exceeded.
    """
    client_ip = request.client.host if request.client else "unknown"
    key = f"rate:{client_ip}"
    r = await get_redis()

    now = int(time.time())
    window_start = now - settings.RATE_LIMIT_WINDOW_SECONDS

    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS)
    results = await pipe.execute()

    count = results[2]
    if count > settings.RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait before retrying.",
        )
