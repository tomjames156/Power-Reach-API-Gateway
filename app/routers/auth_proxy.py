from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from app.dependencies.clients import pools
import httpx

router = APIRouter()

@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_to_auth(path: str, request: Request):
    body    = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    headers["X-Request-ID"] = getattr(request.state, "request_id", "")

    try:
        resp = await pools["auth"].request(
            method=request.method,
            url=f"/{path}",
            headers=headers,
            content=body,
            params=request.query_params,
        )
    except httpx.TimeoutException:
        raise HTTPException(504, "Auth service timed out")
    except httpx.RequestError:
        raise HTTPException(503, "Auth service unreachable")

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
        media_type=resp.headers.get("content-type"),
    )