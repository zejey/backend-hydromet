"""
Automatic Weather Prediction Service
Fetches hourly forecast and runs predictions automatically
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import requests
from backend.ml.predictor import WeatherPredictor
from scripts.config import (
    OPENWEATHER_API_KEY,
    OPENWEATHER_LAT,
    OPENWEATHER_LON,
    OPENWEATHER_BASE_URL
)

logger = logging.getLogger(__name__)


class AutoPredictor:
    """Automatically fetch forecast and run predictions"""
    
    def __init__(self):
        self.predictor = WeatherPredictor()
        self.api_key = OPENWEATHER_API_KEY
        self.lat = OPENWEATHER_LAT
        self.lon = OPENWEATHER_LON
        self.base_url = OPENWEATHER_BASE_URL
        
        if not self.api_key:
            raise ValueError("❌ OPENWEATHER_API_KEY not set in .env!")
        
        logger.info("🤖 Auto-Predictor initialized")
        logger.info(f"   Location: ({self.lat}, {self.lon})")
        logger.info(f"   API Key: {self.api_key[:10]}...")
    
    def fetch_hourly_forecast(self) -> List[Dict[str, Any]]:
        """
        Fetch hourly forecast from OpenWeather (up to 96 hours / 4 days)
        
        Note: This requires OpenWeather Pro subscription
        Free tier only provides 5-day/3-hour forecast
        
        Returns:
            List of hourly forecast data
        """
        # ✅ OpenWeather Pro hourly forecast endpoint
        url = f"{self.base_url}/forecast/hourly"
        
        params = {
            'lat': self.lat,
            'lon': self.lon,
            'appid': self.api_key,
            'units': 'standard'  # Kelvin (to match your model training)
        }
        
        try:
            logger.info("🌤️  Fetching hourly forecast from OpenWeather Pro API...")
            logger.debug(f"   URL: {url}")
            logger.debug(f"   Params: lat={self.lat}, lon={self.lon}")
            
            response = requests.get(url, params=params, timeout=10)
            
            # Check for API errors
            if response.status_code == 401:
                logger.error("❌ OpenWeather API authentication failed!")
                logger.error("   Check if your API key is valid and has Pro subscription")
                return []
            elif response.status_code == 403:
                logger.error("❌ OpenWeather API access forbidden!")
                logger.error("   Hourly forecast requires Pro subscription")
                logger.info("   Falling back to 3-hour forecast (free tier)...")
                return self._fetch_3hour_forecast()  # Fallback
            
            response.raise_for_status()
            
            data = response.json()
            forecast_list = data.get('list', [])
            
            logger.info(f"✅ Fetched {len(forecast_list)} hourly forecast points")
            
            return forecast_list
            
        except requests.exceptions.Timeout:
            logger.error("❌ OpenWeather API timeout")
            return []
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ OpenWeather API HTTP error: {e}")
            if 'response' in locals():
                logger.error(f"   Status: {response.status_code}")
                logger.error(f"   Response: {response.text[:200]}")
            
            # Fallback to free tier
            logger.info("   Trying 3-hour forecast (free tier) as fallback...")
            return self._fetch_3hour_forecast()
        except Exception as e:
            logger.error(f"❌ Failed to fetch forecast: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _fetch_3hour_forecast(self) -> List[Dict[str, Any]]:
        """
        Fallback: Fetch 5-day/3-hour forecast (FREE tier)
        
        Returns:
            List of 3-hour interval forecast data (40 intervals = 5 days)
        """
        url = f"{self.base_url}/forecast"
        
        params = {
            'lat': self.lat,
            'lon': self.lon,
            'appid': self.api_key,
            'units': 'standard'
        }
        
        try:
            logger.info("🌤️  Fetching 3-hour forecast from OpenWeather (free tier)...")
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            forecast_list = data.get('list', [])
            
            logger.info(f"✅ Fetched {len(forecast_list)} forecast intervals (3-hour steps)")
            logger.info(f"   Coverage: {len(forecast_list) * 3} hours (~{len(forecast_list) * 3 / 24:.1f} days)")
            
            return forecast_list
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch 3-hour forecast: {e}")
            return []
    
    def run_predictions_on_forecast(self, forecast_list: List[Dict]) -> List[Dict]:
        """
        Run predictions on each forecast interval
        
        Returns:
            List of predictions with hazards detected
        """
        hazards_found = []
        
        # Detect if hourly (96 items) or 3-hourly (40 items)
        is_hourly = len(forecast_list) > 50
        interval_hours = 1 if is_hourly else 3
        
        logger.info(f"📊 Processing {len(forecast_list)} forecast points ({interval_hours}h intervals)")
        
        for i, forecast_hour in enumerate(forecast_list):
            try:
                # Extract forecast time
                dt = forecast_hour.get('dt')
                forecast_time = datetime.fromtimestamp(dt)
                hours_ahead = i * interval_hours
                
                logger.info(f"🔮 Predicting for {forecast_time.strftime('%Y-%m-%d %H:%M')} (T+{hours_ahead}h)")
                
                # Run prediction
                result = self.predictor.predict({
                    'weather_data': forecast_hour,
                    'source': 'openweather'
                })
                
                # Check if hazard detected
                prediction = result.get('prediction', {})
                if prediction.get('event') == 1:
                    hazard_info = {
                        'forecast_time': forecast_time.isoformat(),
                        'hours_ahead': hours_ahead,
                        'hazard_type': prediction.get('hazard_type'),
                        'probability': prediction.get('probability'),
                        'risk_level': prediction.get('risk_level'),
                        'hazards': prediction.get('hazards', []),
                        'weather_data': {
                            'temp': forecast_hour.get('main', {}).get('temp'),
                            'pressure': forecast_hour.get('main', {}).get('pressure'),
                            'humidity': forecast_hour.get('main', {}).get('humidity'),
                            'wind_speed': forecast_hour.get('wind', {}).get('speed'),
                            'rain': forecast_hour.get('rain', {}).get('1h', 0)
                        }
                    }
                    
                    hazards_found.append(hazard_info)
                    
                    logger.warning(f"⚠️  HAZARD DETECTED at T+{hours_ahead}h: {hazard_info['hazard_type']}")
                    logger.warning(f"    Time: {forecast_time.strftime('%Y-%m-%d %H:%M')}")
                    logger.warning(f"    Probability: {hazard_info['probability']*100:.1f}%")
                    logger.warning(f"    Risk: {hazard_info['risk_level']}")
                    logger.warning(f"    Details: {', '.join(hazard_info['hazards'])}")
                else:
                    logger.debug(f"   ✓ No hazard at T+{hours_ahead}h")
            
            except Exception as e:
                logger.error(f"❌ Prediction failed for interval {i}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                continue
        
        return hazards_found    

    def run_once(self) -> Dict[str, Any]:
        """
        Run one prediction cycle
        
        Returns:
            Summary of hazards found
        """
        start_time = datetime.now()
        logger.info("=" * 80)
        logger.info(f"🚀 Starting auto-prediction cycle at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)
        
        # Fetch forecast
        forecast_list = self.fetch_hourly_forecast()
        
        if not forecast_list:
            logger.error("❌ No forecast data available")
            return {
                'success': False,
                'error': 'No forecast data',
                'timestamp': start_time.isoformat()
            }
        
        # Run predictions
        hazards = self.run_predictions_on_forecast(forecast_list)
        
        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()
        
        # Summary
        summary = {
            'success': True,
            'timestamp': start_time.isoformat(),
            'duration_seconds': duration,
            'forecast_intervals': len(forecast_list),
            'hazards_detected': len(hazards),
            'hazards': hazards
        }
        
        logger.info("=" * 80)
        if hazards:
            logger.warning(f"⚠️  SUMMARY: {len(hazards)} hazard(s) detected in next 48h")
            logger.warning("")
            for h in hazards:
                logger.warning(f"   📍 T+{h['hours_ahead']}h ({h['forecast_time'][:16]})")
                logger.warning(f"      Type: {h['hazard_type']}")
                logger.warning(f"      Risk: {h['risk_level'].upper()}")
                logger.warning(f"      Probability: {h['probability']*100:.1f}%")
                logger.warning(f"      Details: {', '.join(h['hazards'])}")
                logger.warning("")
        else:
            logger.info("✅ No hazards detected in forecast")
        
        logger.info(f"⏱️  Cycle completed in {duration:.1f}s")
        logger.info("=" * 80)
        
        return summary
    
    async def run_continuous(self, interval_hours: int = 1):
        """
        Run predictions continuously every N hours
        
        Args:
            interval_hours: How often to run (default: 1 hour)
        """
        logger.info("🔁 Starting continuous auto-predictor")
        logger.info(f"   Interval: Every {interval_hours} hour(s)")
        logger.info(f"   Location: {self.lat}, {self.lon}")
        logger.info("")
        
        while True:
            try:
                # Run prediction cycle
                summary = self.run_once()
                
                # Wait for next cycle
                next_run = datetime.now() + timedelta(hours=interval_hours)
                logger.info(f"😴 Next cycle at {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"   Sleeping for {interval_hours} hour(s)...")
                logger.info("")
                
                await asyncio.sleep(interval_hours * 3600)
                
            except KeyboardInterrupt:
                logger.info("🛑 Auto-predictor stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Auto-predictor error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                logger.info("⏳ Waiting 5 minutes before retry...")
                await asyncio.sleep(300)  # Wait 5 min before retry


# Singleton instance
_auto_predictor = None


def get_auto_predictor() -> AutoPredictor:
    """Get or create auto-predictor singleton"""
    global _auto_predictor
    if _auto_predictor is None:
        _auto_predictor = AutoPredictor()
    return _auto_predictor
