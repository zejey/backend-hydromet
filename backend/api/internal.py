"""
Internal endpoints for backend automation tasks.
All routes require the X-Internal-Token header to match INTERNAL_COLLECTOR_TOKEN env var.
Forecast routes require the X-Internal-Secret header to match INTERNAL_CRON_SECRET env var.
"""

import os
from fastapi import APIRouter, Header, HTTPException, status
from backend.services.openweather_collector import run_collection
from backend.utils.logger import get_logger

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
    from backend.services.forecast_runner import run_forecast

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
    from backend.services.forecast_runner import run_forecast

    try:
        result = run_forecast(test_user_id=user_id)
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