from jose import jwt, JWTError
from fastapi import HTTPException, Request
from app.config import settings

# Routes that don't require a token
PUBLIC_PATHS = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/auth/verify-email",
}

def validate_token(path: str, authorization: str | None) -> dict | None:
    """
    Returns the decoded payload if the token is valid.
    Returns None for public routes.
    Raises HTTPException for invalid tokens on protected routes.
    """
    if path in PUBLIC_PATHS:
        return None

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")

async def get_user_payload(request: Request) -> dict | None:
    return validate_token(
        path=str(request.url.path),
        authorization=request.headers.get("Authorization"),
    )