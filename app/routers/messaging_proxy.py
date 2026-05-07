from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import Response
from app.dependencies.clients import pools
from jose import jwt
from app.config import settings
from app.middleware.auth import get_user_payload
import httpx

router = APIRouter()

@router.get("/chat_conversation/{conversation_id}")
async def get_chat_conversation(request: Request, conversation_id: str):
    # 0. Get the token from the incoming headers
    token = request.headers.get("Authorization")

    if not token:
        raise HTTPException(status_code=401, detail="Missing Token")

        # 1. Decode the token in the Gateway
    try:
        # Strip "Bearer " prefix if present
        actual_token = token.split(" ")[1] if " " in token else token
        payload = jwt.decode(actual_token, settings.secret_key, algorithms=[settings.algorithm])

        user_id = str(payload.get("sub"))  # Or however you store the ID
        user_role = payload.get("role", "customer")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Token")

        # 2. Build the "Internal" headers your microservices expect
    internal_headers = {
        "Authorization": token,
        "X-User-ID": user_id,
        "X-User-Role": user_role,
        "X-Request-ID": request.headers.get("X-Request-ID", "gateway-generated")
    }

    messaging_client = pools["messaging"]
    auth_client = pools["auth"]

    chat_resp = await messaging_client.get(f"/conversations/{conversation_id}", headers=internal_headers)
    if chat_resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation_data = chat_resp.json()
    customer_id = conversation_data.get("customer_id")
    agent_id = conversation_data.get("agent_id")

    customer_data = None
    agent_data = None

    if customer_id:
       customer_resp = await auth_client.get(f"/users/customers/{customer_id}", headers={
           "Authorization": token})
       if customer_resp.status_code == 200:
            customer_data = customer_resp.json()

    if agent_id:
        agent_resp = await auth_client.get(f"/users/service-agents/{agent_id}", headers={
            "Authorization": token})
        if agent_resp.status_code == 200:
            agent_data = agent_resp.json()

    return {
        "conversation": conversation_data,
        "customer": customer_data,
        "agent": agent_data
    }

@router.get("/agents_chats")
async def get_agents_chat_conversations(request: Request):
    # 0. Get the token from the incoming headers
    token = request.headers.get("Authorization")

    if not token:
        raise HTTPException(status_code=401, detail="Missing Token")

        # 1. Decode the token in the Gateway
    try:
        # Strip "Bearer " prefix if present
        actual_token = token.split(" ")[1] if " " in token else token
        payload = jwt.decode(actual_token, settings.secret_key, algorithms=[settings.algorithm])

        user_id = str(payload.get("sub"))  # Or however you store the ID
        user_role = payload.get("role")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Token")

        # 2. Build the "Internal" headers your microservices expect
    internal_headers = {
        "Authorization": token,
        "X-User-ID": user_id,
        "X-User-Role": user_role,
        "X-Request-ID": request.headers.get("X-Request-ID", "gateway-generated")
    }

    messaging_client = pools["messaging"]
    auth_client = pools["auth"]

    conversations_resp = await messaging_client.get("/conversations/agents_chats", headers=internal_headers)
    conversations_data = conversations_resp.json()

    enriched_conversations = []
    for convo in conversations_data:
        customer_id = convo.get("customer_id")
        customer_data = None

        if customer_id:
            customer_resp = await auth_client.get(f"/users/customers/{customer_id}", headers={
                "Authorization": token})
            if customer_resp.status_code == 200:
                customer_data = customer_resp.json()

        enriched_conversations.append({
            **convo,
            "customer": customer_data
        })

    return {
        "conversations": enriched_conversations
    }

@router.get("/customers_chats")
async def get_customers_chat_conversations(request: Request):
    # 0. Get the token from the incoming headers
    token = request.headers.get("Authorization")

    if not token:
        raise HTTPException(status_code=401, detail="Missing Token")

        # 1. Decode the token in the Gateway
    try:
        # Strip "Bearer " prefix if present
        actual_token = token.split(" ")[1] if " " in token else token
        payload = jwt.decode(actual_token, settings.secret_key, algorithms=[settings.algorithm])

        user_id = str(payload.get("sub"))  # Or however you store the ID
        user_role = payload.get("role")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Token")

        # 2. Build the "Internal" headers your microservices expect
    internal_headers = {
        "Authorization": token,
        "X-User-ID": user_id,
        "X-User-Role": user_role,
        "X-Request-ID": request.headers.get("X-Request-ID", "gateway-generated")
    }

    messaging_client = pools["messaging"]
    auth_client = pools["auth"]


    conversations_resp = await messaging_client.get("/conversations/customers_chats",
                                                    headers=internal_headers)
    conversations_data = conversations_resp.json()

    enriched_conversations = []
    for convo in conversations_data:
        agent_id = convo.get("agent_id")
        agent_data = None

        if agent_id:
            agents_resp = await auth_client.get(f"/users/service-agents/{agent_id}", headers={
                "Authorization": token})
            if agents_resp.status_code == 200:
                agent_data = agents_resp.json()

        enriched_conversations.append({
            **convo,
            "agent": agent_data
        })

    return {
        "conversations": enriched_conversations
    }

@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_to_reporting(
    path: str,
    request: Request,
    user: dict = Depends(get_user_payload),
):
    client = pools["messaging"]

    # Build forwarded headers — pass the original auth header through
    # and inject the validated user_id so the reporting service trusts it
    headers = dict(request.headers)
    headers.pop("host", None)  # never forward the Host header

    if user:
        # The reporting service can now trust X-User-ID without calling auth itself
        headers["X-User-ID"]   = user["sub"]
        headers["X-User-Role"] = user.get("role", "")
        headers["X-Request-ID"] = getattr(request.state, "request_id", "")

    body = await request.body()

    try:
        resp = await client.request(
            method=request.method,
            url=f"/{path}",
            headers=headers,
            content=body,
            params=request.query_params,
        )
    except httpx.TimeoutException:
        raise HTTPException(504, "Messaging service timed out")
    except httpx.RequestError:
        raise HTTPException(503, "Messaging service unreachable")

    # Stream the response back to the client
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
        media_type=resp.headers.get("content-type"),
    )