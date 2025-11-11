"""
Safety Category and Safety Tip Pydantic models
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# Safety Category Models
class SafetyCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    order_num: Optional[int] = Field(None, ge=0)
    icon: Optional[str] = Field(None, max_length=100)  # e.g., "flood", "typhoon"
    gradient_colors: Optional[str] = None  # e.g., "#FF0000,#00FF00" for gradients
    is_active: bool = Field(default=True)


class CategoryCreate(SafetyCategoryBase):
    """Model for creating a new safety category"""
    pass


class CategoryUpdate(BaseModel):
    """Model for updating a safety category"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    order_num: Optional[int] = Field(None, ge=0)
    icon: Optional[str] = Field(None, max_length=100)
    gradient_colors: Optional[str] = None
    is_active: Optional[bool] = None


class SafetyCategory(SafetyCategoryBase):
    """Model for safety category response"""
    category_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Safety Tip Models
class SafetyTipBase(BaseModel):
    category_id: str = Field(..., max_length=128)
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    order_num: Optional[int] = Field(None, ge=0)
    icon: Optional[str] = Field(None, max_length=100)
    is_active: bool = Field(default=True)


class TipCreate(SafetyTipBase):
    """Model for creating a new safety tip"""
    pass


class TipUpdate(BaseModel):
    """Model for updating a safety tip"""
    category_id: Optional[str] = Field(None, max_length=128)
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = Field(None, min_length=1)
    order_num: Optional[int] = Field(None, ge=0)
    icon: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


class SafetyTip(SafetyTipBase):
    """Model for safety tip response"""
    tip_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Response Models
class CategoryResponse(BaseModel):
    """Standard response for category operations"""
    success: bool
    message: str
    category: Optional[SafetyCategory] = None


class TipResponse(BaseModel):
    """Standard response for tip operations"""
    success: bool
    message: str
    tip: Optional[SafetyTip] = None