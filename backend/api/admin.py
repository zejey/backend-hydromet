"""
Admin API endpoints
"""

from fastapi import APIRouter, HTTPException, status
from typing import List

from backend.models.admin import Admin, AdminCreate, AdminUpdate, AdminResponse
from backend.database import get_db_cursor

router = APIRouter(prefix="/api/admins", tags=["Admin Management"])


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
            
            # Insert new admin
            cur.execute("""
                INSERT INTO admin (email, role, username, uid)
                VALUES (%s, %s, %s, %s)
                RETURNING id, email, role, username, uid
            """, (
                admin_data.email,
                admin_data.role,
                admin_data.username,
                admin_data.uid
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


@router.get("/", response_model=List[Admin])
async def get_admins():
    """Get all admins"""
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT id, email, role, username, uid FROM admin ORDER BY id")
            admins = cur.fetchall()
            return [Admin(**admin) for admin in admins]
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching admins: {str(e)}"
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