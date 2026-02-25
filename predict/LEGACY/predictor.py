"""
Weather Hazard Predictor
Uses the trained ML model from scripts/model.py
"""

import sys
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import pandas as pd

# Add scripts to path to import model.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from model import (
    predict_from_features,
    features_from_openweather_json,
    engineer_features,
    hazard_score
)
from hazard_type_mapping import determine_hazard_type
from backend.ml.model_manager import ModelManager
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class WeatherPredictor:
    """Weather hazard prediction using trained ML model"""
    
    def __init__(self):
        self.model_manager = ModelManager()
        
        # Verify model is ready
        if not self.model_manager.is_model_ready():
            logger.warning("⚠️ ML model not ready. Please train the model first.")
    
    def extract_features_from_openweather(self, weather_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract features from OpenWeather API response
        Uses the logic from your model.py
        
        Args:
            weather_data: Raw OpenWeather API JSON
        
        Returns:
            Dictionary of extracted features
        """
        try:
            features = features_from_openweather_json(weather_data)
            logger.debug(f"Features extracted: {list(features.keys())}")
            return features
        except Exception as e:
            logger.error(f"Feature extraction failed: {e}")
            raise
    
    def extract_features_from_weatherlink(self, weather_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract features from WeatherLink API response
        
        Args:
            weather_data: Raw WeatherLink API JSON
        
        Returns:
            Dictionary of extracted features
        """
        features = {
            "timestamp": pd.to_datetime(weather_data.get("ts", 0), unit='s'),
            "temperature": weather_data.get("temp_last", 0),
            "temp_min": weather_data.get("temp_lo", 0),
            "temp_max": weather_data.get("temp_hi", 0),
            "pressure": weather_data.get("pressure", 1013),
            "humidity": weather_data.get("hum_last", 60),
            "wind_speed": weather_data.get("wind_speed_last", 0),
            "wind_gust": weather_data.get("wind_speed_hi", 0),
            "wind_direction": weather_data.get("wind_dir_last", 180),
            "precipitation": weather_data.get("rainfall_mm", 0),
        }
        
        return features
    
    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make hazard prediction from extracted features
        Uses your model.py predict_from_features() function
        
        Args:
            features: Dictionary of weather features
        
        Returns:
            Prediction result with hazard info
        """
        if not self.model_manager.is_model_ready():
            logger.warning("Model not ready, using rule-based prediction only")
            # Fallback to rule-based hazard scoring
            event, hazards = hazard_score(features, explain=True)
            hazard_type = determine_hazard_type(hazards) if event else "None"
            
            return {
                "event": event,
                "probability": 0.0,
                "probabilities": {"no_event": 1.0, "event": 0.0},
                "hazard_type": hazard_type,
                "hazards": hazards,
                "timestamp": features.get("timestamp").isoformat() if features.get("timestamp") else None,
                "source": "rules_only"
            }
        
        try:
            # Use YOUR model.py prediction logic
            result = predict_from_features(features)
            
            # Add timestamp
            result["timestamp"] = features.get("timestamp").isoformat() if features.get("timestamp") else None
            result["source"] = "ml_model"
            
            logger.debug(f"Prediction: {result['hazard_type']} (event={result['event']}, prob={result['probability']:.2f})")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Prediction failed: {e}", exc_info=True)
            
            # Fallback to rule-based
            event, hazards = hazard_score(features, explain=True)
            hazard_type = determine_hazard_type(hazards) if event else "None"
            
            return {
                "event": event,
                "probability": 0.0,
                "hazard_type": hazard_type,
                "hazards": hazards,
                "timestamp": features.get("timestamp").isoformat() if features.get("timestamp") else None,
                "error": str(e),
                "source": "rules_fallback"
            }
    
    def predict_batch(self, weather_data_list: List[Dict[str, Any]], source: str = "openweather") -> List[Dict[str, Any]]:
        """
        Make predictions for multiple weather data points
        
        Args:
            weather_data_list: List of weather data (OpenWeather or WeatherLink format)
            source: Data source ("openweather" or "weatherlink")
        
        Returns:
            List of prediction results
        """
        results = []
        
        for weather_data in weather_data_list:
            # Extract features based on source
            if source == "openweather":
                features = self.extract_features_from_openweather(weather_data)
            elif source == "weatherlink":
                features = self.extract_features_from_weatherlink(weather_data)
            else:
                logger.error(f"Unknown source: {source}")
                continue
            
            # Make prediction
            prediction = self.predict(features)
            
            results.append({
                "timestamp": features.get("timestamp").isoformat() if features.get("timestamp") else None,
                "prediction": prediction,
                "features": features
            })
        
        return results
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        return self.model_manager.get_model_info()