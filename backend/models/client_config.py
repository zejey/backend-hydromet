"""
Pydantic models for client threshold configuration
"""

from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime


class ClientConfigCreate(BaseModel):
    """Model for creating a new client configuration"""
    client_id: str = Field(..., min_length=1, max_length=100, description="Unique client identifier")
    location_name: str = Field(..., min_length=1, max_length=200, description="Location name")
    barangay: Optional[str] = Field(None, max_length=100, description="Barangay name")
    
    rain_multiplier: float = Field(1.0, ge=0.1, le=5.0, description="Rain threshold multiplier")
    wind_multiplier: float = Field(1.0, ge=0.1, le=5.0, description="Wind threshold multiplier")
    heat_multiplier: float = Field(1.0, ge=0.1, le=5.0, description="Heat threshold multiplier")
    pressure_multiplier: float = Field(1.0, ge=0.1, le=5.0, description="Pressure threshold multiplier")
    
    alert_duration_hours: int = Field(2, ge=0, le=48, description="Alert duration in hours")
    cooldown_hours: int = Field(6, ge=0, le=168, description="Cooldown period in hours")
    
    description: Optional[str] = Field(None, max_length=500, description="Configuration description")
    created_by: Optional[str] = Field(None, max_length=100, description="Creator identifier")


class ClientConfigUpdate(BaseModel):
    """Model for updating an existing client configuration"""
    location_name: Optional[str] = Field(None, min_length=1, max_length=200)
    barangay: Optional[str] = Field(None, max_length=100)
    
    rain_multiplier: Optional[float] = Field(None, ge=0.1, le=5.0)
    wind_multiplier: Optional[float] = Field(None, ge=0.1, le=5.0)
    heat_multiplier: Optional[float] = Field(None, ge=0.1, le=5.0)
    pressure_multiplier: Optional[float] = Field(None, ge=0.1, le=5.0)
    
    alert_duration_hours: Optional[int] = Field(None, ge=0, le=48)
    cooldown_hours: Optional[int] = Field(None, ge=0, le=168)
    
    description: Optional[str] = Field(None, max_length=500)


class ClientConfigResponse(BaseModel):
    """Model for client configuration response"""
    client_id: str
    location_name: str
    barangay: Optional[str]
    
    rain_multiplier: float
    wind_multiplier: float
    heat_multiplier: float
    pressure_multiplier: float
    
    alert_duration_hours: int
    cooldown_hours: int
    
    description: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    created_by: Optional[str]
    
    class Config:
        from_attributes = True


class ClientConfigListResponse(BaseModel):
    """Model for listing multiple client configurations"""
    success: bool = True
    total: int
    configs: list[ClientConfigResponse]


class ClientConfigDeleteResponse(BaseModel):
    """Model for delete response"""
    success: bool = True
    message: str
    client_id: str
