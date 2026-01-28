"""
Calculate percentile-based thresholds from OpenWeather historical data
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime
from pathlib import Path
import argparse


def calculate_thresholds(
    df: pd.DataFrame,
    percentiles=[75, 90, 95, 99],
    filter_hazard_days=False
) -> dict:
    """
    Calculate monthly percentile thresholds from weather data
    
    Args:
        df: DataFrame with columns: timestamp, temp, precipitation, wind_speed, pressure
        percentiles: List of percentiles to calculate (default: [75, 90, 95, 99])
        filter_hazard_days: If True, exclude known hazard days (requires 'is_hazard' column)
        
    Returns:
        dict: Monthly thresholds for each weather variable
    """
    # Ensure we have a timestamp column
    if "timestamp" not in df.columns and "dt" in df.columns:
        df["timestamp"] = pd.to_datetime(df["dt"], unit="s")
    elif "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    # Extract month
    df["month"] = df["timestamp"].dt.month
    
    # Filter out hazard days if requested
    if filter_hazard_days and "is_hazard" in df.columns:
        original_len = len(df)
        df = df[df["is_hazard"] == False].copy()
        filtered_count = original_len - len(df)
        print(f"   Filtered {filtered_count} hazard days")
        
        if len(df) == 0:
            raise ValueError("All data was filtered out as hazard days. Cannot compute thresholds from empty dataset.")
    
    # Map column names (support various formats)
    col_map = {
        "temp": ["temp", "temperature", "temp_max", "tmax"],
        "precipitation": ["precipitation", "prcp", "rain"],
        "wind_speed": ["wind_speed", "wspd", "wind"],
        "pressure": ["pressure", "pres"]
    }
    
    # Standardize column names
    for target_col, possible_names in col_map.items():
        for name in possible_names:
            if name in df.columns:
                df[target_col] = df[name]
                break
    
    # Check we have required columns
    required = ["temp", "precipitation", "wind_speed", "pressure"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Calculate thresholds for each month
    monthly_thresholds = {}
    
    for month in range(1, 13):
        month_data = df[df["month"] == month]
        
        if len(month_data) == 0:
            print(f"   Warning: No data for month {month}, using default values")
            monthly_thresholds[str(month)] = {
                "precipitation_mm": [20, 50, 100, 150],
                "wind_speed_ms": [15, 20, 25, 30],
                "temp_c": [35, 38, 40, 42],
                "pressure_hpa": [975, 960, 940, 910]
            }
            continue
        
        # Calculate percentiles
        rain_thresholds = np.percentile(month_data["precipitation"], percentiles).tolist()
        wind_thresholds = np.percentile(month_data["wind_speed"], percentiles).tolist()
        temp_thresholds = np.percentile(month_data["temp"], percentiles).tolist()
        
        # For pressure, we want LOW pressure thresholds (inverted)
        # So we calculate the lower percentiles (25, 10, 5, 1)
        pressure_lower_percentiles = [100 - p for p in percentiles]
        pressure_thresholds = np.percentile(month_data["pressure"], pressure_lower_percentiles).tolist()
        
        monthly_thresholds[str(month)] = {
            "precipitation_mm": [round(x, 1) for x in rain_thresholds],
            "wind_speed_ms": [round(x, 1) for x in wind_thresholds],
            "temp_c": [round(x, 1) for x in temp_thresholds],
            "pressure_hpa": [round(x, 1) for x in pressure_thresholds]
        }
    
    return monthly_thresholds


def main():
    parser = argparse.ArgumentParser(
        description="Calculate percentile-based thresholds from OpenWeather historical data"
    )
    parser.add_argument("--csv", required=True, help="Input CSV file with historical weather data")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--location", default="San Pedro, Laguna", help="Location name")
    parser.add_argument("--lat", type=float, default=14.3644, help="Latitude")
    parser.add_argument("--lon", type=float, default=121.0619, help="Longitude")
    parser.add_argument("--data-source", default="OpenWeather History", help="Data source description")
    parser.add_argument("--percentiles", default="75,90,95,99", help="Comma-separated percentiles (default: 75,90,95,99)")
    parser.add_argument("--filter-hazards", action="store_true", help="Filter out known hazard days")
    
    args = parser.parse_args()
    
    # Parse percentiles
    percentiles = [int(p) for p in args.percentiles.split(",")]
    
    print(f"📊 Loading data from {args.csv}...")
    df = pd.read_csv(args.csv)
    print(f"   Loaded {len(df)} records")
    
    # Get date range
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        date_min = df["timestamp"].min()
        date_max = df["timestamp"].max()
    elif "dt" in df.columns:
        df["timestamp"] = pd.to_datetime(df["dt"], unit="s")
        date_min = df["timestamp"].min()
        date_max = df["timestamp"].max()
    else:
        date_min = datetime(2024, 1, 1)
        date_max = datetime(2024, 12, 31)
    
    print(f"   Date range: {date_min} to {date_max}")
    
    print(f"🔧 Calculating thresholds (percentiles: {percentiles})...")
    monthly_thresholds = calculate_thresholds(
        df,
        percentiles=percentiles,
        filter_hazard_days=args.filter_hazards
    )
    
    # Build output structure
    output = {
        "version": "1.0",
        "location": args.location,
        "lat": args.lat,
        "lon": args.lon,
        "data_source": args.data_source,
        "computed_at": datetime.now().isoformat(),
        "total_samples": len(df),
        "date_range": {
            "start": date_min.strftime("%Y-%m-%d"),
            "end": date_max.strftime("%Y-%m-%d")
        },
        "percentiles": percentiles,
        "monthly_thresholds": monthly_thresholds
    }
    
    # Save to JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"✅ Thresholds saved to {args.output}")
    print(f"📋 Summary:")
    print(f"   Location: {args.location}")
    print(f"   Samples: {len(df)}")
    print(f"   Percentiles: {percentiles}")
    print(f"   Months: 12")
    
    # Show example for January
    jan_thresholds = monthly_thresholds["1"]
    print(f"\n   Example (January):")
    print(f"      Precipitation: {jan_thresholds['precipitation_mm']} mm")
    print(f"      Wind Speed: {jan_thresholds['wind_speed_ms']} m/s")
    print(f"      Temperature: {jan_thresholds['temp_c']} °C")
    print(f"      Pressure: {jan_thresholds['pressure_hpa']} hPa")


if __name__ == "__main__":
    main()
