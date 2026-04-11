"""
Service for managing system-wide settings, including hazard thresholds
"""
import json
import logging
from typing import Dict, Any, Optional
from app.database import get_db_cursor

logger = logging.getLogger(__name__)

class SystemSettingsService:
    """Service to handle system configuration stored in database"""
    
    _TABLE_NAME = "system_settings"
    
    @classmethod
    def initialize_table(cls):
        """Create the system_settings table if it doesn't exist"""
        try:
            with get_db_cursor() as cur:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {cls._TABLE_NAME} (
                        key VARCHAR(100) PRIMARY KEY,
                        value JSONB NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                logger.info(f"✅ Table '{cls._TABLE_NAME}' verified/created")
        except Exception as e:
            logger.error(f"Failed to initialize settings table: {e}")
            raise

    @classmethod
    def get_setting(cls, key: str, default: Any = None) -> Any:
        """Get a specific setting by key"""
        try:
            with get_db_cursor() as cur:
                cur.execute(f"SELECT value FROM {cls._TABLE_NAME} WHERE key = %s", (key,))
                result = cur.fetchone()
                if result:
                    return result['value']
                return default
        except Exception as e:
            logger.error(f"Error fetching setting '{key}': {e}")
            return default

    @classmethod
    def update_setting(cls, key: str, value: Any):
        """Update or create a setting"""
        try:
            with get_db_cursor() as cur:
                cur.execute(f"""
                    INSERT INTO {cls._TABLE_NAME} (key, value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
                """, (key, json.dumps(value)))
                logger.info(f"✅ Setting '{key}' updated")
        except Exception as e:
            logger.error(f"Error updating setting '{key}': {e}")
            raise

    @classmethod
    def get_hazard_thresholds(cls) -> Dict[str, Any]:
        """
        Get hazard thresholds from database.
        Returns default thresholds if not found in database.
        """
        from app.scripts.hazard_labeling import HazardLabeler
        
        defaults = HazardLabeler._default_thresholds()
        stored = cls.get_setting("hazard_thresholds")
        
        if stored:
            # Merge stored values with defaults to handle schema updates
            for hazard, vals in defaults.items():
                if hazard in stored:
                    defaults[hazard].update(stored[hazard])
            return defaults
        
        return defaults

    @classmethod
    def update_hazard_thresholds(cls, thresholds: Dict[str, Any]):
        """Update hazard thresholds in database"""
        return cls.update_setting("hazard_thresholds", thresholds)
