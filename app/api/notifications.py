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

from app.models.notification import Notification, NotificationCreate, NotificationUpdate, NotificationWithReadState
from app.database import get_db_cursor

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


# ---------------------------------------------------------------------------
# Internal helper — ensures the reads table exists on first use.
# In production you'd handle this via a proper migration instead.
# ---------------------------------------------------------------------------

def _ensure_reads_table(cur) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_notification_reads (
            user_id         TEXT NOT NULL,
            notification_id TEXT NOT NULL,
            read_at         TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, notification_id)
        )
    """)


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

            cur.execute("""
                INSERT INTO notifications (id, title, message, type, sent_to, status, date_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, title, message, type, sent_to, status, date_time
            """, (
                notification_id,
                notification_data.title,
                notification_data.message,
                notification_data.type,
                notification_data.sent_to,
                notification_data.status,
                now,
            ))

            return Notification(**cur.fetchone())

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating notification: {str(e)}")


@router.get("/", response_model=List[NotificationWithReadState])
async def get_notifications(user_id: Optional[str] = Query(default=None)):
    """
    Get all notifications (newest first).

    Pass ?user_id=<id> to include per-user is_read state.
    Without user_id every item returns is_read=False.
    """
    try:
        with get_db_cursor() as cur:
            _ensure_reads_table(cur)

            if user_id:
                # LEFT JOIN so we get all notifications + read state for this user
                cur.execute("""
                    SELECT
                        n.id,
                        n.title,
                        n.message,
                        n.type,
                        n.sent_to,
                        n.status,
                        n.date_time,
                        CASE WHEN r.notification_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_read
                    FROM notifications n
                    LEFT JOIN user_notification_reads r
                        ON r.notification_id = n.id AND r.user_id = %s
                    ORDER BY n.date_time DESC
                """, (user_id,))
            else:
                cur.execute("""
                    SELECT
                        id, title, message, type, sent_to, status, date_time,
                        FALSE AS is_read
                    FROM notifications
                    ORDER BY date_time DESC
                """)

            rows = cur.fetchall()
            return [NotificationWithReadState(**row) for row in rows]

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

            # Verify notification exists
            cur.execute("SELECT id FROM notifications WHERE id = %s", (notification_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Notification not found")

            # INSERT ... ON CONFLICT DO NOTHING — safe to call multiple times
            cur.execute("""
                INSERT INTO user_notification_reads (user_id, notification_id, read_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, notification_id) DO NOTHING
            """, (user_id, notification_id, datetime.utcnow()))

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

            cur.execute("""
                DELETE FROM user_notification_reads
                WHERE user_id = %s AND notification_id = %s
            """, (user_id, notification_id))

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

            # Fetch all notification IDs then bulk insert, skipping conflicts
            cur.execute("SELECT id FROM notifications")
            all_ids = [row["id"] for row in cur.fetchall()]

            if not all_ids:
                return {"success": True, "message": "No notifications to mark", "count": 0}

            now = datetime.utcnow()
            values = [(user_id, nid, now) for nid in all_ids]

            cur.executemany("""
                INSERT INTO user_notification_reads (user_id, notification_id, read_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, notification_id) DO NOTHING
            """, values)

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
                cur.execute("""
                    SELECT
                        n.id, n.title, n.message, n.type, n.sent_to, n.status, n.date_time,
                        CASE WHEN r.notification_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_read
                    FROM notifications n
                    LEFT JOIN user_notification_reads r
                        ON r.notification_id = n.id AND r.user_id = %s
                    WHERE n.id = %s
                """, (user_id, notification_id))
            else:
                cur.execute("""
                    SELECT id, title, message, type, sent_to, status, date_time, FALSE AS is_read
                    FROM notifications
                    WHERE id = %s
                """, (notification_id,))

            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Notification not found")

            return NotificationWithReadState(**row)

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
            cur.execute(f"""
                UPDATE notifications
                SET {', '.join(update_fields)}
                WHERE id = %s
                RETURNING id, title, message, type, sent_to, status, date_time
            """, values)

            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Notification not found")

            return Notification(**row)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating notification: {str(e)}")


@router.delete("/{notification_id}")
async def delete_notification(notification_id: str):
    """Permanently delete a notification (admin — removes for all users)."""
    try:
        with get_db_cursor() as cur:
            # Clean up read records first to avoid orphaned rows
            cur.execute(
                "DELETE FROM user_notification_reads WHERE notification_id = %s",
                (notification_id,),
            )
            cur.execute(
                "DELETE FROM notifications WHERE id = %s RETURNING id",
                (notification_id,),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Notification not found")

            return {"success": True, "message": "Notification deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting notification: {str(e)}")


@router.get("/status/{status_filter}", response_model=List[Notification])
async def get_notifications_by_status(status_filter: str):
    """Get notifications by status (e.g. sent, pending, failed)."""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, title, message, type, sent_to, status, date_time
                FROM notifications
                WHERE status = %s
                ORDER BY date_time DESC
            """, (status_filter,))
            return [Notification(**row) for row in cur.fetchall()]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching notifications: {str(e)}")