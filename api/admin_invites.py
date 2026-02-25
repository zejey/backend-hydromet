import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks
from backend.models.admin_invites import (
    AdminInviteCreate, AdminInviteResponse, SetPasswordRequest
)
from backend.database import get_db_cursor
from passlib.hash import bcrypt

# --- Brevo (Sendinblue) imports ---
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

router = APIRouter(prefix='/api/admin-invites', tags=['AdminInvites'])

# Brevo configuration
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
FROM_EMAIL = os.environ.get("BREVO_SENDER")
FRONTEND_URL = os.environ.get("FRONTEND_URL")

def send_invite_email(email: str, link: str):
    """Send the invite email using Brevo (Sendinblue)"""
    
    if not BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY is not configured")
    
    if not FROM_EMAIL:
        raise RuntimeError("BREVO_SENDER is not configured")
    
    # Configure Brevo API
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = BREVO_API_KEY
    
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )
    
    html_content = f"""
    <html>
    <body>
        <p>You have been invited to become a HydroMet admin.</p>
        <p><strong>Set your password with this link:</strong><br>
        <a href="{link}">{link}</a></p>
        <p>This invite expires in 24 hours.</p>
    </body>
    </html>
    """
    
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": email}],
        sender={"name": "HydroMet Admin System", "email": FROM_EMAIL},
        subject="HydroMet Admin Invitation",
        html_content=html_content
    )
    
    try:
        api_response = api_instance.send_transac_email(send_smtp_email)
        print(f"✅ Brevo: Invite sent to {email}. Message ID: {api_response.message_id}")
    except ApiException as e:
        print(f"❌ Brevo API Exception: {e}")
        raise RuntimeError(f"Failed to send email via Brevo: {e}")
    except Exception as e:
        print(f"❌ EMAIL SEND ERROR: {type(e).__name__}: {e}")
        raise

@router.post("/invite", response_model=AdminInviteResponse)
async def create_admin_invite(invite: AdminInviteCreate, background_tasks: BackgroundTasks):
    token = secrets.token_urlsafe(48)
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(hours=24)
    
    with get_db_cursor() as cur:
        # Check for existing admin
        cur.execute("SELECT 1 FROM admin WHERE email = %s", (invite.email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Admin with this email already exists.")
        
        # DELETE old unused invites for this email (instead of raising error)
        cur.execute(
            "DELETE FROM admin_invites WHERE email = %s AND used = false",
            (invite.email,)
        )
        
        # Now insert the new invite
        cur.execute(
            """
            INSERT INTO admin_invites (email, role, token, created_at, expires_at, used, invited_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, email, role, token, created_at, expires_at, used, used_at, invited_by;
            """,
            (invite.email, invite.role, token, created_at, expires_at, False, invite.invited_by),
        )
        res = cur.fetchone()
    
    # FIXED: Add /#/ for hash routing
    invite_link = f"{FRONTEND_URL}/#/set-password?token={token}"
    background_tasks.add_task(send_invite_email, invite.email, invite_link)
    
    return AdminInviteResponse(
        success=True, 
        message="Admin invite sent.", 
        invite=res
    )

@router.post("/set-password", response_model=AdminInviteResponse)
async def set_admin_password(req: SetPasswordRequest):
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM admin_invites WHERE token = %s", (req.token,))
        invite = cur.fetchone()
        
        if not invite:
            raise HTTPException(status_code=400, detail="Invalid token.")
        if invite['used']:
            raise HTTPException(status_code=400, detail="Invite already used.")
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
    
    return AdminInviteResponse(
        success=True, 
        message="Admin account created! You can now log in.", 
        invite=None
    )
