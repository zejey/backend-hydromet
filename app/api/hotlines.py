"""
Emergency Hotlines API endpoints
"""

from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime
import uuid

from app.models.hotline import EmergencyHotline, HotlineCreate, HotlineUpdate
from app.database import get_db_cursor

router = APIRouter(
    prefix="/api/hotlines", 
    tags=["Emergency Hotlines"],
    redirect_slashes=False  # ✅ Fix the 307 redirect issue
)

from app.services.system_logs_service import SystemLogsService

@router.post("/", response_model=EmergencyHotline, status_code=status.HTTP_201_CREATED)
async def create_hotline(hotline_data: HotlineCreate):
    """Create a new emergency hotline"""
    try:
        with get_db_cursor() as cur:
            hotline_id = str(uuid.uuid4())
            now = datetime.utcnow()

            cur.execute("""
                INSERT INTO emergency_hotlines (
                    id, service_name, phone_number, category, icon_color, 
                    icon_type, is_active, priority, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, service_name, phone_number, category, icon_color,
                          icon_type, is_active, priority, created_at, updated_at
            """, (
                hotline_id,
                hotline_data.service_name,
                hotline_data.phone_number,
                hotline_data.category,
                hotline_data.icon_color,
                hotline_data.icon_type,
                hotline_data.is_active,
                hotline_data.priority,
                now,
                now
            ))

            new_hotline = cur.fetchone()
            hotline_dict = dict(new_hotline) if new_hotline else None

        SystemLogsService.create_log(
            action="Emergency Hotline Created",
            category="System Configuration",
            status="Success",
            details=f"Created hotline '{hotline_data.service_name}' ({hotline_data.phone_number}) in category '{hotline_data.category}'.",
            user="System Admin",
            role="admin"
        )

        return EmergencyHotline(**hotline_dict)

    except Exception as e:
        SystemLogsService.create_log(
            action="Emergency Hotline Created",
            category="System Configuration",
            status="Failed",
            details=f"Failed to create hotline '{hotline_data.service_name}': {type(e).__name__}",
            user="System Admin",
            role="admin"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating hotline: {str(e)}"
        )

@router.get("/", response_model=List[EmergencyHotline])
async def get_hotlines(active_only: bool = True):
    """Get all emergency hotlines (active only by default, sorted by priority)"""
    try:
        with get_db_cursor() as cur:
            if active_only:
                cur.execute("""
                    SELECT id, service_name, phone_number, category, icon_color,
                           icon_type, is_active, priority, created_at, updated_at
                    FROM emergency_hotlines
                    WHERE is_active = true
                    ORDER BY priority ASC, service_name ASC
                """)
            else:
                cur.execute("""
                    SELECT id, service_name, phone_number, category, icon_color,
                           icon_type, is_active, priority, created_at, updated_at
                    FROM emergency_hotlines
                    ORDER BY priority ASC, service_name ASC
                """)
            
            # ✅ Convert all rows to dicts while cursor is active
            hotlines = [dict(row) for row in cur.fetchall()]
            return [EmergencyHotline(**hotline) for hotline in hotlines]
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching hotlines: {str(e)}"
        )


@router.get("/category/{category}", response_model=List[EmergencyHotline])
async def get_hotlines_by_category(category: str):
    """Get hotlines by category (e.g., 'Medical', 'Fire', 'Police')"""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, service_name, phone_number, category, icon_color,
                       icon_type, is_active, priority, created_at, updated_at
                FROM emergency_hotlines
                WHERE category = %s AND is_active = true
                ORDER BY priority ASC
            """, (category,))
            
            # ✅ Convert all rows to dicts while cursor is active
            hotlines = [dict(row) for row in cur.fetchall()]
            return [EmergencyHotline(**hotline) for hotline in hotlines]
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching hotlines: {str(e)}"
        )


@router.get("/{hotline_id}", response_model=EmergencyHotline)
async def get_hotline(hotline_id: str):
    """Get hotline by ID"""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, service_name, phone_number, category, icon_color,
                       icon_type, is_active, priority, created_at, updated_at
                FROM emergency_hotlines
                WHERE id = %s
            """, (hotline_id,))
            
            hotline_data = cur.fetchone()
            
            if not hotline_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Hotline not found"
                )
            
            # ✅ Convert to dict while cursor is active
            hotline_dict = dict(hotline_data)
            return EmergencyHotline(**hotline_dict)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching hotline: {str(e)}"
        )


@router.put("/{hotline_id}", response_model=EmergencyHotline)
async def update_hotline(hotline_id: str, hotline_data: HotlineUpdate):
    """Update hotline"""
    try:
        with get_db_cursor() as cur:
            update_fields = []
            values = []

            if hotline_data.service_name is not None:
                update_fields.append("service_name = %s")
                values.append(hotline_data.service_name)
            if hotline_data.phone_number is not None:
                update_fields.append("phone_number = %s")
                values.append(hotline_data.phone_number)
            if hotline_data.category is not None:
                update_fields.append("category = %s")
                values.append(hotline_data.category)
            if hotline_data.icon_color is not None:
                update_fields.append("icon_color = %s")
                values.append(hotline_data.icon_color)
            if hotline_data.icon_type is not None:
                update_fields.append("icon_type = %s")
                values.append(hotline_data.icon_type)
            if hotline_data.is_active is not None:
                update_fields.append("is_active = %s")
                values.append(hotline_data.is_active)
            if hotline_data.priority is not None:
                update_fields.append("priority = %s")
                values.append(hotline_data.priority)

            if not update_fields:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No fields to update"
                )

            update_fields.append("updated_at = %s")
            values.append(datetime.utcnow())
            values.append(hotline_id)

            cur.execute(f"""
                UPDATE emergency_hotlines
                SET {', '.join(update_fields)}
                WHERE id = %s
                RETURNING id, service_name, phone_number, category, icon_color,
                          icon_type, is_active, priority, created_at, updated_at
            """, values)

            updated_hotline = cur.fetchone()

            if not updated_hotline:
                SystemLogsService.create_log(
                    action="Emergency Hotline Updated",
                    category="System Configuration",
                    status="Failed",
                    details=f"Hotline update failed: hotline_id={hotline_id} not found.",
                    user="System Admin",
                    role="admin"
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Hotline not found"
                )

            hotline_dict = dict(updated_hotline)

        SystemLogsService.create_log(
            action="Emergency Hotline Updated",
            category="System Configuration",
            status="Success",
            details=f"Updated hotline id={hotline_id}.",
            user="System Admin",
            role="admin"
        )

        return EmergencyHotline(**hotline_dict)

    except HTTPException:
        raise
    except Exception as e:
        SystemLogsService.create_log(
            action="Emergency Hotline Updated",
            category="System Configuration",
            status="Failed",
            details=f"Failed to update hotline id={hotline_id}: {type(e).__name__}",
            user="System Admin",
            role="admin"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating hotline: {str(e)}"
        )

@router.delete("/{hotline_id}")
async def delete_hotline(hotline_id: str):
    """Delete hotline"""
    try:
        with get_db_cursor() as cur:
            cur.execute("DELETE FROM emergency_hotlines WHERE id = %s RETURNING id", (hotline_id,))
            deleted = cur.fetchone()

            if not deleted:
                SystemLogsService.create_log(
                    action="Emergency Hotline Deleted",
                    category="System Configuration",
                    status="Failed",
                    details=f"Hotline delete failed: hotline_id={hotline_id} not found.",
                    user="System Admin",
                    role="admin"
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Hotline not found"
                )

        SystemLogsService.create_log(
            action="Emergency Hotline Deleted",
            category="System Configuration",
            status="Success",
            details=f"Deleted hotline id={hotline_id}.",
            user="System Admin",
            role="admin"
        )

        return {
            "success": True,
            "message": "Hotline deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        SystemLogsService.create_log(
            action="Emergency Hotline Deleted",
            category="System Configuration",
            status="Failed",
            details=f"Failed to delete hotline id={hotline_id}: {type(e).__name__}",
            user="System Admin",
            role="admin"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting hotline: {str(e)}"
        )
