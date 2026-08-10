import asyncio

from redis.asyncio import Redis

from app.config import settings

_redis: Redis | None = None
# Guards the lazy singleton init so concurrent first-callers don't each build a
# throwaway client (the naive check-then-set below races under concurrency).
_redis_lock = asyncio.Lock()


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        async with _redis_lock:
            # Re-check inside the lock: a caller that lost the race must reuse the
            # client the winner already created rather than build a second one.
            if _redis is None:
                _redis = Redis.from_url(str(settings.REDIS_URL), decode_responses=True)
    return _redis


async def close_redis() -> None:
    """Close the singleton. Called from the app/worker shutdown hook."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
