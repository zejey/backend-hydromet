"""
Notifications API endpoints
"""

from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime
import uuid

from backend.models.notification import Notification, NotificationCreate, NotificationUpdate
from backend.database import get_db_cursor

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.post("/", response_model=Notification, status_code=status.HTTP_201_CREATED)
async def create_notification(notification_data: NotificationCreate):
    """Create a new notification"""
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
                now
            ))
            
            new_notification = cur.fetchone()
            return Notification(**new_notification)
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating notification: {str(e)}"
        )


@router.get("/", response_model=List[Notification])
async def get_notifications():
    """Get all notifications (newest first)"""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, title, message, type, sent_to, status, date_time
                FROM notifications
                ORDER BY date_time DESC
            """)
            notifications = cur.fetchall()
            return [Notification(**notif) for notif in notifications]
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching notifications: {str(e)}"
        )


@router.get("/{notification_id}", response_model=Notification)
async def get_notification(notification_id: str):
    """Get notification by ID"""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, title, message, type, sent_to, status, date_time
                FROM notifications
                WHERE id = %s
            """, (notification_id,))
            
            notification_data = cur.fetchone()
            
            if not notification_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Notification not found"
                )
            
            return Notification(**notification_data)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching notification: {str(e)}"
        )


@router.put("/{notification_id}", response_model=Notification)
async def update_notification(notification_id: str, notification_data: NotificationUpdate):
    """Update notification"""
    try:
        with get_db_cursor() as cur:
            # Build dynamic update query based on provided fields
            update_fields = []
            values = []
            
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
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No fields to update"
                )
            
            values.append(notification_id)
            
            cur.execute(f"""
                UPDATE notifications
                SET {', '.join(update_fields)}
                WHERE id = %s
                RETURNING id, title, message, type, sent_to, status, date_time
            """, values)
            
            updated_notification = cur.fetchone()
            
            if not updated_notification:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Notification not found"
                )
            
            return Notification(**updated_notification)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating notification: {str(e)}"
        )


@router.delete("/{notification_id}")
async def delete_notification(notification_id: str):
    """Delete notification"""
    try:
        with get_db_cursor() as cur:
            cur.execute("DELETE FROM notifications WHERE id = %s RETURNING id", (notification_id,))
            deleted = cur.fetchone()
            
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Notification not found"
                )
            
            return {
                "success": True,
                "message": "Notification deleted successfully"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting notification: {str(e)}"
        )


@router.get("/status/{status_filter}", response_model=List[Notification])
async def get_notifications_by_status(status_filter: str):
    """Get notifications by status (e.g., 'sent', 'pending', 'failed')"""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, title, message, type, sent_to, status, date_time
                FROM notifications
                WHERE status = %s
                ORDER BY date_time DESC
            """, (status_filter,))
            
            notifications = cur.fetchall()
            return [Notification(**notif) for notif in notifications]
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching notifications: {str(e)}"
        )