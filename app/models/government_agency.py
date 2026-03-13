from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime


class LatLng(BaseModel):
    latitude: float
    longitude: float


class GovernmentAgency(BaseModel):
    id: Optional[str] = None
    name: str
    location: LatLng
    type: str
    contact: Optional[str] = None
    facilities: List[str] = []
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GovernmentAgencyCreate(BaseModel):
    name: str
    location: LatLng
    type: str
    contact: Optional[str] = None
    facilities: List[str] = []
    description: Optional[str] = None


class GovernmentAgencyUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[LatLng] = None
    type: Optional[str] = None
    contact: Optional[str] = None
    facilities: Optional[List[str]] = None
    description: Optional[str] = None
