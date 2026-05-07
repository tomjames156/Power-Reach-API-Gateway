from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx

from app.config import settings
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.routers import auth_proxy, reporting_proxy, messaging_proxy, ws_proxy
from app.dependencies.clients import pools

@asynccontextmanager
async def lifespan(app: FastAPI):
    pools["auth"]      = httpx.AsyncClient(
        base_url=settings.auth_service_url,
        limits=httpx.Limits(max_connections=30, max_keepalive_connections=15),
        timeout=httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=1.0),
    )
    pools["reporting"] = httpx.AsyncClient(
        base_url=settings.reporting_service_url,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        timeout=httpx.Timeout(connect=3.0, read=15.0, write=5.0, pool=1.0),
    )
    pools["messaging"]  = httpx.AsyncClient(
        base_url=settings.messaging_service_url,
        limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
        timeout=httpx.Timeout(connect=3.0, read=20.0, write=10.0, pool=1.0),
    )
    print("Gateway pools open")
    yield
    for client in pools.values():
        await client.aclose()
    print("Gateway pools closed")


# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="API Gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth_proxy.router,      prefix="/api/auth")
app.include_router(reporting_proxy.router, prefix="/api/reports")
app.include_router(messaging_proxy.router, prefix="/api/chat")
app.include_router(ws_proxy.router, prefix="/ws")