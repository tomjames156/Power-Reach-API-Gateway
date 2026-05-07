from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import uuid, time, logging

logger = logging.getLogger("gateway")

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        start = time.perf_counter()
        response = await call_next(request)
        duration = (time.perf_counter() - start) * 1000

        logger.info(
            f"[{request_id}] {request.method} {request.url.path} "
            f"→ {response.status_code} ({duration:.1f}ms)"
        )

        # Attach to response so clients and downstream services can correlate logs
        response.headers["X-Request-ID"] = request_id
        return response