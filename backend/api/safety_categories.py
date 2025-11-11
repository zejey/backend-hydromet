"""
Safety Categories API endpoints
"""

from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime
import uuid

from backend.models.safety import SafetyCategory, CategoryCreate, CategoryUpdate
from backend.database import get_db_cursor

router = APIRouter(prefix="/api/safety/categories", tags=["Safety Categories"])


@router.post("/", response_model=SafetyCategory, status_code=status.HTTP_201_CREATED)
async def create_category(category_data: CategoryCreate):
    """Create a new safety category"""
    try:
        with get_db_cursor() as cur:
            category_id = str(uuid.uuid4())
            now = datetime.utcnow()
            
            cur.execute("""
                INSERT INTO safety_categories (
                    category_id, name, description, order_num, icon, 
                    gradient_colors, created_at, updated_at, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING category_id, name, description, order_num, icon,
                          gradient_colors, created_at, updated_at, is_active
            """, (
                category_id,
                category_data.name,
                category_data.description,
                category_data.order_num,
                category_data.icon,
                category_data.gradient_colors,
                now,
                now,
                category_data.is_active
            ))
            
            new_category = cur.fetchone()
            return SafetyCategory(**new_category)
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating category: {str(e)}"
        )


@router.get("/", response_model=List[SafetyCategory])
async def get_categories(active_only: bool = True):
    """Get all safety categories (active only by default, sorted by order_num)"""
    try:
        with get_db_cursor() as cur:
            if active_only:
                cur.execute("""
                    SELECT category_id, name, description, order_num, icon,
                           gradient_colors, created_at, updated_at, is_active
                    FROM safety_categories
                    WHERE is_active = true
                    ORDER BY order_num ASC, name ASC
                """)
            else:
                cur.execute("""
                    SELECT category_id, name, description, order_num, icon,
                           gradient_colors, created_at, updated_at, is_active
                    FROM safety_categories
                    ORDER BY order_num ASC, name ASC
                """)
            
            categories = cur.fetchall()
            return [SafetyCategory(**cat) for cat in categories]
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching categories: {str(e)}"
        )


@router.get("/{category_id}", response_model=SafetyCategory)
async def get_category(category_id: str):
    """Get category by ID"""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT category_id, name, description, order_num, icon,
                       gradient_colors, created_at, updated_at, is_active
                FROM safety_categories
                WHERE category_id = %s
            """, (category_id,))
            
            category_data = cur.fetchone()
            
            if not category_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Category not found"
                )
            
            return SafetyCategory(**category_data)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching category: {str(e)}"
        )


@router.put("/{category_id}", response_model=SafetyCategory)
async def update_category(category_id: str, category_data: CategoryUpdate):
    """Update category"""
    try:
        with get_db_cursor() as cur:
            # Build dynamic update query
            update_fields = []
            values = []
            
            if category_data.name is not None:
                update_fields.append("name = %s")
                values.append(category_data.name)
            
            if category_data.description is not None:
                update_fields.append("description = %s")
                values.append(category_data.description)
            
            if category_data.order_num is not None:
                update_fields.append("order_num = %s")
                values.append(category_data.order_num)
            
            if category_data.icon is not None:
                update_fields.append("icon = %s")
                values.append(category_data.icon)
            
            if category_data.gradient_colors is not None:
                update_fields.append("gradient_colors = %s")
                values.append(category_data.gradient_colors)
            
            if category_data.is_active is not None:
                update_fields.append("is_active = %s")
                values.append(category_data.is_active)
            
            if not update_fields:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No fields to update"
                )
            
            update_fields.append("updated_at = %s")
            values.append(datetime.utcnow())
            values.append(category_id)
            
            cur.execute(f"""
                UPDATE safety_categories
                SET {', '.join(update_fields)}
                WHERE category_id = %s
                RETURNING category_id, name, description, order_num, icon,
                          gradient_colors, created_at, updated_at, is_active
            """, values)
            
            updated_category = cur.fetchone()
            
            if not updated_category:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Category not found"
                )
            
            return SafetyCategory(**updated_category)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating category: {str(e)}"
        )


@router.delete("/{category_id}")
async def delete_category(category_id: str):
    """Delete category"""
    try:
        with get_db_cursor() as cur:
            cur.execute("DELETE FROM safety_categories WHERE category_id = %s RETURNING category_id", (category_id,))
            deleted = cur.fetchone()
            
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Category not found"
                )
            
            return {
                "success": True,
                "message": "Category deleted successfully"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting category: {str(e)}"
        )