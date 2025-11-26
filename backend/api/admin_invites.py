# backend/api/admin_invites.py

from fastapi import APIRouter, HTTPException, BackgroundTasks
from backend.models.admin_invites import (
    AdminInviteCreate, AdminInviteResponse, SetPasswordRequest
)
from backend.database import get_db_cursor
from passlib.hash import bcrypt
from datetime import datetime, timedelta
import secrets, smtplib, ssl
from email.message import EmailMessage
import uuid

router = APIRouter(prefix='/api/admin-invites', tags=['AdminInvites'])

SMTP_USER = "yourapp@gmail.com"
SMTP_PASS = "YOUR_GMAIL_APP_PASSWORD"
FRONTEND_URL = "https://your-frontend.com"  # Adjust!

def send_invite_email(email: str, link: str):
    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = email
    msg["Subject"] = "HydroMet Admin Invitation"
    msg.set_content(f"Set your HydroMet admin account password: {link}\n\nThis invite expires in 24h.")
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)

@router.post("/invite", response_model=AdminInviteResponse)
async def create_admin_invite(invite: AdminInviteCreate, background_tasks: BackgroundTasks):
    token = secrets.token_urlsafe(48)
    created_at = datetime.utcnow()
    expires_at = created_at + timedelta(hours=24)
    with get_db_cursor() as cur:
        # Check for existing admin or pending invite
        cur.execute("SELECT 1 FROM admin WHERE email = %s", (invite.email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Admin with this email already exists.")
        cur.execute("SELECT 1 FROM admin_invites WHERE email = %s AND used = false AND expires_at > now()", (invite.email,))
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
        if invite['expires_at'] < datetime.utcnow():
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
            (datetime.utcnow(), req.token)
        )
    return AdminInviteResponse(success=True, message="Admin account created! You can now log in.", invite=None)
