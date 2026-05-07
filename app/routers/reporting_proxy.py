from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from app.middleware.auth import validate_token, get_user_payload
from app.dependencies.clients import pools
from jose import jwt
from app.config import settings
from uuid import UUID
import asyncio
import httpx

router = APIRouter()

async def get_display_id(token):
    auth_client = pools["auth"]

    profile_resp = await auth_client.get("/users/me", headers={"Authorization": token})
    return profile_resp.json().get("profile", {}).get("display_id")

@router.get("/all")
async def get_all_reports_with_customers(request: Request):

    token = request.headers.get("Authorization")

    if not token:
        raise HTTPException(status_code=401, detail="Missing Token")

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

    # 1. Get the internal clients
    report_client = pools["reporting"]
    auth_client = pools["auth"]

    # 2. Fetch all base reports
    report_resp = await report_client.get("/reports/all", headers=internal_headers)
    if report_resp.status_code != 200:
        raise HTTPException(status_code=report_resp.status_code, detail="Failed to fetch reports")

    reports_list = report_resp.json()  # Assuming this returns a list of report dicts

    # 3. Identify unique customer IDs to avoid redundant API calls
    # We use a set to ensure we only fetch each customer once
    unique_customer_ids = {r.get("customer_id") for r in reports_list if r.get("customer_id")}

    # 4. Fetch all unique customer profiles in PARALLEL
    async def fetch_customer(cid):
        resp = await auth_client.get(f"/users/customers/{cid}", headers={"Authorization": token})
        return cid, resp.json() if resp.status_code == 200 else None

    # Create a list of tasks and run them concurrently
    tasks = [fetch_customer(cid) for cid in unique_customer_ids]
    customer_results = await asyncio.gather(*tasks)

    # 5. Create a lookup map: {customer_id: profile_data}
    customer_map = {cid: profile for cid, profile in customer_results if profile}

    # 6. Merge the data
    enriched_reports = []
    for report in reports_list:
        cid = report.get("customer_id")
        enriched_reports.append({
            **report,
            "customer": customer_map.get(cid)  # Attach profile or None if not found
        })

    return {
        "reports": enriched_reports
    }

@router.get("/assigned")
async def get_engineers_assigned_reports_with_customers(request: Request):

    token = request.headers.get("Authorization")
    engineer_id = await get_display_id(token)

    if not token:
        raise HTTPException(status_code=401, detail="Missing Token")

    try:
        # Strip "Bearer " prefix if present
        actual_token = token.split(" ")[1] if " " in token else token
        payload = jwt.decode(actual_token, settings.secret_key, algorithms=[settings.algorithm])

        user_id = str(payload.get("sub"))
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

    # 1. Get the internal clients
    report_client = pools["reporting"]
    auth_client = pools["auth"]

    # 2. Fetch all base reports
    report_resp = await report_client.get(f"/reports/engineers/{engineer_id}", headers=internal_headers)
    if report_resp.status_code != 200:
        raise HTTPException(status_code=report_resp.status_code, detail="Failed to fetch reports")

    reports_list = report_resp.json()  # Assuming this returns a list of report dicts

    # 3. Identify unique customer IDs to avoid redundant API calls
    # We use a set to ensure we only fetch each customer once
    unique_customer_ids = {r.get("customer_id") for r in reports_list if r.get("customer_id")}

    # 4. Fetch all unique customer profiles in PARALLEL
    async def fetch_customer(cid):
        resp = await auth_client.get(f"/users/customers/{cid}", headers={"Authorization": token})
        return cid, resp.json() if resp.status_code == 200 else None

    # Create a list of tasks and run them concurrently
    tasks = [fetch_customer(cid) for cid in unique_customer_ids]
    customer_results = await asyncio.gather(*tasks)

    # 5. Create a lookup map: {customer_id: profile_data}
    customer_map = {cid: profile for cid, profile in customer_results if profile}

    # 6. Merge the data
    enriched_reports = []
    for report in reports_list:
        cid = report.get("customer_id")
        enriched_reports.append({
            **report,
            "customer": customer_map.get(cid)  # Attach profile or None if not found
        })

    return {
        "reports": enriched_reports
    }

@router.get("/test")
async def test_gateway():
    return {"Gate Opened"}

@router.get("/{report_id}")
async def get_report_with_customer(report_id: UUID, request: Request):
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

    # 1. Get the internal clients from our pools
    report_client = pools["reporting"]
    auth_client = pools["auth"]


    # 2. Fetch the base report
    report_resp = await report_client.get(f"/reports/{report_id}", headers=internal_headers)
    if report_resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Report not found")

    report_data = report_resp.json()
    customer_id = report_data.get("customer_id")

    # 3. Fetch the customer profile if an ID exists
    customer_data = None
    if customer_id:
        auth_resp = await auth_client.get(f"/users/customers/{customer_id}", headers={"Authorization": token})
        if auth_resp.status_code == 200:
            customer_data = auth_resp.json()

    # 4. Merge and return
    return {"message": "Merged report and customer data", "report": report_data, "customer":
        customer_data}

@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_to_reporting(
    path: str,
    request: Request,
    user: dict = Depends(get_user_payload),
):
    client = pools["reporting"]

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
        raise HTTPException(504, "Reporting service timed out")
    except httpx.RequestError:
        raise HTTPException(503, "Reporting service unreachable")

    # Stream the response back to the client
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
        media_type=resp.headers.get("content-type"),
    )