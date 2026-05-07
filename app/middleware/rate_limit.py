from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import redis.asyncio as aioredis
import time

redis = aioredis.from_url("redis://localhost:6379", decode_responses=True)

RATE_LIMIT    = 60   # requests
WINDOW_SECS   = 60   # per minute

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ip  = request.client.host
        key = f"rl:{ip}"

        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, WINDOW_SECS)

        if current > RATE_LIMIT:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests — slow down"},
                headers={"Retry-After": str(WINDOW_SECS)},
            )

        return await call_next(request)