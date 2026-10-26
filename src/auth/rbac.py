import os
from typing import List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if len(SECRET_KEY) < 32 or any(
    marker in SECRET_KEY.lower()
    for marker in ("replace_with", "change_me", "your_secret")
):
    raise RuntimeError(
        "JWT_SECRET_KEY must be configured with a non-placeholder value "
        "of at least 32 characters."
    )
ALGORITHM = "HS256"
security = HTTPBearer()


class User(BaseModel):
    """Authenticated user context extracted from a verified JWT."""

    username: str
    roles: List[str] = Field(default_factory=list)
    clearance_level: int = 1


def decode_jwt_token(token: str) -> User:
    """Verify JWT signature and validate the required subject claim."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        roles: List[str] = payload.get("roles", [])
        clearance_level: int = payload.get("clearance_level", 1)
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token payload.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return User(username=username, roles=roles, clearance_level=clearance_level)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    return decode_jwt_token(credentials.credentials)


class RoleChecker:
    """Dependency factory checking role intersection and minimum clearance."""

    def __init__(self, allowed_roles: List[str], min_clearance: int = 1):
        self.allowed_roles = allowed_roles
        self.min_clearance = min_clearance

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.clearance_level < self.min_clearance:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient clearance. Required level: {self.min_clearance}, "
                    f"user level: {current_user.clearance_level}"
                ),
            )
        has_role = any(role in self.allowed_roles for role in current_user.roles)
        if self.allowed_roles and not has_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have a required role.",
            )
        return current_user
