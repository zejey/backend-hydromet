"""
Safety Tips API endpoints
"""

from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime
import uuid

from backend.models.safety import SafetyTip, TipCreate, TipUpdate
from backend.database import get_db_cursor

router = APIRouter(prefix="/api/safety/tips", tags=["Safety Tips"])


@router.post("/", response_model=SafetyTip, status_code=status.HTTP_201_CREATED)
async def create_tip(tip_data: TipCreate):
    """Create a new safety tip"""
    try:
        with get_db_cursor() as cur:
            # Verify category exists
            cur.execute("SELECT category_id FROM safety_categories WHERE category_id = %s", (tip_data.category_id,))
            if not cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Category does not exist"
                )
            
            tip_id = str(uuid.uuid4())
            now = datetime.utcnow()
            
            cur.execute("""
                INSERT INTO safety_tips (
                    tip_id, category_id, title, content, order_num, 
                    icon, created_at, updated_at, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING tip_id, category_id, title, content, order_num,
                          icon, created_at, updated_at, is_active
            """, (
                tip_id,
                tip_data.category_id,
                tip_data.title,
                tip_data.content,
                tip_data.order_num,
                tip_data.icon,
                now,
                now,
                tip_data.is_active
            ))
            
            new_tip = cur.fetchone()
            return SafetyTip(**new_tip)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating tip: {str(e)}"
        )


@router.get("/", response_model=List[SafetyTip])
async def get_tips(active_only: bool = True):
    """Get all safety tips (active only by default, sorted by order_num)"""
    try:
        with get_db_cursor() as cur:
            if active_only:
                cur.execute("""
                    SELECT tip_id, category_id, title, content, order_num,
                           icon, created_at, updated_at, is_active
                    FROM safety_tips
                    WHERE is_active = true
                    ORDER BY order_num ASC, title ASC
                """)
            else:
                cur.execute("""
                    SELECT tip_id, category_id, title, content, order_num,
                           icon, created_at, updated_at, is_active
                    FROM safety_tips
                    ORDER BY order_num ASC, title ASC
                """)
            
            tips = cur.fetchall()
            return [SafetyTip(**tip) for tip in tips]
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching tips: {str(e)}"
        )


@router.get("/category/{category_id}", response_model=List[SafetyTip])
async def get_tips_by_category(category_id: str):
    """Get all tips for a specific category"""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT tip_id, category_id, title, content, order_num,
                       icon, created_at, updated_at, is_active
                FROM safety_tips
                WHERE category_id = %s AND is_active = true
                ORDER BY order_num ASC, title ASC
            """, (category_id,))
            
            tips = cur.fetchall()
            return [SafetyTip(**tip) for tip in tips]
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching tips: {str(e)}"
        )


@router.get("/{tip_id}", response_model=SafetyTip)
async def get_tip(tip_id: str):
    """Get tip by ID"""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT tip_id, category_id, title, content, order_num,
                       icon, created_at, updated_at, is_active
                FROM safety_tips
                WHERE tip_id = %s
            """, (tip_id,))
            
            tip_data = cur.fetchone()
            
            if not tip_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tip not found"
                )
            
            return SafetyTip(**tip_data)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching tip: {str(e)}"
        )


@router.put("/{tip_id}", response_model=SafetyTip)
async def update_tip(tip_id: str, tip_data: TipUpdate):
    """Update tip"""
    try:
        with get_db_cursor() as cur:
            # Build dynamic update query
            update_fields = []
            values = []
            
            if tip_data.category_id is not None:
                # Verify category exists
                cur.execute("SELECT category_id FROM safety_categories WHERE category_id = %s", (tip_data.category_id,))
                if not cur.fetchone():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Category does not exist"
                    )
                update_fields.append("category_id = %s")
                values.append(tip_data.category_id)
            
            if tip_data.title is not None:
                update_fields.append("title = %s")
                values.append(tip_data.title)
            
            if tip_data.content is not None:
                update_fields.append("content = %s")
                values.append(tip_data.content)
            
            if tip_data.order_num is not None:
                update_fields.append("order_num = %s")
                values.append(tip_data.order_num)
            
            if tip_data.icon is not None:
                update_fields.append("icon = %s")
                values.append(tip_data.icon)
            
            if tip_data.is_active is not None:
                update_fields.append("is_active = %s")
                values.append(tip_data.is_active)
            
            if not update_fields:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No fields to update"
                )
            
            update_fields.append("updated_at = %s")
            values.append(datetime.utcnow())
            values.append(tip_id)
            
            cur.execute(f"""
                UPDATE safety_tips
                SET {', '.join(update_fields)}
                WHERE tip_id = %s
                RETURNING tip_id, category_id, title, content, order_num,
                          icon, created_at, updated_at, is_active
            """, values)
            
            updated_tip = cur.fetchone()
            
            if not updated_tip:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tip not found"
                )
            
            return SafetyTip(**updated_tip)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating tip: {str(e)}"
        )


@router.delete("/{tip_id}")
async def delete_tip(tip_id: str):
    """Delete tip"""
    try:
        with get_db_cursor() as cur:
            cur.execute("DELETE FROM safety_tips WHERE tip_id = %s RETURNING tip_id", (tip_id,))
            deleted = cur.fetchone()
            
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tip not found"
                )
            
            return {
                "success": True,
                "message": "Tip deleted successfully"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting tip: {str(e)}"
        )