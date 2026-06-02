"""
Internal endpoints for app automation tasks.
All routes require the X-Internal-Token header to match INTERNAL_COLLECTOR_TOKEN env var.
Forecast routes require the X-Internal-Secret header to match INTERNAL_CRON_SECRET env var.
"""

import os
from fastapi import APIRouter, Header, HTTPException, status, Query
from app.services.openweather_collector import run_collection
from app.services.email_service import EmailService
from app.services.semaphore_notification import get_semaphore_service
from app.services.alert_dispatcher import get_alert_dispatcher
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/internal", tags=["Internal"])

_MISSING = object()


def _verify_token(x_internal_token: str) -> None:
    """Raise 401 if the token header is missing or does not match env var."""
    expected = os.getenv("INTERNAL_COLLECTOR_TOKEN", _MISSING)
    if expected is _MISSING or not expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Internal token not configured on server",
        )
    if x_internal_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Internal-Token",
        )


def _verify_secret(x_internal_secret: str) -> None:
    """Raise 401 if X-Internal-Secret header is missing or does not match INTERNAL_CRON_SECRET."""
    expected = os.getenv("INTERNAL_CRON_SECRET", _MISSING)
    if expected is _MISSING or not expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INTERNAL_CRON_SECRET not configured on server",
        )
    if x_internal_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Internal-Secret",
        )


@router.post("/collect/openweather")
async def collect_openweather(
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
):
    """
    Trigger OpenWeather current weather collection and upsert into Postgres.

    Requires header:
        X-Internal-Token: <INTERNAL_COLLECTOR_TOKEN>

    Returns a summary of the inserted/updated observation.
    """
    _verify_token(x_internal_token)

    from app.config import Config
    if not Config.OPENWEATHER_COLLECTOR_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OpenWeather collector is disabled (OPENWEATHER_COLLECTOR_ENABLED=false)",
        )

    try:
        summary = run_collection()
        logger.info(f"OpenWeather collection successful: dt={summary['dt']}")
        return {"success": True, **summary}
    except KeyError as exc:
        logger.error(f"OpenWeather collection failed - missing env var: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Missing required environment variable: {exc}",
        )
    except Exception as exc:
        logger.error(f"OpenWeather collection failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.post("/forecast/run")
async def forecast_run_all(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
):
    """
    Fetch the OpenWeather forecast, detect hazards, and send in-app Postgres
    notifications + Semaphore SMS to **all** verified users with a phone number.

    Requires header:
        X-Internal-Secret: <INTERNAL_CRON_SECRET>

    Deduplication prevents repeated alerts within FORECAST_DEDUPE_HOURS (default 6 h)
    unless severity escalates.
    """
    _verify_secret(x_internal_secret)
    from app.services.forecast_runner import run_forecast

    from app.config import Config
    if not Config.FORECAST_RUNNER_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forecast runner is disabled (FORECAST_RUNNER_ENABLED=false)",
        )

    try:
        result = run_forecast(test_user_id=None)
        logger.info(f"Forecast run (all users) complete: {result}")
        return result
    except ValueError as exc:
        logger.error(f"Forecast run failed - configuration error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(f"Forecast run failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.post("/forecast/test/user/{user_id}")
async def forecast_run_test_user(
    user_id: str,
    force_hazard: str | None = Query(default=None),  # <-- add this
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
):
    """
    Test forecast run scoped to a **single user**.

    Fetches the OpenWeather forecast, detects hazards, and sends an in-app
    notification + Semaphore SMS to the specified user only.

    Requires header:
        X-Internal-Secret: <INTERNAL_CRON_SECRET>

    Path parameter:
        user_id: The target user's ID (UUID string).
    """
    _verify_secret(x_internal_secret)
    from app.services.forecast_runner import run_forecast

    try:
        result = run_forecast(test_user_id=user_id, force_hazard=force_hazard)
        logger.info(f"Forecast test run (user={user_id}) complete: {result}")
        return result
    except ValueError as exc:
        logger.error(f"Forecast test run failed - configuration error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(f"Forecast test run failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.post("/test/email")
async def test_email(
    email: str = Query(...),
    subject: str = Query(default="Test Email"),
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
):
    """Send a test email to an arbitrary address."""
    _verify_token(x_internal_token)
    try:
        # Using the hazard alert template as it's the more complex one
        result = EmailService.send_hazard_alert_email(
            recipient_email=email,
            hazard_name="Test Hazard",
            horizon=24,
            probability=0.75,
            safety_tips=["Test tip 1", "Test tip 2"]
        )
        return {"success": True, "detail": "Test email sent", "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/test/sms")
async def test_sms(
    phone: str = Query(...),
    message: str = Query(default="This is a test SMS from HydroMet."),
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
):
    """Send a test SMS to an arbitrary phone number."""
    _verify_token(x_internal_token)
    try:
        sms_service = get_semaphore_service()
        success, response, error = sms_service.send_sms(phone, message)
        return {"success": success, "response": response, "error": error}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/test/full-alert/{user_id}")
async def test_full_alert(
    user_id: str,
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
):
    """Send a full multi-channel test alert to a specific user (In-app + SMS + Email)."""
    _verify_token(x_internal_token)
    try:
        dispatcher = get_alert_dispatcher()
        # Mocking a prediction results for the dispatcher
        mock_predictions = {
            "success": True,
            "predictions": {
                "heavy_rain": {
                    "24h": {
                        "available": True,
                        "hazard_detected": True,
                        "probability": 0.85
                    }
                }
            }
        }
        
        # Get user details from DB to provide to dispatcher
        from app.database import get_db_cursor
        with get_db_cursor() as cur:
            cur.execute("SELECT id as user_id, phone_number, email FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
        
        result = dispatcher.dispatch_from_predictions(
            predictions=mock_predictions,
            location="Test Location",
            recipients=[dict(user)]
        )
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}