"""
Admin Pydantic models
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional


class AdminBase(BaseModel):
    email: EmailStr
    role: str = Field(..., max_length=50)
    username: str = Field(..., min_length=3, max_length=50)
    uid: str = Field(..., max_length=128)


class AdminCreate(AdminBase):
    """Model for creating a new admin"""
    pass


class AdminUpdate(BaseModel):
    """Model for updating an admin"""
    email: Optional[EmailStr] = None
    role: Optional[str] = Field(None, max_length=50)
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    uid: Optional[str] = Field(None, max_length=128)


class Admin(AdminBase):
    """Model for admin response"""
    id: int
    
    class Config:
        from_attributes = True


class AdminResponse(BaseModel):
    """Standard response for admin operations"""
    success: bool
    message: str
    admin: Optional[Admin] = None