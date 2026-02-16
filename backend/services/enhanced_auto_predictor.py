"""
Enhanced Automatic Weather Prediction Service with Multi-Hazard Support
Integrates multi-hazard predictor with alert dispatching
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import sys
import os

# Add parent directory to path for config imports
# NOTE: In production, install package with 'pip install -e .' to avoid this
try:
    from scripts.config import (
        OPENWEATHER_API_KEY,
        OPENWEATHER_LAT,
        OPENWEATHER_LON,
        OPENWEATHER_BASE_URL
    )
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
    from scripts.config import (
        OPENWEATHER_API_KEY,
        OPENWEATHER_LAT,
        OPENWEATHER_LON,
        OPENWEATHER_BASE_URL
    )

import requests
from backend.ml.multi_hazard_predictor import get_multi_hazard_predictor
from backend.services.alert_dispatcher import get_alert_dispatcher

logger = logging.getLogger(__name__)


class EnhancedAutoPredictor:
    """
    Enhanced automatic predictor with multi-hazard support
    
    Features:
    - Multi-hazard, multi-horizon predictions
    - Intelligent alert dispatching with throttling
    - Hourly forecast analysis
    - Integration with existing auto-predictor endpoints
    """
    
    def __init__(
        self,
        use_multi_hazard: bool = True,
        enable_alerts: bool = True
    ):
        """
        Initialize enhanced auto-predictor
        
        Args:
            use_multi_hazard: Whether to use multi-hazard predictor (True) or legacy (False)
            enable_alerts: Whether to send SMS alerts
        """
        self.api_key = OPENWEATHER_API_KEY
        self.lat = OPENWEATHER_LAT
        self.lon = OPENWEATHER_LON
        self.base_url = OPENWEATHER_BASE_URL
        
        if not self.api_key:
            raise ValueError("❌ OPENWEATHER_API_KEY not set in .env!")
        
        # Multi-hazard predictor
        self.use_multi_hazard = use_multi_hazard
        if use_multi_hazard:
            self.multi_predictor = get_multi_hazard_predictor()
            logger.info("✓ Multi-hazard predictor initialized")
        else:
            self.multi_predictor = None
            logger.info("⚠️  Using legacy single-model predictor")
        
        # Alert dispatcher
        self.enable_alerts = enable_alerts
        if enable_alerts:
            self.alert_dispatcher = get_alert_dispatcher()
            logger.info("✓ Alert dispatcher initialized")
        else:
            self.alert_dispatcher = None
            logger.info("⚠️  Alert dispatching disabled")
        
        logger.info("🤖 Enhanced Auto-Predictor initialized")
        logger.info(f"   Location: ({self.lat}, {self.lon})")
        logger.info(f"   API Key: {self.api_key[:10]}...")
    
    def fetch_hourly_forecast(self) -> List[Dict[str, Any]]:
        """
        Fetch hourly forecast from OpenWeather (up to 96 hours / 4 days)
        
        Returns:
            List of hourly forecast data
        """
        # Try Pro hourly forecast endpoint first
        url = f"{self.base_url}/forecast/hourly"
        
        params = {
            'lat': self.lat,
            'lon': self.lon,
            'appid': self.api_key,
            'units': 'metric'  # Celsius for ML features
        }
        
        try:
            logger.info("🌤️  Fetching hourly forecast from OpenWeather...")
            logger.debug(f"   URL: {url}")
            
            response = requests.get(url, params=params, timeout=10)
            
            # Check for API errors
            if response.status_code == 401:
                logger.error("❌ OpenWeather API authentication failed!")
                return []
            elif response.status_code == 403:
                logger.warning("⚠️  Hourly forecast requires Pro subscription")
                logger.info("   Falling back to 3-hour forecast (free tier)...")
                return self._fetch_3hour_forecast()
            
            response.raise_for_status()
            
            data = response.json()
            forecast_list = data.get('list', [])
            
            logger.info(f"✅ Fetched {len(forecast_list)} hourly forecast points")
            
            return forecast_list
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ OpenWeather API HTTP error: {e}")
            logger.info("   Trying 3-hour forecast (free tier) as fallback...")
            return self._fetch_3hour_forecast()
        except Exception as e:
            logger.error(f"❌ Failed to fetch forecast: {e}")
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
            'units': 'metric'
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
    
    def run_multi_hazard_prediction(
        self,
        forecast_list: List[Dict]
    ) -> Dict[str, Any]:
        """
        Run multi-hazard prediction on current weather + forecast
        
        Args:
            forecast_list: List of forecast data points
            
        Returns:
            Multi-hazard prediction results
        """
        if not forecast_list:
            return {"success": False, "error": "No forecast data"}
        
        logger.info("📊 Running multi-hazard multi-horizon prediction...")
        
        try:
            # Use current conditions (first forecast point) for immediate prediction
            current_weather = forecast_list[0]
            
            # Run prediction
            results = self.multi_predictor.predict_from_weather_data(
                current_weather,
                source="openweather"
            )
            
            if not results.get("success"):
                logger.error(f"❌ Multi-hazard prediction failed: {results.get('error')}")
                return results
            
            # Add forecast context
            results["forecast_points_analyzed"] = len(forecast_list)
            results["forecast_hours_coverage"] = len(forecast_list) * (1 if len(forecast_list) > 50 else 3)
            
            # Log summary
            summary = results.get("summary", {})
            total_hazards = summary.get("total_hazards_detected", 0)
            
            if total_hazards > 0:
                logger.warning(f"⚠️  {total_hazards} hazard(s) detected")
                
                highest = summary.get("highest_risk_hazard")
                if highest:
                    logger.warning(f"   Highest: {highest['hazard']} @ {highest['horizon']}h ({highest['probability']:.1%})")
                
                # Log by horizon
                for horizon_key, hazards_list in summary.get("hazards_by_horizon", {}).items():
                    hazard_names = [h['hazard'] for h in hazards_list]
                    logger.warning(f"   {horizon_key}: {', '.join(hazard_names)}")
            else:
                logger.info("✅ No hazards detected in forecast period")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Multi-hazard prediction failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def dispatch_alerts(
        self,
        predictions: Dict[str, Any],
        location: str = "your area"
    ) -> Dict[str, Any]:
        """
        Dispatch alerts based on prediction results
        
        Args:
            predictions: Multi-hazard prediction results
            location: Location name for SMS messages
            
        Returns:
            Alert dispatch results
        """
        if not self.enable_alerts:
            logger.info("Alert dispatching disabled")
            return {"enabled": False}
        
        if not predictions.get("success"):
            logger.warning("Cannot dispatch alerts from failed predictions")
            return {"success": False, "error": "Prediction failed"}
        
        logger.info("📱 Dispatching hazard alerts...")
        
        try:
            dispatch_results = self.alert_dispatcher.dispatch_from_predictions(
                predictions=predictions,
                location=location,
                recipients=None  # Use all verified users
            )
            
            if dispatch_results.get("success"):
                hazards_count = dispatch_results.get("hazards_detected", 0)
                
                if hazards_count > 0:
                    if dispatch_results.get("dispatch_mode") == "bundled":
                        sent = dispatch_results.get("sent_count", 0)
                        eligible = dispatch_results.get("eligible_count", 0)
                        logger.info(f"✓ Bundled alert sent to {sent}/{eligible} users")
                    else:
                        total_sent = dispatch_results.get("total_sent", 0)
                        total_throttled = dispatch_results.get("total_throttled", 0)
                        logger.info(f"✓ Individual alerts: {total_sent} sent, {total_throttled} throttled")
                else:
                    logger.info("No hazards to alert")
            else:
                logger.error(f"Alert dispatch failed: {dispatch_results.get('error')}")
            
            return dispatch_results
            
        except Exception as e:
            logger.error(f"❌ Alert dispatching failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def run_once(self, location: str = "your area") -> Dict[str, Any]:
        """
        Run one enhanced prediction cycle
        
        Args:
            location: Location name for alerts
            
        Returns:
            Summary of predictions and alerts
        """
        start_time = datetime.now()
        
        logger.info("=" * 80)
        logger.info(f"🚀 Enhanced Auto-Predictor Cycle: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
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
        
        # Run multi-hazard prediction
        predictions = self.run_multi_hazard_prediction(forecast_list)
        
        # Dispatch alerts if hazards detected
        alert_results = None
        if predictions.get("success") and self.enable_alerts:
            alert_results = self.dispatch_alerts(predictions, location=location)
        
        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()
        
        # Build summary
        summary = {
            'success': predictions.get("success", False),
            'timestamp': start_time.isoformat(),
            'duration_seconds': duration,
            'forecast_intervals': len(forecast_list),
            'use_multi_hazard': self.use_multi_hazard,
            'predictions': predictions,
            'alerts': alert_results
        }
        
        # Log summary
        logger.info("=" * 80)
        if predictions.get("success"):
            total_hazards = predictions.get("summary", {}).get("total_hazards_detected", 0)
            
            if total_hazards > 0:
                logger.warning(f"⚠️  SUMMARY: {total_hazards} hazard(s) detected")
                
                if alert_results and alert_results.get("success"):
                    if alert_results.get("dispatch_mode") == "bundled":
                        sent = alert_results.get("sent_count", 0)
                        logger.warning(f"   📱 Bundled alerts sent to {sent} users")
                    else:
                        sent = alert_results.get("total_sent", 0)
                        logger.warning(f"   📱 {sent} alerts sent")
            else:
                logger.info("✅ No hazards detected")
        else:
            logger.error(f"❌ Prediction failed: {predictions.get('error')}")
        
        logger.info(f"⏱️  Cycle completed in {duration:.1f}s")
        logger.info("=" * 80)
        
        return summary
    
    async def run_continuous(self, interval_hours: int = 1, location: str = "your area"):
        """
        Run predictions continuously every N hours
        
        Args:
            interval_hours: How often to run (default: 1 hour)
            location: Location name for alerts
        """
        logger.info("🔁 Starting continuous enhanced auto-predictor")
        logger.info(f"   Interval: Every {interval_hours} hour(s)")
        logger.info(f"   Location: {self.lat}, {self.lon}")
        logger.info(f"   Multi-hazard: {self.use_multi_hazard}")
        logger.info(f"   Alerts: {self.enable_alerts}")
        logger.info("")
        
        while True:
            try:
                # Run prediction cycle
                summary = self.run_once(location=location)
                
                # Wait for next cycle
                next_run = datetime.now() + timedelta(hours=interval_hours)
                logger.info(f"😴 Next cycle at {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"   Sleeping for {interval_hours} hour(s)...")
                logger.info("")
                
                await asyncio.sleep(interval_hours * 3600)
                
            except KeyboardInterrupt:
                logger.info("🛑 Enhanced auto-predictor stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Auto-predictor error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                logger.info("⏳ Waiting 5 minutes before retry...")
                await asyncio.sleep(300)  # Wait 5 min before retry


# Singleton instance
_enhanced_auto_predictor = None


def get_enhanced_auto_predictor(
    use_multi_hazard: bool = True,
    enable_alerts: bool = True
) -> EnhancedAutoPredictor:
    """
    Get or create singleton EnhancedAutoPredictor instance
    
    Args:
        use_multi_hazard: Whether to use multi-hazard predictor
        enable_alerts: Whether to enable SMS alerts
        
    Returns:
        EnhancedAutoPredictor instance
    """
    global _enhanced_auto_predictor
    
    if _enhanced_auto_predictor is None:
        _enhanced_auto_predictor = EnhancedAutoPredictor(
            use_multi_hazard=use_multi_hazard,
            enable_alerts=enable_alerts
        )
    
    return _enhanced_auto_predictor


if __name__ == "__main__":
    # Testing
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("\n" + "="*80)
    print("ENHANCED AUTO-PREDICTOR - TESTING")
    print("="*80)
    
    # Create predictor (with alerts disabled for testing)
    predictor = get_enhanced_auto_predictor(
        use_multi_hazard=True,
        enable_alerts=False  # Disable for testing
    )
    
    print("\n✓ Enhanced auto-predictor initialized")
    print(f"  Multi-hazard: {predictor.use_multi_hazard}")
    print(f"  Alerts: {predictor.enable_alerts}")
    
    # Run one cycle
    print("\n" + "="*80)
    print("Running one prediction cycle...")
    print("="*80)
    
    summary = predictor.run_once(location="Test Location")
    
    print("\n" + "="*80)
    print("CYCLE SUMMARY")
    print("="*80)
    print(f"Success: {summary.get('success')}")
    print(f"Duration: {summary.get('duration_seconds', 0):.1f}s")
    print(f"Forecast intervals: {summary.get('forecast_intervals', 0)}")
    
    if summary.get('predictions', {}).get('success'):
        pred_summary = summary['predictions'].get('summary', {})
        print(f"Hazards detected: {pred_summary.get('total_hazards_detected', 0)}")
    
    print("\n✅ Enhanced auto-predictor test complete!")
