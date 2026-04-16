"""
Multi-Hazard Weather Predictor
Extends the existing predictor with multi-hazard, multi-horizon capabilities
"""

import sys
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import pandas as pd
import numpy as np
from app.ml.multi_model_manager import get_multi_model_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)


class MultiHazardPredictor:
    """
    Multi-hazard, multi-horizon weather prediction using ensemble of Naive Bayes models
    """
    
    def __init__(self, models_dir: Optional[str] = None):
        """
        Initialize multi-hazard predictor
        
        Args:
            models_dir: Optional directory containing trained models
        """
        self.model_manager = get_multi_model_manager(models_dir=models_dir)
        
        # Verify at least some models are ready
        status = self.model_manager.get_model_status()
        if status['available_count'] == 0:
            logger.warning("⚠️ No multi-hazard models available. Please train models first.")
        else:
            logger.info(f"✓ {status['available_count']}/{status['total_expected']} models ready")
        
        self.hazards = self.model_manager.hazards
        self.horizons = self.model_manager.horizons
    
    def extract_and_prepare_features(
        self,
        weather_data: Dict[str, Any],
        source: str = "openweather"
    ) -> pd.DataFrame:
        """
        Extract and prepare features from weather data
        
        Args:
            weather_data: Raw weather data (OpenWeather or WeatherLink format)
            source: Data source type
            
        Returns:
            DataFrame with engineered features
        """
        from app.ml.feature_engineering import extract_features_from_openweather_forecast
        
        if source == "openweather":
            # Handle both current weather and forecast formats
            features_df = extract_features_from_openweather_forecast(
                weather_data,
                include_extended=True  # Include lag/delta/rolling features
            )
        else:
            # Fallback: create basic feature dict
            logger.warning(f"Source '{source}' not fully supported for multi-hazard. Using basic features.")
            features_df = pd.DataFrame([{
                'timestamp': datetime.now(),
                'temp': weather_data.get('temp', 25),
                'temperature': weather_data.get('temp', 25),
                'pressure': weather_data.get('pressure', 1013),
                'humidity': weather_data.get('humidity', 60),
                'wind_speed': weather_data.get('wind_speed', 0),
                'rain_1h': weather_data.get('rain_1h', 0),
            }])
        
        return features_df
    
    def predict_multi_hazard_multi_horizon(
        self,
        features: pd.DataFrame,
        hazards: Optional[List[str]] = None,
        horizons: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Predict multiple hazards across multiple horizons
        
        Args:
            features: Prepared feature DataFrame
            hazards: List of hazards to predict (None = all)
            horizons: List of horizons to predict (None = all)
            
        Returns:
            Dictionary with predictions per hazard per horizon
        """
        if hazards is None:
            hazards = self.hazards
        
        if horizons is None:
            horizons = self.horizons
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "predictions": {},
            "summary": {
                "total_hazards_detected": 0,
                "hazards_by_horizon": {},
                "highest_risk_hazard": None,
                "highest_risk_probability": 0.0,
            }
        }
        
        # Predict for each hazard-horizon combination
        for hazard in hazards:
            results["predictions"][hazard] = {}
            
            for horizon in horizons:
                horizon_key = f"{horizon}h"
                
                if not self.model_manager.is_model_available(hazard, horizon):
                    results["predictions"][hazard][horizon_key] = {
                        "available": False,
                        "prediction": 0,
                        "probability": 0.0
                    }
                    continue
                
                try:
                    # Make prediction
                    prediction, probability = self.model_manager.predict(
                        hazard, horizon, features
                    )
                    
                    results["predictions"][hazard][horizon_key] = {
                        "available": True,
                        "prediction": prediction,
                        "probability": probability,
                        "hazard_detected": bool(prediction == 1)
                    }
                    
                    # Update summary
                    if prediction == 1:
                        results["summary"]["total_hazards_detected"] += 1
                        
                        # Track hazards by horizon
                        if horizon_key not in results["summary"]["hazards_by_horizon"]:
                            results["summary"]["hazards_by_horizon"][horizon_key] = []
                        
                        results["summary"]["hazards_by_horizon"][horizon_key].append({
                            "hazard": hazard,
                            "probability": probability
                        })
                        
                        # Track highest risk
                        if probability > results["summary"]["highest_risk_probability"]:
                            results["summary"]["highest_risk_probability"] = probability
                            results["summary"]["highest_risk_hazard"] = {
                                "hazard": hazard,
                                "horizon": horizon,
                                "probability": probability
                            }
                    
                except Exception as e:
                    logger.error(f"Prediction failed for {hazard}_{horizon}h: {e}")
                    results["predictions"][hazard][horizon_key] = {
                        "available": True,
                        "error": str(e),
                        "prediction": 0,
                        "probability": 0.0
                    }
        
        return results
    
    def predict_from_weather_data(
        self,
        weather_data: Dict[str, Any],
        source: str = "openweather"
    ) -> Dict[str, Any]:
        """
        Main prediction method: extract features and predict all hazards/horizons
        
        Args:
            weather_data: Raw weather data
            source: Data source type
            
        Returns:
            Prediction results for all hazards and horizons
        """
        logger.info("Making multi-hazard multi-horizon prediction...")
        
        # Extract and prepare features
        try:
            features_df = self.extract_and_prepare_features(weather_data, source)
            logger.debug(f"Extracted features: {features_df.shape}")
        except Exception as e:
            logger.error(f"Feature extraction failed: {e}")
            return {
                "success": False,
                "error": f"Feature extraction failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        
        # Make predictions
        try:
            results = self.predict_multi_hazard_multi_horizon(features_df)
            results["success"] = True
            results["features_shape"] = features_df.shape
            
            logger.info(f"Prediction complete: {results['summary']['total_hazards_detected']} hazards detected")
            
            return results
            
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return {
                "success": False,
                "error": f"Prediction failed: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def get_risk_level(self, predictions: Dict[str, Any]) -> str:
        """
        Determine overall risk level from multi-hazard predictions
        
        Priority: severe_storm > thunderstorm > heavy_rain > heat_stress
        
        Args:
            predictions: Prediction results dictionary
            
        Returns:
            Risk level: "low", "moderate", "high", "critical"
        """
        if not predictions.get("success"):
            return "unknown"
        
        highest_risk = predictions["summary"].get("highest_risk_hazard")
        
        if highest_risk is None:
            return "low"
        
        hazard = highest_risk["hazard"]
        probability = highest_risk["probability"]
        
        # Critical hazards (severe_storm, thunderstorm)
        if hazard in ["severe_storm", "thunderstorm"]:
            if probability >= 0.8:
                return "critical"
            elif probability >= 0.6:
                return "high"
            else:
                return "moderate"
        
        # Other hazards (heavy_rain, heat_stress)
        if probability >= 0.7:
            return "high"
        elif probability >= 0.5:
            return "moderate"
        else:
            return "low"
    
    def format_prediction_summary(self, predictions: Dict[str, Any]) -> str:
        """
        Create human-readable summary of predictions
        
        Args:
            predictions: Prediction results dictionary
            
        Returns:
            Summary string
        """
        if not predictions.get("success"):
            return "Prediction failed"
        
        total = predictions["summary"]["total_hazards_detected"]
        
        if total == 0:
            return "No hazards detected in forecast period"
        
        summary_parts = [f"{total} hazard(s) detected:"]
        
        # Group by horizon
        for horizon_key in sorted(predictions["summary"]["hazards_by_horizon"].keys()):
            hazards_list = predictions["summary"]["hazards_by_horizon"][horizon_key]
            hazard_names = [h["hazard"].replace("_", " ").title() for h in hazards_list]
            summary_parts.append(f"  {horizon_key}: {', '.join(hazard_names)}")
        
        return "\n".join(summary_parts)
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about available models"""
        return self.model_manager.get_model_status()


# Singleton instance
_multi_hazard_predictor = None


def get_multi_hazard_predictor(models_dir: Optional[str] = None) -> MultiHazardPredictor:
    """
    Get or create singleton MultiHazardPredictor instance
    
    Args:
        models_dir: Optional models directory
        
    Returns:
        MultiHazardPredictor instance
    """
    global _multi_hazard_predictor
    
    if _multi_hazard_predictor is None or models_dir is not None:
        _multi_hazard_predictor = MultiHazardPredictor(models_dir=models_dir)
    
    return _multi_hazard_predictor


if __name__ == "__main__":
    # Testing
    import logging
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "="*80)
    print("MULTI-HAZARD PREDICTOR - TESTING")
    print("="*80)
    
    # Create predictor
    predictor = get_multi_hazard_predictor()
    
    # Get model info
    info = predictor.get_model_info()
    print(f"\nModels available: {info['available_count']}/{info['total_expected']}")
    
    if info['available_count'] == 0:
        print("\n⚠️  No models available for testing")
        print("   Train models first with: python scripts/train_multi_models.py --csv data.csv")
    else:
        print("\n✓ Ready for predictions")
        
        # Test with mock weather data
        print("\n" + "="*80)
        print("Testing prediction with mock data...")
        print("="*80)
        
        mock_weather = {
            "dt": int(datetime.now().timestamp()),
            "main": {
                "temp": 35,  # Hot
                "feels_like": 38,  # Heat stress threshold
                "pressure": 985,  # Low pressure
                "humidity": 80,
            },
            "wind": {
                "speed": 22,  # Strong wind
                "deg": 180,
            },
            "rain": {
                "1h": 25,  # Heavy rain
            },
            "clouds": {"all": 90},
            "weather": [{"id": 200, "main": "Thunderstorm"}]  # Thunderstorm
        }
        
        results = predictor.predict_from_weather_data(mock_weather, source="openweather")
        
        if results.get("success"):
            print(f"\n✓ Prediction successful")
            print(f"  Hazards detected: {results['summary']['total_hazards_detected']}")
            print(f"  Risk level: {predictor.get_risk_level(results)}")
            
            if results['summary']['highest_risk_hazard']:
                highest = results['summary']['highest_risk_hazard']
                print(f"  Highest risk: {highest['hazard']} @ {highest['horizon']}h ({highest['probability']:.2%})")
            
            print(f"\n{predictor.format_prediction_summary(results)}")
        else:
            print(f"\n✗ Prediction failed: {results.get('error')}")
    
    print("\n" + "="*80)
    print("✅ Multi-hazard predictor test complete!")
    print("="*80)