"""
Email Verification Pydantic models
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class EmailVerificationRequest(BaseModel):
    user_id: str = Field(..., description="User ID (UUID)")
    email: EmailStr = Field(..., description="Email address to verify")


class EmailVerificationVerifyRequest(BaseModel):
    user_id: str = Field(..., description="User ID (UUID)")
    email: EmailStr = Field(..., description="Email address being verified")
    otp_code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")


class EmailVerificationResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None
