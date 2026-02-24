"""
Multi-Hazard Predictor
Predicts multiple hazard types across multiple time horizons

Supports:
- 4 hazard types: heat, heavy_rain, thunderstorm, severe_storm
- 3 horizons: 12h, 24h, 48h
"""

import sys
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import pandas as pd

# Add scripts to path to import model utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from backend.ml.multi_model_manager import MultiModelManager, HAZARD_TYPES, HORIZONS
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Hazard priority for determining highest risk
HAZARD_PRIORITY = {
    "severe_storm": 1,
    "thunderstorm": 2,
    "heavy_rain": 3,
    "heat": 4
}

# Risk level thresholds based on probability
RISK_LEVELS = {
    "critical": 0.8,
    "high": 0.6,
    "moderate": 0.4,
    "low": 0.0
}


class MultiHazardPredictor:
    """Multi-hazard weather prediction using multiple ML models"""
    
    def __init__(self):
        self.model_manager = MultiModelManager()
        self._check_model_availability()
    
    def _check_model_availability(self):
        """Check and log model availability"""
        status = self.model_manager.get_model_status()
        
        if status["available_count"] == 0:
            logger.warning("⚠️ No ML models available. Predictions will not be possible.")
        elif status["available_count"] < status["total_models"]:
            logger.info(
                f"⚠️ Partial models available: {status['available_count']}/{status['total_models']}"
            )
        else:
            logger.info(f"✅ All {status['total_models']} models ready")
    
    def get_risk_level(self, probability: float) -> str:
        """Determine risk level from probability"""
        if probability >= RISK_LEVELS["critical"]:
            return "critical"
        elif probability >= RISK_LEVELS["high"]:
            return "high"
        elif probability >= RISK_LEVELS["moderate"]:
            return "moderate"
        return "low"
    
    def predict_single(
        self, 
        features: Dict[str, Any], 
        hazard_type: str, 
        horizon: str
    ) -> Dict[str, Any]:
        """
        Make prediction for a single hazard type and horizon
        
        Args:
            features: Weather features dictionary
            hazard_type: Type of hazard (heat, heavy_rain, thunderstorm, severe_storm)
            horizon: Prediction horizon (12h, 24h, 48h)
        
        Returns:
            Prediction result with availability, detection, and probability
        """
        model = self.model_manager.load_model(hazard_type, horizon)
        
        if model is None:
            return {
                "available": False,
                "hazard_detected": False,
                "probability": 0.0,
                "message": f"Model {hazard_type}/{horizon} not trained"
            }
        
        try:
            # Prepare features as DataFrame for sklearn
            feature_df = self._prepare_features(features)
            
            # Make prediction
            prediction = model.predict(feature_df)[0]
            
            # Get probability if available
            probability = 0.0
            if hasattr(model, 'predict_proba'):
                proba = model.predict_proba(feature_df)[0]
                # For binary classification, proba is [P(class=0), P(class=1)]
                if len(proba) >= 2:
                    probability = float(proba[1])  # P(hazard detected)
                else:
                    # Unexpected model output format
                    logger.warning(
                        f"Unexpected predict_proba output shape for {hazard_type}/{horizon}: "
                        f"expected 2 classes, got {len(proba)}"
                    )
                    probability = float(proba[0]) if len(proba) > 0 else 0.0
            
            hazard_detected = bool(prediction == 1)
            
            return {
                "available": True,
                "hazard_detected": hazard_detected,
                "probability": probability,
                "risk_level": self.get_risk_level(probability) if hazard_detected else "low"
            }
            
        except Exception as e:
            logger.error(f"Prediction failed for {hazard_type}/{horizon}: {e}")
            return {
                "available": True,
                "hazard_detected": False,
                "probability": 0.0,
                "error": str(e)
            }
    
    def _prepare_features(self, features: Dict[str, Any]) -> pd.DataFrame:
        """Prepare features for ML model prediction"""
        # Extract relevant numeric features
        numeric_features = {
            k: v for k, v in features.items() 
            if isinstance(v, (int, float)) and k != 'timestamp'
        }
        
        return pd.DataFrame([numeric_features])
    
    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make predictions for all hazard types and horizons
        
        Args:
            features: Weather features dictionary
        
        Returns:
            Comprehensive prediction result with all hazards and horizons
        """
        status = self.model_manager.get_model_status()
        
        if status["available_count"] == 0:
            return {
                "success": False,
                "available_models": 0,
                "message": status["message"],
                "predictions": {},
                "summary": {
                    "total_hazards_detected": 0,
                    "highest_risk_hazard": None
                }
            }
        
        predictions = {}
        all_detections = []
        
        for hazard_type in HAZARD_TYPES:
            predictions[hazard_type] = {}
            
            for horizon in HORIZONS:
                result = self.predict_single(features, hazard_type, horizon)
                predictions[hazard_type][horizon] = result
                
                if result.get("hazard_detected"):
                    all_detections.append({
                        "hazard_type": hazard_type,
                        "horizon": horizon,
                        "probability": result.get("probability", 0.0),
                        "risk_level": result.get("risk_level", "low")
                    })
        
        # Create summary
        summary = self._create_summary(all_detections)
        
        return {
            "success": True,
            "available_models": status["available_count"],
            "predictions": predictions,
            "summary": summary,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _create_summary(self, detections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create summary of all hazard detections"""
        if not detections:
            return {
                "total_hazards_detected": 0,
                "highest_risk_hazard": None,
                "hazards_by_type": {},
                "hazards_by_horizon": {}
            }
        
        # Find highest risk hazard (by priority, then probability)
        sorted_detections = sorted(
            detections,
            key=lambda x: (
                HAZARD_PRIORITY.get(x["hazard_type"], 99),
                -x.get("probability", 0)
            )
        )
        highest_risk = sorted_detections[0]
        
        # Group by type and horizon
        hazards_by_type = {}
        hazards_by_horizon = {}
        
        for detection in detections:
            hazard_type = detection["hazard_type"]
            horizon = detection["horizon"]
            
            if hazard_type not in hazards_by_type:
                hazards_by_type[hazard_type] = []
            hazards_by_type[hazard_type].append(horizon)
            
            if horizon not in hazards_by_horizon:
                hazards_by_horizon[horizon] = []
            hazards_by_horizon[horizon].append(hazard_type)
        
        return {
            "total_hazards_detected": len(detections),
            "highest_risk_hazard": {
                "hazard_type": highest_risk["hazard_type"],
                "horizon": highest_risk["horizon"],
                "probability": highest_risk["probability"],
                "risk_level": highest_risk["risk_level"]
            },
            "hazards_by_type": hazards_by_type,
            "hazards_by_horizon": hazards_by_horizon
        }
    
    def get_backwards_compatible_prediction(
        self, 
        multi_hazard_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convert multi-hazard result to backwards-compatible format
        
        This provides legacy fields (event, hazard_type, risk_level, probability)
        derived from the highest-priority detected hazard.
        """
        summary = multi_hazard_result.get("summary", {})
        highest_risk = summary.get("highest_risk_hazard")
        
        if highest_risk:
            # Convert hazard_type to display name
            hazard_display_names = {
                "severe_storm": "Severe Storm",
                "thunderstorm": "Thunderstorm", 
                "heavy_rain": "Heavy Rain",
                "heat": "Extreme Heat"
            }
            
            return {
                "event": 1,
                "hazard_type": hazard_display_names.get(
                    highest_risk["hazard_type"], 
                    highest_risk["hazard_type"].replace("_", " ").title()
                ),
                "risk_level": highest_risk["risk_level"],
                "probability": highest_risk["probability"],
                "hazards": list(summary.get("hazards_by_type", {}).keys())
            }
        
        return {
            "event": 0,
            "hazard_type": "None",
            "risk_level": "low",
            "probability": 0.0,
            "hazards": []
        }
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        return self.model_manager.get_aggregated_info()
