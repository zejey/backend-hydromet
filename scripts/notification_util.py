"""
Enhanced Notification System
Sends both in-app (Firestore) and SMS notifications
"""

from google.cloud import firestore
from datetime import datetime
import pytz
import os
import requests
import logging
from pathlib import Path
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service-key.json"

# IPROGSMS Configuration
IPROG_API_TOKEN = os.getenv("IPROG_API_TOKEN")  # Store in environment variable
IPROG_BASE_URL = os.getenv("IPROG_BASE_URL")

# Default recipient numbers (can be overridden per notification)
# DEFAULT_SMS_RECIPIENTS = [
#     os.getenv("SMS_RECIPIENT_1", "+63912345678"),  # Main admin
#     os.getenv("SMS_RECIPIENT_2", "+63987654321"),  # Secondary admin
# ]

class NotificationService:
    """Combined in-app + SMS notification service"""
    
    def __init__(self):
        self.db = firestore.Client()
        self.api_key = os.getenv("IPROG_API_TOKEN")
        self.api_url = os.getenv("IPROG_BASE_URL")
        
        if IPROG_BASE_URL:
            self.api_url = f"{IPROG_BASE_URL.rstrip('/')}/sms_messages/send_bulk"
        else:
            self.api_url = "https://sms.iprogtech.com/api/v1/sms_messages/send_bulk"
            logger.warning("⚠️ IPROG_BASE_URL not set, using hardcoded URL")

        if not self.api_key:
            logger.warning("⚠️ IPROG_API_TOKEN not set. SMS notifications disabled.")
    
    def send_notification(
        self,
        title,
        message,
        notif_type="Warning",
        status="Active",
        sent_to=0,
        dt=None,
        send_sms=True,
        sms_recipients=None
    ):
        """Send both in-app and SMS notifications"""
        now = dt or datetime.now(pytz.timezone("Asia/Manila"))
        
        # Save to Firestore
        try:
            in_app_doc = {
                'dateTime': firestore.SERVER_TIMESTAMP,
                'message': message,
                'title': title,
                'type': notif_type,
                'status': status,
                'sentTo': sent_to
            }
            self.db.collection('notifications').add(in_app_doc)
            logger.info(f"✓ In-app notification saved: {title}")
        except Exception as e:
            logger.error(f"✗ Failed to save in-app notification: {str(e)}")
        
        # Send SMS
        if send_sms and self.api_key:
            if sms_recipients is None:
                sms_recipients = self._get_registered_users_phones()
            
            if sms_recipients:
                sms_message = self._create_sms_message(title, message)
                self._send_sms_batch(sms_recipients, sms_message)
    
    def _send_sms_batch(self, recipients, message):
        """Send SMS to multiple recipients using iProg bulk endpoint"""
        
        if not self.api_key:
            logger.warning("⚠️ SMS disabled - no API key")
            return
        
        # ✅ Format phone numbers as comma-separated string
        # Convert 09XXXXXXXXX format to required format
        phone_numbers = ",".join(recipients)
        
        logger.info(f"📱 Attempting to send SMS to {len(recipients)} recipients")
        logger.info(f"   API URL: {self.api_url}")
        logger.info(f"   Phone numbers: {phone_numbers}")
        logger.info(f"   Message: {message[:50]}...")
        
        try:
            # ✅ iProg API format
            payload = {
                'api_token': self.api_key,
                'phone_number': phone_numbers,  # Comma-separated
                'message': message
            }
            
            logger.debug(f"   Payload: {payload}")
            
            response = requests.post(
                self.api_url,
                json=payload,
                timeout=10
            )
            
            logger.info(f"   Response Status: {response.status_code}")
            logger.info(f"   Response Body: {response.text[:200]}...")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    logger.info(f"   Response JSON: {result}")
                    
                    # Check for success
                    if result.get("success") or "successfully" in str(result.get("message", "")).lower():
                        logger.info(f"✅ Bulk SMS sent successfully to {len(recipients)} recipients")
                        logger.info(f"📱 SMS: {len(recipients)}/{len(recipients)} sent")
                        return
                    else:
                        logger.error(f"❌ iProg API error: {result.get('message', 'Unknown error')}")
                except Exception as e:
                    logger.error(f"❌ Failed to parse JSON response: {e}")
            else:
                logger.error(f"❌ HTTP error {response.status_code}: {response.text[:200]}")
            
            logger.info(f"📱 SMS: 0/{len(recipients)} sent")
            
        except requests.exceptions.Timeout:
            logger.error(f"❌ SMS request timeout")
            logger.info(f"📱 SMS: 0/{len(recipients)} sent")
        except Exception as e:
            logger.error(f"❌ SMS error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            logger.info(f"📱 SMS: 0/{len(recipients)} sent")
        
    def _get_registered_users_phones(self):
        """Get phone numbers from database"""
        try:
            import sys
            import os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from backend.database import get_db_connection
            
            logger.info("📱 Fetching registered users from database...")
            
            # Use context manager
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # ✅ FIXED: Use correct column names
                    cursor.execute("""
                        SELECT phone_number, first_name, last_name 
                        FROM users 
                        WHERE phone_number IS NOT NULL 
                        AND phone_number != ''
                        AND is_verified = true
                    """)
                    users = cursor.fetchall()
            
            if not users:
                logger.warning("⚠️ No registered users found in database")
                return []
            
            # Extract phone numbers and create display names
            phones = []
            user_names = []
            
            for user in users:
                phone = user[0]
                first_name = user[1] or ""
                last_name = user[2] or ""
                full_name = f"{first_name} {last_name}".strip() or phone
                
                phones.append(phone)
                user_names.append(full_name)
            
            logger.info(f"📱 Found {len(phones)} verified users: {', '.join(user_names)}")
            
            return phones
            
        except Exception as e:
            logger.error(f"❌ Failed to get phone numbers: {e}")
            
            # More detailed error logging
            import traceback
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            
            return []
    
    def _create_sms_message(self, title, long_message):
        """Create SMS (max 160 chars)"""
        sms = f"{title}: {long_message[:120]}"
        return sms[:157] + "..." if len(sms) > 160 else sms

# ===== CONVENIENCE FUNCTIONS =====

def send_event_notification(
    title,
    message,
    notif_type="Warning",
    status="Active",
    sent_to=0,
    dt=None,
    send_sms=True,
    sms_recipients=None
):
    """
    Legacy function for backward compatibility
    Sends both in-app and SMS notifications
    """
    service = NotificationService()
    service.send_notification(
        title=title,
        message=message,
        notif_type=notif_type,
        status=status,
        sent_to=sent_to,
        dt=dt,
        send_sms=send_sms,
        sms_recipients=sms_recipients
    )


def send_sms_only(phone_numbers, message):
    """Send SMS without in-app notification"""
    sms_service = NotificationService()
    return sms_service.send_sms(phone_numbers, message)


def send_weather_alert(hazard_type, message, recipients=None):
    """
    Convenience function for weather alerts
    Automatically formats notification for both channels
    """
    service = NotificationService()
    service.send_notification(
        title=f"⚠️ {hazard_type} Alert",
        message=message,
        notif_type="Alert",
        status="Active",
        send_sms=True,
        sms_recipients=recipients
    )