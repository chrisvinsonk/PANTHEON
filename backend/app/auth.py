from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import (
    InvalidTokenError,
    PyJWKClientConnectionError,
    PyJWKClientError,
)

from .config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=4)
def get_jwks_client(issuer: str) -> PyJWKClient:
    return PyJWKClient(f"{issuer.rstrip('/')}/.well-known/jwks.json")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.clerk_issuer:
        raise HTTPException(status_code=503, detail="Authentication is not configured")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        signing_key = get_jwks_client(settings.clerk_issuer).get_signing_key_from_jwt(
            credentials.credentials
        )
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except PyJWKClientConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is unavailable",
        ) from exc
    except (InvalidTokenError, PyJWKClientError) as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if "*" not in settings.cors_origins and claims.get("azp") not in settings.cors_origins:
        raise HTTPException(
            status_code=401,
            detail="Token was not issued for this application origin",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return claims
