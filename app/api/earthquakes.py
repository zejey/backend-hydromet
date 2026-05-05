"""
Earthquake API Endpoints
Real-time earthquake data from USGS for the Philippines
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime

from app.services.earthquake_client import EarthquakeClient
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/earthquakes", tags=["Earthquake Monitoring"])

_client = EarthquakeClient()


@router.get("/recent")
async def get_recent_earthquakes(
    hours: int = Query(default=24, description="Look-back window in hours", ge=1, le=168),
    min_magnitude: float = Query(default=3.0, description="Minimum magnitude", ge=0, le=10),
    limit: int = Query(default=50, description="Max results", ge=1, le=100),
):
    """
    Get recent earthquakes near the Philippines from USGS.

    Returns earthquakes within the Philippine bounding box
    (4.5°N-21.5°N, 116°E-127°E) for the specified time window.
    """
    try:
        quakes = _client.fetch_recent(
            hours=hours, min_magnitude=min_magnitude, limit=limit
        )

        return {
            "success": True,
            "source": "USGS",
            "count": len(quakes),
            "filters": {
                "hours": hours,
                "min_magnitude": min_magnitude,
            },
            "earthquakes": quakes,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Recent earthquakes fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/significant")
async def get_significant_earthquakes(
    days: int = Query(default=7, description="Look-back window in days", ge=1, le=30),
    min_magnitude: float = Query(default=5.0, description="Minimum magnitude", ge=4.0, le=10),
):
    """
    Get significant earthquakes (M5.0+) near the Philippines.
    Useful for dashboard display and historical context.
    """
    try:
        quakes = _client.fetch_significant(days=days, min_magnitude=min_magnitude)

        return {
            "success": True,
            "source": "USGS",
            "count": len(quakes),
            "earthquakes": quakes,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Significant earthquakes fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nearest")
async def get_nearest_earthquakes(
    lat: float = Query(default=14.3597, description="Latitude"),
    lon: float = Query(default=121.0583, description="Longitude"),
    radius_km: float = Query(default=300, description="Search radius in km", ge=10, le=1000),
    hours: int = Query(default=72, description="Look-back window in hours", ge=1, le=720),
    min_magnitude: float = Query(default=2.5, description="Minimum magnitude"),
):
    """
    Get earthquakes nearest to a specific location.
    Results are sorted by distance (nearest first).

    Default location: San Pedro, Laguna (14.3597, 121.0583)
    """
    try:
        quakes = _client.fetch_nearest(
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            hours=hours,
            min_magnitude=min_magnitude,
        )

        return {
            "success": True,
            "source": "USGS",
            "count": len(quakes),
            "search_center": {"lat": lat, "lon": lon},
            "radius_km": radius_km,
            "earthquakes": quakes,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Nearest earthquakes fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
