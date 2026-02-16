"""
Semaphore SMS Notification Service
Sends hazard alerts via Semaphore SMS API
"""

import requests
import logging
from typing import List, Tuple, Optional, Dict, Any
from backend.config import Config
from backend.utils.validators import format_phone_for_semaphore

logger = logging.getLogger(__name__)


class SemaphoreNotificationService:
    """
    Send SMS notifications using Semaphore API
    
    Replaces TextBee for production hazard alerting
    """
    
    def __init__(self):
        """Initialize Semaphore service"""
        self.api_key = Config.SEMAPHORE_API_KEY
        self.api_url = "https://api.semaphore.co/api/v4/messages"
        self.sender_name = "HydroMET"  # Semaphore sender ID
        
        if not self.api_key:
            logger.warning("⚠️ SEMAPHORE_API_KEY not configured. SMS disabled.")
    
    def is_available(self) -> bool:
        """Check if Semaphore service is configured and available"""
        return bool(self.api_key)
    
    def format_hazard_message(
        self,
        hazard: str,
        horizon: int,
        probability: float,
        location: str = "your area"
    ) -> str:
        """
        Format SMS message for hazard alert
        
        Args:
            hazard: Hazard type (e.g., "heat_stress", "severe_storm")
            horizon: Time horizon in hours
            probability: Hazard probability (0-1)
            location: Location name
            
        Returns:
            Formatted SMS message (max 160 chars)
        """
        # Map hazard types to user-friendly names
        hazard_names = {
            "heat_stress": "Heat Stress",
            "heavy_rain": "Heavy Rain",
            "thunderstorm": "Thunderstorm",
            "severe_storm": "Severe Storm",
        }
        
        hazard_name = hazard_names.get(hazard, hazard.replace("_", " ").title())
        
        # Create concise message
        risk_pct = int(probability * 100)
        
        if hazard == "severe_storm":
            emoji = "🌪️"
        elif hazard == "thunderstorm":
            emoji = "⛈️"
        elif hazard == "heavy_rain":
            emoji = "🌧️"
        elif hazard == "heat_stress":
            emoji = "🔥"
        else:
            emoji = "⚠️"
        
        # SMS format (max 160 chars)
        message = f"{emoji} ALERT: {hazard_name} expected in {horizon}h ({risk_pct}% risk). Stay safe. -HydroMET"
        
        return message[:160]  # Ensure max 160 chars
    
    def send_sms(
        self,
        phone_number: str,
        message: str
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Send SMS to a single phone number
        
        Args:
            phone_number: Philippine phone number (any format)
            message: SMS message text
            
        Returns:
            Tuple of (success, response_data, error_message)
        """
        if not self.is_available():
            return False, None, "Semaphore API key not configured"
        
        try:
            # Format phone number for Semaphore (639XXXXXXXXX format)
            formatted_phone = format_phone_for_semaphore(phone_number)
            
            # Prepare API request
            payload = {
                "apikey": self.api_key,
                "number": formatted_phone,
                "message": message,
                "sendername": self.sender_name,
            }
            
            logger.debug(f"Sending SMS to {formatted_phone}: {message[:50]}...")
            
            # Send request
            response = requests.post(self.api_url, data=payload, timeout=10)
            
            # Parse response
            content_type = response.headers.get("Content-Type", "")
            
            if "application/json" in content_type:
                try:
                    response_data = response.json()
                except Exception:
                    response_data = None
            else:
                response_data = {"raw_response": response.text}
            
            # Check for success
            if 200 <= response.status_code < 300:
                logger.info(f"✓ SMS sent successfully to {formatted_phone}")
                return True, response_data, None
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.error(f"✗ SMS failed to {formatted_phone}: {error_msg}")
                return False, response_data, error_msg
        
        except requests.exceptions.Timeout:
            error_msg = "SMS request timeout"
            logger.error(f"✗ {error_msg}")
            return False, None, error_msg
        
        except ValueError as e:
            # Phone formatting error
            error_msg = f"Invalid phone number: {str(e)}"
            logger.error(f"✗ {error_msg}")
            return False, None, error_msg
        
        except Exception as e:
            error_msg = f"SMS sending failed: {str(e)}"
            logger.error(f"✗ {error_msg}")
            return False, None, error_msg
    
    def send_sms_batch(
        self,
        phone_numbers: List[str],
        message: str
    ) -> Dict[str, Any]:
        """
        Send SMS to multiple phone numbers
        
        Args:
            phone_numbers: List of phone numbers
            message: SMS message text
            
        Returns:
            Dictionary with send results
        """
        results = {
            "total": len(phone_numbers),
            "success": 0,
            "failed": 0,
            "details": []
        }
        
        logger.info(f"Sending SMS to {len(phone_numbers)} recipients...")
        
        for phone in phone_numbers:
            success, response_data, error = self.send_sms(phone, message)
            
            results["details"].append({
                "phone": phone,
                "success": success,
                "error": error
            })
            
            if success:
                results["success"] += 1
            else:
                results["failed"] += 1
        
        logger.info(f"✓ SMS batch complete: {results['success']}/{results['total']} sent")
        
        return results
    
    def send_hazard_alert(
        self,
        phone_numbers: List[str],
        hazard: str,
        horizon: int,
        probability: float,
        location: str = "your area"
    ) -> Dict[str, Any]:
        """
        Send formatted hazard alert to multiple recipients
        
        Args:
            phone_numbers: List of recipient phone numbers
            hazard: Hazard type
            horizon: Time horizon in hours
            probability: Hazard probability
            location: Location name
            
        Returns:
            Dictionary with send results
        """
        message = self.format_hazard_message(hazard, horizon, probability, location)
        
        logger.info(f"Sending {hazard} alert ({horizon}h) to {len(phone_numbers)} recipients")
        logger.debug(f"Message: {message}")
        
        return self.send_sms_batch(phone_numbers, message)
    
    def send_bundled_hazard_alert(
        self,
        phone_numbers: List[str],
        hazards: List[Dict[str, Any]],
        location: str = "your area"
    ) -> Dict[str, Any]:
        """
        Send bundled alert for multiple hazards
        
        Args:
            phone_numbers: List of recipient phone numbers
            hazards: List of hazard dictionaries with keys: hazard, horizon, probability
            location: Location name
            
        Returns:
            Dictionary with send results
        """
        if not hazards:
            logger.warning("No hazards to send in bundled alert")
            return {"total": 0, "success": 0, "failed": 0, "details": []}
        
        # Sort hazards by priority
        priority_order = {"severe_storm": 0, "thunderstorm": 1, "heavy_rain": 2, "heat_stress": 3}
        sorted_hazards = sorted(
            hazards,
            key=lambda h: (priority_order.get(h['hazard'], 99), h.get('horizon', 999))
        )
        
        # Format bundled message
        if len(sorted_hazards) == 1:
            # Single hazard - use regular format
            h = sorted_hazards[0]
            message = self.format_hazard_message(h['hazard'], h['horizon'], h['probability'], location)
        else:
            # Multiple hazards - create summary
            top_hazard = sorted_hazards[0]
            hazard_names = {
                "heat_stress": "Heat",
                "heavy_rain": "Rain",
                "thunderstorm": "Storm",
                "severe_storm": "Severe Storm",
            }
            
            top_name = hazard_names.get(top_hazard['hazard'], top_hazard['hazard'])
            count = len(sorted_hazards)
            
            message = f"⚠️ ALERT: {count} hazards detected. Primary: {top_name} in {top_hazard['horizon']}h. Stay alert. -HydroMET"
            message = message[:160]
        
        logger.info(f"Sending bundled alert ({len(sorted_hazards)} hazards) to {len(phone_numbers)} recipients")
        logger.debug(f"Message: {message}")
        
        return self.send_sms_batch(phone_numbers, message)


# Singleton instance
_semaphore_service = None


def get_semaphore_service() -> SemaphoreNotificationService:
    """
    Get or create singleton SemaphoreNotificationService instance
    
    Returns:
        SemaphoreNotificationService instance
    """
    global _semaphore_service
    
    if _semaphore_service is None:
        _semaphore_service = SemaphoreNotificationService()
    
    return _semaphore_service


if __name__ == "__main__":
    # Testing
    import logging
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "="*60)
    print("SEMAPHORE NOTIFICATION SERVICE - TESTING")
    print("="*60)
    
    service = get_semaphore_service()
    
    print(f"\nAPI Configured: {service.is_available()}")
    
    if not service.is_available():
        print("\n⚠️  Semaphore API key not configured")
        print("   Set SEMAPHORE_API_KEY in environment")
    else:
        print("\n✓ Semaphore service ready")
    
    # Test message formatting
    print("\n" + "="*60)
    print("Sample Messages:")
    print("="*60)
    
    test_hazards = [
        ("severe_storm", 12, 0.85),
        ("thunderstorm", 24, 0.72),
        ("heavy_rain", 48, 0.65),
        ("heat_stress", 24, 0.78),
    ]
    
    for hazard, horizon, prob in test_hazards:
        message = service.format_hazard_message(hazard, horizon, prob)
        print(f"\n{hazard} @ {horizon}h ({prob:.0%}):")
        print(f"  {message}")
        print(f"  Length: {len(message)} chars")
    
    # Test bundled message
    print("\n" + "="*60)
    print("Bundled Message Sample:")
    print("="*60)
    
    bundled_hazards = [
        {"hazard": "thunderstorm", "horizon": 12, "probability": 0.7},
        {"hazard": "heavy_rain", "horizon": 12, "probability": 0.8},
    ]
    
    # Format bundled message manually for testing
    if len(bundled_hazards) > 1:
        top = bundled_hazards[0]
        message = f"⚠️ ALERT: {len(bundled_hazards)} hazards detected. Primary: Storm in {top['horizon']}h. Stay alert. -HydroMET"
        print(f"\n{message}")
        print(f"Length: {len(message)} chars")
    
    print("\n✅ Semaphore notification service test complete!")
