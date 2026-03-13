"""
Notification Service
Sends in-app (PostgreSQL) and SMS (Semaphore) hazard notifications
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

import pytz

from app.database import get_db_connection
from app.services.semaphore_notification import get_semaphore_service

logger = logging.getLogger(__name__)

MANILA_TZ = pytz.timezone("Asia/Manila")


class NotificationService:
    """Combined in-app (PostgreSQL) + SMS (Semaphore) notification service"""

    def __init__(self):
        self.sms = get_semaphore_service()

    # ------------------------------------------------------------------
    # Core send method
    # ------------------------------------------------------------------

    def send_notification(
        self,
        title: str,
        message: str,
        notif_type: str = "Warning",
        status: str = "Active",
        sent_to: int = 0,
        dt: Optional[datetime] = None,
        send_sms: bool = True,
        sms_message: Optional[str] = None,
        sms_recipients: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Save notification to PostgreSQL and optionally send SMS via Semaphore.

        Args:
            title: Notification title
            message: In-app message body
            notif_type: Notification type label (e.g. "Warning", "Alert")
            status: Notification status (e.g. "Active")
            sent_to: Number of recipients (informational)
            dt: Override timestamp (defaults to now in Manila time)
            send_sms: Whether to dispatch an SMS
            sms_message: SMS body (defaults to a trimmed version of message)
            sms_recipients: Phone numbers to SMS (fetched from DB if None)

        Returns:
            Dict with keys: in_app_saved (bool), sms_results (dict|None)
        """
        now = dt or datetime.now(MANILA_TZ)
        result: Dict[str, Any] = {"in_app_saved": False, "sms_results": None}

        # 1. Save to PostgreSQL
        result["in_app_saved"] = self._save_to_db(title, message, notif_type, status, sent_to, now)

        # 2. Send SMS
        if send_sms and self.sms.is_available():
            recipients = sms_recipients or self._get_user_phones()
            if recipients:
                body = sms_message or self._trim_for_sms(title, message)
                result["sms_results"] = self.sms.send_sms_batch(recipients, body)
            else:
                logger.warning("No SMS recipients found — skipping SMS")

        return result

    # ------------------------------------------------------------------
    # Hazard-specific helpers
    # ------------------------------------------------------------------

    def send_hazard_alert(
        self,
        hazard: str,
        horizon: int,
        probability: float,
        location: str = "your area",
        sms_recipients: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Send a single-hazard alert to in-app + SMS.

        Args:
            hazard: Hazard key e.g. "heavy_rain", "thunderstorm"
            horizon: Forecast horizon in hours
            probability: Risk probability 0–1
            location: Location label shown in SMS
            sms_recipients: Override recipients (fetched from DB if None)
        """
        sms_body = self.sms.format_hazard_message(hazard, horizon, probability, location)
        hazard_label = hazard.replace("_", " ").title()
        risk_pct = int(probability * 100)

        return self.send_notification(
            title=f"{hazard_label} Alert",
            message=f"{hazard_label} detected with {risk_pct}% probability within {horizon}h. Stay safe.",
            notif_type="Alert",
            status="Active",
            send_sms=True,
            sms_message=sms_body,
            sms_recipients=sms_recipients,
        )

    def send_bundled_hazard_alert(
        self,
        hazards: List[Dict[str, Any]],
        location: str = "your area",
        sms_recipients: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Send a bundled alert for multiple hazards.

        Args:
            hazards: List of dicts with keys: hazard, horizon, probability
            location: Location label shown in SMS
            sms_recipients: Override recipients (fetched from DB if None)
        """
        if not hazards:
            logger.warning("send_bundled_hazard_alert called with empty hazard list")
            return {"in_app_saved": False, "sms_results": None}

        recipients = sms_recipients or self._get_user_phones()
        sms_result = self.sms.send_bundled_hazard_alert(recipients, hazards, location)

        priority_order = {"severe_storm": 0, "thunderstorm": 1, "heavy_rain": 2, "heat_stress": 3}
        top = sorted(hazards, key=lambda h: priority_order.get(h["hazard"], 99))[0]
        top_label = top["hazard"].replace("_", " ").title()
        count = len(hazards)

        in_app_saved = self._save_to_db(
            title=f"{count} Hazard{'s' if count > 1 else ''} Detected",
            message=f"Primary: {top_label} in {top['horizon']}h. {count} hazard(s) active. Stay alert.",
            notif_type="Alert",
            status="Active",
            sent_to=len(recipients),
        )

        return {"in_app_saved": in_app_saved, "sms_results": sms_result}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _save_to_db(
        self,
        title: str,
        message: str,
        notif_type: str,
        status: str,
        sent_to: int,
        dt: Optional[datetime] = None,
    ) -> bool:
        """Persist notification row to PostgreSQL."""
        now = dt or datetime.now(MANILA_TZ)
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO notifications
                            (title, message, type, status, sent_to, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (title, message, notif_type, status, sent_to, now),
                    )
                conn.commit()
            logger.info(f"✓ Notification saved to DB: {title}")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to save notification: {e}")
            return False

    def _get_user_phones(self) -> List[str]:
        """Fetch phone numbers of all verified users from PostgreSQL."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT phone_number
                        FROM users
                        WHERE phone_number IS NOT NULL
                          AND phone_number != ''
                          AND is_verified = true
                        """
                    )
                    rows = cur.fetchall()

            phones = [row[0] for row in rows]
            logger.info(f"Fetched {len(phones)} verified user phone numbers")
            return phones
        except Exception as e:
            logger.error(f"✗ Failed to fetch user phones: {e}")
            return []

    @staticmethod
    def _trim_for_sms(title: str, message: str) -> str:
        """Produce a 160-char-safe SMS body from title + message."""
        body = f"{title}: {message}"
        return body[:157] + "..." if len(body) > 160 else body


# ------------------------------------------------------------------
# Convenience functions (backward-compatible)
# ------------------------------------------------------------------

def send_event_notification(
    title: str,
    message: str,
    notif_type: str = "Warning",
    status: str = "Active",
    sent_to: int = 0,
    dt: Optional[datetime] = None,
    send_sms: bool = True,
    sms_recipients: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Send an in-app + SMS notification."""
    return NotificationService().send_notification(
        title=title,
        message=message,
        notif_type=notif_type,
        status=status,
        sent_to=sent_to,
        dt=dt,
        send_sms=send_sms,
        sms_recipients=sms_recipients,
    )


def send_weather_alert(
    hazard: str,
    message: str,
    horizon: int = 24,
    probability: float = 1.0,
    recipients: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Convenience wrapper for single hazard weather alerts."""
    return NotificationService().send_hazard_alert(
        hazard=hazard,
        horizon=horizon,
        probability=probability,
        sms_recipients=recipients,
    )