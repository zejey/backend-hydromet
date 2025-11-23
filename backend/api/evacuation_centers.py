from fastapi import APIRouter, HTTPException
from typing import List
from backend.utils.database import get_db_cursor
from backend.models.evacuation_center import EvacuationCenter

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
