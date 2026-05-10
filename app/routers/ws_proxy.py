import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from jose import jwt, JWTError
from app.config import settings
import asyncio
import logging

logger = logging.getLogger("gateway.ws")
router = APIRouter(tags=["websocket"])


def decode_ws_token(token: str) -> dict:
    """
    Decodes and validates the JWT passed as a query parameter.
    Raises HTTPException if invalid — WebSocket will be closed before accepting.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        if not payload.get("sub"):
            raise ValueError("Token has no subject claim")
        return payload
    except JWTError as e:
        raise HTTPException(401, f"Invalid token: {e}")
    except ValueError as e:
        raise HTTPException(401, str(e))


@router.websocket("/{path:path}")
async def websocket_proxy(
    websocket: WebSocket,
    path: str,
    token: str = Query(..., description="JWT access token"),
):
    # Validate token before accepting the connection
    try:
        payload = decode_ws_token(token)
    except HTTPException as e:
        await websocket.close(code=4001, reason=e.detail)
        return

    user_id   = payload.get("sub")
    user_role = payload.get("role") or payload.get("user_type", "")

    # Build the upstream URL with the same path and query params
    # but without the token — the messaging service gets identity via headers
    upstream_url = (
        f"{settings.messaging_service_ws_url}/{path}"
    )

    logger.info(f"WS proxy: {user_id} ({user_role}) → /ws/{path}")

    # Connect to the upstream messaging service WebSocket
    # injecting identity headers the same way the HTTP proxy does
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET",
                upstream_url,
                headers={
                    "X-User-ID":    user_id,
                    "X-User-Role":  user_role,
                    "X-Request-ID": str(websocket.headers.get("sec-websocket-key", ""))[:8],
                    "Connection":   "Upgrade",
                    "Upgrade":      "websocket",
                    "Sec-WebSocket-Version": "13",
                    "Sec-WebSocket-Key": websocket.headers.get("sec-websocket-key", ""),
                },
            ):
                pass
    except Exception:
        pass

    # NOTE: proxying raw WebSocket frames via httpx is limited.
    # The cleaner approach below connects two WebSocket sessions
    # and pipes frames between them bidirectionally.
    await _pipe_websocket(websocket, upstream_url, user_id, user_role)


async def _pipe_websocket(
    client_ws: WebSocket,
    upstream_url: str,
    user_id: str,
    user_role: str,
):
    """
    Accepts the client connection then opens a second WebSocket
    to the upstream service, piping frames in both directions.
    """
    import websockets

    await client_ws.accept()

    extra_headers = {
        "X-User-ID":   user_id,
        "X-User-Role": user_role,
    }

    try:
        async with websockets.connect(upstream_url, additional_headers=extra_headers) as upstream_ws:

            async def client_to_upstream():
                try:
                    while True:
                        data = await client_ws.receive_text()
                        await upstream_ws.send(data)
                except WebSocketDisconnect:
                    await upstream_ws.close()

            async def upstream_to_client():
                try:
                    async for message in upstream_ws:
                        await client_ws.send_text(message)
                except Exception:
                    await client_ws.close()

            await asyncio.gather(
                client_to_upstream(),
                upstream_to_client(),
            )
    except Exception as e:
        logger.error(f"WS pipe error for {user_id}: {e}")
        try:
            await client_ws.close(code=1011)
        except Exception:
            pass