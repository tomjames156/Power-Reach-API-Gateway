# gateway/app/middleware/rate_limit.py

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import time
import asyncio
from collections import defaultdict

RATE_LIMIT  = 60   # requests
WINDOW_SECS = 60   # per minute


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # { ip: {"count": int, "window_start": float} }
        self._buckets: dict = defaultdict(lambda: {"count": 0, "window_start": 0.0})
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        ip  = request.client.host
        now = time.time()

        async with self._lock:
            bucket = self._buckets[ip]

            # If the window has expired, reset it
            if now - bucket["window_start"] >= WINDOW_SECS:
                bucket["count"]        = 0
                bucket["window_start"] = now

            bucket["count"] += 1
            count = bucket["count"]

        if count > RATE_LIMIT:
            retry_after = int(WINDOW_SECS - (now - self._buckets[ip]["window_start"]))
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests — slow down"},
                headers={"Retry-After": str(max(retry_after, 1))},
            )

        return await call_next(request)