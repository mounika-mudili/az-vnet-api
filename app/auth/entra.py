"""Entra ID access token validation.

Authorization is flat on purpose: a valid token for this API reaches every endpoint.
No roles, groups or ownership checks.
"""

import logging
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False, description="Entra ID access token")

UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


class Principal(BaseModel):
    subject: str
    display_name: str


@lru_cache
def _jwk_client(tenant_id: str) -> PyJWKClient:
    return PyJWKClient(
        f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
        cache_keys=True,
    )


def _accepted_audiences(client_id: str) -> list[str]:
    return [client_id, f"api://{client_id}"]


def _accepted_issuers(tenant_id: str) -> set[str]:
    return {
        f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        f"https://sts.windows.net/{tenant_id}/",
    }


def _principal_from_claims(claims: dict) -> Principal:
    subject = claims.get("oid") or claims.get("sub") or "unknown"
    display_name = (
        claims.get("preferred_username") or claims.get("upn") or claims.get("email") or claims.get("appid") or subject
    )
    return Principal(subject=subject, display_name=display_name)


def require_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers=UNAUTHENTICATED_HEADERS,
        )

    token = credentials.credentials
    try:
        signing_key = _jwk_client(settings.azure_tenant_id).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=_accepted_audiences(settings.entra_api_client_id),
            options={"verify_iss": False, "require": ["exp", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        logger.info("Rejected token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers=UNAUTHENTICATED_HEADERS,
        ) from exc

    if claims.get("iss") not in _accepted_issuers(settings.azure_tenant_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token was not issued by the expected tenant",
            headers=UNAUTHENTICATED_HEADERS,
        )

    return _principal_from_claims(claims)
