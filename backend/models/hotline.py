"""
Emergency Hotline Pydantic models
"""

from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
import re


class HotlineBase(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=255)
    phone_number: str = Field(..., max_length=20)
    category: str = Field(..., max_length=100)  # e.g., "Medical", "Fire", "Police"
    icon_color: str = Field(..., max_length=50)  # e.g., "red", "#FF0000"
    icon_type: str = Field(..., max_length=50)  # e.g., "medical", "fire", "police"
    is_active: bool = Field(default=True)
    priority: int = Field(default=0, ge=0)  # Lower number = higher priority
    
    @validator('phone_number')
    def validate_phone_number(cls, v):
        # Allow various phone number formats
        v = v.strip()
        if not re.match(r'^[\d\s\-\+\(\)]+$', v):
            raise ValueError('Invalid phone number format')
        return v


class HotlineCreate(HotlineBase):
    """Model for creating a new hotline"""
    pass


class HotlineUpdate(BaseModel):
    """Model for updating a hotline"""
    service_name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    category: Optional[str] = Field(None, max_length=100)
    icon_color: Optional[str] = Field(None, max_length=50)
    icon_type: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=0)


class EmergencyHotline(HotlineBase):
    """Model for hotline response"""
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class HotlineResponse(BaseModel):
    """Standard response for hotline operations"""
    success: bool
    message: str
    hotline: Optional[EmergencyHotline] = None