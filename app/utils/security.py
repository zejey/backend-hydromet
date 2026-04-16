"""
Centralized password hashing utility

Uses passlib with bcrypt backend. Handles bcrypt's 72-byte UTF-8 limit.
"""

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _truncate_to_bcrypt_limit(password: str) -> str:
    """Truncate password to bcrypt's 72-byte UTF-8 limit."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) <= 72:
        return password
    password_bytes = password_bytes[:72]
    # Ensure we don't cut in the middle of a multi-byte character
    for i in range(4):
        try:
            return password_bytes[: 72 - i].decode("utf-8")
        except UnicodeDecodeError:
            continue
    return password  # fallback (shouldn't happen)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(_truncate_to_bcrypt_limit(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    return pwd_context.verify(
        _truncate_to_bcrypt_limit(plain_password), hashed_password
    )
