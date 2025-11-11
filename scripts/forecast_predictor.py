"""
Forecast weather hazard predictions.
Fetches OpenWeather forecast and uses trained model to predict hazards.

Usage:
    python forecast_predictor.py --summary
    python forecast_predictor.py --detailed
    python forecast_predictor.py --save hazard_forecast.json
"""
import os
import sys
import argparse
import json
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from model import predict_from_features, features_from_openweather_json
from hazard_type_mapping import determine_hazard_type
from logger_util import get_logger

load_dotenv()
logger = get_logger(__name__)

class OpenWeatherForecastClient:
    """Fetch weather forecast from OpenWeatherMap API."""
    
    BASE_URL = "https://api.openweathermap.org/data/2.5/forecast"
    
    def __init__(self):
        self.api_key = os.getenv("OPENWEATHER_API_KEY")
        self.lat = float(os.getenv("OPENWEATHER_LAT", 14.3644))
        self.lon = float(os.getenv("OPENWEATHER_LON", -121.0619))
        
        if not self.api_key:
            raise ValueError("OPENWEATHER_API_KEY missing in .env")
    
    def fetch_forecast(self):
        """Fetch 5-day forecast (40 data points, 3-hour intervals)."""
        params = {
            "lat": self.lat,
            "lon": self.lon,
            "appid": self.api_key,
            "units": "metric"  # Celsius
        }
        
        logger.info(f"Fetching forecast for lat={self.lat}, lon={self.lon}")
        
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise
        
        data = response.json()
        forecasts = data.get("list", [])
        logger.info(f"Retrieved {len(forecasts)} forecast records (5 days, 3-hour intervals)")
        
        return forecasts
    
    def get_current(self):
        """Fetch current weather."""
        current_url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": self.lat,
            "lon": self.lon,
            "appid": self.api_key,
            "units": "metric"
        }
        
        try:
            response = requests.get(current_url, params=params, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Current weather fetch failed: {e}")
            return None
        
        return response.json()

def predict_forecast(forecasts):
    """Make predictions for each forecast record."""
    predictions = []
    
    for forecast in forecasts:
        try:
            features = features_from_openweather_json(forecast)
            prediction = predict_from_features(features)
            
            dt = forecast.get("dt")
            forecast_dt = datetime.fromtimestamp(dt, tz=timezone.utc)
            
            result = {
                "timestamp": forecast_dt.isoformat(),
                "timestamp_unix": dt,
                "prediction": prediction,
                "summary": {
                    "event_probability": f"{prediction['probability']*100:.1f}%",
                    "hazard_type": prediction["hazard_type"],
                    "hazards_triggered": prediction["hazards_triggered"]
                }
            }
            
            predictions.append(result)
        
        except Exception as e:
            logger.warning(f"Prediction for record failed: {e}")
            continue
    
    return predictions

def print_summary(predictions):
    """Print short summary of hazards."""
    logger.info("=" * 70)
    logger.info("🌦️  WEATHER HAZARD FORECAST SUMMARY")
    logger.info("=" * 70)
    
    hazard_events = [p for p in predictions if p["prediction"]["event"] == 1]
    
    if not hazard_events:
        logger.info("✅ No significant hazards detected in next 5 days")
    else:
        logger.warning(f"⚠️  Found {len(hazard_events)} hazardous periods:")
        logger.info("-" * 70)
        
        for p in hazard_events:
            ts = p["timestamp"]
            summary = p["summary"]
            logger.warning(f"  📅 {ts}")
            logger.warning(f"     Hazard Type: {summary['hazard_type']}")
            logger.warning(f"     Event Probability: {summary['event_probability']}")
            if summary['hazards_triggered']:
                logger.warning(f"     Triggers: {', '.join(summary['hazards_triggered'][:3])}")
            logger.info("-" * 70)
    
    logger.info("=" * 70)
    
    return len(hazard_events)

def print_detailed(predictions):
    """Print detailed predictions."""
    logger.info("=" * 70)
    logger.info("🔍 DETAILED HAZARD PREDICTIONS")
    logger.info("=" * 70)
    
    for i, p in enumerate(predictions, 1):
        ts = p["timestamp"]
        pred = p["prediction"]
        
        logger.info(f"\n[{i}] {ts}")
        logger.info(f"    Event Predicted: {'YES' if pred['event'] == 1 else 'NO'}")
        logger.info(f"    Probability: {pred['probability']*100:.2f}%")
        logger.info(f"    Hazard Type: {pred['hazard_type']}")
        logger.info(f"    Triggered: {', '.join(pred['hazards_triggered']) if pred['hazards_triggered'] else 'None'}")
        logger.info(f"    Confidence: {pred['probabilities']['event']*100:.2f}%")
    
    logger.info("\n" + "=" * 70)

def main():
    parser = argparse.ArgumentParser(description="Predict weather hazards from forecast")
    parser.add_argument("--summary", action="store_true", help="Print summary of hazards")
    parser.add_argument("--detailed", action="store_true", help="Print detailed predictions")
    parser.add_argument("--save", type=str, help="Save predictions to JSON file")
    parser.add_argument("--current", action="store_true", help="Also predict current weather")
    
    args = parser.parse_args()
    
    # Default to summary if no args
    if not any([args.summary, args.detailed, args.save, args.current]):
        args.summary = True
    
    logger.info("=" * 70)
    logger.info(f"🚀 Starting Forecast Predictions: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info("=" * 70)
    
    try:
        # Fetch forecasts
        client = OpenWeatherForecastClient()
        forecasts = client.fetch_forecast()
        
        if not forecasts:
            logger.error("❌ No forecast data received")
            return 1
        
        # Make predictions
        predictions = predict_forecast(forecasts)
        
        if not predictions:
            logger.error("❌ No valid predictions generated")
            return 1
        
        logger.info(f"✅ Generated predictions for {len(predictions)} forecast records")
        
        # Get current weather if requested
        if args.current:
            logger.info("\nFetching current weather...")
            current = client.get_current()
            if current:
                try:
                    features = features_from_openweather_json(current)
                    current_pred = predict_from_features(features)
                    logger.info("📍 CURRENT WEATHER PREDICTION:")
                    logger.info(f"   Event: {'YES' if current_pred['event'] == 1 else 'NO'}")
                    logger.info(f"   Hazard Type: {current_pred['hazard_type']}")
                    logger.info(f"   Probability: {current_pred['probability']*100:.2f}%")
                except Exception as e:
                    logger.warning(f"Could not predict current weather: {e}")
        
        # Print output
        if args.summary:
            hazard_count = print_summary(predictions)
        
        if args.detailed:
            print_detailed(predictions)
        
        # Save to file
        if args.save:
            with open(args.save, 'w') as f:
                json.dump({
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "predictions": predictions
                }, f, indent=2)
            logger.info(f"✅ Predictions saved to {args.save}")
        
        logger.info("=" * 70)
        return 0
    
    except Exception as e:
        logger.error(f"❌ Forecast prediction failed: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())