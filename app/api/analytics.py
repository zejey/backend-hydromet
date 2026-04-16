"""
Analytics API endpoints

Provides aggregated data for the web admin dashboard:
  GET /api/analytics/users          — registration trends
  GET /api/analytics/logins         — login frequency
  GET /api/analytics/notifications  — notification send counts
  GET /api/analytics/overview       — quick summary counts
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.database import get_db_cursor

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class TimeSeriesPoint(BaseModel):
    date: str
    count: int


class OverviewResponse(BaseModel):
    total_users: int
    total_admins: int
    total_notifications: int
    total_predictions: int


# ---------------------------------------------------------------------------
# GET /api/analytics/overview
# ---------------------------------------------------------------------------

@router.get("/overview", response_model=OverviewResponse)
async def analytics_overview():
    """Quick summary counts for dashboard cards."""
    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM users")
        total_users = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) AS cnt FROM admin")
        total_admins = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) AS cnt FROM notifications")
        total_notifications = cur.fetchone()["cnt"]

        # predictions might not have a table; fall back to 0
        try:
            cur.execute("SELECT COUNT(*) AS cnt FROM predictions")
            total_predictions = cur.fetchone()["cnt"]
        except Exception:
            total_predictions = 0

        return OverviewResponse(
            total_users=total_users,
            total_admins=total_admins,
            total_notifications=total_notifications,
            total_predictions=total_predictions,
        )


# ---------------------------------------------------------------------------
# GET /api/analytics/users
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[TimeSeriesPoint])
async def analytics_users(
    start_date: Optional[str] = Query(None, description="ISO date, e.g. 2025-01-01"),
    end_date: Optional[str] = Query(None, description="ISO date, e.g. 2025-12-31"),
    interval: str = Query("day", description="day | week | month"),
):
    """User registrations over time."""
    trunc = _pg_trunc(interval)
    where, params = _date_range_clause("created_at", start_date, end_date)

    with get_db_cursor() as cur:
        cur.execute(
            f"""
            SELECT DATE_TRUNC('{trunc}', created_at)::date AS date,
                   COUNT(*) AS count
            FROM users
            {where}
            GROUP BY 1 ORDER BY 1
            """,
            params,
        )
        return [TimeSeriesPoint(date=str(r["date"]), count=r["count"]) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# GET /api/analytics/logins
# ---------------------------------------------------------------------------

@router.get("/logins", response_model=list[TimeSeriesPoint])
async def analytics_logins(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    interval: str = Query("day"),
):
    """Login frequency over time (sourced from system_logs)."""
    trunc = _pg_trunc(interval)
    base_where = "WHERE action IN ('User Login', 'Admin Login') AND status = 'Success'"
    date_clause, params = _date_range_clause("created_at", start_date, end_date, prefix="AND")

    with get_db_cursor() as cur:
        cur.execute(
            f"""
            SELECT DATE_TRUNC('{trunc}', created_at)::date AS date,
                   COUNT(*) AS count
            FROM system_logs
            {base_where} {date_clause}
            GROUP BY 1 ORDER BY 1
            """,
            params,
        )
        return [TimeSeriesPoint(date=str(r["date"]), count=r["count"]) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# GET /api/analytics/notifications
# ---------------------------------------------------------------------------

@router.get("/notifications", response_model=list[TimeSeriesPoint])
async def analytics_notifications(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    interval: str = Query("day"),
):
    """Notification send counts over time."""
    trunc = _pg_trunc(interval)
    where, params = _date_range_clause("date_time", start_date, end_date)

    with get_db_cursor() as cur:
        cur.execute(
            f"""
            SELECT DATE_TRUNC('{trunc}', date_time)::date AS date,
                   COUNT(*) AS count
            FROM notifications
            {where}
            GROUP BY 1 ORDER BY 1
            """,
            params,
        )
        return [TimeSeriesPoint(date=str(r["date"]), count=r["count"]) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TRUNCS = {"day", "week", "month"}


def _pg_trunc(interval: str) -> str:
    """Sanitise the DATE_TRUNC interval to prevent injection."""
    interval = interval.lower().strip()
    if interval not in _VALID_TRUNCS:
        return "day"
    return interval


def _date_range_clause(
    column: str, start_date: Optional[str], end_date: Optional[str], prefix: str = "WHERE"
) -> tuple[str, list]:
    """Build a WHERE/AND clause with parameterised date bounds."""
    parts: list[str] = []
    params: list = []
    if start_date:
        parts.append(f"{column} >= %s")
        params.append(start_date)
    if end_date:
        parts.append(f"{column} < (%s::date + INTERVAL '1 day')")
        params.append(end_date)
    if not parts:
        return "", params
    return f"{prefix} " + " AND ".join(parts), params
