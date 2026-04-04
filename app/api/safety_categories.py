"""
Safety Categories API endpoints
"""

from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime

from app.models.safety import SafetyCategory, CategoryCreate, CategoryUpdate
from app.database import get_db_cursor
from app.services.system_logs_service import SystemLogsService

router = APIRouter(prefix="/api/safety/categories", tags=["Safety Categories"])


@router.post("/", response_model=SafetyCategory, status_code=status.HTTP_201_CREATED)
async def create_category(category_data: CategoryCreate):
    """Create a new safety category"""
    try:
        with get_db_cursor() as cur:
            now = datetime.utcnow()

            cur.execute("""
                INSERT INTO safety_categories (
                    name, description, order_num, icon, 
                    gradient_colors, created_at, updated_at, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, name, description, order_num, icon,
                          gradient_colors, created_at, updated_at, is_active
            """, (
                category_data.name,
                category_data.description,
                category_data.order_num,
                category_data.icon,
                category_data.gradient_colors,
                now,
                now,
                category_data.is_active
            ))

            new_category = dict(cur.fetchone())

        SystemLogsService.create_log(
            action="Safety Category Created",
            category="Content Management",
            status="Success",
            details=f"Created safety category '{new_category['name']}' (id={new_category['id']}).",
            user="System Admin",
            role="admin"
        )

        return SafetyCategory(**new_category)

    except Exception as e:
        SystemLogsService.create_log(
            action="Safety Category Created",
            category="Content Management",
            status="Failed",
            details=f"Failed to create safety category '{category_data.name}': {type(e).__name__}",
            user="System Admin",
            role="admin"
        )
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
                cur. execute("""
                    SELECT id, name, description, order_num, icon,
                           gradient_colors, created_at, updated_at, is_active
                    FROM safety_categories
                    WHERE is_active = true
                    ORDER BY order_num ASC, name ASC
                """)
            else:
                cur.execute("""
                    SELECT id, name, description, order_num, icon,
                           gradient_colors, created_at, updated_at, is_active
                    FROM safety_categories
                    ORDER BY order_num ASC, name ASC
                """)
            
            categories = [dict(row) for row in cur.fetchall()]
            return [SafetyCategory(**cat) for cat in categories]
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching categories: {str(e)}"
        )


@router.get("/{category_id}", response_model=SafetyCategory)
async def get_category(category_id: int):  # ✅ Changed from str to int
    """Get category by ID"""
    try: 
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, name, description, order_num, icon,
                       gradient_colors, created_at, updated_at, is_active
                FROM safety_categories
                WHERE id = %s
            """, (category_id,))
            
            category_data = cur.fetchone()
            
            if not category_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Category not found"
                )
            
            return SafetyCategory(**dict(category_data))
            
    except HTTPException: 
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status. HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching category: {str(e)}"
        )


@router.put("/{category_id}", response_model=SafetyCategory)
async def update_category(category_id: int, category_data: CategoryUpdate):
    """Update category"""
    try:
        with get_db_cursor() as cur:
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
                SystemLogsService.create_log(
                    action="Safety Category Updated",
                    category="Content Management",
                    status="Failed",
                    details=f"Safety category update failed: no fields provided (id={category_id}).",
                    user="System Admin",
                    role="admin"
                )
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
                WHERE id = %s
                RETURNING id, name, description, order_num, icon,
                          gradient_colors, created_at, updated_at, is_active
            """, values)

            updated_category = cur.fetchone()

            if not updated_category:
                SystemLogsService.create_log(
                    action="Safety Category Updated",
                    category="Content Management",
                    status="Failed",
                    details=f"Safety category update failed: not found (id={category_id}).",
                    user="System Admin",
                    role="admin"
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Category not found"
                )

            updated_category = dict(updated_category)

        SystemLogsService.create_log(
            action="Safety Category Updated",
            category="Content Management",
            status="Success",
            details=f"Updated safety category id={category_id} ('{updated_category['name']}').",
            user="System Admin",
            role="admin"
        )

        return SafetyCategory(**updated_category)

    except HTTPException:
        raise
    except Exception as e:
        SystemLogsService.create_log(
            action="Safety Category Updated",
            category="Content Management",
            status="Failed",
            details=f"Failed to update safety category id={category_id}: {type(e).__name__}",
            user="System Admin",
            role="admin"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating category: {str(e)}"
        )


@router.delete("/{category_id}")
async def delete_category(category_id: int):
    """Delete category"""
    try:
        with get_db_cursor() as cur:
            cur.execute("DELETE FROM safety_categories WHERE id = %s RETURNING id, name", (category_id,))
            deleted = cur.fetchone()

            if not deleted:
                SystemLogsService.create_log(
                    action="Safety Category Deleted",
                    category="Content Management",
                    status="Failed",
                    details=f"Safety category delete failed: not found (id={category_id}).",
                    user="System Admin",
                    role="admin"
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Category not found"
                )

            deleted = dict(deleted)

        SystemLogsService.create_log(
            action="Safety Category Deleted",
            category="Content Management",
            status="Success",
            details=f"Deleted safety category id={category_id} ('{deleted.get('name', '')}').",
            user="System Admin",
            role="admin"
        )

        return {
            "success": True,
            "message": "Category deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        SystemLogsService.create_log(
            action="Safety Category Deleted",
            category="Content Management",
            status="Failed",
            details=f"Failed to delete safety category id={category_id}: {type(e).__name__}",
            user="System Admin",
            role="admin"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting category: {str(e)}"
        )
