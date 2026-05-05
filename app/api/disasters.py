"""
Disaster Monitoring API Endpoints
Unified dashboard for all active disasters: earthquakes, typhoons, floods, etc.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.services.disaster_monitor import get_disaster_monitor
from app.services.system_logs_service import SystemLogsService
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/disasters", tags=["Disaster Monitoring"])


class ManualDisasterCreate(BaseModel):
    """Payload for admin-created manual disaster alerts."""
    title: str = Field(..., min_length=1, max_length=512)
    disaster_type: str = Field(
        ..., description="Type: earthquake, typhoon, flood, volcanic, landslide, other"
    )
    description: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    affected_radius_km: Optional[float] = None
    severity: str = Field(
        default="advisory",
        description="Severity: advisory, watch, warning, critical",
    )
    magnitude: Optional[float] = None
    category: Optional[str] = None


@router.get("/active")
async def get_active_disasters(
    disaster_type: Optional[str] = Query(
        None, description="Filter by type: earthquake, typhoon, flood, volcanic"
    ),
    severity: Optional[str] = Query(
        None, description="Filter by severity: advisory, watch, warning, critical"
    ),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Get all currently active disasters.

    Aggregates data from USGS, GDACS, and manual admin alerts.
    Ordered by severity (critical first) then by time (most recent first).
    """
    try:
        monitor = get_disaster_monitor()
        disasters = monitor.get_active_disasters(
            disaster_type=disaster_type,
            severity=severity,
            limit=limit,
        )

        return {
            "success": True,
            "count": len(disasters),
            "disasters": disasters,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Active disasters fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard")
async def get_disaster_dashboard():
    """
    Get summary dashboard data for all active disasters.

    Returns aggregate counts by type, severity breakdown,
    and count of new events in the last 24 hours.
    """
    try:
        monitor = get_disaster_monitor()
        summary = monitor.get_dashboard_summary()

        return {"success": True, **summary}
    except Exception as e:
        logger.error(f"Dashboard fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_disaster_history(
    days: int = Query(default=30, description="Look-back in days", ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
):
    """
    Get historical disasters (both active and resolved) for the given period.
    """
    try:
        monitor = get_disaster_monitor()
        history = monitor.get_disaster_history(days=days, limit=limit)

        return {
            "success": True,
            "count": len(history),
            "disasters": history,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Disaster history fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{disaster_id}")
async def get_disaster_detail(disaster_id: str):
    """Get detailed information about a specific disaster event."""
    try:
        monitor = get_disaster_monitor()
        disaster = monitor.get_disaster_by_id(disaster_id)

        if not disaster:
            raise HTTPException(status_code=404, detail="Disaster not found")

        return {"success": True, "disaster": disaster}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Disaster detail fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manual")
async def create_manual_disaster(payload: ManualDisasterCreate):
    """
    Admin creates a manual disaster alert.

    Use this for locally-observed events that aren't yet in USGS/GDACS,
    or for PAGASA-sourced advisories.
    """
    try:
        monitor = get_disaster_monitor()
        disaster = monitor.create_manual_alert(payload.model_dump())

        SystemLogsService.create_log(
            action="Manual Disaster Alert Created",
            status="Success",
            details=f"Created '{payload.title}' ({payload.disaster_type}, {payload.severity})",
            user="System Admin",
            role="admin",
        )

        return {
            "success": True,
            "message": "Manual disaster alert created",
            "disaster": disaster,
        }
    except Exception as e:
        SystemLogsService.create_log(
            action="Manual Disaster Alert Created",
            status="Failed",
            details=f"Failed: {type(e).__name__}",
            user="System Admin",
            role="admin",
        )
        logger.error(f"Manual disaster creation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{disaster_id}/resolve")
async def resolve_disaster(disaster_id: str):
    """Admin marks a disaster as resolved."""
    try:
        monitor = get_disaster_monitor()
        success = monitor.resolve_disaster(disaster_id)

        if not success:
            raise HTTPException(status_code=404, detail="Disaster not found")

        SystemLogsService.create_log(
            action="Disaster Resolved",
            status="Success",
            details=f"Resolved disaster {disaster_id}",
            user="System Admin",
            role="admin",
        )

        return {"success": True, "message": "Disaster marked as resolved"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Disaster resolve failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitor/run")
async def trigger_monitoring_cycle():
    """
    Manually trigger a disaster monitoring cycle.

    Fetches latest data from USGS and GDACS, upserts into the
    active_disasters table, and auto-resolves stale events.

    Normally this runs on a schedule, but this endpoint allows
    admins to trigger it on demand.
    """
    try:
        monitor = get_disaster_monitor()
        result = monitor.run_monitoring_cycle()

        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Manual monitoring cycle failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
