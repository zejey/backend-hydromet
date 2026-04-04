"""System Logs Pydantic models"""

from pydantic import BaseModel, Field
from typing import Optional, Literal, List
from datetime import datetime

LogStatus = Literal["Success", "Failed", "Warning"]


class SystemLogBase(BaseModel):
    # Display fields required by frontend
    user: Optional[str] = Field(
        None, max_length=120, description="Display name of actor"
    )
    action: str = Field(..., max_length=120)
    status: LogStatus
    details: str

    # Optional audit metadata
    user_id: Optional[int] = None
    role: Optional[str] = Field(None, max_length=50)
    ip_address: Optional[str] = Field(None, max_length=64)
    user_agent: Optional[str] = None


class SystemLogCreate(SystemLogBase):
    """Model for creating a system log (usually internal server use)"""
    pass


class SystemLog(SystemLogBase):
    """Model for system log response"""
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class SystemLogListResponse(BaseModel):
    """Paginated list response"""
    success: bool
    message: str
    total: int
    page: int
    page_size: int
    logs: List[SystemLog]
