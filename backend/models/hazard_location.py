from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class HazardLocationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., max_length=64)          # e.g. 'flood', 'heat', etc.
    lat: float                                    # Latitude
    lng: float                                    # Longitude
    severity: str = Field(..., max_length=16)     # 'low', 'medium', 'high'
    description: Optional[str] = None

class HazardLocationCreate(HazardLocationBase):
    pass

class HazardLocationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    type: Optional[str] = Field(None, max_length=64)
    lat: Optional[float] = None
    lng: Optional[float] = None
    severity: Optional[str] = Field(None, max_length=16)
    description: Optional[str] = None

class HazardLocation(HazardLocationBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class HazardLocationResponse(BaseModel):
    success: bool
    message: str
    hazard: Optional[HazardLocation] = None
