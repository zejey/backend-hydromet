"""
Hazard Labeling Module
Creates binary labels for different hazard types across multiple time horizons
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class HazardLabeler:
    """
    Generate hazard labels for multi-hazard, multi-horizon prediction
    
    Supported hazards:
    - Heat stress
    - Heavy rain
    - Thunderstorm
    - Severe storm
    
    Supported horizons: 12h, 24h, 48h
    """
    
    def __init__(self, thresholds: Optional[Dict] = None):
        """
        Initialize labeler with configurable thresholds
        
        Args:
            thresholds: Dictionary of threshold values per hazard
                If None, uses default thresholds
        """
        self.thresholds = thresholds or self._default_thresholds()
        
    @staticmethod
    def _default_thresholds() -> Dict:
        """Default thresholds for hazard detection (metric units)"""
        return {
            "heat_stress": {
                "feels_like_c": 38.0,  # Feels like temperature in Celsius
            },
            "heavy_rain": {
                "rain_1h_mm": 20.0,  # Rain accumulation in 1 hour (mm)
            },
            "thunderstorm": {
                "weather_id_range": (200, 232),  # OpenWeather thunderstorm codes
            },
            "severe_storm": {
                "pressure_hpa": 980.0,  # Atmospheric pressure (hPa)
                "wind_speed_ms": 20.0,  # Wind speed (m/s)
                "include_rain": False,  # Optional: require rain
                "rain_threshold_mm": 10.0,  # Rain threshold if include_rain=True
                "include_thunder": False,  # Optional: require thunderstorm
            }
        }
    
    def label_heat_stress(
        self, 
        df: pd.DataFrame, 
        horizon_hours: int,
        time_col: str = 'dt',
        feels_like_col: str = 'feels_like_c'
    ) -> pd.Series:
        """
        Label heat stress events for given time horizon
        
        Heat stress occurs when max(feels_like) in next H hours >= threshold
        
        Args:
            df: DataFrame with weather observations (must be sorted by time)
            horizon_hours: Time horizon in hours (12, 24, or 48)
            time_col: Name of timestamp column
            feels_like_col: Name of feels-like temperature column
            
        Returns:
            Binary series (1 = heat stress expected, 0 = no heat stress)
        """
        threshold = self.thresholds["heat_stress"]["feels_like_c"]
        
        # Ensure sorted by time
        df = df.sort_values(time_col).reset_index(drop=True)
        
        # Convert timestamp to datetime if needed
        if not pd.api.types.is_datetime64_any_dtype(df[time_col]):
            df[time_col] = pd.to_datetime(df[time_col], unit='s', errors='coerce')
        
        labels = []
        
        for idx in range(len(df)):
            current_time = df.loc[idx, time_col]
            horizon_end = current_time + pd.Timedelta(hours=horizon_hours)
            
            # Get all records within horizon window
            future_mask = (df[time_col] > current_time) & (df[time_col] <= horizon_end)
            future_data = df.loc[future_mask, feels_like_col]
            
            # Check if max feels_like exceeds threshold
            if len(future_data) > 0:
                max_feels_like = future_data.max()
                label = 1 if (max_feels_like >= threshold and not pd.isna(max_feels_like)) else 0
            else:
                # No future data available - cannot label
                label = 0
            
            labels.append(label)
        
        return pd.Series(labels, index=df.index)
    
    def label_heavy_rain(
        self,
        df: pd.DataFrame,
        horizon_hours: int,
        time_col: str = 'dt',
        rain_col: str = 'rain_1h'
    ) -> pd.Series:
        """
        Label heavy rain events for given time horizon
        
        Heavy rain occurs when max(rain_1h) in next H hours >= threshold
        
        Args:
            df: DataFrame with weather observations (must be sorted by time)
            horizon_hours: Time horizon in hours (12, 24, or 48)
            time_col: Name of timestamp column
            rain_col: Name of 1-hour rain accumulation column (mm)
            
        Returns:
            Binary series (1 = heavy rain expected, 0 = no heavy rain)
        """
        threshold = self.thresholds["heavy_rain"]["rain_1h_mm"]
        
        # Ensure sorted by time
        df = df.sort_values(time_col).reset_index(drop=True)
        
        # Convert timestamp to datetime if needed
        if not pd.api.types.is_datetime64_any_dtype(df[time_col]):
            df[time_col] = pd.to_datetime(df[time_col], unit='s', errors='coerce')
        
        # Fill missing rain values with 0 (assumption: missing = no rain)
        df[rain_col] = df[rain_col].fillna(0)
        
        labels = []
        
        for idx in range(len(df)):
            current_time = df.loc[idx, time_col]
            horizon_end = current_time + pd.Timedelta(hours=horizon_hours)
            
            # Get all records within horizon window
            future_mask = (df[time_col] > current_time) & (df[time_col] <= horizon_end)
            future_data = df.loc[future_mask, rain_col]
            
            # Check if max rain exceeds threshold
            if len(future_data) > 0:
                max_rain = future_data.max()
                label = 1 if max_rain >= threshold else 0
            else:
                label = 0
            
            labels.append(label)
        
        return pd.Series(labels, index=df.index)
    
    def label_thunderstorm(
        self,
        df: pd.DataFrame,
        horizon_hours: int,
        time_col: str = 'dt',
        weather_id_col: str = 'weather_id'
    ) -> pd.Series:
        """
        Label thunderstorm events for given time horizon
        
        Thunderstorm occurs when any weather_id in [200-232] appears in next H hours
        
        OpenWeather thunderstorm codes:
        - 200-232: Thunderstorm variants (with rain, drizzle, etc.)
        
        Args:
            df: DataFrame with weather observations (must be sorted by time)
            horizon_hours: Time horizon in hours (12, 24, or 48)
            time_col: Name of timestamp column
            weather_id_col: Name of OpenWeather condition ID column
            
        Returns:
            Binary series (1 = thunderstorm expected, 0 = no thunderstorm)
        """
        id_min, id_max = self.thresholds["thunderstorm"]["weather_id_range"]
        
        # Ensure sorted by time
        df = df.sort_values(time_col).reset_index(drop=True)
        
        # Convert timestamp to datetime if needed
        if not pd.api.types.is_datetime64_any_dtype(df[time_col]):
            df[time_col] = pd.to_datetime(df[time_col], unit='s', errors='coerce')
        
        labels = []
        
        for idx in range(len(df)):
            current_time = df.loc[idx, time_col]
            horizon_end = current_time + pd.Timedelta(hours=horizon_hours)
            
            # Get all records within horizon window
            future_mask = (df[time_col] > current_time) & (df[time_col] <= horizon_end)
            future_weather_ids = df.loc[future_mask, weather_id_col]
            
            # Check if any thunderstorm code appears
            if len(future_weather_ids) > 0:
                has_thunder = future_weather_ids.between(id_min, id_max, inclusive='both').any()
                label = 1 if has_thunder else 0
            else:
                label = 0
            
            labels.append(label)
        
        return pd.Series(labels, index=df.index)
    
    def label_severe_storm(
        self,
        df: pd.DataFrame,
        horizon_hours: int,
        time_col: str = 'dt',
        pressure_col: str = 'pressure',
        wind_speed_col: str = 'wind_speed',
        rain_col: Optional[str] = 'rain_1h',
        weather_id_col: Optional[str] = 'weather_id'
    ) -> pd.Series:
        """
        Label severe storm events for given time horizon
        
        Severe storm (proxy for cyclone influence) occurs when:
        - min(pressure) in next H hours <= pressure_threshold AND
        - max(wind_speed) in next H hours >= wind_threshold AND
        - (optional) heavy rain or thunderstorm present
        
        Args:
            df: DataFrame with weather observations (must be sorted by time)
            horizon_hours: Time horizon in hours (12, 24, or 48)
            time_col: Name of timestamp column
            pressure_col: Name of pressure column (hPa)
            wind_speed_col: Name of wind speed column (m/s)
            rain_col: Name of rain column (optional, for additional condition)
            weather_id_col: Name of weather ID column (optional, for thunder check)
            
        Returns:
            Binary series (1 = severe storm expected, 0 = no severe storm)
        """
        config = self.thresholds["severe_storm"]
        pressure_thresh = config["pressure_hpa"]
        wind_thresh = config["wind_speed_ms"]
        include_rain = config.get("include_rain", False)
        rain_thresh = config.get("rain_threshold_mm", 10.0)
        include_thunder = config.get("include_thunder", False)
        
        # Ensure sorted by time
        df = df.sort_values(time_col).reset_index(drop=True)
        
        # Convert timestamp to datetime if needed
        if not pd.api.types.is_datetime64_any_dtype(df[time_col]):
            df[time_col] = pd.to_datetime(df[time_col], unit='s', errors='coerce')
        
        labels = []
        
        for idx in range(len(df)):
            current_time = df.loc[idx, time_col]
            horizon_end = current_time + pd.Timedelta(hours=horizon_hours)
            
            # Get all records within horizon window
            future_mask = (df[time_col] > current_time) & (df[time_col] <= horizon_end)
            future_data = df.loc[future_mask]
            
            if len(future_data) == 0:
                labels.append(0)
                continue
            
            # Check pressure and wind conditions
            min_pressure = future_data[pressure_col].min()
            max_wind = future_data[wind_speed_col].max()
            
            # Core condition: low pressure + high wind
            pressure_cond = (not pd.isna(min_pressure)) and (min_pressure <= pressure_thresh)
            wind_cond = (not pd.isna(max_wind)) and (max_wind >= wind_thresh)
            
            severe_storm = pressure_cond and wind_cond
            
            # Optional: also require rain
            if severe_storm and include_rain and rain_col:
                if rain_col in future_data.columns:
                    max_rain = future_data[rain_col].fillna(0).max()
                    severe_storm = severe_storm and (max_rain >= rain_thresh)
                else:
                    severe_storm = False
            
            # Optional: also require thunderstorm
            if severe_storm and include_thunder and weather_id_col:
                if weather_id_col in future_data.columns:
                    id_min, id_max = self.thresholds["thunderstorm"]["weather_id_range"]
                    has_thunder = future_data[weather_id_col].between(id_min, id_max, inclusive='both').any()
                    severe_storm = severe_storm and has_thunder
                else:
                    severe_storm = False
            
            labels.append(1 if severe_storm else 0)
        
        return pd.Series(labels, index=df.index)
    
    def create_all_labels(
        self,
        df: pd.DataFrame,
        horizons: List[int] = [12, 24, 48],
        hazards: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Create labels for all hazards and horizons
        
        Args:
            df: DataFrame with weather observations
            horizons: List of time horizons in hours (default: [12, 24, 48])
            hazards: List of hazards to label (default: all supported hazards)
            
        Returns:
            DataFrame with original data plus label columns
            Label columns named: "{hazard}_{horizon}h" (e.g., "heat_stress_12h")
        """
        if hazards is None:
            hazards = ["heat_stress", "heavy_rain", "thunderstorm", "severe_storm"]
        
        result_df = df.copy()
        
        logger.info(f"Creating labels for {len(hazards)} hazards across {len(horizons)} horizons")
        
        for hazard in hazards:
            for horizon in horizons:
                col_name = f"{hazard}_{horizon}h"
                
                logger.info(f"  Labeling {col_name}...")
                
                try:
                    if hazard == "heat_stress":
                        result_df[col_name] = self.label_heat_stress(result_df, horizon)
                    elif hazard == "heavy_rain":
                        result_df[col_name] = self.label_heavy_rain(result_df, horizon)
                    elif hazard == "thunderstorm":
                        result_df[col_name] = self.label_thunderstorm(result_df, horizon)
                    elif hazard == "severe_storm":
                        result_df[col_name] = self.label_severe_storm(result_df, horizon)
                    else:
                        logger.warning(f"Unknown hazard type: {hazard}")
                        continue
                    
                    # Log label distribution
                    pos_count = result_df[col_name].sum()
                    total_count = len(result_df[col_name])
                    pct = 100 * pos_count / total_count if total_count > 0 else 0
                    logger.info(f"    ✓ {col_name}: {pos_count}/{total_count} positive ({pct:.1f}%)")
                    
                except Exception as e:
                    logger.error(f"    ✗ Failed to label {col_name}: {e}")
                    result_df[col_name] = 0
        
        return result_df


def get_labeler(custom_thresholds: Optional[Dict] = None) -> HazardLabeler:
    """
    Factory function to create a HazardLabeler instance
    
    Args:
        custom_thresholds: Optional custom thresholds
        
    Returns:
        Configured HazardLabeler instance
    """
    return HazardLabeler(thresholds=custom_thresholds)


if __name__ == "__main__":
    # Example usage and testing
    logging.basicConfig(level=logging.INFO)
    
    # Create sample data
    print("Creating sample weather data...")
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
    sample_data = pd.DataFrame({
        'dt': dates,
        'feels_like_c': np.random.uniform(25, 42, 100),
        'rain_1h': np.random.choice([0, 0, 0, 5, 15, 25, 35], 100),
        'pressure': np.random.uniform(970, 1020, 100),
        'wind_speed': np.random.uniform(0, 30, 100),
        'weather_id': np.random.choice([800, 801, 200, 500, 600], 100),
    })
    
    print(f"Sample data shape: {sample_data.shape}")
    print("\nFirst few rows:")
    print(sample_data.head())
    
    # Create labeler
    labeler = get_labeler()
    
    # Generate labels
    print("\n" + "="*60)
    print("Generating hazard labels...")
    print("="*60)
    
    labeled_data = labeler.create_all_labels(sample_data)
    
    print("\n" + "="*60)
    print("Label Summary:")
    print("="*60)
    
    label_cols = [col for col in labeled_data.columns if col.endswith('h')]
    for col in label_cols:
        pos = labeled_data[col].sum()
        total = len(labeled_data)
        pct = 100 * pos / total
        print(f"{col:25s}: {pos:3d}/{total:3d} ({pct:5.1f}%)")
    
    print("\nSample labeled data:")
    print(labeled_data[['dt', 'feels_like_c', 'rain_1h'] + label_cols[:4]].head(10))