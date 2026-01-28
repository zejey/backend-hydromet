"""
Client Configuration Database Manager
Database operations for client threshold configs
"""

import os
from typing import Dict, Optional

# Conditional imports to avoid circular dependencies
try:
    from database import DatabaseManager
    from logger_util import get_logger
except ImportError:
    from scripts.database import DatabaseManager
    from scripts.logger_util import get_logger

logger = get_logger(__name__)


class ClientConfigManager:
    """Database operations for client threshold configs"""
    
    def __init__(self):
        """Initialize with database connection"""
        self.db = DatabaseManager(min_conn=1, max_conn=5)
    
    @staticmethod
    def get_multipliers(client_id: str = "default") -> dict:
        """
        Fetch multipliers from DB
        
        Args:
            client_id: Client identifier (defaults to "default")
            
        Returns:
            dict: Multipliers for rain, wind, heat, pressure
                  Returns all 1.0 if client not found
        """
        try:
            db = DatabaseManager(min_conn=1, max_conn=5)
            conn = db.get_connection()
            
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT rain_multiplier, wind_multiplier, heat_multiplier, pressure_multiplier
                    FROM client_threshold_config
                    WHERE client_id = %s
                """, (client_id,))
                
                result = cursor.fetchone()
                cursor.close()
                
                if result:
                    return {
                        "rain": float(result[0]) if result[0] is not None else 1.0,
                        "wind": float(result[1]) if result[1] is not None else 1.0,
                        "heat": float(result[2]) if result[2] is not None else 1.0,
                        "pressure": float(result[3]) if result[3] is not None else 1.0
                    }
                else:
                    # Client not found, return baseline
                    logger.warning(f"Client {client_id} not found, using baseline multipliers")
                    return {
                        "rain": 1.0,
                        "wind": 1.0,
                        "heat": 1.0,
                        "pressure": 1.0
                    }
                    
            finally:
                db.return_connection(conn)
                
        except Exception as e:
            logger.error(f"Failed to fetch multipliers for client {client_id}: {e}")
            # Return baseline on error
            return {
                "rain": 1.0,
                "wind": 1.0,
                "heat": 1.0,
                "pressure": 1.0
            }
    
    @staticmethod
    def get_alert_rules(client_id: str = "default") -> dict:
        """
        Fetch alert rules (duration, cooldown)
        
        Args:
            client_id: Client identifier
            
        Returns:
            dict: Alert configuration with duration_hours and cooldown_hours
        """
        try:
            db = DatabaseManager(min_conn=1, max_conn=5)
            conn = db.get_connection()
            
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT alert_duration_hours, cooldown_hours
                    FROM client_threshold_config
                    WHERE client_id = %s
                """, (client_id,))
                
                result = cursor.fetchone()
                cursor.close()
                
                if result:
                    return {
                        "duration_hours": int(result[0]) if result[0] is not None else 2,
                        "cooldown_hours": int(result[1]) if result[1] is not None else 6
                    }
                else:
                    # Defaults
                    return {
                        "duration_hours": 2,
                        "cooldown_hours": 6
                    }
                    
            finally:
                db.return_connection(conn)
                
        except Exception as e:
            logger.error(f"Failed to fetch alert rules for client {client_id}: {e}")
            return {
                "duration_hours": 2,
                "cooldown_hours": 6
            }
    
    @staticmethod
    def get_config(client_id: str) -> Optional[dict]:
        """
        Get full configuration for a client
        
        Args:
            client_id: Client identifier
            
        Returns:
            dict: Full client configuration or None if not found
        """
        try:
            db = DatabaseManager(min_conn=1, max_conn=5)
            conn = db.get_connection()
            
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT client_id, location_name, barangay,
                           rain_multiplier, wind_multiplier, heat_multiplier, pressure_multiplier,
                           alert_duration_hours, cooldown_hours,
                           description, created_at, updated_at, created_by
                    FROM client_threshold_config
                    WHERE client_id = %s
                """, (client_id,))
                
                result = cursor.fetchone()
                cursor.close()
                
                if result:
                    return {
                        "client_id": result[0],
                        "location_name": result[1],
                        "barangay": result[2],
                        "rain_multiplier": float(result[3]),
                        "wind_multiplier": float(result[4]),
                        "heat_multiplier": float(result[5]),
                        "pressure_multiplier": float(result[6]),
                        "alert_duration_hours": int(result[7]),
                        "cooldown_hours": int(result[8]),
                        "description": result[9],
                        "created_at": result[10].isoformat() if result[10] else None,
                        "updated_at": result[11].isoformat() if result[11] else None,
                        "created_by": result[12]
                    }
                else:
                    return None
                    
            finally:
                db.return_connection(conn)
                
        except Exception as e:
            logger.error(f"Failed to fetch config for client {client_id}: {e}")
            return None
