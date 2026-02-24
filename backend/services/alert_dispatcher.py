"""
Alert Dispatcher Service
Handles hazard alerting with Semaphore SMS integration

Features:
- Semaphore SMS API integration
- Throttling to prevent alert spam
- Priority-based alerting
- Alert bundling for multiple hazards
"""

import os
import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from threading import Lock
from pathlib import Path
from dotenv import load_dotenv

from backend.utils.logger import get_logger
from backend.utils.validators import format_phone_for_semaphore
from backend.database import get_db_connection

logger = get_logger(__name__)

# Load environment variables
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Semaphore API configuration
SEMAPHORE_API_KEY = os.getenv("SEMAPHORE_API_KEY")
SEMAPHORE_SENDER_NAME = os.getenv("SEMAPHORE_SENDER_NAME", "HYDROMET")
SEMAPHORE_API_URL = "https://api.semaphore.co/api/v4/messages"

# Throttling configuration
ALERT_COOLDOWN_MINUTES = int(os.getenv("ALERT_COOLDOWN_MINUTES", 30))
MAX_ALERTS_PER_HOUR = int(os.getenv("MAX_ALERTS_PER_HOUR", 4))

# Priority levels (lower = higher priority)
PRIORITY_LEVELS = {
    "critical": 1,
    "high": 2,
    "moderate": 3,
    "low": 4
}


class AlertDispatcher:
    """
    Dispatches weather hazard alerts via Semaphore SMS
    
    Features:
    - Throttling: Prevents alert spam using cooldown periods
    - Priority: Critical alerts bypass some throttling
    - Bundling: Multiple hazards combined into single alert
    - Semaphore: Uses Semaphore SMS API for Philippines numbers
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        """Singleton pattern for shared alert state"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.api_key = SEMAPHORE_API_KEY
        self.sender_name = SEMAPHORE_SENDER_NAME
        self.api_url = SEMAPHORE_API_URL
        
        # Alert tracking for throttling
        self._last_alert_time: Dict[str, datetime] = {}
        self._alert_count_hour: Dict[str, int] = {}
        self._last_hour_reset: datetime = datetime.utcnow()
        
        if not self.api_key:
            logger.warning("⚠️ SEMAPHORE_API_KEY not set. SMS alerts disabled.")
        else:
            logger.info("✅ AlertDispatcher initialized with Semaphore SMS")
        
        self._initialized = True
    
    def _reset_hourly_counts_if_needed(self):
        """Reset hourly alert counts if hour has passed"""
        now = datetime.utcnow()
        if (now - self._last_hour_reset) > timedelta(hours=1):
            self._alert_count_hour.clear()
            self._last_hour_reset = now
    
    def _can_send_alert(
        self, 
        hazard_type: str, 
        priority: str = "moderate"
    ) -> bool:
        """
        Check if alert can be sent based on throttling rules
        
        Args:
            hazard_type: Type of hazard
            priority: Alert priority level
        
        Returns:
            True if alert can be sent
        """
        self._reset_hourly_counts_if_needed()
        now = datetime.utcnow()
        
        # Critical alerts always go through (with reduced cooldown)
        if priority == "critical":
            last_alert = self._last_alert_time.get(hazard_type)
            if last_alert:
                cooldown = timedelta(minutes=ALERT_COOLDOWN_MINUTES // 2)
                if (now - last_alert) < cooldown:
                    logger.info(
                        f"Critical alert for {hazard_type} within reduced cooldown, skipping"
                    )
                    return False
            return True
        
        # Check hourly limit
        total_alerts = sum(self._alert_count_hour.values())
        if total_alerts >= MAX_ALERTS_PER_HOUR:
            logger.info(f"Hourly alert limit reached ({MAX_ALERTS_PER_HOUR})")
            return False
        
        # Check cooldown for this hazard type
        last_alert = self._last_alert_time.get(hazard_type)
        if last_alert:
            cooldown = timedelta(minutes=ALERT_COOLDOWN_MINUTES)
            if (now - last_alert) < cooldown:
                remaining = cooldown - (now - last_alert)
                logger.info(
                    f"Alert for {hazard_type} in cooldown, {remaining.seconds}s remaining"
                )
                return False
        
        return True
    
    def _record_alert_sent(self, hazard_type: str):
        """Record that an alert was sent for throttling"""
        now = datetime.utcnow()
        self._last_alert_time[hazard_type] = now
        self._alert_count_hour[hazard_type] = (
            self._alert_count_hour.get(hazard_type, 0) + 1
        )
    
    def _get_registered_users_phones(self) -> List[str]:
        """Get verified users' phone numbers from database"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT phone_number 
                        FROM users 
                        WHERE phone_number IS NOT NULL 
                        AND phone_number != ''
                        AND is_verified = true
                    """)
                    users = cursor.fetchall()
            
            if not users:
                logger.warning("⚠️ No verified users found in database")
                return []
            
            phones = [user[0] for user in users]
            logger.info(f"📱 Found {len(phones)} verified users for alerts")
            return phones
            
        except Exception as e:
            logger.error(f"❌ Failed to get phone numbers: {e}")
            return []
    
    def _send_sms_semaphore(
        self, 
        phone_numbers: List[str], 
        message: str
    ) -> Dict[str, Any]:
        """
        Send SMS via Semaphore API
        
        Args:
            phone_numbers: List of phone numbers to send to
            message: SMS message content
        
        Returns:
            Result dictionary with success status and details
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "Semaphore API key not configured"
            }
        
        if not phone_numbers:
            return {
                "success": False,
                "error": "No recipients"
            }
        
        results = {
            "success": True,
            "sent": 0,
            "failed": 0,
            "details": []
        }
        
        for phone in phone_numbers:
            try:
                # Format phone for Semaphore (Philippines format)
                formatted_phone = format_phone_for_semaphore(phone)
                
                payload = {
                    "apikey": self.api_key,
                    "number": formatted_phone,
                    "message": message,
                    "sendername": self.sender_name
                }
                
                response = requests.post(
                    self.api_url,
                    data=payload,
                    timeout=10
                )
                
                if response.status_code == 200:
                    result_data = response.json()
                    results["sent"] += 1
                    results["details"].append({
                        "phone": phone,
                        "status": "sent",
                        "message_id": result_data.get("message_id")
                    })
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "phone": phone,
                        "status": "failed",
                        "error": f"HTTP {response.status_code}"
                    })
                    
            except requests.exceptions.RequestException as e:
                results["failed"] += 1
                results["details"].append({
                    "phone": phone,
                    "status": "failed", 
                    "error": str(e)
                })
        
        if results["failed"] > 0 and results["sent"] == 0:
            results["success"] = False
        
        logger.info(
            f"📱 SMS sent: {results['sent']}/{len(phone_numbers)} successful"
        )
        
        return results
    
    def dispatch_alert(
        self,
        hazard_type: str,
        risk_level: str,
        message: str,
        title: Optional[str] = None,
        recipients: Optional[List[str]] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Dispatch a hazard alert via SMS
        
        Args:
            hazard_type: Type of hazard (e.g., "severe_storm")
            risk_level: Risk level ("low", "moderate", "high", "critical")
            message: Alert message content
            title: Optional alert title
            recipients: Optional list of phone numbers (uses DB if None)
            force: Bypass throttling if True
        
        Returns:
            Dispatch result with status and details
        """
        # Check throttling
        if not force and not self._can_send_alert(hazard_type, risk_level):
            return {
                "success": False,
                "reason": "throttled",
                "message": "Alert throttled due to cooldown or rate limit"
            }
        
        # Get recipients
        if recipients is None:
            recipients = self._get_registered_users_phones()
        
        if not recipients:
            return {
                "success": False,
                "reason": "no_recipients",
                "message": "No recipients available"
            }
        
        # Format message with title
        if title:
            full_message = f"{title}\n{message}"
        else:
            full_message = f"⚠️ {hazard_type.replace('_', ' ').title()} Alert\n{message}"
        
        # Truncate for SMS (160 chars)
        if len(full_message) > 157:
            full_message = full_message[:157] + "..."
        
        # Send SMS
        result = self._send_sms_semaphore(recipients, full_message)
        
        # Record alert for throttling
        if result["success"]:
            self._record_alert_sent(hazard_type)
        
        return {
            "success": result["success"],
            "hazard_type": hazard_type,
            "risk_level": risk_level,
            "recipients_count": len(recipients),
            "sms_result": result
        }
    
    def dispatch_multi_hazard_alert(
        self,
        hazards: List[Dict[str, Any]],
        recipients: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Dispatch bundled alert for multiple hazards
        
        Args:
            hazards: List of hazard dictionaries with type, risk_level, probability
            recipients: Optional list of phone numbers
        
        Returns:
            Dispatch result
        """
        if not hazards:
            return {
                "success": False,
                "reason": "no_hazards",
                "message": "No hazards to alert"
            }
        
        # Sort by priority
        sorted_hazards = sorted(
            hazards,
            key=lambda x: PRIORITY_LEVELS.get(x.get("risk_level", "low"), 4)
        )
        
        # Get highest priority hazard for throttling check
        highest_risk = sorted_hazards[0]
        highest_type = highest_risk.get("hazard_type", "weather")
        highest_level = highest_risk.get("risk_level", "moderate")
        
        if not self._can_send_alert(highest_type, highest_level):
            return {
                "success": False,
                "reason": "throttled",
                "message": "Multi-hazard alert throttled"
            }
        
        # Build bundled message
        if len(hazards) == 1:
            title = f"⚠️ {highest_type.replace('_', ' ').title()} Alert"
            message = (
                f"Risk: {highest_level.upper()}\n"
                f"Probability: {highest_risk.get('probability', 0):.0%}"
            )
        else:
            title = f"⚠️ {len(hazards)} Weather Hazard Alert"
            hazard_names = [h.get("hazard_type", "").replace("_", " ").title() 
                          for h in sorted_hazards[:3]]
            message = f"Hazards: {', '.join(hazard_names)}"
            if len(hazards) > 3:
                message += f" +{len(hazards)-3} more"
        
        # Get recipients
        if recipients is None:
            recipients = self._get_registered_users_phones()
        
        if not recipients:
            return {
                "success": False,
                "reason": "no_recipients"
            }
        
        # Format and send
        full_message = f"{title}\n{message}\nStay alert and monitor updates."
        if len(full_message) > 157:
            full_message = full_message[:157] + "..."
        
        result = self._send_sms_semaphore(recipients, full_message)
        
        if result["success"]:
            self._record_alert_sent(highest_type)
        
        return {
            "success": result["success"],
            "hazards_count": len(hazards),
            "primary_hazard": highest_type,
            "recipients_count": len(recipients),
            "sms_result": result
        }
