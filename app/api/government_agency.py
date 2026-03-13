from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime
import uuid

from app.models.government_agency import (
    GovernmentAgency,
    GovernmentAgencyCreate,
    GovernmentAgencyUpdate
)
from app.database import get_db_cursor

router = APIRouter(prefix="/api/government-agencies", tags=["Government Agencies"])

@router.get("/", response_model=List[GovernmentAgency])
def get_government_agencies():
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT id, name, 
                   location_latitude as latitude, location_longitude as longitude, 
                   type, contact, facilities, description, created_at, updated_at
            FROM government_agencies
            ORDER BY created_at DESC
        """)
        agencies = []
        for row in cur.fetchall():
            agency = dict(row)
            agency['location'] = {
                "latitude": agency.pop('latitude'),
                "longitude": agency.pop('longitude')
            }
            if agency.get('facilities') and isinstance(agency['facilities'], str):
                import json
                agency['facilities'] = json.loads(agency['facilities'])
            agencies.append(agency)
        return agencies

@router.post("/", response_model=GovernmentAgency, status_code=status.HTTP_201_CREATED)
def create_government_agency(agency: GovernmentAgencyCreate):
    try:
        agency_id = str(uuid.uuid4())
        now = datetime.utcnow()

        facilities = agency.facilities or []
        import json
        facilities_json = json.dumps(facilities)

        with get_db_cursor() as cur:
            cur.execute("""
                INSERT INTO government_agencies (
                    id, name, location_latitude, location_longitude, type,
                    contact, facilities, description, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, name, location_latitude as latitude, location_longitude as longitude, 
                          type, contact, facilities, description, created_at, updated_at
            """, (
                agency_id,
                agency.name,
                agency.location.latitude,
                agency.location.longitude,
                agency.type,
                agency.contact,
                facilities_json,
                agency.description,
                now,
                now
            ))
            row = cur.fetchone()
            data = dict(row)
            data['location'] = {
                "latitude": data.pop('latitude'),
                "longitude": data.pop('longitude')
            }
            if data.get('facilities') and isinstance(data['facilities'], str):
                data['facilities'] = json.loads(data['facilities'])
            return data
    except Exception as e:
        print(f"❌ Error creating government agency: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating government agency: {str(e)}"
        )


@router.get("/{agency_id}", response_model=GovernmentAgency)
def get_government_agency_by_id(agency_id: str):
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT id, name, location_latitude as latitude, location_longitude as longitude, 
                   type, contact, facilities, description, created_at, updated_at
            FROM government_agencies
            WHERE id = %s
        """, (agency_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Government agency not found")
        agency = dict(row)
        agency['location'] = {
            "latitude": agency.pop('latitude'),
            "longitude": agency.pop('longitude')
        }
        if agency.get('facilities') and isinstance(agency['facilities'], str):
            import json
            agency['facilities'] = json.loads(agency['facilities'])
        return agency

@router.put("/{agency_id}", response_model=GovernmentAgency)
def update_government_agency(agency_id: str, agency_update: GovernmentAgencyUpdate):
    try:
        with get_db_cursor() as cur:
            # Get existing first
            cur.execute("""
                SELECT id, name, location_latitude, location_longitude, 
                       type, contact, facilities, description, created_at, updated_at
                FROM government_agencies
                WHERE id = %s
            """, (agency_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Government agency not found")
            # Prepare updated values
            updated = dict(existing)
            if agency_update.name is not None:
                updated['name'] = agency_update.name
            if agency_update.location is not None:
                updated['location_latitude'] = agency_update.location.latitude
                updated['location_longitude'] = agency_update.location.longitude
            if agency_update.type is not None:
                updated['type'] = agency_update.type
            if agency_update.contact is not None:
                updated['contact'] = agency_update.contact
            if agency_update.facilities is not None:
                import json
                updated['facilities'] = json.dumps(agency_update.facilities)
            if agency_update.description is not None:
                updated['description'] = agency_update.description
            updated['updated_at'] = datetime.utcnow()
            # Update row
            cur.execute("""
                UPDATE government_agencies
                SET name = %s,
                    location_latitude = %s,
                    location_longitude = %s,
                    type = %s,
                    contact = %s,
                    facilities = %s,
                    description = %s,
                    updated_at = %s
                WHERE id = %s
                RETURNING id, name, location_latitude as latitude, location_longitude as longitude, 
                          type, contact, facilities, description, created_at, updated_at
            """, (
                updated['name'],
                updated['location_latitude'],
                updated['location_longitude'],
                updated['type'],
                updated['contact'],
                updated['facilities'],
                updated['description'],
                updated['updated_at'],
                agency_id
            ))
            row = cur.fetchone()
            data = dict(row)
            data['location'] = {
                "latitude": data.pop('latitude'),
                "longitude": data.pop('longitude')
            }
            if data.get('facilities') and isinstance(data['facilities'], str):
                import json
                data['facilities'] = json.loads(data['facilities'])
            return data
    except Exception as e:
        print(f"❌ Error updating government agency: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating government agency: {str(e)}"
        )


@router.delete("/{agency_id}")
def delete_government_agency(agency_id: str):
    with get_db_cursor() as cur:
        cur.execute(
            "DELETE FROM government_agencies WHERE id = %s RETURNING id",
            (agency_id,)
        )
        deleted = cur.fetchone()
        if not deleted:
            raise HTTPException(status_code=404, detail="Government agency not found")
        return {"success": True, "message": "Government agency deleted successfully"}
