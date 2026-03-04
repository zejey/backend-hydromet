"""
Forecast Runner: fetches OpenWeather /data/2.5/forecast, analyzes for hazards,
creates in-app Postgres notifications, and sends Semaphore SMS alerts.

Hazard detection is rule-based using OpenWeather weather codes and rain fields,
so it works even when ML models are not trained.
"""

import os
import uuid
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from backend.database import get_db_cursor, get_db_connection
from backend.services.semaphore_notification import get_semaphore_service

logger = logging.getLogger(__name__)

OPENWEATHER_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

# OpenWeather weather ID ranges / sets
_THUNDERSTORM_IDS = set(range(200, 233))
_HEAVY_RAIN_IDS = {502, 503, 504, 511, 522}
_SEVERE_STORM_IDS = {781}  # Tornado

RAIN_3H_HEAVY_MM = 10.0    # mm in 3 h → triggers heavy_rain
HEAT_STRESS_TEMP_C = 36.0  # °C → triggers heat_stress
SEVERE_WIND_MS = 15.0      # m/s with thunderstorm → severe_storm

# Probability calculation constants
_PROB_MAX = 0.95            # Cap for any probability estimate
_RAIN_PROB_BASE = 0.60      # Base probability for heavy rain rule
_RAIN_PROB_SCALE = 20.0     # mm/3h that maps to _PROB_MAX - _RAIN_PROB_BASE extra risk
_RAIN_HIGH_SEV_MM = 20.0    # mm/3h that upgrades heavy_rain to "high" severity
_HEAT_PROB_BASE = 0.50      # Base probability for heat stress rule
_HEAT_PROB_SCALE = 10.0     # °C above threshold that maps to _PROB_MAX - _HEAT_PROB_BASE

_SEVERITY_RANK = {"moderate": 0, "high": 1, "critical": 2}


def _hazard_display_name(hazard: str) -> str:
    """Convert internal hazard key to a human-readable title (e.g. 'heavy_rain' → 'Heavy Rain')."""
    return hazard.replace("_", " ").title()


def _get_config() -> Dict[str, Any]:
    return {
        "api_key": os.environ.get("OPENWEATHER_API_KEY", ""),
        "lat": float(
            os.environ.get(
                "FORECAST_DEFAULT_LAT",
                os.environ.get("OPENWEATHER_LAT", "14.3597"),
            )
        ),
        "lon": float(
            os.environ.get(
                "FORECAST_DEFAULT_LON",
                os.environ.get("OPENWEATHER_LON", "121.0583"),
            )
        ),
        "location_name": os.environ.get("OPENWEATHER_CITY_NAME", "San Pedro, Laguna, PH"),
        "dedupe_hours": int(os.environ.get("FORECAST_DEDUPE_HOURS", "6")),
    }


# ---------------------------------------------------------------------------
# Forecast fetching
# ---------------------------------------------------------------------------

def fetch_forecast(api_key: str, lat: float, lon: float, cnt: int = 8) -> dict:
    """Fetch 5-day/3-hour forecast from OpenWeather (cnt items = cnt×3 h ahead)."""
    url = (
        f"{OPENWEATHER_FORECAST_URL}"
        f"?lat={lat}&lon={lon}&appid={api_key}&units=metric&cnt={cnt}"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Rule-based hazard analysis
# ---------------------------------------------------------------------------

def analyze_forecast(forecast_data: dict) -> List[Dict[str, Any]]:
    """
    Analyze OpenWeather forecast payload and return detected hazards.

    Returns a list of dicts, one per distinct hazard type, keeping the entry
    with the *highest severity* found across all forecast steps:
        {hazard, severity, probability, horizon_h, weather_id, weather_main, description}
    """
    now_dt = datetime.utcnow()
    detected: Dict[str, Dict[str, Any]] = {}

    for item in forecast_data.get("list", []):
        weather_list = item.get("weather") or [{}]
        weather0 = weather_list[0] if weather_list else {}
        weather_id = weather0.get("id", 800)
        weather_main = weather0.get("main", "")

        main = item.get("main") or {}
        rain = item.get("rain") or {}
        wind = item.get("wind") or {}

        temp = main.get("temp") or 0.0
        rain_3h = rain.get("3h") or 0.0
        wind_speed = wind.get("speed") or 0.0

        item_dt = item.get("dt", 0)
        item_time = datetime.utcfromtimestamp(item_dt)
        horizon_h = max(0, int((item_time - now_dt).total_seconds() / 3600))

        hazard: Optional[str] = None
        probability = 0.0
        severity = "moderate"

        if weather_id in _SEVERE_STORM_IDS or (
            weather_id in _THUNDERSTORM_IDS and wind_speed >= SEVERE_WIND_MS
        ):
            hazard = "severe_storm"
            probability = 0.90
            severity = "critical"
        elif weather_id in _THUNDERSTORM_IDS:
            hazard = "thunderstorm"
            probability = 0.80
            severity = "high"
        elif weather_id in _HEAVY_RAIN_IDS or rain_3h >= RAIN_3H_HEAVY_MM:
            hazard = "heavy_rain"
            probability = min(_PROB_MAX, _RAIN_PROB_BASE + rain_3h / _RAIN_PROB_SCALE)
            severity = "high" if rain_3h >= _RAIN_HIGH_SEV_MM else "moderate"
        elif temp >= HEAT_STRESS_TEMP_C:
            hazard = "heat_stress"
            probability = min(_PROB_MAX, _HEAT_PROB_BASE + (temp - HEAT_STRESS_TEMP_C) / _HEAT_PROB_SCALE)
            severity = "moderate"

        if not hazard:
            continue

        existing = detected.get(hazard)
        if not existing or _SEVERITY_RANK[severity] > _SEVERITY_RANK[existing["severity"]]:
            detected[hazard] = {
                "hazard": hazard,
                "severity": severity,
                "probability": probability,
                "horizon_h": horizon_h,
                "weather_id": weather_id,
                "weather_main": weather_main,
                "description": weather0.get("description", ""),
            }

    return list(detected.values())


# ---------------------------------------------------------------------------
# forecast_alert_log table helpers
# ---------------------------------------------------------------------------

def _ensure_forecast_alert_log_table() -> None:
    """Create forecast_alert_log table if it doesn't exist."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS forecast_alert_log (
                        id SERIAL PRIMARY KEY,
                        hazard VARCHAR(50) NOT NULL,
                        severity VARCHAR(20) NOT NULL,
                        scope VARCHAR(100) NOT NULL,
                        notified_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_forecast_alert_log_lookup
                    ON forecast_alert_log (hazard, scope, notified_at DESC)
                """)
                conn.commit()
    except Exception as exc:
        logger.error(f"Failed to create forecast_alert_log table: {exc}")


def _is_duplicate(hazard: str, severity: str, scope: str, dedupe_hours: int) -> bool:
    """
    Return True if the same hazard+scope was already notified within
    dedupe_hours *at the same or higher severity* (allows re-alert on escalation).
    """
    try:
        cutoff = datetime.utcnow() - timedelta(hours=dedupe_hours)
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT severity FROM forecast_alert_log
                WHERE hazard = %s AND scope = %s AND notified_at > %s
                ORDER BY notified_at DESC
                LIMIT 1
                """,
                (hazard, scope, cutoff),
            )
            row = cur.fetchone()
        if not row:
            return False
        prev_rank = _SEVERITY_RANK.get(row["severity"], 0)
        curr_rank = _SEVERITY_RANK.get(severity, 0)
        return curr_rank <= prev_rank  # duplicate if not escalating
    except Exception as exc:
        logger.error(f"Dedup check failed: {exc}")
        return False  # on error, prefer sending


def _log_forecast_alert(hazard: str, severity: str, scope: str) -> None:
    """Record a sent forecast alert in the dedup log."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO forecast_alert_log (hazard, severity, scope) VALUES (%s, %s, %s)",
                    (hazard, severity, scope),
                )
                conn.commit()
    except Exception as exc:
        logger.error(f"Failed to log forecast alert: {exc}")


# ---------------------------------------------------------------------------
# Postgres notifications table helpers
# ---------------------------------------------------------------------------

def _insert_notification(title: str, message: str, sent_to: str) -> Optional[str]:
    """Insert a record into the notifications table and return its id, or None on failure."""
    notification_id = str(uuid.uuid4())
    try:
        with get_db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO notifications (id, title, message, type, sent_to, status, date_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    notification_id,
                    title,
                    message,
                    "weather_alert",
                    sent_to,
                    "sent",
                    datetime.utcnow(),
                ),
            )
        return notification_id
    except Exception as exc:
        logger.error(f"Failed to insert notification: {exc}")
        return None


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

def _get_verified_users() -> List[Dict]:
    """Fetch all verified users with a non-empty phone number."""
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id AS user_id, phone_number, first_name, last_name
                FROM users
                WHERE phone_number IS NOT NULL
                  AND phone_number != ''
                  AND is_verified = TRUE
            """)
            return [dict(u) for u in cur.fetchall()]
    except Exception as exc:
        logger.error(f"Failed to fetch verified users: {exc}")
        return []


def _get_single_user(user_id: str) -> Optional[Dict]:
    """Fetch a single user by id."""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT id AS user_id, phone_number, first_name, last_name
                FROM users WHERE id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as exc:
        logger.error(f"Failed to fetch user {user_id}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_forecast(test_user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch the OpenWeather forecast, detect hazards, deduplicate, then:
      - Insert a notification record into Postgres notifications table.
      - Send Semaphore SMS to all verified users (or a single user for test runs).

    Args:
        test_user_id: If set, restricts SMS + notification scope to this user only.

    Returns:
        Summary dict with keys: success, scope, location, hazards_detected,
        hazards_skipped_dedup, notifications_created, alerts_sent, recipients_count.
    """
    cfg = _get_config()
    scope = f"user:{test_user_id}" if test_user_id else "all"

    logger.info(f"Starting forecast run (scope={scope})")

    _ensure_forecast_alert_log_table()

    # 1. Fetch forecast
    if not cfg["api_key"]:
        raise ValueError("OPENWEATHER_API_KEY is not configured")

    forecast_data = fetch_forecast(cfg["api_key"], cfg["lat"], cfg["lon"])
    location_name = cfg["location_name"]

    # 2. Analyze hazards
    hazards = analyze_forecast(forecast_data)

    if not hazards:
        logger.info("No hazards detected in forecast")
        return {
            "success": True,
            "scope": scope,
            "location": location_name,
            "hazards_detected": 0,
            "hazards_skipped_dedup": 0,
            "alerts_sent": 0,
            "notifications_created": 0,
            "recipients_count": 0,
        }

    logger.info(f"Detected {len(hazards)} hazard(s): {[h['hazard'] for h in hazards]}")

    # 3. Get recipients
    if test_user_id:
        user = _get_single_user(test_user_id)
        recipients = [user] if user else []
    else:
        recipients = _get_verified_users()

    phone_numbers = [u["phone_number"] for u in recipients if u.get("phone_number")]
    sms_service = get_semaphore_service()

    alerts_sent = 0
    notifications_created = 0
    hazards_skipped = 0

    for hazard_info in hazards:
        hazard = hazard_info["hazard"]
        severity = hazard_info["severity"]
        probability = hazard_info["probability"]
        horizon_h = hazard_info["horizon_h"]

        # 4. Dedup check
        if _is_duplicate(hazard, severity, scope, cfg["dedupe_hours"]):
            logger.info(
                f"Skipping {hazard} (already sent within {cfg['dedupe_hours']}h "
                f"at same or higher severity)"
            )
            hazards_skipped += 1
            continue

        # 5. Create in-app notification
        notif_title = f"{_hazard_display_name(hazard)} Alert"
        notif_message = (
            f"Forecast alert: {_hazard_display_name(hazard)} expected in "
            f"approximately {horizon_h} hour(s) for {location_name}. "
            f"Risk level: {severity} ({int(probability * 100)}%)."
        )
        sent_to = f"user:{test_user_id}" if test_user_id else "all"

        notif_id = _insert_notification(notif_title, notif_message, sent_to)
        if notif_id:
            notifications_created += 1

        # 6. Send SMS
        if phone_numbers:
            results = sms_service.send_hazard_alert(
                phone_numbers=phone_numbers,
                hazard=hazard,
                horizon=horizon_h,
                probability=probability,
                location=location_name,
            )
            alerts_sent += results.get("success", 0)
            logger.info(
                f"SMS for {hazard}: {results.get('success', 0)}/{results.get('total', 0)} sent"
            )

        # 7. Log to dedup table
        _log_forecast_alert(hazard, severity, scope)

    result = {
        "success": True,
        "scope": scope,
        "location": location_name,
        "hazards_detected": len(hazards),
        "hazards_skipped_dedup": hazards_skipped,
        "alerts_sent": alerts_sent,
        "notifications_created": notifications_created,
        "recipients_count": len(recipients),
    }

    logger.info(f"Forecast run complete: {result}")
    return result
