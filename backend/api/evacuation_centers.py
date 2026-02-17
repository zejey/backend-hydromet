from fastapi import APIRouter, HTTPException, Query
from typing import List
from backend.database import get_db_cursor
from backend.models.evacuation_center import EvacuationCenter

router = APIRouter(prefix="/api/evacuation-centers", tags=["Evacuation Centers"])


def _convert_facilities(row_dict):
    """
    Convert PostgreSQL array to Python list for facilities field if needed.
    
    Args:
        row_dict: Dictionary representing a row from the database
        
    Returns:
        The modified row_dict with facilities as a list
    """
    if row_dict.get("facilities") and not isinstance(row_dict["facilities"], list):
        row_dict["facilities"] = list(row_dict["facilities"])
    return row_dict

@router.get("/", response_model=List[EvacuationCenter])
def get_evacuation_centers():
    """
    Get all evacuation centers
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, name, location_lat as lat, location_lng as lng,
                       capacity, families, type, description, facilities
                FROM evacuation_centers
                ORDER BY name ASC
            """)
            rows = cur.fetchall()
            # Convert PG array to Python list if needed
            return [_convert_facilities(dict(row)) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.get("/nearby", response_model=List[EvacuationCenter])
def get_nearby_evacuation_centers(
    lat: float = Query(..., description="Latitude of the point to search from", ge=-90, le=90),
    lng: float = Query(..., description="Longitude of the point to search from", ge=-180, le=180),
    radius: float = Query(..., description="Search radius in meters", gt=0)
):
    """
    Get evacuation centers within a specified radius from a given point.
    Uses Haversine formula to calculate distances.
    
    Parameters:
    - lat: Latitude of the search point
    - lng: Longitude of the search point  
    - radius: Search radius in meters
    
    Returns list of evacuation centers within the radius, ordered by distance (nearest first).
    """
    try:
        with get_db_cursor() as cur:
            # Haversine formula to calculate distance in meters
            # Earth's radius is approximately 6371000 meters
            # Using a CTE to avoid duplicate calculation and handle floating-point edge cases
            cur.execute("""
                WITH distances AS (
                    SELECT id, name, location_lat as lat, location_lng as lng,
                           capacity, families, type, description, facilities,
                           (
                               6371000 * acos(
                                   LEAST(1, GREATEST(-1,
                                       cos(radians(%s)) * cos(radians(location_lat)) * 
                                       cos(radians(location_lng) - radians(%s)) + 
                                       sin(radians(%s)) * sin(radians(location_lat))
                                   ))
                               )
                           ) as distance
                    FROM evacuation_centers
                )
                SELECT id, name, lat, lng, capacity, families, type, description, facilities
                FROM distances
                WHERE distance <= %s
                ORDER BY distance ASC
            """, (lat, lng, lat, radius))
            rows = cur.fetchall()
            # Convert facilities if needed
            return [_convert_facilities(dict(row)) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
