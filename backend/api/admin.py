"""
Admin API endpoints
"""
import uuid
from fastapi import APIRouter, HTTPException, status
from typing import List
from passlib.context import CryptContext
import jwt
import datetime
import os
from pydantic import BaseModel
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from backend.models.admin import Admin, AdminCreate, AdminUpdate, AdminResponse
from backend.database import get_db_cursor

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.environ.get("SECRET_KEY", "SUPER_SECRET_KEY")  # Use a strong, real secret in prod!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

router = APIRouter(prefix="/api/admins", tags=["Admin Management"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admins/login")


def hash_password(password: str) -> str:
    # Truncate to 72 bytes before hashing (bcrypt's maximum)
    password_bytes = password.encode('utf-8')[:72]
    password_truncated = password_bytes.decode('utf-8', errors='ignore')
    return pwd_context.hash(password_truncated)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Truncate to 72 bytes before verifying (must match hash behavior)
    password_bytes = plain_password.encode('utf-8')[:72]
    password_truncated = password_bytes.decode('utf-8', errors='ignore')
    return pwd_context.verify(password_truncated, hashed_password)

def create_access_token(data: dict, expires_delta: int = None):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(
        minutes=expires_delta or ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

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
        # Optionally: fetch admin from database here
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
            detail=f"Error fetching admins: {str(e)}"
        )


@router.post("/login", response_model=Token)
async def login(data: dict):
    """
    Admin login endpoint. Receives: {"email": "...", "password": "..."} 
    Returns: {"access_token": "...", "token_type": "bearer"}
    """
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")
    
    # Add validation for password length BEFORE calling verify_password
    if len(password.encode('utf-8')) > 72:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT id, email, role, username, uid, password_hash FROM admin WHERE email = %s", (email,))
            admin_row = cur.fetchone()
            if not admin_row or not verify_password(password, admin_row["password_hash"]):
                raise HTTPException(status_code=401, detail="Incorrect email or password.")
            # Build JWT
            access_token = create_access_token({
                "sub": str(admin_row["id"]),
                "email": admin_row["email"],
                "role": admin_row["role"]
            })
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login error: {str(e)}")

@router.post("/", response_model=Admin, status_code=status.HTTP_201_CREATED)
async def create_admin(admin_data: AdminCreate):
    """Create a new admin"""
    try:
        with get_db_cursor() as cur:
            # Check if admin with same email already exists
            cur.execute("SELECT id FROM admin WHERE email = %s", (admin_data.email,))
            if cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Admin with this email already exists"
                )
           
            password = admin_data.password
            if len(password.encode('utf-8')) > 72:
                raise HTTPException(
                    status_code=400,
                    detail="Password is too long (over 72 bytes after UTF-8 encoding). Please use a shorter password."
                )

            password_hash = hash_password(password)
            # Insert new admin
            cur.execute("""
                INSERT INTO admin (email, role, username, uid, password_hash)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, email, role, username, uid
            """, (
                admin_data.email,
                admin_data.role,
                admin_data.username,
                admin_data.uid,
                password_hash
            ))
            
            new_admin = cur.fetchone()
            return Admin(**new_admin)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating admin: {str(e)}"
        )


@router.get("/{admin_id}", response_model=Admin)
async def get_admin(admin_id: int):
    """Get admin by ID"""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT id, email, role, username, uid FROM admin WHERE id = %s",
                (admin_id,)
            )
            admin_data = cur.fetchone()
            
            if not admin_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Admin not found"
                )
            
            return Admin(**admin_data)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching admin: {str(e)}"
        )


@router.put("/{admin_id}", response_model=Admin)
async def update_admin(admin_id: int, admin_data: AdminCreate):
    """Update admin"""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                UPDATE admin
                SET email = %s, role = %s, username = %s, uid = %s
                WHERE id = %s
                RETURNING id, email, role, username, uid
            """, (
                admin_data.email,
                admin_data.role,
                admin_data.username,
                admin_data.uid,
                admin_id
            ))
            
            updated_admin = cur.fetchone()
            
            if not updated_admin:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Admin not found"
                )
            
            return Admin(**updated_admin)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating admin: {str(e)}"
        )


@router.delete("/{admin_id}")
async def delete_admin(admin_id: int):
    """Delete admin"""
    try:
        with get_db_cursor() as cur:
            cur.execute("DELETE FROM admin WHERE id = %s RETURNING id", (admin_id,))
            deleted = cur.fetchone()
            
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Admin not found"
                )
            
            return {
                "success": True,
                "message": "Admin deleted successfully"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting admin: {str(e)}"
        )
