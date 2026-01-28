"""
Refactored hazard score logic with dynamic thresholds
Version 2 - Uses percentile-based thresholds + client multipliers
"""

import os
from datetime import datetime
from typing import Tuple, Dict, List, Optional

# Conditional imports to handle different execution contexts
try:
    from threshold_loader import ThresholdLoader
    from client_config_db import ClientConfigManager
    from logger_util import get_logger
except ImportError:
    from scripts.threshold_loader import ThresholdLoader
    from scripts.client_config_db import ClientConfigManager
    from scripts.logger_util import get_logger

logger = get_logger(__name__)


def hazard_score_v2(
    row: dict,
    thresholds_path: str,
    client_id: str = "default",
    month: int = None,
    explain: bool = False
) -> tuple:
    """
    Compute hazard score with dynamic thresholds + client multipliers.
    
    Args:
        row: Weather data dict with keys:
             - temp/temperature/temp_max (temperature in Celsius)
             - prcp/precipitation/rain (precipitation in mm)
             - wind/wind_speed/wspd (wind speed in m/s)
             - pressure/pres/main.pressure (pressure in hPa)
        thresholds_path: Path to thresholds JSON file
        client_id: Client ID to fetch multipliers from DB (default: "default")
        month: Month (1-12) for seasonal thresholds; auto-detected if None
        explain: If True, return (event, score, hazards, details)
    
    Returns:
        - If explain=False: event (0 or 1)
        - If explain=True: (event, score, hazards, details_dict)
    
    Example:
        >>> event, score, hazards, details = hazard_score_v2(
        ...     row={"temp": 36.5, "prcp": 45.2, "wind": 8.3, "pressure": 1003.1},
        ...     thresholds_path="thresholds/sanpedro_monthly_v1.json",
        ...     client_id="san_pedro_zone_a",
        ...     month=8,
        ...     explain=True
        ... )
    """
    
    # Load thresholds
    try:
        thresholds = ThresholdLoader.load(thresholds_path)
    except Exception as e:
        logger.error(f"Failed to load thresholds from {thresholds_path}: {e}")
        raise
    
    # Determine month
    if month is None:
        # Try to extract from row timestamp
        if "timestamp" in row:
            try:
                if isinstance(row["timestamp"], str):
                    from datetime import datetime
                    dt = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                    month = dt.month
                elif hasattr(row["timestamp"], "month"):
                    month = row["timestamp"].month
                else:
                    month = datetime.now().month
            except:
                month = datetime.now().month
        else:
            month = datetime.now().month
    
    # Get monthly thresholds
    try:
        monthly_thresh = ThresholdLoader.get_for_month(thresholds, month)
    except Exception as e:
        logger.error(f"Failed to get thresholds for month {month}: {e}")
        raise
    
    # Get client multipliers
    try:
        multipliers = ClientConfigManager.get_multipliers(client_id)
    except Exception as e:
        logger.warning(f"Failed to get multipliers for client {client_id}, using baseline: {e}")
        multipliers = {"rain": 1.0, "wind": 1.0, "heat": 1.0, "pressure": 1.0}
    
    # Apply multipliers to thresholds
    rain_thresh = [t * multipliers["rain"] for t in monthly_thresh["precipitation_mm"]]
    wind_thresh = [t * multipliers["wind"] for t in monthly_thresh["wind_speed_ms"]]
    heat_thresh = [t * multipliers["heat"] for t in monthly_thresh["temp_c"]]
    pressure_thresh = [t * multipliers["pressure"] for t in monthly_thresh["pressure_hpa"]]
    
    # Extract weather values from row (support multiple formats)
    prcp = _extract_value(row, ["precipitation", "prcp", "rain"])
    if isinstance(prcp, dict):  # OpenWeather format: {"1h": 5.2}
        prcp = prcp.get("1h", 0) or 0
    prcp = float(prcp or 0)
    
    wind = _extract_value(row, ["wind_speed", "wind", "wspd"])
    if isinstance(wind, dict):  # OpenWeather format: {"speed": 8.5}
        wind = wind.get("speed", 0) or 0
    wind = float(wind or 0)
    
    temp = _extract_value(row, ["temp_max", "temp", "temperature", "tmax"])
    if isinstance(temp, dict):  # OpenWeather format: {"temp": 30.5}
        temp = temp.get("temp", 0) or 0
    temp = float(temp or 0)
    
    pressure = _extract_value(row, ["pressure", "pres"])
    if isinstance(pressure, dict):  # OpenWeather format: {"pressure": 1013}
        pressure = pressure.get("pressure", 1013) or 1013
    try:
        pressure = float(pressure or 1013)
    except:
        pressure = 1013
    
    # Calculate score and hazards
    score = 0.0
    hazards = []
    details = {}
    
    # Precipitation scoring
    if prcp >= rain_thresh[3]:  # 99th percentile
        score += 4
        hazards.append("extreme rain")
        details["rain"] = {
            "value": prcp,
            "threshold_crossed": f"99th percentile ({monthly_thresh['precipitation_mm'][3]:.1f}mm)",
            "adjusted_threshold": round(rain_thresh[3], 1)
        }
    elif prcp >= rain_thresh[2]:  # 95th percentile
        score += 3
        hazards.append("heavy rain")
        details["rain"] = {
            "value": prcp,
            "threshold_crossed": f"95th percentile ({monthly_thresh['precipitation_mm'][2]:.1f}mm)",
            "adjusted_threshold": round(rain_thresh[2], 1)
        }
    elif prcp >= rain_thresh[1]:  # 90th percentile
        score += 2
        hazards.append("moderate rain")
        details["rain"] = {
            "value": prcp,
            "threshold_crossed": f"90th percentile ({monthly_thresh['precipitation_mm'][1]:.1f}mm)",
            "adjusted_threshold": round(rain_thresh[1], 1)
        }
    elif prcp >= rain_thresh[0]:  # 75th percentile
        score += 1
        hazards.append("light rain")
        details["rain"] = {
            "value": prcp,
            "threshold_crossed": f"75th percentile ({monthly_thresh['precipitation_mm'][0]:.1f}mm)",
            "adjusted_threshold": round(rain_thresh[0], 1)
        }
    
    # Wind scoring
    if wind >= wind_thresh[3]:  # 99th percentile
        score += 3
        hazards.append("extreme wind")
        details["wind"] = {
            "value": wind,
            "threshold_crossed": f"99th percentile ({monthly_thresh['wind_speed_ms'][3]:.1f}m/s)",
            "adjusted_threshold": round(wind_thresh[3], 1)
        }
    elif wind >= wind_thresh[2]:  # 95th percentile
        score += 2.5
        hazards.append("very strong wind")
        details["wind"] = {
            "value": wind,
            "threshold_crossed": f"95th percentile ({monthly_thresh['wind_speed_ms'][2]:.1f}m/s)",
            "adjusted_threshold": round(wind_thresh[2], 1)
        }
    elif wind >= wind_thresh[1]:  # 90th percentile
        score += 1.5
        hazards.append("strong wind")
        details["wind"] = {
            "value": wind,
            "threshold_crossed": f"90th percentile ({monthly_thresh['wind_speed_ms'][1]:.1f}m/s)",
            "adjusted_threshold": round(wind_thresh[1], 1)
        }
    elif wind >= wind_thresh[0]:  # 75th percentile
        score += 1
        hazards.append("moderate wind")
        details["wind"] = {
            "value": wind,
            "threshold_crossed": f"75th percentile ({monthly_thresh['wind_speed_ms'][0]:.1f}m/s)",
            "adjusted_threshold": round(wind_thresh[0], 1)
        }
    
    # Heat scoring
    if temp >= heat_thresh[3]:  # 99th percentile
        score += 3
        hazards.append("extreme heat")
        details["heat"] = {
            "value": temp,
            "threshold_crossed": f"99th percentile ({monthly_thresh['temp_c'][3]:.1f}°C)",
            "adjusted_threshold": round(heat_thresh[3], 1)
        }
    elif temp >= heat_thresh[2]:  # 95th percentile
        score += 2.5
        hazards.append("very extreme heat")
        details["heat"] = {
            "value": temp,
            "threshold_crossed": f"95th percentile ({monthly_thresh['temp_c'][2]:.1f}°C)",
            "adjusted_threshold": round(heat_thresh[2], 1)
        }
    elif temp >= heat_thresh[1]:  # 90th percentile
        score += 1.5
        hazards.append("very hot")
        details["heat"] = {
            "value": temp,
            "threshold_crossed": f"90th percentile ({monthly_thresh['temp_c'][1]:.1f}°C)",
            "adjusted_threshold": round(heat_thresh[1], 1)
        }
    elif temp >= heat_thresh[0]:  # 75th percentile
        score += 1
        hazards.append("hot")
        details["heat"] = {
            "value": temp,
            "threshold_crossed": f"75th percentile ({monthly_thresh['temp_c'][0]:.1f}°C)",
            "adjusted_threshold": round(heat_thresh[0], 1)
        }
    
    # Pressure scoring (inverted - LOW pressure is hazardous)
    if pressure < pressure_thresh[3]:  # 1st percentile (very low)
        score += 3
        hazards.append("cyclone pressure")
        details["pressure"] = {
            "value": pressure,
            "threshold_crossed": f"1st percentile ({monthly_thresh['pressure_hpa'][3]:.1f}hPa)",
            "adjusted_threshold": round(pressure_thresh[3], 1)
        }
    elif pressure < pressure_thresh[2]:  # 5th percentile
        score += 2.5
        hazards.append("very low pressure")
        details["pressure"] = {
            "value": pressure,
            "threshold_crossed": f"5th percentile ({monthly_thresh['pressure_hpa'][2]:.1f}hPa)",
            "adjusted_threshold": round(pressure_thresh[2], 1)
        }
    elif pressure < pressure_thresh[1]:  # 10th percentile
        score += 1.5
        hazards.append("low pressure")
        details["pressure"] = {
            "value": pressure,
            "threshold_crossed": f"10th percentile ({monthly_thresh['pressure_hpa'][1]:.1f}hPa)",
            "adjusted_threshold": round(pressure_thresh[1], 1)
        }
    elif pressure < pressure_thresh[0]:  # 25th percentile
        score += 1
        hazards.append("moderate low pressure")
        details["pressure"] = {
            "value": pressure,
            "threshold_crossed": f"25th percentile ({monthly_thresh['pressure_hpa'][0]:.1f}hPa)",
            "adjusted_threshold": round(pressure_thresh[0], 1)
        }
    
    # Combination bonus (storm detection)
    if prcp >= rain_thresh[1] and wind >= wind_thresh[1]:
        score += 1
        hazards.append("rain + wind (possible storm)")
    
    # Determine event
    event = int(score >= 2.0)
    
    if explain:
        # Add metadata
        season = "wet season" if 5 <= month <= 10 else "dry season"
        details["thresholds_used"] = f"Month {month} ({season})"
        details["client_multipliers"] = multipliers
        details["score"] = round(score, 1)
        
        return event, score, hazards, details
    else:
        return event


def _extract_value(row: dict, keys: List[str]) -> any:
    """
    Extract value from row using list of possible keys
    Handles nested dicts (e.g., row["main"]["pressure"])
    """
    for key in keys:
        if key in row:
            return row[key]
        
        # Check nested paths (e.g., "main.pressure")
        if "." in key:
            parts = key.split(".")
            val = row
            for part in parts:
                if isinstance(val, dict) and part in val:
                    val = val[part]
                else:
                    val = None
                    break
            if val is not None:
                return val
    
    # Check common nested structures
    if "main" in row and isinstance(row["main"], dict):
        for key in keys:
            if key in row["main"]:
                return row["main"][key]
    
    return None
