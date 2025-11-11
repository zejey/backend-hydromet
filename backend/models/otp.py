"""
OTP Pydantic models
"""

from pydantic import BaseModel, Field
from typing import Optional


class OTPRequest(BaseModel):
    phone_number: str = Field(..., min_length=11, max_length=12, description="Phone number in format 09XXXXXXXXX or 639XXXXXXXXX")


class OTPVerifyRequest(BaseModel):
    phone_number: str = Field(..., min_length=11, max_length=12)
    otp_code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")


class OTPResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None
