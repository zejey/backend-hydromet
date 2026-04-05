from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid

from app.database import get_db_cursor
from app.services.system_logs_service import SystemLogsService

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
                cur.execute("""
                    SELECT id, name, is_active, created_at, updated_at
                    FROM barangays
                    WHERE is_active = TRUE
                    ORDER BY name ASC
                """)
            else:
                cur.execute("""
                    SELECT id, name, is_active, created_at, updated_at
                    FROM barangays
                    ORDER BY name ASC
                """)
            rows = cur.fetchall()
            return [Barangay(**dict(r)) for r in rows]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing barangays: {str(e)}"
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
            role="admin"
        )
        raise HTTPException(status_code=400, detail="Barangay name is required")

    try:
        with get_db_cursor() as cur:
            barangay_id = str(uuid.uuid4())
            now = datetime.utcnow()
            cur.execute("""
                INSERT INTO barangays (id, name, is_active, created_at, updated_at)
                VALUES (%s, %s, TRUE, %s, %s)
                RETURNING id, name, is_active, created_at, updated_at
            """, (barangay_id, name, now, now))
            row = cur.fetchone()

        SystemLogsService.create_log(
            action="Barangay Created",
            status="Success",
            details=f"Created barangay '{name}' (id={barangay_id}).",
            user="System Admin",
            role="admin"
        )

        return Barangay(**dict(row))
    except Exception as e:
        SystemLogsService.create_log(
            action="Barangay Created",
            status="Failed",
            details=f"Failed to create barangay '{name}': {type(e).__name__}",
            user="System Admin",
            role="admin"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not create barangay: {str(e)}"
        )
        
@router.put("/{barangay_id}", response_model=Barangay)
async def update_barangay(barangay_id: str, payload: BarangayUpdate):
    if payload.name is None and payload.is_active is None:
        SystemLogsService.create_log(
            action="Barangay Updated",
            status="Failed",
            details=f"Barangay update failed: no fields provided (id={barangay_id}).",
            user="System Admin",
            role="admin"
        )
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, name, is_active, created_at, updated_at
                FROM barangays
                WHERE id = %s
            """, (barangay_id,))
            existing = cur.fetchone()
                    status="Failed",
                    details=f"Barangay update failed: not found (id={barangay_id}).",
                    user="System Admin",
                    role="admin"
                )
                raise HTTPException(status_code=404, detail="Barangay not found")

            new_name = payload.name.strip() if payload.name is not None else existing["name"]
            new_is_active = payload.is_active if payload.is_active is not None else existing["is_active"]
            now = datetime.utcnow()

            cur.execute("""
                UPDATE barangays
                SET name = %s,
                    is_active = %s,
                    updated_at = %s
                WHERE id = %s
                RETURNING id, name, is_active, created_at, updated_at
            """, (new_name, new_is_active, now, barangay_id))

            row = cur.fetchone()

            status="Success",
            details=f"Updated barangay id={barangay_id}: name='{new_name}', is_active={new_is_active}.",
            user="System Admin",
            role="admin"
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
            role="admin"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not update barangay: {str(e)}"
        )
