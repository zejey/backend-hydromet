"""
Hazard Analysis and Classification
Uses the hazard_type_mapping.py and notification_mapping.py from scripts/
"""

import sys
import os
from typing import List, Dict, Any

# Add scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from hazard_type_mapping import determine_hazard_type
from notification_mapping import hazard_notification_templates


class HazardAnalyzer:
    """Analyze and classify weather hazards"""
    
    @staticmethod
    def get_hazard_info(hazard_type: str) -> Dict[str, Any]:
        """
        Get notification templates for hazard type
        
        Args:
            hazard_type: Type of hazard
        
        Returns:
            Dictionary with notification templates
        """
        template = hazard_notification_templates.get(hazard_type, hazard_notification_templates.get("General Hazard", {}))
        
        # Normalize format for API response
        in_app = template.get("in_app", {})
        
        return {
            "title": in_app.get("title", f"{hazard_type} Alert"),
            "in_app": in_app.get("message", f"{hazard_type} detected. Please stay alert."),
            "sms": template.get("sms", f"ALERT: {hazard_type} detected.")
        }
    
    @staticmethod
    def analyze_prediction(prediction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze prediction and add notification info
        
        Args:
            prediction: Prediction result from WeatherPredictor
        
        Returns:
            Enhanced prediction with notification templates
        """
        hazard_type = prediction.get("hazard_type", "None")
        hazard_info = HazardAnalyzer.get_hazard_info(hazard_type)
        
        return {
            **prediction,
            "notification": hazard_info
        }
    
    @staticmethod
    def get_risk_level(prediction: Dict[str, Any]) -> str:
        """
        Determine risk level from prediction
        
        Args:
            prediction: Prediction result
        
        Returns:
            Risk level: "low", "moderate", "high", "critical"
        """
        probability = prediction.get("probability", 0)
        hazard_type = prediction.get("hazard_type", "None")
        event = prediction.get("event", 0)
        
        if hazard_type == "None" or event == 0:
            return "low"
        
        # Critical hazards
        if hazard_type in ["Tropical Cyclone", "Tropical Storm"]:
            if probability >= 0.8:
                return "critical"
            elif probability >= 0.6:
                return "high"
            else:
                return "moderate"
        
        # Other hazards
        if probability >= 0.7:
            return "high"
        elif probability >= 0.5:
            return "moderate"
        else:
            return "low"
    
    @staticmethod
    def should_send_alert(prediction: Dict[str, Any]) -> bool:
        """
        Determine if alert should be sent based on prediction
        
        Args:
            prediction: Prediction result
        
        Returns:
            True if alert should be sent
        """
        event = prediction.get("event", 0)
        risk_level = HazardAnalyzer.get_risk_level(prediction)
        
        # Send alert for any hazard event with moderate or higher risk
        return event == 1 and risk_level in ["moderate", "high", "critical"]