"""
Extended Feature Engineering for Multi-Hazard Prediction
Adds lag, delta, and rolling features while maintaining compatibility with existing code
"""

import pandas as pd
import numpy as np
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


def engineer_extended_features(
    df: pd.DataFrame,
    lag_hours: Optional[List[int]] = None,
    rolling_hours: Optional[List[int]] = None,
    add_deltas: bool = True,
    time_col: str = 'timestamp'
) -> pd.DataFrame:
    """
    Add extended features for multi-hazard prediction
    
    Features added:
    - Lag features: Previous values at t-3h, t-6h
    - Delta features: Rate of change (current - previous)
    - Rolling features: Moving averages over 3h, 6h, 12h windows
    
    Args:
        df: DataFrame with base weather features (must be sorted by time)
        lag_hours: List of lag periods in hours (default: [3, 6])
        rolling_hours: List of rolling window sizes in hours (default: [3, 6, 12])
        add_deltas: Whether to add rate-of-change features
        time_col: Name of timestamp column
        
    Returns:
        DataFrame with added features
    """
    if lag_hours is None:
        lag_hours = [3, 6]
    
    if rolling_hours is None:
        rolling_hours = [3, 6, 12]
    
    df = df.copy()
    
    # Ensure sorted by time
    if time_col in df.columns:
        df = df.sort_values(time_col).reset_index(drop=True)
    
    # Define key features to engineer
    key_features = [
        'temp', 'temperature', 'feels_like', 'feels_like_c',
        'pressure', 'humidity', 'wind_speed', 
        'rain_1h', 'dew_point'
    ]
    
    # Filter to only features present in dataframe
    available_features = [f for f in key_features if f in df.columns]
    
    logger.info(f"Engineering extended features for {len(available_features)} variables")
    
    # ===== LAG FEATURES =====
    for lag_h in lag_hours:
        logger.debug(f"  Adding {lag_h}h lag features...")
        
        for feat in available_features:
            lag_col = f"{feat}_lag{lag_h}h"
            df[lag_col] = df[feat].shift(lag_h)
            
            # Fill initial NaN values with current value (reasonable for short lags)
            df[lag_col] = df[lag_col].fillna(df[feat])
    
    # ===== DELTA FEATURES (Rate of Change) =====
    if add_deltas:
        logger.debug(f"  Adding delta (rate of change) features...")
        
        # Use shortest lag for delta calculation
        delta_lag = min(lag_hours) if lag_hours else 1
        
        for feat in available_features:
            delta_col = f"{feat}_delta{delta_lag}h"
            
            # Calculate change over delta_lag periods
            df[delta_col] = df[feat] - df[feat].shift(delta_lag)
            
            # Fill NaN with 0 (no change for first records)
            df[delta_col] = df[delta_col].fillna(0)
    
    # ===== ROLLING FEATURES (Moving Averages) =====
    for roll_h in rolling_hours:
        logger.debug(f"  Adding {roll_h}h rolling average features...")
        
        for feat in available_features:
            roll_col = f"{feat}_roll{roll_h}h"
            
            # Calculate rolling mean
            df[roll_col] = df[feat].rolling(window=roll_h, min_periods=1).mean()
    
    logger.info(f"✓ Extended features added. New shape: {df.shape}")
    
    return df


def engineer_multi_hazard_features(
    df: pd.DataFrame,
    include_extended: bool = True,
    time_col: str = 'timestamp'
) -> pd.DataFrame:
    """
    Full feature engineering pipeline for multi-hazard prediction
    
    Combines base feature engineering (from model.py) with extended features
    
    Args:
        df: Raw weather DataFrame
        include_extended: Whether to include lag/delta/rolling features
        time_col: Name of timestamp column
        
    Returns:
        DataFrame with all engineered features
    """
    try:
        from model import engineer_features as base_engineer_features
        
        logger.info("Starting multi-hazard feature engineering pipeline")
        logger.info(f"Input shape: {df.shape}")
        
        # Step 1: Base feature engineering (from existing model.py)
        logger.info("[1/2] Applying base feature engineering...")
        df = base_engineer_features(df)
        
        # Step 2: Extended features for multi-hazard
        if include_extended:
            logger.info("[2/2] Adding extended lag/delta/rolling features...")
            df = engineer_extended_features(df, time_col=time_col)
        
        logger.info(f"✓ Feature engineering complete. Final shape: {df.shape}")
        
        return df
    except Exception as e:
        logger.warning(f"Base feature engineering failed: {e}. Using simplified pipeline.")
        
        # Fallback: just do extended features
        if include_extended:
            logger.info("Applying extended features only...")
            df = engineer_extended_features(df, time_col=time_col)
        
        return df


def get_feature_columns_for_hazard(
    df: pd.DataFrame,
    hazard_type: str,
    exclude_cols: Optional[List[str]] = None
) -> List[str]:
    """
    Get relevant feature columns for specific hazard type
    
    Different hazards may benefit from different feature sets:
    - Heat stress: temperature, humidity, solar features
    - Heavy rain: precipitation, humidity, pressure
    - Thunderstorm: pressure, humidity, temperature gradients
    - Severe storm: pressure, wind, precipitation combo
    
    Args:
        df: DataFrame with engineered features
        hazard_type: Type of hazard ('heat_stress', 'heavy_rain', etc.)
        exclude_cols: Additional columns to exclude
        
    Returns:
        List of feature column names
    """
    if exclude_cols is None:
        exclude_cols = []
    
    # Default exclusions (labels, timestamps, identifiers)
    default_exclude = {
        'event', 'hazard_level', 'label', 'timestamp', 'date', 'dt',
        'weather_id',  # May be too specific for general prediction
    }
    
    # Also exclude label columns for other hazards/horizons
    label_pattern_exclude = [
        col for col in df.columns 
        if any(col.startswith(h) for h in ['heat_stress_', 'heavy_rain_', 'thunderstorm_', 'severe_storm_'])
    ]
    
    all_exclude = default_exclude.union(set(exclude_cols)).union(set(label_pattern_exclude))
    
    # Get all numeric columns
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    
    # Filter out excluded columns
    feature_cols = [col for col in numeric_cols if col not in all_exclude]
    
    # Hazard-specific feature selection (optional refinement)
    # For now, use all available features for maximum information
    # Future: could implement feature selection per hazard type
    
    logger.debug(f"Selected {len(feature_cols)} features for {hazard_type}")
    
    return feature_cols


def extract_features_from_openweather_forecast(
    forecast_data: dict,
    include_extended: bool = False
) -> pd.DataFrame:
    """
    Extract features from OpenWeather forecast API response
    Compatible with both current weather and forecast formats
    
    Args:
        forecast_data: OpenWeather API response (single point or list)
        include_extended: Whether to compute extended features (requires history)
        
    Returns:
        DataFrame with extracted and engineered features
    """
    # Handle both single dict and list of dicts
    if isinstance(forecast_data, dict):
        if 'list' in forecast_data:
            # 5-day forecast format: {"list": [...]}
            data_points = forecast_data['list']
        else:
            # Single current weather format
            data_points = [forecast_data]
    elif isinstance(forecast_data, list):
        data_points = forecast_data
    else:
        raise ValueError(f"Unexpected forecast_data type: {type(forecast_data)}")
    
    # Extract features from each data point
    records = []
    
    for point in data_points:
        # Extract timestamp
        dt = point.get('dt', 0)
        timestamp = pd.to_datetime(dt, unit='s') if dt else pd.Timestamp.now()
        
        # Main weather data
        main = point.get('main', {})
        wind = point.get('wind', {})
        rain = point.get('rain', {})
        snow = point.get('snow', {})
        clouds = point.get('clouds', {})
        
        # Weather condition
        weather_list = point.get('weather', [])
        weather_id = weather_list[0].get('id', 800) if weather_list else 800
        
        # Build feature dict (metric units - Celsius, hPa, m/s, mm)
        features = {
            'timestamp': timestamp,
            'dt': dt,
            'temp': main.get('temp', 20),
            'temperature': main.get('temp', 20),
            'feels_like': main.get('feels_like', 20),
            'feels_like_c': main.get('feels_like', 20),
            'temp_min': main.get('temp_min', main.get('temp', 20)),
            'temp_max': main.get('temp_max', main.get('temp', 20)),
            'pressure': main.get('pressure', 1013),
            'humidity': main.get('humidity', 60),
            'wind_speed': wind.get('speed', 0),
            'wind_deg': wind.get('deg', 0),
            'wind_gust': wind.get('gust', wind.get('speed', 0)),
            'clouds_all': clouds.get('all', 0),
            'rain_1h': rain.get('1h', 0),
            'rain_3h': rain.get('3h', 0),
            'snow_1h': snow.get('1h', 0),
            'snow_3h': snow.get('3h', 0),
            'visibility': point.get('visibility', 10000),
            'weather_id': weather_id,
        }
        
        # Add dew point if available
        if 'dew_point' in main:
            features['dew_point'] = main['dew_point']
        
        records.append(features)
    
    # Convert to DataFrame
    df = pd.DataFrame(records)
    
    # Apply base feature engineering
    df = engineer_multi_hazard_features(df, include_extended=include_extended)
    
    return df


if __name__ == "__main__":
    # Testing
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "="*60)
    print("EXTENDED FEATURE ENGINEERING - TESTING")
    print("="*60)
    
    # Create sample weather data
    print("\nCreating sample weather data...")
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
    
    sample_data = pd.DataFrame({
        'timestamp': dates,
        'temp': np.random.uniform(20, 35, 100),
        'temperature': np.random.uniform(20, 35, 100),
        'feels_like_c': np.random.uniform(22, 40, 100),
        'pressure': np.random.uniform(990, 1020, 100),
        'humidity': np.random.uniform(40, 90, 100),
        'wind_speed': np.random.uniform(0, 25, 100),
        'rain_1h': np.random.choice([0, 0, 0, 5, 15, 25], 100),
        'dew_point': np.random.uniform(15, 25, 100),
    })
    
    print(f"Sample data shape: {sample_data.shape}")
    print(f"Columns: {list(sample_data.columns)}")
    
    # Test extended feature engineering
    print("\n" + "="*60)
    print("Testing extended feature engineering...")
    print("="*60)
    
    extended_data = engineer_extended_features(
        sample_data,
        lag_hours=[3, 6],
        rolling_hours=[3, 6, 12],
        add_deltas=True
    )
    
    print(f"\nExtended data shape: {extended_data.shape}")
    print(f"New columns added: {extended_data.shape[1] - sample_data.shape[1]}")
    
    # Show sample of new features
    new_cols = [col for col in extended_data.columns if col not in sample_data.columns]
    print(f"\nNew feature columns ({len(new_cols)}):")
    for col in sorted(new_cols)[:20]:
        print(f"  - {col}")
    if len(new_cols) > 20:
        print(f"  ... and {len(new_cols) - 20} more")
    
    print("\n" + "="*60)
    print("Sample data with extended features:")
    print("="*60)
    display_cols = ['timestamp', 'temp', 'temp_lag3h', 'temp_delta3h', 'temp_roll3h']
    display_cols = [c for c in display_cols if c in extended_data.columns]
    print(extended_data[display_cols].head(10))
    
    # Test OpenWeather format extraction
    print("\n" + "="*60)
    print("Testing OpenWeather forecast extraction...")
    print("="*60)
    
    # Simulate OpenWeather forecast response
    mock_forecast = {
        'list': [
            {
                'dt': int(dates[i].timestamp()),
                'main': {
                    'temp': 25 + i * 0.1,
                    'feels_like': 27 + i * 0.1,
                    'pressure': 1010,
                    'humidity': 70,
                },
                'wind': {'speed': 5, 'deg': 180},
                'rain': {'1h': 0},
                'clouds': {'all': 50},
                'weather': [{'id': 800, 'main': 'Clear'}]
            }
            for i in range(10)
        ]
    }
    
    forecast_df = extract_features_from_openweather_forecast(mock_forecast, include_extended=False)
    
    print(f"\nForecast DataFrame shape: {forecast_df.shape}")
    print(f"Columns: {len(forecast_df.columns)}")
    print("\nFirst few rows:")
    print(forecast_df[['timestamp', 'temp', 'pressure', 'humidity', 'wind_speed']].head())
    
    print("\n✅ Extended feature engineering tests completed successfully!")
