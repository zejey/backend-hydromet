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

# -------------------------------------------------------------------
# ✅ Railway-friendly Google credentials handling
#
# DO NOT hardcode: os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service-key.json"
# because the file won't exist on Railway unless you create it.
#
# Instead:
# - Put the JSON contents into Railway Variables as GOOGLE_APPLICATION_CREDENTIALS_JSON
# - (Optional) Set GOOGLE_APPLICATION_CREDENTIALS=/tmp/service-key.json
# This block writes the JSON to a file at runtime.
# -------------------------------------------------------------------
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
if creds_json:
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/service-key.json")
    try:
        with open(creds_path, "w") as f:
            f.write(creds_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        logger.info(f"✅ Wrote Google credentials to {creds_path}")
    except Exception as e:
        logger.error(f"❌ Failed to write Google credentials file: {e}")
else:
    logger.warning("⚠️ GOOGLE_APPLICATION_CREDENTIALS_JSON not set; Firestore may fail.")
# -------------------------------------------------------------------

# TextBee Configuration
TEXTBEE_API_KEY = os.getenv("TEXTBEE_API_KEY")
TEXTBEE_DEVICE_ID = os.getenv("TEXTBEE_DEVICE_ID")
TEXTBEE_BASE_URL = os.getenv("TEXTBEE_BASE_URL", "https://api.textbee.dev/api/v1")


def format_phone_for_textbee(phone_number: str) -> str:
    """
    Convert PH phone numbers to E.164 for TextBee: +639XXXXXXXXX

    Accepts:
    - 09XXXXXXXXX
    - 9XXXXXXXXX
    - 63XXXXXXXXXX
    - 639XXXXXXXXX
    - +63XXXXXXXXXX
    Returns:
    - +639XXXXXXXXX
    """
    if not phone_number:
        raise ValueError("Empty phone number")

    s = phone_number.strip()

    # Keep leading + if present, otherwise keep digits only
    if s.startswith("+"):
        digits = "+" + "".join(ch for ch in s[1:] if ch.isdigit())
    else:
        digits = "".join(ch for ch in s if ch.isdigit())

    if digits.startswith("09") and len(digits) == 11:
        return "+63" + digits[1:]  # 09xxxxxxxxx -> +639xxxxxxxxx

    if digits.startswith("9") and len(digits) == 10:
        return "+63" + digits       # 9xxxxxxxxx -> +639xxxxxxxxx

    if digits.startswith("63"):
        rest = digits[2:]
        if rest.startswith("0"):
            rest = rest[1:]
        return "+63" + rest

    if digits.startswith("+63"):
        rest = digits[3:]
        if rest.startswith("0"):
            rest = rest[1:]
        return "+63" + rest

    # If you only support PH numbers, fail loudly
    raise ValueError(f"Invalid PH phone number format for TextBee: {phone_number}")


class NotificationService:
    """Combined in-app + SMS notification service"""

    def __init__(self):
        self.db = firestore.Client()

        self.textbee_api_key = TEXTBEE_API_KEY
        self.textbee_device_id = TEXTBEE_DEVICE_ID
        self.textbee_base_url = TEXTBEE_BASE_URL.rstrip("/")

        if not self.textbee_api_key or not self.textbee_device_id:
            logger.warning("⚠️ TEXTBEE_API_KEY / TEXTBEE_DEVICE_ID not set. SMS notifications disabled.")

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
        if send_sms and self.textbee_api_key and self.textbee_device_id:
            if sms_recipients is None:
                sms_recipients = self._get_registered_users_phones()

            if sms_recipients:
                sms_message = self._create_sms_message(title, message)
                self._send_sms_batch(sms_recipients, sms_message)

    def _send_sms_batch(self, recipients, message):
        """Send SMS to multiple recipients using TextBee send-sms endpoint"""

        if not self.textbee_api_key or not self.textbee_device_id:
            logger.warning("⚠️ SMS disabled - missing TextBee credentials")
            return

        # Format recipients for TextBee (+E164)
        formatted = []
        for r in recipients:
            try:
                formatted.append(format_phone_for_textbee(r))
            except Exception as e:
                logger.warning(f"⚠️ Skipping invalid phone number '{r}': {e}")

        if not formatted:
            logger.warning("⚠️ No valid recipients after formatting; SMS not sent.")
            return

        url = f"{self.textbee_base_url}/gateway/devices/{self.textbee_device_id}/send-sms"

        logger.info(f"📱 Attempting to send SMS to {len(formatted)} recipients")
        logger.info(f"   Provider: TextBee")
        logger.info(f"   API URL: {url}")
        logger.info(f"   Recipients: {formatted}")
        logger.info(f"   Message: {message[:50]}...")

        try:
            response = requests.post(
                url,
                json={
                    "recipients": formatted,
                    "message": message
                },
                headers={
                    "x-api-key": self.textbee_api_key,
                    "Content-Type": "application/json",
                },
                timeout=10
            )

            logger.info(f"   Response Status: {response.status_code}")
            logger.info(f"   Response Body: {response.text[:200]}...")

            if 200 <= response.status_code < 300:
                logger.info(f"✅ TextBee SMS request accepted for {len(formatted)} recipients")
                return

            logger.error(f"❌ TextBee API error {response.status_code}: {response.text[:200]}")

        except requests.exceptions.Timeout:
            logger.error("❌ SMS request timeout")
        except Exception as e:
            logger.error(f"❌ SMS error: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _get_registered_users_phones(self):
        """Get phone numbers from database"""
        try:
            import sys
            import os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from backend.database import get_db_connection

            logger.info("📱 Fetching registered users from database...")

            with get_db_connection() as conn:
                with conn.cursor() as cursor:
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
    sms_recipients=["+639762881182"]
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