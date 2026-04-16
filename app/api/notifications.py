"""
Notifications API endpoints

Schema expectations:
  notifications          — existing table (id, title, message, type, sent_to, status, date_time)
  user_notification_reads — new table created below if it doesn't exist
      user_id         TEXT NOT NULL
      notification_id TEXT NOT NULL
      read_at         TIMESTAMP NOT NULL DEFAULT NOW()
      PRIMARY KEY (user_id, notification_id)
"""

from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Optional
from datetime import datetime
import uuid

from app.models.notification import (
    Notification,
    NotificationCreate,
    NotificationUpdate,
    NotificationWithReadState,
)
from app.database import get_db_cursor
from app.services.system_logs_service import SystemLogsService

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


# ---------------------------------------------------------------------------
# Internal helper — ensures the reads table exists on first use.
# In production you'd handle this via a proper migration instead.
# ---------------------------------------------------------------------------

def _ensure_reads_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_notification_reads (
            user_id         TEXT NOT NULL,
            notification_id TEXT NOT NULL,
            read_at         TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, notification_id)
        )
        """
    )


# ---------------------------------------------------------------------------
# Broadcast endpoints (admin / existing)
# ---------------------------------------------------------------------------

@router.post("/", response_model=Notification, status_code=status.HTTP_201_CREATED)
async def create_notification(notification_data: NotificationCreate):
    """Create a new notification (admin broadcast)."""
    try:
        with get_db_cursor() as cur:
            notification_id = str(uuid.uuid4())
            now = datetime.utcnow()

            cur.execute(
                """
                INSERT INTO notifications (id, title, message, type, sent_to, status, date_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, title, message, type, sent_to, status, date_time
                """,
                (
                    notification_id,
                    notification_data.title,
                    notification_data.message,
                    notification_data.type,
                    notification_data.sent_to,
                    notification_data.status,
                    now,
                ),
            )

            created = cur.fetchone()
            if not created:
                raise HTTPException(status_code=500, detail="Failed to create notification")

        SystemLogsService.create_log(
            action="Notification Posted",
            status="Success",
            details=(
                f"Notification posted: title='{notification_data.title}', "
                f"type='{notification_data.type}', sent_to='{notification_data.sent_to}'."
            ),
            user="System Admin",
            role="admin",
        )

        return Notification(**dict(created))

    except HTTPException:
        raise
    except Exception as e:
        SystemLogsService.create_log(
            action="Notification Posted",
            status="Failed",
            details=f"Error creating notification: {type(e).__name__}",
            user="System Admin",
            role="admin",
        )
        raise HTTPException(status_code=500, detail=f"Error creating notification: {str(e)}")


@router.get("/")
async def get_notifications(
    user_id: Optional[str] = Query(default=None),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(25, ge=1, le=200, description="Items per page"),
    type: Optional[str] = Query(default=None, description="Filter by notification type"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter by status"),
    start_date: Optional[str] = Query(default=None, description="Start date (ISO 8601)"),
    end_date: Optional[str] = Query(default=None, description="End date (ISO 8601)"),
    search: Optional[str] = Query(default=None, description="Search title or message"),
):
    """
    Get notifications with pagination, filtering, and date range.

    Pass ?user_id=<id> to include per-user is_read state.
    Without user_id every item returns is_read=False.
    """
    try:
        with get_db_cursor() as cur:
            _ensure_reads_table(cur)

            where_parts: list[str] = []
            params: list = []

            if type:
                where_parts.append("n.type = %s")
                params.append(type)

            if status_filter:
                where_parts.append("n.status = %s")
                params.append(status_filter)

            if start_date:
                where_parts.append("n.date_time >= %s")
                params.append(start_date)

            if end_date:
                where_parts.append("n.date_time < (%s::date + INTERVAL '1 day')")
                params.append(end_date)

            if search:
                where_parts.append("(n.title ILIKE %s OR n.message ILIKE %s)")
                like = f"%{search}%"
                params.extend([like, like])

            where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

            # Total count
            cur.execute(f"SELECT COUNT(*) AS cnt FROM notifications n {where_clause}", params)
            total = cur.fetchone()["cnt"]

            offset = (page - 1) * limit

            if user_id:
                cur.execute(
                    f"""
                    SELECT
                        n.id, n.title, n.message, n.type, n.sent_to, n.status, n.date_time,
                        CASE WHEN r.notification_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_read
                    FROM notifications n
                    LEFT JOIN user_notification_reads r
                        ON r.notification_id = n.id AND r.user_id = %s
                    {where_clause}
                    ORDER BY n.date_time DESC
                    LIMIT %s OFFSET %s
                    """,
                    [user_id] + params + [limit, offset],
                )
            else:
                cur.execute(
                    f"""
                    SELECT
                        id, title, message, type, sent_to, status, date_time,
                        FALSE AS is_read
                    FROM notifications n
                    {where_clause}
                    ORDER BY date_time DESC
                    LIMIT %s OFFSET %s
                    """,
                    params + [limit, offset],
                )

            rows = cur.fetchall()
            return {
                "items": [NotificationWithReadState(**dict(row)) for row in rows],
                "total": total,
                "page": page,
                "limit": limit,
                "pages": (total + limit - 1) // limit if total else 0,
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching notifications: {str(e)}")


# ---------------------------------------------------------------------------
# Per-user read state endpoints
# ---------------------------------------------------------------------------

@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    user_id: str = Query(..., description="The user marking this notification as read"),
):
    """Mark a single notification as read for a specific user."""
    try:
        with get_db_cursor() as cur:
            _ensure_reads_table(cur)

            cur.execute("SELECT id FROM notifications WHERE id = %s", (notification_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Notification not found")

            cur.execute(
                """
                INSERT INTO user_notification_reads (user_id, notification_id, read_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, notification_id) DO NOTHING
                """,
                (user_id, notification_id, datetime.utcnow()),
            )

        return {"success": True, "message": "Marked as read"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error marking as read: {str(e)}")


@router.delete("/{notification_id}/read")
async def mark_as_unread(
    notification_id: str,
    user_id: str = Query(..., description="The user unmarking this notification"),
):
    """Mark a single notification as unread for a specific user."""
    try:
        with get_db_cursor() as cur:
            _ensure_reads_table(cur)

            cur.execute(
                """
                DELETE FROM user_notification_reads
                WHERE user_id = %s AND notification_id = %s
                """,
                (user_id, notification_id),
            )

        return {"success": True, "message": "Marked as unread"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error marking as unread: {str(e)}")


@router.patch("/read/all")
async def mark_all_as_read(
    user_id: str = Query(..., description="The user marking all notifications as read"),
):
    """Mark all current notifications as read for a specific user."""
    try:
        with get_db_cursor() as cur:
            _ensure_reads_table(cur)

            cur.execute("SELECT id FROM notifications")
            all_ids = [row["id"] for row in cur.fetchall()]

            if not all_ids:
                return {"success": True, "message": "No notifications to mark", "count": 0}

            now = datetime.utcnow()
            values = [(user_id, nid, now) for nid in all_ids]

            cur.executemany(
                """
                INSERT INTO user_notification_reads (user_id, notification_id, read_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, notification_id) DO NOTHING
                """,
                values,
            )

        return {"success": True, "message": "All marked as read", "count": len(all_ids)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error marking all as read: {str(e)}")


@router.get("/{notification_id}", response_model=NotificationWithReadState)
async def get_notification(
    notification_id: str,
    user_id: Optional[str] = Query(default=None),
):
    """Get a single notification by ID, with optional per-user read state."""
    try:
        with get_db_cursor() as cur:
            _ensure_reads_table(cur)

            if user_id:
                cur.execute(
                    """
                    SELECT
                        n.id, n.title, n.message, n.type, n.sent_to, n.status, n.date_time,
                        CASE WHEN r.notification_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_read
                    FROM notifications n
                    LEFT JOIN user_notification_reads r
                        ON r.notification_id = n.id AND r.user_id = %s
                    WHERE n.id = %s
                    """,
                    (user_id, notification_id),
                )
            else:
                cur.execute(
                    """
                    SELECT id, title, message, type, sent_to, status, date_time, FALSE AS is_read
                    FROM notifications
                    WHERE id = %s
                    """,
                    (notification_id,),
                )

            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Notification not found")

            return NotificationWithReadState(**dict(row))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching notification: {str(e)}")


@router.put("/{notification_id}", response_model=Notification)
async def update_notification(notification_id: str, notification_data: NotificationUpdate):
    """Update notification content (admin only)."""
    try:
        with get_db_cursor() as cur:
            update_fields, values = [], []

            if notification_data.title is not None:
                update_fields.append("title = %s")
                values.append(notification_data.title)
            if notification_data.message is not None:
                update_fields.append("message = %s")
                values.append(notification_data.message)
            if notification_data.type is not None:
                update_fields.append("type = %s")
                values.append(notification_data.type)
            if notification_data.sent_to is not None:
                update_fields.append("sent_to = %s")
                values.append(notification_data.sent_to)
            if notification_data.status is not None:
                update_fields.append("status = %s")
                values.append(notification_data.status)

            if not update_fields:
                raise HTTPException(status_code=400, detail="No fields to update")

            values.append(notification_id)
            cur.execute(
                f"""
                UPDATE notifications
                SET {', '.join(update_fields)}
                WHERE id = %s
                RETURNING id, title, message, type, sent_to, status, date_time
                """,
                values,
            )

            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Notification not found")

        SystemLogsService.create_log(
            action="Notification Updated",
            status="Success",
            details=f"Notification updated: id={notification_id}.",
            user="System Admin",
            role="admin",
        )

        return Notification(**dict(row))

    except HTTPException:
        raise
    except Exception as e:
        SystemLogsService.create_log(
            action="Notification Updated",
            status="Failed",
            details=f"Failed to update notification id={notification_id}: {type(e).__name__}",
            user="System Admin",
            role="admin",
        )
        raise HTTPException(status_code=500, detail=f"Error updating notification: {str(e)}")


@router.delete("/{notification_id}")
async def delete_notification(notification_id: str):
    """Permanently delete a notification (admin — removes for all users)."""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                "DELETE FROM user_notification_reads WHERE notification_id = %s",
                (notification_id,),
            )
            cur.execute(
                "DELETE FROM notifications WHERE id = %s RETURNING id, title",
                (notification_id,),
            )
            deleted = cur.fetchone()
            if not deleted:
                raise HTTPException(status_code=404, detail="Notification not found")

        SystemLogsService.create_log(
            action="Notification Deleted",
            status="Success",
            details=f"Notification deleted: id={notification_id}.",
            user="System Admin",
            role="admin",
        )

        return {"success": True, "message": "Notification deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        SystemLogsService.create_log(
            action="Notification Deleted",
            status="Failed",
            details=f"Failed to delete notification id={notification_id}: {type(e).__name__}",
            user="System Admin",
            role="admin",
        )
        raise HTTPException(status_code=500, detail=f"Error deleting notification: {str(e)}")
