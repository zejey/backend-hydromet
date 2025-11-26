from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr
from backend.database import get_db_cursor
from datetime import datetime, timedelta, timezone
from email.utils import formataddr
import secrets, os

# SendGrid
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

router = APIRouter(prefix="/api/auth", tags=["Auth"])

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "your_sendgrid_api_key")
FROM_EMAIL = os.environ.get("SENDGRID_SENDER", "your_verified_sender@email.com")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://your-frontend.com")

RESET_TOKEN_EXPIRY_HOURS = int(os.environ.get("RESET_TOKEN_EXPIRY_HOURS", "2"))

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    password: str

class GenericResponse(BaseModel):
    success: bool
    message: str

def send_reset_email(recipient_email: str, link: str):
    html_content = f"""
    <p>You (or someone) requested a password reset for your account.</p>
    <p>Click the link below to set a new password. This link expires in {RESET_TOKEN_EXPIRY_HOURS} hour(s).</p>
    <p><a href="{link}">{link}</a></p>
    <p>If you did not request this, please ignore this email.</p>
    """
    message = Mail(
        from_email=formataddr(("Support", FROM_EMAIL)),
        to_emails=recipient_email,
        subject="Password reset request",
        html_content=html_content,
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        resp = sg.send(message)
        print(f"SendGrid: reset email sent to {recipient_email}, status {resp.status_code}")
    except Exception as e:
        print("SendGrid error:", e)

@router.post("/forgot-password", response_model=GenericResponse)
async def forgot_password(req: ForgotPasswordRequest, background_tasks: BackgroundTasks):
    email = req.email.lower().strip()
    token = secrets.token_urlsafe(48)
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(hours=RESET_TOKEN_EXPIRY_HOURS)

    with get_db_cursor() as cur:
        # Optionally check user exists (for privacy you may always return success)
        cur.execute("SELECT 1 FROM admin WHERE email = %s", (email,))
        user_exists = bool(cur.fetchone())

        # Insert token record regardless, but if user doesn't exist you can still insert (or skip)
        cur.execute(
            """
            INSERT INTO auth_password_resets (email, token, created_at, expires_at, used)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (email, token, created_at, expires_at, False),
        )
        _ = cur.fetchone()

    # Build a frontend link. For static hosts using hash routing:
    base = FRONTEND_URL.rstrip("/")
    reset_link = f"{base}/#/reset-password?token={token}"

    # Send email in background
    background_tasks.add_task(send_reset_email, email, reset_link)

    # For security, do not reveal whether email exists. Always return success.
    return GenericResponse(success=True, message="If this email exists, a reset link has been sent.")

@router.post("/reset-password", response_model=GenericResponse)
async def reset_password(req: ResetPasswordRequest):
    token = req.token
    new_password = req.password

    if not token or not new_password or len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Invalid token or password requirements not met.")

    # Use passlib or your hashing function
    from passlib.hash import bcrypt
    password_hash = bcrypt.hash(new_password)

    with get_db_cursor() as cur:
        # Look up the token
        cur.execute("SELECT * FROM auth_password_resets WHERE token = %s", (token,))
        record = cur.fetchone()
        if not record:
            raise HTTPException(status_code=400, detail="Invalid token.")
        if record["used"]:
            raise HTTPException(status_code=400, detail="Token already used.")
        if record["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Token expired.")
        email = record["email"]

        # Update user's password in the admin table (or users table if applicable)
        cur.execute(
            "UPDATE admin SET password_hash = %s WHERE email = %s RETURNING id;",
            (password_hash, email),
        )
        updated = cur.fetchone()
        if not updated:
            # If you have separate users table, update that instead. Fail securely.
            raise HTTPException(status_code=400, detail="Account not found.")

        # Mark token used
        cur.execute(
            "UPDATE auth_password_resets SET used = true, used_at = %s WHERE token = %s",
            (datetime.now(timezone.utc), token),
        )

    return GenericResponse(success=True, message="Password has been reset. You may now log in.")
