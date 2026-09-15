import os
from typing import List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from jose import JWTError, jwt

# Secret key and algorithm configuration (loaded from environment or defaults)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secret-zero-trust-key-change-in-prod")
ALGORITHM = "HS256"

# FastAPI Bearer security scheme
security = HTTPBearer()


class User(BaseModel):
    """Represents the authenticated user context extracted from JWT tokens."""
    username: str
    roles: List[str] = Field(default_factory=list)
    clearance_level: int = 1


def decode_jwt_token(token: str) -> User:
    """Decodes a JWT token, verifies signature, and returns a User object."""
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

        return User(
            username=username,
            roles=roles,
            clearance_level=clearance_level
        )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """FastAPI dependency to extract and authenticate the current user from Bearer token."""
    return decode_jwt_token(credentials.credentials)


class RoleChecker:
    """
    FastAPI dependency factory for verifying whether a user possesses
    at least one required role or sufficient clearance level.
    """

    def __init__(self, allowed_roles: List[str], min_clearance: int = 1):
        self.allowed_roles = allowed_roles
        self.min_clearance = min_clearance

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        # Check clearance level first
        if current_user.clearance_level < self.min_clearance:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient clearance. Required level: {self.min_clearance}, User level: {current_user.clearance_level}"
            )

        # Check role match (user must have at least one allowed role)
        has_role = any(role in self.allowed_roles for role in current_user.roles)
        if not has_role and self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User missing required roles: {self.allowed_roles}"
            )

        return current_user


if __name__ == "__main__":
    # --- Quick Verification Test ---
    test_payload = {
        "sub": "zainab",
        "roles": ["engineering", "security"],
        "clearance_level": 3
    }

    # Generate test token
    token = jwt.encode(test_payload, SECRET_KEY, algorithm=ALGORITHM)
    print(f"Generated Test Token:\n{token}\n")

    # Decode and verify token
    user = decode_jwt_token(token)
    print(f"Decoded User Context: Username='{user.username}', Roles={user.roles}, Clearance={user.clearance_level}")