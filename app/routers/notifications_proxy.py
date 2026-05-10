import httpx
import websockets
import asyncio
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import Response
from jose import jwt, JWTError
from app.config import settings
from app.dependencies.clients import pools
import logging

logger = logging.getLogger("gateway.notifications")
router = APIRouter(tags=["notifications"])

STAFF_ROLES = {"admin", "service_agent", "staff"}


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if not payload.get("sub"):
            raise ValueError("No subject in token")
        return payload
    except JWTError as e:
        raise HTTPException(401, f"Invalid token: {e}")


# ── HTTP proxy ────────────────────────────────────────────────────────────────

@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_notifications(path: str, request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization header")

    payload = decode_token(auth_header.removeprefix("Bearer "))

    user_id   = payload.get("sub", "")
    user_role = payload.get("role") or payload.get("user_type", "")

    excluded = {"host", "content-length", "transfer-encoding", "connection"}
    headers  = {k: v for k, v in request.headers.items() if k.lower() not in excluded}
    headers["X-User-ID"]    = user_id
    headers["X-User-Role"]  = user_role
    headers["X-Request-ID"] = getattr(request.state, "request_id", "")

    # Log send/broadcast attempts for audit
    if path in {"send", "send-many", "broadcast"} and request.method == "POST":
        logger.info(f"[gateway] {user_role} {user_id} → POST /notifications/{path}")

    body = await request.body()

    try:
        resp = await pools["notifications"].request(
            method=request.method,
            url=f"/{path}",
            headers=headers,
            content=body,
            params=request.query_params,
        )
    except httpx.TimeoutException:
        raise HTTPException(504, "Notification service timed out")
    except httpx.RequestError as e:
        raise HTTPException(503, f"Notification service unreachable: {e}")

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
        media_type=resp.headers.get("content-type"),
    )


# ── WebSocket proxy ───────────────────────────────────────────────────────────

@router.websocket("/ws/notifications/{user_id}")
async def ws_notification_proxy(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(...),
):

    auth_client = pools['auth']
    user_data = None
    resp = await auth_client.get(f"/users/me", headers={"Authorization": f"Bearer {token}"})
    if resp.status_code == 200:
        user_data = resp.json()
        if user_data.get("id") != user_id:
            await websocket.close(code=4003, reason="Identity mismatch")
            return

    try:
        payload = decode_token(token)
    except HTTPException as e:
        await websocket.close(code=4001, reason=e.detail)
        return

    authenticated_user_id = payload.get("sub", "")
    user_role             = payload.get("role") or payload.get("user_type", "")

    if authenticated_user_id != user_id:
        await websocket.close(code=4003, reason="Identity mismatch")
        return

    await websocket.accept()

    upstream_url = f"{settings.notification_service_ws_url}/{user_id}"

    try:
        async with websockets.connect(
            upstream_url,
            additional_headers={
                "X-User-ID":   authenticated_user_id,
                "X-User-Role": user_role,
                "X-Display-Id": user_data["profile"]["display_id"]
            }
        ) as upstream:

            async def client_to_upstream():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await upstream.send(data)
                except WebSocketDisconnect:
                    await upstream.close()

            async def upstream_to_client():
                try:
                    async for message in upstream:
                        await websocket.send_text(message)
                except Exception:
                    try:
                        await websocket.close()
                    except Exception:
                        pass

            await asyncio.gather(client_to_upstream(), upstream_to_client())

    except Exception as e:
        logger.error(f"[gateway] WS notification proxy error for {user_id}: {e}")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass