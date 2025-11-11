"""
Notification Pydantic models
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class NotificationBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1)
    type: str = Field(..., max_length=50)  # e.g., "weather_alert", "warning", "info"
    sent_to: str = Field(..., max_length=50)  # e.g., "all", "barangay_name", "user_id"
    status: str = Field(..., max_length=50)  # e.g., "sent", "pending", "failed"


class NotificationCreate(NotificationBase):
    """Model for creating a new notification"""
    pass


class NotificationUpdate(BaseModel):
    """Model for updating a notification"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    message: Optional[str] = Field(None, min_length=1)
    type: Optional[str] = Field(None, max_length=50)
    sent_to: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(None, max_length=50)


class Notification(NotificationBase):
    """Model for notification response"""
    id: str
    date_time: datetime
    
    class Config:
        from_attributes = True


class NotificationResponse(BaseModel):
    """Standard response for notification operations"""
    success: bool
    message: str
    notification: Optional[Notification] = None