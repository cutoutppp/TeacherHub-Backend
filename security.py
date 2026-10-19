import os
import logging
import jwt
from fastapi import Request, HTTPException, status, Depends
from auth_router import SECRET_KEY, ALGORITHM
from auth_db import ADMIN_TEACCODES

logger = logging.getLogger("teacherhub.auth")

def get_auth_mode() -> str:
    """Read AUTH_MODE from environment: 'off', 'log' (default), or 'enforce'."""
    return os.getenv("AUTH_MODE", "log").strip().lower()

def _log_auth_event(reason: str, request: Request):
    """Log authentication anomalies without recording sensitive tokens, PINs, or bodies."""
    path = request.url.path
    method = request.method
    origin = request.headers.get("origin", "no-origin")
    logger.warning("[AUTH-LOG] %s path=%s method=%s origin=%s", reason, path, method, origin)

async def get_current_user(request: Request) -> dict | None:
    """Dependency to validate Bearer JWT token.
    In 'log' mode, anomalies are recorded but requests are never rejected.
    In 'enforce' mode, missing/invalid/expired tokens return 401."""
    mode = get_auth_mode()
    if mode == "off":
        return None

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        if mode == "enforce":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        _log_auth_event("missing", request)
        return None

    token = auth_header.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = payload.get("user")
        if not user:
            user = {
                "userid": payload.get("sub"),
                "is_admin": payload.get("is_admin", False),
                "teaccode": payload.get("teaccode", "")
            }
        return user
    except jwt.ExpiredSignatureError:
        if mode == "enforce":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        _log_auth_event("expired", request)
        return None
    except Exception:
        if mode == "enforce":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        _log_auth_event("invalid", request)
        return None

async def require_admin(request: Request, user: dict | None = Depends(get_current_user)) -> dict | None:
    """Dependency to verify administrator privileges.
    In 'log' mode, non-admin access is recorded but allowed through.
    In 'enforce' mode, non-admins receive 403 (or 401 if unauthenticated)."""
    mode = get_auth_mode()
    if mode == "off":
        return user

    is_admin = False
    if user:
        is_admin_flag = user.get("is_admin", False)
        teaccode = str(user.get("teaccode", "")).strip()
        if is_admin_flag is True or teaccode in ADMIN_TEACCODES:
            is_admin = True

    if not is_admin:
        if mode == "enforce":
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required"
            )
        _log_auth_event("non-admin", request)
        return user

    return user
