"""
Weather Data Proxy API
Securely fetches weather data from OpenWeather API without exposing API key
"""

from fastapi import APIRouter, HTTPException, status, Query
from typing import Optional
import httpx
import os
from datetime import datetime

from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/weather", tags=["Weather Data"])

# Load API key from environment variable
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"
OPENWEATHER_GEO_URL = "https://api.openweathermap.org/geo/1.0"

if not OPENWEATHER_API_KEY:
    logger.warning("⚠️ OPENWEATHER_API_KEY not set in environment variables")


async def fetch_from_openweather(url: str) -> dict:
    """Helper function to fetch data from OpenWeather API"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"OpenWeather API error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Weather API error: {e.response.text}"
        )
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather service temporarily unavailable"
        )


@router.get("/current")
async def get_current_weather(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    units: str = Query(default="metric", description="Units of measurement (metric, imperial)")
):
    """
    Get current weather by coordinates
    
    Query Parameters:
    - lat: Latitude (e.g., 14.3583)
    - lon: Longitude (e.g., 121.0167)
    - units: metric (Celsius) or imperial (Fahrenheit)
    
    Example:
    GET /api/weather/current?lat=14.3583&lon=121.0167
    """
    url = f"{OPENWEATHER_BASE_URL}/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units={units}"
    
    logger.info(f"Fetching current weather for ({lat}, {lon})")
    data = await fetch_from_openweather(url)
    
    return {
        "success": True,
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/current/city")
async def get_current_weather_by_city(
    city: str = Query(..., description="City name"),
    units: str = Query(default="metric", description="Units of measurement")
):
    """
    Get current weather by city name
    
    Query Parameters:
    - city: City name (e.g., "San Pedro")
    - units: metric or imperial
    
    Example:
    GET /api/weather/current/city?city=San Pedro
    """
    url = f"{OPENWEATHER_BASE_URL}/weather?q={city}&appid={OPENWEATHER_API_KEY}&units={units}"
    
    logger.info(f"Fetching current weather for city: {city}")
    data = await fetch_from_openweather(url)
    
    return {
        "success": True,
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/forecast")
async def get_forecast(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    units: str = Query(default="metric", description="Units of measurement"),
    cnt: Optional[int] = Query(default=None, description="Number of timestamps (max 40)")
):
    """
    Get 5-day/3-hour forecast by coordinates
    
    Query Parameters:
    - lat: Latitude
    - lon: Longitude
    - units: metric or imperial
    - cnt: Number of forecast points (optional, max 40)
    
    Returns 3-hour interval forecasts for up to 5 days
    
    Example:
    GET /api/weather/forecast?lat=14.3583&lon=121.0167&cnt=24
    """
    url = f"{OPENWEATHER_BASE_URL}/forecast?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units={units}"
    
    if cnt:
        url += f"&cnt={min(cnt, 40)}"  # Max 40 points
    
    logger.info(f"Fetching forecast for ({lat}, {lon})")
    data = await fetch_from_openweather(url)
    
    return {
        "success": True,
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/air-quality")
async def get_air_quality(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude")
):
    """
    Get air pollution data by coordinates
    
    Query Parameters:
    - lat: Latitude
    - lon: Longitude
    
    Returns Air Quality Index (AQI) and pollutant levels
    
    Example:
    GET /api/weather/air-quality?lat=14.3583&lon=121.0167
    """
    url = f"{OPENWEATHER_BASE_URL}/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}"
    
    logger.info(f"Fetching air quality for ({lat}, {lon})")
    data = await fetch_from_openweather(url)
    
    return {
        "success": True,
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/geocoding/search")
async def search_location(
    q: str = Query(..., description="City name to search"),
    limit: int = Query(default=5, description="Number of results (max 5)")
):
    """
    Search for city coordinates by name
    
    Query Parameters:
    - q: City name (e.g., "San Pedro")
    - limit: Number of results (default 5)
    
    Returns list of matching locations with coordinates
    
    Example:
    GET /api/weather/geocoding/search?q=San Pedro&limit=5
    """
    url = f"{OPENWEATHER_GEO_URL}/direct?q={q}&limit={min(limit, 5)}&appid={OPENWEATHER_API_KEY}"
    
    logger.info(f"Searching location: {q}")
    data = await fetch_from_openweather(url)
    
    return {
        "success": True,
        "data": data,
        "count": len(data),
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/geocoding/reverse")
async def reverse_geocode(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    limit: int = Query(default=1, description="Number of results")
):
    """
    Get location name from coordinates (reverse geocoding)
    
    Query Parameters:
    - lat: Latitude
    - lon: Longitude
    - limit: Number of results (default 1)
    
    Returns location names for given coordinates
    
    Example:
    GET /api/weather/geocoding/reverse?lat=14.3583&lon=121.0167
    """
    url = f"{OPENWEATHER_GEO_URL}/reverse?lat={lat}&lon={lon}&limit={limit}&appid={OPENWEATHER_API_KEY}"
    
    logger.info(f"Reverse geocoding: ({lat}, {lon})")
    data = await fetch_from_openweather(url)
    
    return {
        "success": True,
        "data": data,
        "count": len(data),
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/health")
async def weather_health_check():
    """
    Check if weather API is accessible
    
    Returns:
    - API key status
    - OpenWeather API connectivity
    """
    has_api_key = bool(OPENWEATHER_API_KEY)
    
    if not has_api_key:
        return {
            "success": False,
            "status": "error",
            "message": "OpenWeather API key not configured",
            "api_key_set": False
        }
    
    try:
        # Test API with a simple request (San Pedro coordinates)
        url = f"{OPENWEATHER_BASE_URL}/weather?lat=14.3583&lon=121.0167&appid={OPENWEATHER_API_KEY}&units=metric"
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            response.raise_for_status()
        
        return {
            "success": True,
            "status": "operational",
            "message": "Weather API is accessible",
            "api_key_set": True,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Weather API health check failed: {e}")
        return {
            "success": False,
            "status": "error",
            "message": f"Weather API error: {str(e)}",
            "api_key_set": True
        }