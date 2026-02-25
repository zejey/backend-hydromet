# backend/models/admin_invites.py

from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime

class AdminInviteBase(BaseModel):
    email: EmailStr
    role: str = Field('admin', max_length=32)

class AdminInviteCreate(AdminInviteBase):
    invited_by: Optional[str] = Field(None, max_length=128)

class AdminInvite(AdminInviteBase):
    id: int
    token: str = Field(..., max_length=128)
    used: bool
    created_at: datetime
    expires_at: datetime
    used_at: Optional[datetime] = None
    invited_by: Optional[str] = None

    class Config:
        from_attributes = True

class AdminInviteResponse(BaseModel):
    success: bool
    message: str
    invite: Optional[AdminInvite] = None

class SetPasswordRequest(BaseModel):
    token: str = Field(..., description="Token received from the invite email")
    password: str = Field(..., min_length=8, max_length=128)
