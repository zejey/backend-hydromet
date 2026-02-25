"""
Weather API Clients
OpenWeather and WeatherLink API integrations
"""

import os
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from backend.config import Config
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class OpenWeatherClient:
    """Client for OpenWeather API"""
    
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    
    def __init__(self, api_key: Optional[str] = None, lat: Optional[float] = None, lon: Optional[float] = None):
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY")
        self.lat = lat or float(os.getenv("OPENWEATHER_LAT", "14.3644"))
        self.lon = lon or float(os.getenv("OPENWEATHER_LON", "121.0619"))
        
        if not self.api_key:
            raise ValueError("OpenWeather API key not configured")
    
    def get_current_weather(self) -> Dict[str, Any]:
        """Get current weather data"""
        url = f"{self.BASE_URL}/weather"
        params = {
            "lat": self.lat,
            "lon": self.lon,
            "appid": self.api_key,
            "units": "metric"
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"✅ Current weather fetched for ({self.lat}, {self.lon})")
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to fetch current weather: {e}")
            raise
    
    def get_forecast(self, cnt: int = 40) -> List[Dict[str, Any]]:
        """
        Get 5-day weather forecast (3-hour intervals)
        
        Args:
            cnt: Number of timestamps (default 40 = 5 days * 8 readings/day)
        
        Returns:
            List of forecast data points
        """
        url = f"{self.BASE_URL}/forecast"
        params = {
            "lat": self.lat,
            "lon": self.lon,
            "appid": self.api_key,
            "units": "metric",
            "cnt": cnt
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            forecasts = data.get("list", [])
            logger.info(f"✅ Forecast fetched: {len(forecasts)} time points")
            
            return forecasts
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to fetch forecast: {e}")
            raise


class WeatherLinkClient:
    """Client for WeatherLink API"""
    
    BASE_URL = "https://api.weatherlink.com/v2"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        station_id: Optional[str] = None,
        lsid: Optional[int] = None
    ):
        self.api_key = api_key or os.getenv("WEATHERLINK_API_KEY")
        self.api_secret = api_secret or os.getenv("WEATHERLINK_API_SECRET")
        self.station_id = station_id or os.getenv("WEATHERLINK_STATION_ID")
        self.lsid = lsid or int(os.getenv("WEATHERLINK_LSID", "813260"))
        
        if not all([self.api_key, self.api_secret, self.station_id]):
            raise ValueError("WeatherLink credentials not configured")
    
    def get_current_conditions(self) -> Dict[str, Any]:
        """Get current weather conditions from WeatherLink"""
        url = f"{self.BASE_URL}/current/{self.station_id}"
        params = {"api-key": self.api_key}
        headers = {"x-api-secret": self.api_secret}
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"✅ WeatherLink current conditions fetched")
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to fetch WeatherLink data: {e}")
            raise
    
    def get_historic_data(self, start_timestamp: int, end_timestamp: int) -> List[Dict[str, Any]]:
        """
        Get historic weather data
        
        Args:
            start_timestamp: Unix timestamp start
            end_timestamp: Unix timestamp end
        
        Returns:
            List of weather observations
        """
        url = f"{self.BASE_URL}/historic/{self.station_id}"
        params = {
            "api-key": self.api_key,
            "start-timestamp": start_timestamp,
            "end-timestamp": end_timestamp,
        }
        headers = {"x-api-secret": self.api_secret}
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            payload = response.json()
            
            # Find sensor with matching LSID
            sensor = next(
                (s for s in payload.get("sensors", []) if int(s.get("lsid", -1)) == self.lsid),
                None
            )
            
            if not sensor:
                logger.error(f"Sensor LSID {self.lsid} not found")
                return []
            
            records = sensor.get("data", [])
            logger.info(f"✅ WeatherLink historic data: {len(records)} records")
            
            return records
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to fetch historic data: {e}")
            raise
    
    def get_last_24h(self) -> List[Dict[str, Any]]:
        """Get last 24 hours of data"""
        end_ts = int(datetime.now(timezone.utc).timestamp())
        start_ts = end_ts - (24 * 3600)
        
        return self.get_historic_data(start_ts, end_ts)