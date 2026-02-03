from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr
from backend.database import get_db_cursor
from datetime import datetime, timedelta, timezone
import secrets, os

# --- Brevo imports ---
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

router = APIRouter(prefix="/api/auth", tags=["Auth"])

# Brevo configuration
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
FROM_EMAIL = os.environ.get("BREVO_SENDER")
FRONTEND_URL = os.environ.get("FRONTEND_URL")

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
    """Send password reset email using Brevo"""
    if not BREVO_API_KEY or not FROM_EMAIL:
        raise RuntimeError("Email service not configured")

    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = BREVO_API_KEY

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    html_content = f"""
    <html>
    <body>
        <h2>Password Reset Request</h2>
        <p>You (or someone) requested a password reset for your HydroMet admin account.</p>
        <p><strong>Click this link to reset your password:</strong><br>
        <a href="{link}">{link}</a></p>
        <p>This link expires in {RESET_TOKEN_EXPIRY_HOURS} hour(s).</p>
        <p>If you did not request this, please ignore this email.</p>
    </body>
    </html>
    """

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": recipient_email}],
        sender={"name": "HydroMet Admin System", "email": FROM_EMAIL},
        subject="Reset Your HydroMet Password",
        html_content=html_content
    )

    try:
        api_response = api_instance.send_transac_email(send_smtp_email)
        print(f"✅ Brevo: Password reset email sent to {recipient_email}. Message ID: {api_response.message_id}")
    except ApiException as e:
        print(f"❌ Brevo API Exception: {e}")
        raise RuntimeError(f"Failed to send email via Brevo: {e}")
    except Exception as e:
        print(f"❌ EMAIL SEND ERROR: {e}")
        raise

@router.post("/forgot-password", response_model=GenericResponse)
async def forgot_password(req: ForgotPasswordRequest, background_tasks: BackgroundTasks):
    email = req.email.lower().strip()
    token = secrets.token_urlsafe(48)
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(hours=RESET_TOKEN_EXPIRY_HOURS)

    with get_db_cursor() as cur:
        # Check if admin exists (optional - for privacy you may always send success)
        cur.execute("SELECT 1 FROM admin WHERE email = %s", (email,))
        user_exists = bool(cur.fetchone())

        # Delete any old unused tokens for this email
        cur.execute("DELETE FROM auth_password_resets WHERE email = %s AND used = false", (email,))

        # Insert new token
        cur.execute(
            """
            INSERT INTO auth_password_resets (email, token, created_at, expires_at, used)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (email, token, created_at, expires_at, False),
        )

    # Build frontend link with hash routing
    base = FRONTEND_URL.rstrip("/")
    reset_link = f"{base}/#/reset-password?token={token}"

    # Send email in background
    background_tasks.add_task(send_reset_email, email, reset_link)

    # For security, always return success (don't reveal if email exists)
    return GenericResponse(
        success=True, 
        message="If this email exists, a reset link has been sent."
    )

@router.post("/reset-password", response_model=GenericResponse)
async def reset_password(req: ResetPasswordRequest):
    token = req.token
    new_password = req.password

    if not token or not new_password or len(new_password) < 8:
        raise HTTPException(
            status_code=400, 
            detail="Invalid token or password must be at least 8 characters."
        )

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

        # Update admin password
        cur.execute(
            "UPDATE admin SET password_hash = %s WHERE email = %s RETURNING id;",
            (password_hash, email),
        )
        updated = cur.fetchone()
        
        if not updated:
            raise HTTPException(status_code=400, detail="Account not found.")

        # Mark token as used
        cur.execute(
            "UPDATE auth_password_resets SET used = true, used_at = %s WHERE token = %s",
            (datetime.now(timezone.utc), token),
        )

    return GenericResponse(
        success=True, 
        message="Password has been reset. You may now log in."
    )
