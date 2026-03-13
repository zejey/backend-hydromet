from fastapi import APIRouter, HTTPException, Query
from typing import List
from api.database import get_db_cursor
from api.models.evacuation_center import EvacuationCenter

router = APIRouter(prefix="/api/evacuation-centers", tags=["Evacuation Centers"])

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
            # If any, convert PG array to Python list (psycopg2 usually does this automatically)
            for row in rows:
                if row.get("facilities") and not isinstance(row["facilities"], list):
                    row["facilities"] = list(row["facilities"])
            return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.get("/nearby", response_model=List[EvacuationCenter])
def get_nearby_evacuation_centers(
    lat: float = Query(..., description="Latitude of the point to search from"),
    lng: float = Query(..., description="Longitude of the point to search from"),
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
            cur.execute("""
                SELECT id, name, location_lat as lat, location_lng as lng,
                       capacity, families, type, description, facilities,
                       (
                           6371000 * acos(
                               cos(radians(%s)) * cos(radians(location_lat)) * 
                               cos(radians(location_lng) - radians(%s)) + 
                               sin(radians(%s)) * sin(radians(location_lat))
                           )
                       ) as distance
                FROM evacuation_centers
                WHERE (
                    6371000 * acos(
                        cos(radians(%s)) * cos(radians(location_lat)) * 
                        cos(radians(location_lng) - radians(%s)) + 
                        sin(radians(%s)) * sin(radians(location_lat))
                    )
                ) <= %s
                ORDER BY distance ASC
            """, (lat, lng, lat, lat, lng, lat, radius))
            rows = cur.fetchall()
            # Convert facilities if needed and remove distance field
            result = []
            for row in rows:
                row_dict = dict(row)
                # Remove distance field as it's not part of the model
                row_dict.pop('distance', None)
                # Convert PG array to Python list if needed
                if row_dict.get("facilities") and not isinstance(row_dict["facilities"], list):
                    row_dict["facilities"] = list(row_dict["facilities"])
                result.append(row_dict)
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")