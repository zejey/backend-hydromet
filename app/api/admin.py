"""
Admin API endpoints
"""
import uuid
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional
import jwt
import datetime
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer

from app.models.admin import Admin, AdminCreate
from app.database import get_db_cursor
from app.utils.security import hash_password, verify_password
from app.utils.jwt_handler import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
)

# ✅ system logs
from app.services.system_logs_service import SystemLogsService
from app.services.system_settings_service import SystemSettingsService

router = APIRouter(prefix="/api/admins", tags=["Admin Management"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admins/login")

def get_current_admin(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        admin_id = payload.get("sub")
        if admin_id is None:
            raise credentials_exception
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.PyJWTError:
        raise credentials_exception


class Token(BaseModel):
    access_token: str
    token_type: str


@router.get("/", response_model=List[Admin])
async def get_all_admins():
    """Get a list of all admins"""
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT id, email, role, username, uid FROM admin")
            admins = cur.fetchall()
            return [Admin(**admin) for admin in admins]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching admins: {str(e)}",
        )


@router.post("/login", response_model=Token)
async def login(data: dict):
    """
    Admin login endpoint. Receives: {"email": "...", "password": "..."}
    (The "email" field can be either your email address or your username)
    Returns: {"access_token": "...", "token_type": "bearer"}
    """
    login_input = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if not login_input or not password:
        raise HTTPException(
            status_code=400, detail="Email/Username and password are required."
        )

    # bcrypt has a 72-byte input limit (after UTF-8 encoding)
    if len(password.encode("utf-8")) > 72:
        SystemLogsService.create_log(
            action="Login Attempt Failed",
            status="Failed",
            details=f"Admin login failed for '{login_input}' (password too long).",
            user=login_input,
            role="admin",
        )
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    try:
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT id, email, role, username, uid, password_hash
                FROM admin
                WHERE email = %s OR username = %s
                """,
                (login_input, login_input),
            )
            admin_row = cur.fetchone()

            if not admin_row or not verify_password(password, admin_row["password_hash"]):
                SystemLogsService.create_log(
                    action="Login Attempt Failed",
                    status="Failed",
                    details=f"Admin login failed for '{login_input}'.",
                    user=login_input,
                    role="admin",
                )
                raise HTTPException(status_code=401, detail="Incorrect email or password.")

            access_token = create_access_token(
                {
                    "sub": str(admin_row["id"]),
                    "email": admin_row["email"],
                    "role": admin_row["role"],
                }
            )

            SystemLogsService.create_log(
                action="User Login",
                status="Success",
                details=f"Admin '{admin_row['username']}' logged in successfully.",
                user=admin_row["username"],
                user_id=admin_row["id"],
                role=admin_row["role"],
            )

        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"UNEXPECTED LOGIN ERROR: {e}", flush=True)
        SystemLogsService.create_log(
            action="User Login",
            status="Failed",
            details=f"Unexpected login error for '{login_input}': {type(e).__name__}",
            user=login_input,
            role="admin",
        )
        raise HTTPException(status_code=500, detail=f"Login error: {str(e)}")


@router.post("/", response_model=Admin, status_code=status.HTTP_201_CREATED)
async def create_admin(admin_data: AdminCreate):
    """Create a new admin"""
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT id FROM admin WHERE email = %s", (admin_data.email,))
            if cur.fetchone():
                SystemLogsService.create_log(
                    action="User Account Created",
                    status="Failed",
                    details=f"Attempt to create admin failed: email already exists ({admin_data.email}).",
                    user=admin_data.username,
                    role=admin_data.role,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Admin with this email already exists",
                )

            password = admin_data.password
            if len(password.encode("utf-8")) > 72:
                SystemLogsService.create_log(
                    action="User Account Created",
                    status="Failed",
                    details=f"Attempt to create admin failed: password too long for {admin_data.email}.",
                    user=admin_data.username,
                    role=admin_data.role,
                )
                raise HTTPException(
                    status_code=400,
                    detail="Password is too long (over 72 bytes after UTF-8 encoding). Please use a shorter password.",
                )

            password_hash = hash_password(password)

            cur.execute(
                """
                INSERT INTO admin (email, role, username, uid, password_hash)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, email, role, username, uid
                """,
                (
                    admin_data.email,
                    admin_data.role,
                    admin_data.username,
                    admin_data.uid,
                    password_hash,
                ),
            )

            new_admin = cur.fetchone()

            SystemLogsService.create_log(
                action="User Account Created",
                status="Success",
                details=f"Created admin account: {new_admin['username']} ({new_admin['email']}).",
                user=new_admin["username"],
                user_id=new_admin["id"],
                role=new_admin["role"],
            )

            return Admin(**new_admin)

    except HTTPException:
        raise
    except Exception as e:
        SystemLogsService.create_log(
            action="User Account Created",
            status="Failed",
            details=f"Error creating admin ({admin_data.email}): {type(e).__name__}",
            user=admin_data.username,
            role=admin_data.role,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating admin: {str(e)}",
        )


@router.get("/{admin_id}", response_model=Admin)
async def get_admin(admin_id: int):
    """Get admin by ID"""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT id, email, role, username, uid FROM admin WHERE id = %s",
                (admin_id,),
            )
            admin_data = cur.fetchone()

            if not admin_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found"
                )

            return Admin(**admin_data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching admin: {str(e)}",
        )


@router.put("/{admin_id}", response_model=Admin)
async def update_admin(admin_id: int, admin_data: AdminCreate):
    """Update admin"""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                """
                UPDATE admin
                SET email = %s, role = %s, username = %s, uid = %s
                WHERE id = %s
                RETURNING id, email, role, username, uid
                """,
                (
                    admin_data.email,
                    admin_data.role,
                    admin_data.username,
                    admin_data.uid,
                    admin_id,
                ),
            )

            updated_admin = cur.fetchone()

            if not updated_admin:
                SystemLogsService.create_log(
                    action="User Account Updated",
                    status="Failed",
                    details=f"Admin update failed: admin_id={admin_id} not found.",
                    user=admin_data.username,
                    role=admin_data.role,
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found"
                )

            SystemLogsService.create_log(
                action="User Account Updated",
                status="Success",
                details=f"Updated admin account: id={admin_id}, username={updated_admin['username']}.",
                user=updated_admin["username"],
                user_id=updated_admin["id"],
                role=updated_admin["role"],
            )

            return Admin(**updated_admin)

    except HTTPException:
        raise
    except Exception as e:
        SystemLogsService.create_log(
            action="User Account Updated",
            status="Failed",
            details=f"Error updating admin id={admin_id}: {type(e).__name__}",
            user=admin_data.username,
            role=admin_data.role,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating admin: {str(e)}",
        )


@router.delete("/{admin_id}")
async def delete_admin(admin_id: int):
    """Delete admin"""
    try:
        with get_db_cursor() as cur:
            cur.execute("DELETE FROM admin WHERE id = %s RETURNING id", (admin_id,))
            deleted = cur.fetchone()

            if not deleted:
                SystemLogsService.create_log(
                    action="User Account Deleted",
                    status="Failed",
                    details=f"Admin delete failed: admin_id={admin_id} not found.",
                    user="System",
                    role="admin",
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found"
                )

            SystemLogsService.create_log(
                action="User Account Deleted",
                status="Success",
                details=f"Deleted admin account: id={admin_id}.",
                user="System",
                role="admin",
            )

            return {"success": True, "message": "Admin deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        SystemLogsService.create_log(
            action="User Account Deleted",
            status="Failed",
            details=f"Error deleting admin id={admin_id}: {type(e).__name__}",
            user="System",
            role="admin",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting admin: {str(e)}",
        )


# -----------------------------------------------------------------------------
# Hazard Thresholds Configuration
# -----------------------------------------------------------------------------

@router.get("/config/hazard-thresholds")
async def get_hazard_thresholds(current_admin: dict = Depends(get_current_admin)):
    """Get all hazard thresholds"""
    try:
        thresholds = SystemSettingsService.get_hazard_thresholds()
        return {"success": True, "thresholds": thresholds}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching thresholds: {str(e)}"
        )


@router.post("/config/hazard-thresholds")
async def update_hazard_thresholds(
    thresholds: dict, 
    current_admin: dict = Depends(get_current_admin)
):
    """Update hazard thresholds"""
    try:
        SystemSettingsService.update_hazard_thresholds(thresholds)
        
        # Log the action
        SystemLogsService.create_log(
            action="Config Updated",
            status="Success",
            details=f"Admin updated hazard thresholds.",
            user=current_admin.get("email", "Admin"),
            user_id=current_admin.get("sub"),
            role=current_admin.get("role")
        )
        
        return {"success": True, "message": "Hazard thresholds updated successfully"}
    except Exception as e:
        SystemLogsService.create_log(
            action="Config Updated",
            status="Failed",
            details=f"Error updating hazard thresholds: {str(e)}",
            user=current_admin.get("email", "Admin"),
            user_id=current_admin.get("sub"),
            role=current_admin.get("role")
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating thresholds: {str(e)}"
        )
