from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from datetime import datetime
from backend.database import get_db_cursor

router = APIRouter(prefix="/api/user-emails", tags=["User Emails"])

class AddEmailRequest(BaseModel):
    user_id: str  # ← Changed from int to str
    email: EmailStr

class EmailResponse(BaseModel):
    success: bool
    message: str
    data: dict = None


@router.post("/add", response_model=EmailResponse)
async def add_user_email(request: AddEmailRequest):
    """Add email to user account"""
    try:
        with get_db_cursor() as cur:
            # Check if user exists
            cur.execute("SELECT id FROM users WHERE id = %s", (request.user_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="User not found")
            
            # Check if email already exists
            cur.execute("SELECT id FROM user_emails WHERE email = %s", (request.email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Email already registered")
            
            # Add email
            cur.execute("""
                INSERT INTO user_emails (user_id, email, is_verified, is_primary)
                VALUES (%s, %s, %s, %s)
                RETURNING id, user_id, email, is_verified, is_primary, created_at
            """, (request.user_id, request.email, False, True))
            
            email_data = dict(cur.fetchone())
            
            return EmailResponse(
                success=True,
                message="Email added successfully",
                data=email_data
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding email: {str(e)}")


@router.get("/user/{user_id}")
async def get_user_email(user_id: str):  # ← Changed from int to str
    """Get primary email for a user"""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT email FROM user_emails
                WHERE user_id = %s AND is_primary = TRUE
                LIMIT 1
            """, (user_id,))
            
            result = cur.fetchone()
            
            return {
                "success": True,
                "email": result['email'] if result else None
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check-phone/{phone_number}")
async def check_user_has_email(phone_number: str):
    """Check if user has verified primary email registered"""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT u.id, ue.email, ue.is_verified
                FROM users u
                LEFT JOIN user_emails ue ON ue.user_id = u.id AND ue.is_primary = TRUE AND ue.is_verified = TRUE
                WHERE u.phone_number = %s
                LIMIT 1
            """, (phone_number,))
            
            user = cur.fetchone()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            return {
                "success": True,
                "has_email": user['email'] is not None,
                "email": user['email'],
                "user_id": user['id']
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
