"""
Threshold Loader Module
Loads and validates monthly percentile thresholds from JSON files
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


class ThresholdLoader:
    """Load and cache monthly thresholds from JSON"""
    
    _cache: Dict[str, dict] = {}
    
    @staticmethod
    def load(path: str) -> dict:
        """
        Load thresholds JSON with validation
        
        Args:
            path: Path to thresholds JSON file
            
        Returns:
            dict: Loaded and validated thresholds
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If JSON is invalid or doesn't pass validation
        """
        # Check cache first
        if path in ThresholdLoader._cache:
            return ThresholdLoader._cache[path]
        
        # Load from file
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Threshold file not found: {path}")
        
        try:
            with open(file_path, 'r') as f:
                thresholds = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in threshold file: {e}")
        
        # Validate structure
        if not ThresholdLoader.validate(thresholds):
            raise ValueError(f"Invalid threshold structure in: {path}")
        
        # Cache and return
        ThresholdLoader._cache[path] = thresholds
        return thresholds
    
    @staticmethod
    def get_for_month(thresholds: dict, month: int) -> dict:
        """
        Get thresholds for specific month
        
        Args:
            thresholds: Full thresholds dict
            month: Month number (1-12)
            
        Returns:
            dict: Monthly thresholds with keys: precipitation_mm, wind_speed_ms, temp_c, pressure_hpa
            
        Raises:
            ValueError: If month is invalid
        """
        if not 1 <= month <= 12:
            raise ValueError(f"Invalid month: {month}. Must be 1-12")
        
        monthly_thresholds = thresholds.get("monthly_thresholds", {})
        month_key = str(month)
        
        if month_key not in monthly_thresholds:
            raise ValueError(f"No thresholds found for month {month}")
        
        return monthly_thresholds[month_key]
    
    @staticmethod
    def validate(thresholds: dict) -> bool:
        """
        Validate thresholds structure
        
        Args:
            thresholds: Thresholds dict to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        # Check required top-level keys
        required_keys = ["version", "location", "monthly_thresholds"]
        if not all(key in thresholds for key in required_keys):
            return False
        
        # Check monthly_thresholds structure
        monthly = thresholds.get("monthly_thresholds", {})
        if not isinstance(monthly, dict):
            return False
        
        # Check that all 12 months are present
        for month in range(1, 13):
            month_key = str(month)
            if month_key not in monthly:
                return False
            
            month_data = monthly[month_key]
            if not isinstance(month_data, dict):
                return False
            
            # Check required weather variables
            required_vars = ["precipitation_mm", "wind_speed_ms", "temp_c", "pressure_hpa"]
            for var in required_vars:
                if var not in month_data:
                    return False
                
                # Each variable should have list of 4 percentiles
                values = month_data[var]
                if not isinstance(values, list) or len(values) != 4:
                    return False
                
                # All values should be numeric
                try:
                    [float(v) for v in values]
                except (TypeError, ValueError):
                    return False
        
        return True
    
    @staticmethod
    def clear_cache():
        """Clear the threshold cache"""
        ThresholdLoader._cache.clear()
    
    @staticmethod
    def get_metadata(thresholds: dict) -> dict:
        """
        Extract metadata from thresholds
        
        Args:
            thresholds: Thresholds dict
            
        Returns:
            dict: Metadata (version, location, data_source, etc.)
        """
        return {
            "version": thresholds.get("version"),
            "location": thresholds.get("location"),
            "lat": thresholds.get("lat"),
            "lon": thresholds.get("lon"),
            "data_source": thresholds.get("data_source"),
            "computed_at": thresholds.get("computed_at"),
            "total_samples": thresholds.get("total_samples"),
            "date_range": thresholds.get("date_range")
        }
