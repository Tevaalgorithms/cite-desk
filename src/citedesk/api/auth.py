"""Sign-in tokens and roles.

Local development uses tokens signed with a shared secret (HS256). A production deployment
should verify tokens from an OIDC provider instead (planned); only `decode_token` would change.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

import jwt
from fastapi import Depends, HTTPException, Request, status

Role = Literal["analyst", "reviewer", "admin"]
ALL_ROLES: tuple[Role, ...] = ("analyst", "reviewer", "admin")
_ALGORITHM = "HS256"
_ISSUER = "citedesk-dev"


class InvalidTokenError(ValueError):
    pass


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: Role


def issue_token(secret: str, user_id: str, role: Role, *, ttl_seconds: int = 3600) -> str:
    now = int(time.time())
    claims = {"sub": user_id, "role": role, "iss": _ISSUER, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(claims, secret, algorithm=_ALGORITHM)


def decode_token(secret: str, token: str) -> Principal:
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"require": ["sub", "role", "exp"]},
        )
    except jwt.PyJWTError as error:
        raise InvalidTokenError(str(error)) from error
    role = claims["role"]
    if role not in ALL_ROLES:
        raise InvalidTokenError(f"Unknown role {role!r}")
    return Principal(user_id=str(claims["sub"]), role=role)


def current_principal(request: Request) -> Principal:
    """The signed-in user, or a 401. Used as a FastAPI dependency."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    try:
        return decode_token(request.app.state.jwt_secret, token)
    except InvalidTokenError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from error


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    """Build a dependency that allows only the given roles (403 otherwise)."""

    def check(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role may not do this")
        return principal

    return check
