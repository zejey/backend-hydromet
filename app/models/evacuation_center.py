from pydantic import BaseModel
from typing import Optional, List

class EvacuationCenter(BaseModel):
    id: Optional[int] = None
    name: str
    lat: float
    lng: float
    capacity: Optional[int]
    families: Optional[int]
    type: Optional[str]
    description: Optional[str]
    facilities: Optional[List[str]]
