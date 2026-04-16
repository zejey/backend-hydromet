"""
Centralized JWT utility module

Handles token creation and validation for both admin and user authentication.
Supports access tokens (short-lived) and refresh tokens (long-lived).
"""

import os
import datetime
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

SECRET_KEY = os.environ.get(
    "SECRET_KEY", "DEV_ONLY_SUPER_SECRET_KEY_CHANGE_ME_32+CHARS"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

if len(SECRET_KEY.encode("utf-8")) < 32:
    print(
        "WARNING: SECRET_KEY is shorter than 32 bytes; "
        "use a longer SECRET_KEY to avoid weak JWT HMAC secrets.",
        flush=True,
    )

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def create_access_token(
    data: dict, expires_delta: Optional[int] = None
) -> str:
    """Create a short-lived access token."""
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(
        minutes=expires_delta or ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Create a long-lived refresh token."""
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired.",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
        )


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """FastAPI dependency — extracts user payload from access token."""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
        )
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
        )
    return payload
