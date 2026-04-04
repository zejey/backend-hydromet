
"""
System Logs API endpoints
"""

from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Query

from app.models.system_logs import SystemLogListResponse, SystemLogCreate, SystemLog
from app.services.system_logs_service import SystemLogsService

router = APIRouter(
    prefix="/api/system-logs",
    tags=["System Logs"],
    redirect_slashes=False
)


@router.get("/", response_model=SystemLogListResponse)
async def get_system_logs(
    q: Optional[str] = Query(None, description="Search query (user/action/details/category/status)"),
    category: Optional[str] = Query(None, description="Filter category"),
    status: Optional[str] = Query(None, description="Filter status: Success|Failed|Warning"),
    date_from: Optional[datetime] = Query(None, description="Filter start datetime (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="Filter end datetime (ISO 8601)"),
    sort_by: str = Query("created_at", description="created_at|status|category|action|user_label"),
    sort_dir: str = Query("desc", description="asc|desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    total, logs = SystemLogsService.list_logs(
        q=q,
        category=category,
        status=status,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "message": "System logs fetched successfully",
        "total": total,
        "page": page,
        "page_size": page_size,
        "logs": logs,
    }


@router.post("/", response_model=SystemLog)
async def create_system_log(payload: SystemLogCreate):
    """
    Optional: allow creating logs via API.
    In production, you typically log internally from backend actions.
    """
    row = SystemLogsService.create_log(
        action=payload.action,
        category=payload.category,
        status=payload.status,
        details=payload.details,
        user=payload.user,
        user_id=payload.user_id,
        role=payload.role,
        ip_address=payload.ip_address,
        user_agent=payload.user_agent,
    )
    return row
