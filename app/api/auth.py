"""
User Authentication API endpoints

Provides email/password authentication for regular (mobile) users:
  POST /api/auth/register  — create account with email + password
  POST /api/auth/login     — email + password login, returns JWT tokens
  POST /api/auth/refresh   — exchange refresh token for new access token

The users table is extended with a password_hash column (added automatically
on first use). Email lookup goes through the existing user_emails table.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.database import get_db_cursor
from app.utils.security import hash_password, verify_password
from app.utils.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.services.system_logs_service import SystemLogsService

router = APIRouter(prefix="/api/auth", tags=["User Authentication"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=64)
    last_name: str = Field(..., min_length=1, max_length=64)
    middle_name: str | None = Field(None, max_length=64)
    suffix: str | None = Field(None, max_length=16)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    phone_number: str = Field(..., min_length=11, max_length=11)
    house_address: str = Field(..., min_length=1)
    barangay: str = Field(..., min_length=1, max_length=64)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RegisterResponse(BaseModel):
    success: bool
    message: str
    user_id: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Schema migration helper
# ---------------------------------------------------------------------------

def _ensure_password_column(cur) -> None:
    """Add password_hash column to users table if it doesn't exist."""
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'password_hash'
            ) THEN
                ALTER TABLE users ADD COLUMN password_hash TEXT;
            END IF;
        END
        $$;
        """
    )


# ---------------------------------------------------------------------------
# POST /api/auth/register
# ---------------------------------------------------------------------------

@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(data: RegisterRequest):
    """
    Register a new user with email and password.

    Creates a row in `users` (with hashed password) and a matching row in
    `user_emails` so that the email can be used for login.
    """
    with get_db_cursor() as cur:
        _ensure_password_column(cur)

        # Check duplicate email
        cur.execute(
            "SELECT 1 FROM user_emails WHERE LOWER(email) = LOWER(%s) LIMIT 1",
            (data.email,),
        )
        if cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered.",
            )

        # Check duplicate phone
        cur.execute(
            "SELECT 1 FROM users WHERE phone_number = %s LIMIT 1",
            (data.phone_number,),
        )
        if cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phone number is already registered.",
            )

        user_id = str(uuid.uuid4())
        hashed = hash_password(data.password)

        cur.execute(
            """
            INSERT INTO users
                (id, first_name, middle_name, last_name, suffix,
                 house_address, barangay, phone_number, role,
                 is_verified, password_hash, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                data.first_name,
                data.middle_name,
                data.last_name,
                data.suffix,
                data.house_address,
                data.barangay,
                data.phone_number,
                "resident",
                False,
                hashed,
                datetime.utcnow(),
                datetime.utcnow(),
            ),
        )

        # Create user_emails row
        cur.execute(
            """
            INSERT INTO user_emails (user_id, email, is_verified, is_primary, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, data.email, False, True, datetime.utcnow()),
        )

        token_data = {"sub": user_id, "role": "resident"}
        access = create_access_token(token_data)
        refresh = create_refresh_token(token_data)

        SystemLogsService.create_log(
            action="User Registration",
            status="Success",
            details=f"New user registered: {data.email}",
            user=user_id,
            role="resident",
        )

        return RegisterResponse(
            success=True,
            message="Registration successful.",
            user_id=user_id,
            access_token=access,
            refresh_token=refresh,
        )


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest):
    """
    Authenticate a user with email and password.

    Looks up the email in `user_emails`, fetches the corresponding user,
    verifies the password, and returns JWT access + refresh tokens.
    """
    generic_error = "Incorrect email or password."

    with get_db_cursor() as cur:
        _ensure_password_column(cur)

        # Find user by email
        cur.execute(
            """
            SELECT u.id, u.password_hash, u.role, u.is_verified,
                   u.first_name, u.last_name
            FROM user_emails ue
            JOIN users u ON u.id = ue.user_id
            WHERE LOWER(ue.email) = LOWER(%s) AND ue.is_primary = TRUE
            LIMIT 1
            """,
            (data.email,),
        )
        row = cur.fetchone()

        if not row or not row["password_hash"]:
            SystemLogsService.create_log(
                action="User Login",
                status="Failed",
                details=f"Login failed for '{data.email}' (user not found or no password set).",
                user=data.email,
                role="resident",
            )
            raise HTTPException(status_code=401, detail=generic_error)

        if not verify_password(data.password, row["password_hash"]):
            SystemLogsService.create_log(
                action="User Login",
                status="Failed",
                details=f"Login failed for '{data.email}' (wrong password).",
                user=data.email,
                role="resident",
            )
            raise HTTPException(status_code=401, detail=generic_error)

        token_data = {"sub": row["id"], "role": row["role"]}
        access = create_access_token(token_data)
        refresh = create_refresh_token(token_data)

        SystemLogsService.create_log(
            action="User Login",
            status="Success",
            details=f"User logged in: {data.email}",
            user=row["id"],
            role=row["role"],
        )

        return TokenResponse(access_token=access, refresh_token=refresh)


# ---------------------------------------------------------------------------
# POST /api/auth/refresh
# ---------------------------------------------------------------------------

@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest):
    """
    Exchange a valid refresh token for a fresh pair of access + refresh tokens.
    """
    payload = decode_token(data.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. A refresh token is required.",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
        )

    # Verify user still exists
    with get_db_cursor() as cur:
        cur.execute("SELECT id, role FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User no longer exists.",
            )

    token_data = {"sub": user["id"], "role": user["role"]}
    access = create_access_token(token_data)
    refresh_tok = create_refresh_token(token_data)

    return TokenResponse(access_token=access, refresh_token=refresh_tok)
