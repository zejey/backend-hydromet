"""
API endpoints for auto-predictor service
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
import asyncio

from app.services.enhanced_auto_predictor import get_enhanced_auto_predictor
from app.services.system_logs_service import SystemLogsService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auto-predictor", tags=["Auto-Predictor"])


class AutoPredictorStatus(BaseModel):
    """Auto-predictor status"""
    running: bool
    last_run: Optional[str] = None
    interval_hours: int = 1


class RunOnceResponse(BaseModel):
    """Response for run-once endpoint"""
    success: bool
    message: str
    summary: Optional[Dict[str, Any]] = None


# Global task reference
_background_task = None
_is_running = False
_last_summary = None


@router.get("/status", response_model=AutoPredictorStatus)
async def get_status():
    """Get auto-predictor status"""
    global _is_running, _last_summary
    return AutoPredictorStatus(
        running=_is_running,
        last_run=_last_summary.get('timestamp') if _last_summary else None,
        interval_hours=1
    )

@router.post("/start")
async def start_auto_predictor(background_tasks: BackgroundTasks, interval_hours: int = 1):
    """Start continuous auto-predictor"""
    global _background_task, _is_running

    if _is_running:
        SystemLogsService.create_log(
            action="Auto Predictor Started",
            status="Warning",
            details="Start requested but auto-predictor was already running.",
            user="System Admin",
            role="admin"
        )
        raise HTTPException(status_code=400, detail="Auto-predictor already running")

    try:
        predictor = get_enhanced_auto_predictor()

        _background_task = asyncio.create_task(predictor.run_continuous(interval_hours))
        _is_running = True

        logger.info(f"✅ Auto-predictor started (interval: {interval_hours}h)")

        SystemLogsService.create_log(
            action="Auto Predictor Started",
            status="Success",
            details=f"Auto-predictor started (interval_hours={interval_hours}).",
            user="System Admin",
            role="admin"
        )

        return {
            "success": True,
            "message": f"Auto-predictor started (runs every {interval_hours} hour(s))"
        }

    except Exception as e:
        logger.error(f"❌ Failed to start auto-predictor: {e}")
        SystemLogsService.create_log(
            action="Auto Predictor Started",
            status="Failed",
            details=f"Failed to start auto-predictor: {type(e).__name__}",
            user="System Admin",
            role="admin"
        )
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop")
async def stop_auto_predictor():
    """Stop continuous auto-predictor"""
    global _background_task, _is_running

    if not _is_running:
        SystemLogsService.create_log(
            action="Auto Predictor Stopped",
            status="Warning",
            details="Stop requested but auto-predictor was not running.",
            user="System Admin",
            role="admin"
        )
        raise HTTPException(status_code=400, detail="Auto-predictor not running")

    try:
        if _background_task:
            _background_task.cancel()
            _background_task = None

        _is_running = False

        logger.info("🛑 Auto-predictor stopped")

        SystemLogsService.create_log(
            action="Auto Predictor Stopped",
            status="Success",
            details="Auto-predictor stopped.",
            user="System Admin",
            role="admin"
        )

        return {
            "success": True,
            "message": "Auto-predictor stopped"
        }

    except Exception as e:
        logger.error(f"❌ Failed to stop auto-predictor: {e}")
        SystemLogsService.create_log(
            action="Auto Predictor Stopped",
            status="Failed",
            details=f"Failed to stop auto-predictor: {type(e).__name__}",
            user="System Admin",
            role="admin"
        )
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/run-once", response_model=RunOnceResponse)
async def run_once():
    """Run auto-predictor once (manual trigger)"""
    global _last_summary

    try:
        predictor = get_enhanced_auto_predictor()
        summary = predictor.run_once()

        _last_summary = summary

        total_hazards = summary.get("predictions", {}).get("summary", {}).get("total_hazards_detected", 0)
        message = (
            f"Prediction completed. {total_hazards} hazard(s) detected."
            if summary.get("success")
            else "Prediction failed"
        )

        # ✅ MISSING CALL WAS HERE
        SystemLogsService.create_log(
            action="Auto Predictor Run Once",
            status="Success" if summary.get("success") else "Failed",
            details=message,
            user="System Admin",
            role="admin",
        )

        return RunOnceResponse(
            success=summary.get("success", False),
            message=message,
            summary=summary,
        )

    except Exception as e:
        logger.error(f"❌ Manual prediction failed: {e}")
        SystemLogsService.create_log(
            action="Auto Predictor Run Once",
            status="Failed",
            details=f"Manual run failed: {type(e).__name__}",
            user="System Admin",
            role="admin",
        )
        raise HTTPException(status_code=500, detail=str(e))
