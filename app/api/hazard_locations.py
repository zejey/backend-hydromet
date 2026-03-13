from fastapi import APIRouter, HTTPException
from typing import List
from app.database import get_db_cursor
from app.models.hazard_location import (
    HazardLocation,
    HazardLocationCreate,
    HazardLocationUpdate,
    HazardLocationResponse
)

router = APIRouter(prefix="/api/hazard-locations", tags=["Hazard Locations"])

@router.get("/", response_model=List[HazardLocation])
def get_hazard_locations():
    """
    Get all hazard locations
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, name, type, location_lat AS lat, location_lng AS lng, severity, description,
                       created_at, updated_at
                FROM hazard_locations
                ORDER BY id
            """)
            hazards = cur.fetchall()
            return hazards
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.get("/{hazard_id}", response_model=HazardLocation)
def get_hazard_location_by_id(hazard_id: int):
    """
    Get a hazard location by id
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, name, type, location_lat AS lat, location_lng AS lng, severity, description, created_at, updated_at
                FROM hazard_locations WHERE id = %s
            """, (hazard_id,))
            hazard = cur.fetchone()
            if not hazard:
                raise HTTPException(status_code=404, detail="Hazard not found")
            return hazard
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

# Optionally add POST, PUT, DELETE endpoints as needed, following your other APIs' standards.   hazard: Optional[HazardLocation] = None
