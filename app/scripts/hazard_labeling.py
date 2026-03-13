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
                "rain_1h_mm": 10.0,  # Rain accumulation in 1 hour (mm)
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
        
        # Sort by time, preserving original index
        df_sorted = df.sort_values(time_col).copy()
        
        # Convert timestamp to datetime if needed
        if not pd.api.types.is_datetime64_any_dtype(df_sorted[time_col]):
            df_sorted[time_col] = pd.to_datetime(df_sorted[time_col], unit='s', errors='coerce')
        
        # Detect data frequency to compute rolling window size in rows
        time_diffs = df_sorted[time_col].diff().dropna()
        if len(time_diffs) > 0:
            median_interval = time_diffs.median()
            if hasattr(median_interval, 'total_seconds'):
                median_interval_hours = median_interval.total_seconds() / 3600
            else:
                median_interval_hours = float(median_interval) / 3600
            window_rows = max(1, round(horizon_hours / median_interval_hours))
        else:
            window_rows = horizon_hours
        
        feels = df_sorted[feels_like_col].fillna(0)
        
        # Reverse rolling to look FORWARD: reverse series, roll backward, reverse back.
        # shift(-1) excludes the current row so the window covers strictly future rows.
        labels = (
            feels[::-1]
            .rolling(window=window_rows, min_periods=1)
            .max()[::-1]
            .shift(-1)
            >= threshold
        ).fillna(False).astype(int)
        
        # Map results back to the original DataFrame index
        result = pd.Series(0, index=df.index)
        result.loc[df_sorted.index] = labels.values
        return result
    
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
        
        # Sort by time, preserving original index
        df_sorted = df.sort_values(time_col).copy()
        
        # Convert timestamp to datetime if needed
        if not pd.api.types.is_datetime64_any_dtype(df_sorted[time_col]):
            df_sorted[time_col] = pd.to_datetime(df_sorted[time_col], unit='s', errors='coerce')
        
        # Detect data frequency to compute rolling window size in rows
        time_diffs = df_sorted[time_col].diff().dropna()
        if len(time_diffs) > 0:
            median_interval = time_diffs.median()
            if hasattr(median_interval, 'total_seconds'):
                median_interval_hours = median_interval.total_seconds() / 3600
            else:
                median_interval_hours = float(median_interval) / 3600
            window_rows = max(1, round(horizon_hours / median_interval_hours))
        else:
            window_rows = horizon_hours
        
        # Fill missing rain values with 0 (assumption: missing = no rain)
        rain = df_sorted[rain_col].fillna(0)
        
        # Reverse rolling to look FORWARD; shift(-1) excludes the current row.
        labels = (
            rain[::-1]
            .rolling(window=window_rows, min_periods=1)
            .max()[::-1]
            .shift(-1)
            >= threshold
        ).fillna(False).astype(int)
        
        # Map results back to the original DataFrame index
        result = pd.Series(0, index=df.index)
        result.loc[df_sorted.index] = labels.values
        return result
    
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
        
        # Sort by time, preserving original index
        df_sorted = df.sort_values(time_col).copy()
        
        # Convert timestamp to datetime if needed
        if not pd.api.types.is_datetime64_any_dtype(df_sorted[time_col]):
            df_sorted[time_col] = pd.to_datetime(df_sorted[time_col], unit='s', errors='coerce')
        
        # Detect data frequency to compute rolling window size in rows
        time_diffs = df_sorted[time_col].diff().dropna()
        if len(time_diffs) > 0:
            median_interval = time_diffs.median()
            if hasattr(median_interval, 'total_seconds'):
                median_interval_hours = median_interval.total_seconds() / 3600
            else:
                median_interval_hours = float(median_interval) / 3600
            window_rows = max(1, round(horizon_hours / median_interval_hours))
        else:
            window_rows = horizon_hours
        
        # Binary indicator: 1 if weather_id is in thunderstorm range
        is_thunder = df_sorted[weather_id_col].between(id_min, id_max, inclusive='both').astype(int)
        
        # Reverse rolling max: any 1 in the forward window means thunderstorm present.
        # shift(-1) excludes the current row so the window covers strictly future rows.
        labels = (
            is_thunder[::-1]
            .rolling(window=window_rows, min_periods=1)
            .max()[::-1]
            .shift(-1)
            >= 1
        ).fillna(False).astype(int)
        
        # Map results back to the original DataFrame index
        result = pd.Series(0, index=df.index)
        result.loc[df_sorted.index] = labels.values
        return result
    
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
        
        # Sort by time, preserving original index
        df_sorted = df.sort_values(time_col).copy()
        
        # Convert timestamp to datetime if needed
        if not pd.api.types.is_datetime64_any_dtype(df_sorted[time_col]):
            df_sorted[time_col] = pd.to_datetime(df_sorted[time_col], unit='s', errors='coerce')
        
        # Detect data frequency to compute rolling window size in rows
        time_diffs = df_sorted[time_col].diff().dropna()
        if len(time_diffs) > 0:
            median_interval = time_diffs.median()
            if hasattr(median_interval, 'total_seconds'):
                median_interval_hours = median_interval.total_seconds() / 3600
            else:
                median_interval_hours = float(median_interval) / 3600
            window_rows = max(1, round(horizon_hours / median_interval_hours))
        else:
            window_rows = horizon_hours
        
        # Reverse rolling to look FORWARD; shift(-1) excludes the current row.
        min_pressure = (
            df_sorted[pressure_col][::-1]
            .rolling(window=window_rows, min_periods=1)
            .min()[::-1]
            .shift(-1)
        )
        max_wind = (
            df_sorted[wind_speed_col][::-1]
            .rolling(window=window_rows, min_periods=1)
            .max()[::-1]
            .shift(-1)
        )
        
        # Core condition: low pressure AND high wind
        storm_mask = (min_pressure <= pressure_thresh) & (max_wind >= wind_thresh)
        
        # Optional: also require heavy rain
        if include_rain and rain_col and rain_col in df_sorted.columns:
            rain_series = df_sorted[rain_col].fillna(0)
            max_rain = (
                rain_series[::-1]
                .rolling(window=window_rows, min_periods=1)
                .max()[::-1]
                .shift(-1)
            )
            storm_mask = storm_mask & (max_rain >= rain_thresh)
        
        # Optional: also require thunderstorm
        if include_thunder and weather_id_col and weather_id_col in df_sorted.columns:
            id_min, id_max = self.thresholds["thunderstorm"]["weather_id_range"]
            is_thunder = df_sorted[weather_id_col].between(id_min, id_max, inclusive='both').astype(int)
            max_thunder = (
                is_thunder[::-1]
                .rolling(window=window_rows, min_periods=1)
                .max()[::-1]
                .shift(-1)
            )
            storm_mask = storm_mask & (max_thunder >= 1)
        
        labels = storm_mask.fillna(False).astype(int)
        
        # Map results back to the original DataFrame index
        result = pd.Series(0, index=df.index)
        result.loc[df_sorted.index] = labels.values
        return result
    
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
        logger.info(f"Using vectorized labeling (O(n) vs O(n²) — ~{len(df)**2 // 1_000_000}M ops saved)")
        
        # Sanity check: log raw event counts so users can understand why labels may be sparse
        logger.info("\n--- Raw event counts (sanity check) ---")
        if 'weather_id' in result_df.columns:
            thunder_count = result_df['weather_id'].between(200, 232, inclusive='both').sum()
            logger.info(f"  thunderstorm rows (weather_id 200-232): {thunder_count}")
        if 'rain_1h' in result_df.columns:
            heavy_rain_threshold = self.thresholds["heavy_rain"]["rain_1h_mm"]
            heavy_rain_count = (result_df['rain_1h'] >= heavy_rain_threshold).sum()
            logger.info(f"  rain_1h >= {heavy_rain_threshold}: {heavy_rain_count} rows, max={result_df['rain_1h'].max():.2f}")
        feels_like_col = 'feels_like_c'
        if feels_like_col in result_df.columns:
            heat_threshold = self.thresholds["heat_stress"]["feels_like_c"]
            heat_count = (result_df[feels_like_col] >= heat_threshold).sum()
            logger.info(f"  {feels_like_col} >= {heat_threshold}: {heat_count} rows")
        if 'pressure' in result_df.columns and 'wind_speed' in result_df.columns:
            p_thresh = self.thresholds["severe_storm"]["pressure_hpa"]
            w_thresh = self.thresholds["severe_storm"]["wind_speed_ms"]
            storm_count = ((result_df['pressure'] <= p_thresh) & (result_df['wind_speed'] >= w_thresh)).sum()
            logger.info(f"  severe_storm rows (pressure<={p_thresh} AND wind>={w_thresh}): {storm_count}")
        logger.info("--- End sanity check ---\n")
        
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
                    
                    # Log label distribution including NaN count
                    nan_count = result_df[col_name].isna().sum()
                    pos_count = result_df[col_name].sum()
                    total_count = len(result_df[col_name])
                    pct = 100 * pos_count / total_count if total_count > 0 else 0
                    
                    # Skip severe_storm columns that have no positive examples
                    if pos_count == 0:
                        logger.warning(f"    ⚠️ {col_name}: 0 positive labels — dropping (model cannot train on this)")
                        result_df.drop(columns=[col_name], inplace=True)
                        continue
                    
                    nan_count = result_df[col_name].isna().sum()
                    pct = 100 * pos_count / total_count
                    logger.info(f"    ✓ {col_name}: {pos_count}/{total_count} positive ({pct:.1f}%), NaNs: {nan_count}")

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