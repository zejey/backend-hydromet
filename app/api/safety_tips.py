"""
Safety Tips API endpoints with details (bullet points)
"""

from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime

from app.models.safety import SafetyTip, SafetyTipWithDetails, TipCreate, TipUpdate, SafetyTipDetail
from app.database import get_db_cursor

router = APIRouter(prefix="/api/safety/tips", tags=["Safety Tips"])


@router.get("/category/{category_id}", response_model=List[SafetyTipWithDetails])
async def get_tips_by_category(category_id: int):  # ✅ Changed to int
    """Get all tips with their bullet points for a specific category"""
    try:
        with get_db_cursor() as cur:
            # Get tips
            cur.execute("""
                SELECT id, category_id, range_label, level, color,
                       order_num, is_active, created_at, updated_at
                FROM safety_tips
                WHERE category_id = %s AND is_active = true
                ORDER BY order_num ASC
            """, (category_id,))
            
            tips = [dict(row) for row in cur.fetchall()]
            
            # Get details for each tip
            result = []
            for tip in tips:
                cur.execute("""
                    SELECT id, tip_id, description, order_num, created_at
                    FROM safety_tip_details
                    WHERE tip_id = %s
                    ORDER BY order_num ASC
                """, (tip['id'],))
                
                details = [dict(row) for row in cur.fetchall()]
                tip['details'] = [SafetyTipDetail(**d) for d in details]
                result.append(SafetyTipWithDetails(**tip))
            
            return result
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching tips: {str(e)}"
        )


@router.get("/", response_model=List[SafetyTip])
async def get_all_tips(active_only: bool = True):
    """Get all tips (without details)"""
    try:
        with get_db_cursor() as cur:
            if active_only:
                cur.execute("""
                    SELECT id, category_id, range_label, level, color,
                           order_num, is_active, created_at, updated_at
                    FROM safety_tips
                    WHERE is_active = true
                    ORDER BY order_num ASC
                """)
            else:
                cur.execute("""
                    SELECT id, category_id, range_label, level, color,
                           order_num, is_active, created_at, updated_at
                    FROM safety_tips
                    ORDER BY order_num ASC
                """)
            
            tips = [dict(row) for row in cur.fetchall()]
            return [SafetyTip(**tip) for tip in tips]
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching tips:  {str(e)}"
        )


@router.post("/", response_model=SafetyTip, status_code=status.HTTP_201_CREATED)
async def create_tip(tip_data: TipCreate):
    """Create a new safety tip"""
    try:
        with get_db_cursor() as cur:
            # Verify category exists
            cur.execute("SELECT id FROM safety_categories WHERE id = %s", (tip_data.category_id,))
            if not cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Category does not exist"
                )
            
            now = datetime.utcnow()
            
            # ✅ Let SERIAL generate ID
            cur.execute("""
                INSERT INTO safety_tips (
                    category_id, range_label, level, color, order_num,
                    is_active, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, category_id, range_label, level, color,
                          order_num, is_active, created_at, updated_at
            """, (
                tip_data.category_id,
                tip_data.range_label,
                tip_data. level,
                tip_data. color,
                tip_data. order_num,
                tip_data.is_active,
                now,
                now
            ))
            
            new_tip = dict(cur.fetchone())
            return SafetyTip(**new_tip)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating tip: {str(e)}"
        )


@router.get("/{tip_id}", response_model=SafetyTipWithDetails)
async def get_tip(tip_id: int):  # ✅ Changed to int
    """Get tip by ID with details"""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, category_id, range_label, level, color,
                       order_num, is_active, created_at, updated_at
                FROM safety_tips
                WHERE id = %s
            """, (tip_id,))
            
            tip_data = cur.fetchone()
            
            if not tip_data:
                raise HTTPException(
                    status_code=status. HTTP_404_NOT_FOUND,
                    detail="Tip not found"
                )
            
            tip = dict(tip_data)
            
            # Get details
            cur. execute("""
                SELECT id, tip_id, description, order_num, created_at
                FROM safety_tip_details
                WHERE tip_id = %s
                ORDER BY order_num ASC
            """, (tip_id,))
            
            details = [dict(row) for row in cur.fetchall()]
            tip['details'] = [SafetyTipDetail(**d) for d in details]
            
            return SafetyTipWithDetails(**tip)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching tip:  {str(e)}"
        )


@router.put("/{tip_id}", response_model=SafetyTip)
async def update_tip(tip_id: int, tip_data: TipUpdate):  # ✅ Changed to int
    """Update tip (not details)"""
    try:
        with get_db_cursor() as cur:
            update_fields = []
            values = []
            
            if tip_data. category_id is not None:
                # Verify category exists
                cur. execute("SELECT id FROM safety_categories WHERE id = %s", (tip_data.category_id,))
                if not cur.fetchone():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Category does not exist"
                    )
                update_fields.append("category_id = %s")
                values. append(tip_data.category_id)
            
            if tip_data.range_label is not None:
                update_fields. append("range_label = %s")
                values.append(tip_data.range_label)
            
            if tip_data. level is not None:
                update_fields.append("level = %s")
                values.append(tip_data.level)
            
            if tip_data.color is not None:
                update_fields.append("color = %s")
                values.append(tip_data.color)
            
            if tip_data.order_num is not None:
                update_fields.append("order_num = %s")
                values. append(tip_data.order_num)
            
            if tip_data.is_active is not None:
                update_fields. append("is_active = %s")
                values.append(tip_data.is_active)
            
            if not update_fields:
                raise HTTPException(
                    status_code=status. HTTP_400_BAD_REQUEST,
                    detail="No fields to update"
                )
            
            update_fields.append("updated_at = %s")
            values.append(datetime.utcnow())
            values. append(tip_id)
            
            cur.execute(f"""
                UPDATE safety_tips
                SET {', '.join(update_fields)}
                WHERE id = %s
                RETURNING id, category_id, range_label, level, color,
                          order_num, is_active, created_at, updated_at
            """, values)
            
            updated_tip = cur.fetchone()
            
            if not updated_tip:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tip not found"
                )
            
            return SafetyTip(**dict(updated_tip))
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status. HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating tip: {str(e)}"
        )


@router.delete("/{tip_id}")
async def delete_tip(tip_id: int):  # ✅ Changed to int
    """Delete tip (cascades to details)"""
    try:
        with get_db_cursor() as cur:
            cur.execute("DELETE FROM safety_tips WHERE id = %s RETURNING id", (tip_id,))
            deleted = cur.fetchone()
            
            if not deleted: 
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tip not found"
                )
            
            return {
                "success":  True,
                "message": "Tip deleted successfully"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status. HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting tip: {str(e)}"
        )


# ==================== TIP DETAILS ENDPOINTS ====================

@router.post("/{tip_id}/details", response_model=SafetyTipDetail, status_code=status.HTTP_201_CREATED)
async def add_tip_detail(tip_id: int, description: str, order_num: int = 0):
    """Add a bullet point to a tip"""
    try:
        with get_db_cursor() as cur:
            # Verify tip exists
            cur.execute("SELECT id FROM safety_tips WHERE id = %s", (tip_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Tip not found")
            
            now = datetime. utcnow()
            
            cur.execute("""
                INSERT INTO safety_tip_details (tip_id, description, order_num, created_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id, tip_id, description, order_num, created_at
            """, (tip_id, description, order_num, now))
            
            new_detail = dict(cur.fetchone())
            return SafetyTipDetail(**new_detail)
            
    except HTTPException:
        raise
    except Exception as e: 
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding detail: {str(e)}"
        )


@router.delete("/details/{detail_id}")
async def delete_tip_detail(detail_id: int):
    """Delete a bullet point"""
    try:
        with get_db_cursor() as cur:
            cur.execute("DELETE FROM safety_tip_details WHERE id = %s RETURNING id", (detail_id,))
            deleted = cur.fetchone()
            
            if not deleted:
                raise HTTPException(status_code=404, detail="Detail not found")
            
            return {"success": True, "message": "Detail deleted successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting detail: {str(e)}"
        )