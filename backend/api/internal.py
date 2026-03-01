"""
Internal endpoints for backend automation tasks.
All routes require the X-Internal-Token header to match INTERNAL_COLLECTOR_TOKEN env var.
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