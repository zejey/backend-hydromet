"""
Client Threshold Configuration API Endpoints
CRUD operations for managing client-specific threshold multipliers
"""

from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime

from backend.models.client_config import (
    ClientConfigCreate,
    ClientConfigUpdate,
    ClientConfigResponse,
    ClientConfigListResponse,
    ClientConfigDeleteResponse
)
from backend.database import get_db_cursor
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/client-config", tags=["Client Configuration"])


@router.get("/", response_model=ClientConfigListResponse)
async def list_client_configs():
    """
    List all client threshold configurations
    
    Returns a list of all registered client configurations with their multipliers
    and alert rules.
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT client_id, location_name, barangay,
                       rain_multiplier, wind_multiplier, heat_multiplier, pressure_multiplier,
                       alert_duration_hours, cooldown_hours,
                       description, created_at, updated_at, created_by
                FROM client_threshold_config
                ORDER BY location_name, client_id
            """)
            
            rows = cur.fetchall()
            
            configs = []
            for row in rows:
                configs.append(ClientConfigResponse(
                    client_id=row["client_id"],
                    location_name=row["location_name"],
                    barangay=row["barangay"],
                    rain_multiplier=float(row["rain_multiplier"]),
                    wind_multiplier=float(row["wind_multiplier"]),
                    heat_multiplier=float(row["heat_multiplier"]),
                    pressure_multiplier=float(row["pressure_multiplier"]),
                    alert_duration_hours=int(row["alert_duration_hours"]),
                    cooldown_hours=int(row["cooldown_hours"]),
                    description=row["description"],
                    created_at=row["created_at"].isoformat() if row["created_at"] else None,
                    updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
                    created_by=row["created_by"]
                ))
            
            return ClientConfigListResponse(
                success=True,
                total=len(configs),
                configs=configs
            )
    
    except Exception as e:
        logger.error(f"Failed to list client configs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list client configs: {str(e)}"
        )


@router.get("/{client_id}", response_model=ClientConfigResponse)
async def get_client_config(client_id: str):
    """
    Get a specific client configuration by ID
    
    Args:
        client_id: Unique client identifier
        
    Returns:
        Client configuration with all multipliers and alert rules
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT client_id, location_name, barangay,
                       rain_multiplier, wind_multiplier, heat_multiplier, pressure_multiplier,
                       alert_duration_hours, cooldown_hours,
                       description, created_at, updated_at, created_by
                FROM client_threshold_config
                WHERE client_id = %s
            """, (client_id,))
            
            row = cur.fetchone()
            
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Client configuration not found: {client_id}"
                )
            
            return ClientConfigResponse(
                client_id=row["client_id"],
                location_name=row["location_name"],
                barangay=row["barangay"],
                rain_multiplier=float(row["rain_multiplier"]),
                wind_multiplier=float(row["wind_multiplier"]),
                heat_multiplier=float(row["heat_multiplier"]),
                pressure_multiplier=float(row["pressure_multiplier"]),
                alert_duration_hours=int(row["alert_duration_hours"]),
                cooldown_hours=int(row["cooldown_hours"]),
                description=row["description"],
                created_at=row["created_at"].isoformat() if row["created_at"] else None,
                updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
                created_by=row["created_by"]
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get client config {client_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get client config: {str(e)}"
        )


@router.post("/", response_model=ClientConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_client_config(config: ClientConfigCreate):
    """
    Create a new client threshold configuration
    
    Request Body:
    {
        "client_id": "san_pedro_zone_a",
        "location_name": "Zone A (Mountainous)",
        "barangay": "San Antonio",
        "rain_multiplier": 0.85,
        "wind_multiplier": 1.0,
        "heat_multiplier": 1.1,
        "pressure_multiplier": 1.0,
        "alert_duration_hours": 2,
        "cooldown_hours": 6,
        "description": "Zone A has poor drainage - 15% more sensitive to rain"
    }
    """
    try:
        with get_db_cursor() as cur:
            # Check if client_id already exists
            cur.execute(
                "SELECT client_id FROM client_threshold_config WHERE client_id = %s",
                (config.client_id,)
            )
            
            if cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Client configuration already exists: {config.client_id}"
                )
            
            # Insert new config
            cur.execute("""
                INSERT INTO client_threshold_config (
                    client_id, location_name, barangay,
                    rain_multiplier, wind_multiplier, heat_multiplier, pressure_multiplier,
                    alert_duration_hours, cooldown_hours,
                    description, created_by, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                )
                RETURNING client_id, location_name, barangay,
                          rain_multiplier, wind_multiplier, heat_multiplier, pressure_multiplier,
                          alert_duration_hours, cooldown_hours,
                          description, created_at, updated_at, created_by
            """, (
                config.client_id,
                config.location_name,
                config.barangay,
                config.rain_multiplier,
                config.wind_multiplier,
                config.heat_multiplier,
                config.pressure_multiplier,
                config.alert_duration_hours,
                config.cooldown_hours,
                config.description,
                config.created_by
            ))
            
            row = cur.fetchone()
            
            logger.info(f"Created client config: {config.client_id}")
            
            return ClientConfigResponse(
                client_id=row["client_id"],
                location_name=row["location_name"],
                barangay=row["barangay"],
                rain_multiplier=float(row["rain_multiplier"]),
                wind_multiplier=float(row["wind_multiplier"]),
                heat_multiplier=float(row["heat_multiplier"]),
                pressure_multiplier=float(row["pressure_multiplier"]),
                alert_duration_hours=int(row["alert_duration_hours"]),
                cooldown_hours=int(row["cooldown_hours"]),
                description=row["description"],
                created_at=row["created_at"].isoformat() if row["created_at"] else None,
                updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
                created_by=row["created_by"]
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create client config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create client config: {str(e)}"
        )


@router.put("/{client_id}", response_model=ClientConfigResponse)
async def update_client_config(client_id: str, config: ClientConfigUpdate):
    """
    Update an existing client threshold configuration
    
    Only provided fields will be updated. Omitted fields remain unchanged.
    """
    try:
        with get_db_cursor() as cur:
            # Check if client exists
            cur.execute(
                "SELECT client_id FROM client_threshold_config WHERE client_id = %s",
                (client_id,)
            )
            
            if not cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Client configuration not found: {client_id}"
                )
            
            # Build dynamic UPDATE query based on provided fields
            updates = []
            values = []
            
            if config.location_name is not None:
                updates.append("location_name = %s")
                values.append(config.location_name)
            
            if config.barangay is not None:
                updates.append("barangay = %s")
                values.append(config.barangay)
            
            if config.rain_multiplier is not None:
                updates.append("rain_multiplier = %s")
                values.append(config.rain_multiplier)
            
            if config.wind_multiplier is not None:
                updates.append("wind_multiplier = %s")
                values.append(config.wind_multiplier)
            
            if config.heat_multiplier is not None:
                updates.append("heat_multiplier = %s")
                values.append(config.heat_multiplier)
            
            if config.pressure_multiplier is not None:
                updates.append("pressure_multiplier = %s")
                values.append(config.pressure_multiplier)
            
            if config.alert_duration_hours is not None:
                updates.append("alert_duration_hours = %s")
                values.append(config.alert_duration_hours)
            
            if config.cooldown_hours is not None:
                updates.append("cooldown_hours = %s")
                values.append(config.cooldown_hours)
            
            if config.description is not None:
                updates.append("description = %s")
                values.append(config.description)
            
            if not updates:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No fields provided for update"
                )
            
            # Add updated_at
            updates.append("updated_at = NOW()")
            values.append(client_id)
            
            # Execute update
            query = f"""
                UPDATE client_threshold_config
                SET {', '.join(updates)}
                WHERE client_id = %s
                RETURNING client_id, location_name, barangay,
                          rain_multiplier, wind_multiplier, heat_multiplier, pressure_multiplier,
                          alert_duration_hours, cooldown_hours,
                          description, created_at, updated_at, created_by
            """
            
            cur.execute(query, values)
            row = cur.fetchone()
            
            logger.info(f"Updated client config: {client_id}")
            
            return ClientConfigResponse(
                client_id=row["client_id"],
                location_name=row["location_name"],
                barangay=row["barangay"],
                rain_multiplier=float(row["rain_multiplier"]),
                wind_multiplier=float(row["wind_multiplier"]),
                heat_multiplier=float(row["heat_multiplier"]),
                pressure_multiplier=float(row["pressure_multiplier"]),
                alert_duration_hours=int(row["alert_duration_hours"]),
                cooldown_hours=int(row["cooldown_hours"]),
                description=row["description"],
                created_at=row["created_at"].isoformat() if row["created_at"] else None,
                updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
                created_by=row["created_by"]
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update client config {client_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update client config: {str(e)}"
        )


@router.delete("/{client_id}", response_model=ClientConfigDeleteResponse)
async def delete_client_config(client_id: str):
    """
    Delete a client threshold configuration
    
    Note: Cannot delete the 'default' configuration
    """
    try:
        # Prevent deletion of default config
        if client_id == "default":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete the default configuration"
            )
        
        with get_db_cursor() as cur:
            # Check if client exists
            cur.execute(
                "SELECT client_id FROM client_threshold_config WHERE client_id = %s",
                (client_id,)
            )
            
            if not cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Client configuration not found: {client_id}"
                )
            
            # Delete config
            cur.execute(
                "DELETE FROM client_threshold_config WHERE client_id = %s",
                (client_id,)
            )
            
            logger.info(f"Deleted client config: {client_id}")
            
            return ClientConfigDeleteResponse(
                success=True,
                message=f"Client configuration deleted successfully",
                client_id=client_id
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete client config {client_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete client config: {str(e)}"
        )
