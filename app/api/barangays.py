from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from app.database import get_db_cursor
from app.services.system_logs_service import SystemLogsService
from app.services.vulnerability_resolver import VulnerabilityResolver
from app.models.barangay_vulnerability import (
    BarangayVulnerabilityCreate,
    BarangayVulnerabilityUpdate,
    BarangayVulnerability,
    BarangayRiskAssessment,
)

router = APIRouter(prefix="/api/barangays", tags=["Barangays"])


class Barangay(BaseModel):
    id: str
    name: str
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BarangayCreate(BaseModel):
    name: str


class BarangayUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/", response_model=List[Barangay])
@router.get("", response_model=List[Barangay])
async def list_barangays(active_only: bool = True):
    try:
        with get_db_cursor() as cur:
            if active_only:
                cur.execute(
                    """
                    SELECT id, name, is_active, created_at, updated_at
                    FROM barangays
                    WHERE is_active = TRUE
                    ORDER BY name ASC
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT id, name, is_active, created_at, updated_at
                    FROM barangays
                    ORDER BY name ASC
                    """
                )
            rows = cur.fetchall()
            return [Barangay(**dict(r)) for r in rows]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing barangays: {str(e)}",
        )


@router.post("/", response_model=Barangay, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=Barangay, status_code=status.HTTP_201_CREATED)
async def create_barangay(payload: BarangayCreate):
    name = payload.name.strip()
    if not name:
        SystemLogsService.create_log(
            action="Barangay Created",
            status="Failed",
            details="Barangay create failed: name is required.",
            user="System Admin",
            role="admin",
        )
        raise HTTPException(status_code=400, detail="Barangay name is required")

    try:
        with get_db_cursor() as cur:
            barangay_id = str(uuid.uuid4())
            now = datetime.utcnow()
            cur.execute(
                """
                INSERT INTO barangays (id, name, is_active, created_at, updated_at)
                VALUES (%s, %s, TRUE, %s, %s)
                RETURNING id, name, is_active, created_at, updated_at
                """,
                (barangay_id, name, now, now),
            )
            row = cur.fetchone()

        SystemLogsService.create_log(
            action="Barangay Created",
            status="Success",
            details=f"Created barangay '{name}' (id={barangay_id}).",
            user="System Admin",
            role="admin",
        )

        return Barangay(**dict(row))
    except Exception as e:
        SystemLogsService.create_log(
            action="Barangay Created",
            status="Failed",
            details=f"Failed to create barangay '{name}': {type(e).__name__}",
            user="System Admin",
            role="admin",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not create barangay: {str(e)}",
        )


@router.put("/{barangay_id}", response_model=Barangay)
async def update_barangay(barangay_id: str, payload: BarangayUpdate):
    if payload.name is None and payload.is_active is None:
        SystemLogsService.create_log(
            action="Barangay Updated",
            status="Failed",
            details=f"Barangay update failed: no fields provided (id={barangay_id}).",
            user="System Admin",
            role="admin",
        )
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT id, name, is_active, created_at, updated_at
                FROM barangays
                WHERE id = %s
                """,
                (barangay_id,),
            )
            existing = cur.fetchone()

            if not existing:
                SystemLogsService.create_log(
                    action="Barangay Updated",
                    status="Failed",
                    details=f"Barangay update failed: not found (id={barangay_id}).",
                    user="System Admin",
                    role="admin",
                )
                raise HTTPException(status_code=404, detail="Barangay not found")

            new_name = payload.name.strip() if payload.name is not None else existing["name"]
            new_is_active = payload.is_active if payload.is_active is not None else existing["is_active"]
            now = datetime.utcnow()

            cur.execute(
                """
                UPDATE barangays
                SET name = %s,
                    is_active = %s,
                    updated_at = %s
                WHERE id = %s
                RETURNING id, name, is_active, created_at, updated_at
                """,
                (new_name, new_is_active, now, barangay_id),
            )

            row = cur.fetchone()

        SystemLogsService.create_log(
            action="Barangay Updated",
            status="Success",
            details=f"Updated barangay id={barangay_id}: name='{new_name}', is_active={new_is_active}.",
            user="System Admin",
            role="admin",
        )

        return Barangay(**dict(row))

    except HTTPException:
        raise
    except Exception as e:
        SystemLogsService.create_log(
            action="Barangay Updated",
            status="Failed",
            details=f"Failed to update barangay id={barangay_id}: {type(e).__name__}",
            user="System Admin",
            role="admin",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not update barangay: {str(e)}",
        )


# ═══════════════════════════════════════════════════════════════════════════
# Vulnerability Profile Endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/{barangay_id}/vulnerability")
async def get_vulnerability_profile(barangay_id: str):
    """Get the vulnerability profile for a specific barangay."""
    try:
        profile = VulnerabilityResolver._get_profile(barangay_id)
        if not profile:
            raise HTTPException(
                status_code=404,
                detail="No vulnerability profile found for this barangay. "
                       "Create one via PUT /api/barangays/{id}/vulnerability",
            )
        return {"success": True, "vulnerability": profile}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{barangay_id}/vulnerability")
async def upsert_vulnerability_profile(
    barangay_id: str, payload: BarangayVulnerabilityCreate
):
    """
    Create or update the vulnerability profile for a barangay.

    Example: Set Barangay Landayan as high-flood-risk with 2mm rain threshold:
    ```json
    {
        "flood_susceptibility": "high",
        "flood_rain_threshold_mm": 2.0,
        "near_waterway": true,
        "alert_priority_rank": 10
    }
    ```
    """
    # Verify barangay exists
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT id FROM barangays WHERE id = %s", (barangay_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Barangay not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        result = VulnerabilityResolver.upsert_profile(
            barangay_id, payload.model_dump(exclude_none=True)
        )

        SystemLogsService.create_log(
            action="Vulnerability Profile Updated",
            status="Success",
            details=f"Updated vulnerability profile for barangay {barangay_id}",
            user="System Admin",
            role="admin",
        )

        return {"success": True, "vulnerability": result}
    except Exception as e:
        SystemLogsService.create_log(
            action="Vulnerability Profile Updated",
            status="Failed",
            details=f"Failed for barangay {barangay_id}: {type(e).__name__}",
            user="System Admin",
            role="admin",
        )
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{barangay_id}/vulnerability")
async def patch_vulnerability_profile(
    barangay_id: str, payload: BarangayVulnerabilityUpdate
):
    """
    Partially update specific vulnerability fields for a barangay.
    Only the provided fields will be updated.
    """
    update_data = payload.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        result = VulnerabilityResolver.upsert_profile(barangay_id, update_data)
        return {"success": True, "vulnerability": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/at-risk", response_model=None)
async def get_barangays_at_risk(
    hazard: Optional[str] = Query(
        None, description="Filter by hazard type: heavy_rain, heat_stress, severe_storm"
    ),
):
    """
    List all barangays ordered by vulnerability (most at-risk first).
    Optionally filter to barangays susceptible to a specific hazard type.
    """
    try:
        barangays = VulnerabilityResolver.get_priority_ordered_barangays(hazard)
        return {
            "success": True,
            "count": len(barangays),
            "barangays": barangays,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate-risk", response_model=None)
async def evaluate_all_barangay_risk(weather_data: Dict[str, Any]):
    """
    Evaluate current weather conditions against ALL barangay thresholds.

    Send weather data and receive a list of which barangays are at risk.
    Results are sorted by priority (most vulnerable triggered barangays first).

    Example request body:
    ```json
    {
        "rain_1h": 3.0,
        "feels_like": 35.0,
        "wind_speed": 8.0
    }
    ```

    In this example, Barangay Landayan (threshold 2mm) would be triggered,
    but other barangays with 10mm threshold would not.
    """
    try:
        results = VulnerabilityResolver.evaluate_all_barangays(weather_data)

        triggered = [r for r in results if r["hazards_triggered"]]
        safe = [r for r in results if not r["hazards_triggered"]]

        return {
            "success": True,
            "total_barangays": len(results),
            "triggered_count": len(triggered),
            "safe_count": len(safe),
            "triggered_barangays": triggered,
            "safe_barangays": safe,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

