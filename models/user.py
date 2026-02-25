"""
User Pydantic models
"""

from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
import re


class UserBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=64)
    middle_name: Optional[str] = Field(None, max_length=64)
    last_name: str = Field(..., min_length=1, max_length=64)
    suffix: Optional[str] = Field(None, max_length=16)
    house_address: str = Field(..., min_length=1)
    barangay: str = Field(..., min_length=1, max_length=64)
    phone_number: str = Field(..., min_length=11, max_length=11)
    role: str = Field(default="resident", max_length=32)
    
    @validator('phone_number')
    def validate_phone_number(cls, v):
        v = v.strip()
        if not re.match(r'^09\d{9}$', v):
            raise ValueError('Phone number must be 11 digits starting with 09')
        return v


class UserCreate(UserBase):
    """Model for creating a new user"""
    pass


class UserUpdate(UserBase):
    """Model for updating a user"""
    is_verified: Optional[bool] = None


class User(UserBase):
    """Model for user response"""
    id: str
    is_verified: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class CheckUserRequest(BaseModel):
    phone_number: str = Field(..., min_length=11, max_length=11)


class LoginRequest(BaseModel):
    phone_number: str = Field(..., min_length=11, max_length=11)


class CheckUserResponse(BaseModel):
    success: bool
    exists: bool
    message: str
    user: Optional[User] = None


class LoginResponse(BaseModel):
    success: bool
    message: str
    user: Optional[User] = None