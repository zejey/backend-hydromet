from fastapi import APIRouter, HTTPException, BackgroundTasks
from backend.models.admin_invites import (
    AdminInviteCreate, AdminInviteResponse, SetPasswordRequest
)
from backend.database import get_db_cursor
from passlib.hash import bcrypt
from datetime import datetime, timedelta, timezone
from email.utils import formataddr
import secrets, os, uuid

# --- SendGrid imports ---
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

router = APIRouter(prefix='/api/admin-invites', tags=['AdminInvites'])

# Set your SendGrid API key and verified sender
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "your_sendgrid_api_key")
FROM_EMAIL = os.environ.get("SENDGRID_SENDER", "your_verified_sender@email.com")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://your-frontend.com")

def send_invite_email(email: str, link: str):
    """Send the invite email using SendGrid"""
    html_content = f"""
    <p>You have been invited to become a HydroMet admin.</p>
    <p><strong>Set your password with this link:</strong><br>
    <a href="{link}">{link}</a></p>
    <p>This invite expires in 24 hours.</p>
    """
    message = Mail(
        from_email=formataddr(("HydroMet Admin System", FROM_EMAIL)),
        to_emails=email,
        subject="HydroMet Admin Invitation",
        html_content=html_content
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"SendGrid: Invite sent to {email}. Status code: {response.status_code}")
    except Exception as e:
        print(f"EMAIL SEND ERROR: {e}")

@router.post("/invite", response_model=AdminInviteResponse)
async def create_admin_invite(invite: AdminInviteCreate, background_tasks: BackgroundTasks):
    token = secrets.token_urlsafe(48)
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(hours=24)
    with get_db_cursor() as cur:
        # Check for existing admin or pending invite
        cur.execute("SELECT 1 FROM admin WHERE email = %s", (invite.email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Admin with this email already exists.")
        cur.execute(
            "SELECT 1 FROM admin_invites WHERE email = %s AND used = false AND expires_at > now()", (invite.email,)
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Invite already exists and is still valid.")
        cur.execute(
            """
            INSERT INTO admin_invites (email, role, token, created_at, expires_at, used, invited_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, email, role, token, created_at, expires_at, used, used_at, invited_by;
            """,
            (invite.email, invite.role, token, created_at, expires_at, False, invite.invited_by),
        )
        res = cur.fetchone()
    invite_link = f"{FRONTEND_URL}/set-password?token={token}"
    background_tasks.add_task(send_invite_email, invite.email, invite_link)
    return AdminInviteResponse(success=True, message="Admin invite sent.", invite=res)

@router.post("/set-password", response_model=AdminInviteResponse)
async def set_admin_password(req: SetPasswordRequest):
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM admin_invites WHERE token = %s", (req.token,))
        invite = cur.fetchone()
        if not invite:
            raise HTTPException(status_code=400, detail="Invalid token.")
        if invite['used']:
            raise HTTPException(status_code=400, detail="Invite already used.")
        # compare using timezone-aware now
        if invite['expires_at'] < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Invite expired.")
        email = invite['email']
        role = invite['role']
        username = email.split("@")[0]
        password_hash = bcrypt.hash(req.password)
        uid = str(uuid.uuid4())
        cur.execute(
            """INSERT INTO admin (email, role, username, password_hash, uid)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, email, role, username, uid
            """,
            (email, role, username, password_hash, uid)
        )
        cur.execute(
            "UPDATE admin_invites SET used = true, used_at = %s WHERE token = %s",
            (datetime.now(timezone.utc), req.token)
        )
    return AdminInviteResponse(success=True, message="Admin account created! You can now log in.", invite=None)
