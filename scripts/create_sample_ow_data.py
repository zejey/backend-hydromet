"""
Create sample OpenWeather historical data for testing threshold calculations
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import argparse


def generate_sample_data(num_rows=100, year=2024):
    """
    Generate sample OpenWeather-like historical data
    
    Args:
        num_rows: Number of hourly records to generate
        year: Year for the data
        
    Returns:
        DataFrame with sample weather data
    """
    np.random.seed(42)
    
    start_date = datetime(year, 1, 1)
    dates = [start_date + timedelta(hours=i) for i in range(num_rows)]
    
    # Generate realistic weather data for San Pedro, Laguna
    # (Tropical climate with wet and dry seasons)
    
    data = []
    for dt in dates:
        month = dt.month
        
        # Wet season (May-Oct) vs Dry season (Nov-Apr)
        is_wet_season = 5 <= month <= 10
        
        # Temperature (Celsius) - ranges from 24-35°C typically
        base_temp = 28 + np.random.normal(0, 3)
        temp = np.clip(base_temp, 24, 38)
        
        # Precipitation (mm) - more in wet season
        if is_wet_season:
            # Wet season: occasional heavy rain
            if np.random.random() < 0.3:  # 30% chance of rain
                prcp = np.random.exponential(15)
            else:
                prcp = 0
        else:
            # Dry season: less rain
            if np.random.random() < 0.1:  # 10% chance of rain
                prcp = np.random.exponential(5)
            else:
                prcp = 0
        
        prcp = np.clip(prcp, 0, 150)
        
        # Wind speed (m/s) - typically 3-15 m/s, higher during storms
        wind = np.random.gamma(2, 3)
        if prcp > 30:  # High rain = likely storm = higher wind
            wind += np.random.exponential(5)
        wind = np.clip(wind, 0, 30)
        
        # Pressure (hPa) - typically 1008-1015, lower during storms
        pressure = 1013 + np.random.normal(0, 5)
        if prcp > 30:  # Storm conditions
            pressure -= np.random.uniform(10, 30)
        pressure = np.clip(pressure, 960, 1020)
        
        # Humidity (%)
        humidity = 60 + np.random.normal(0, 15)
        if prcp > 0:
            humidity = min(95, humidity + 20)
        humidity = np.clip(humidity, 40, 100)
        
        data.append({
            "dt": int(dt.timestamp()),
            "timestamp": dt.isoformat(),
            "temp": round(temp, 2),
            "temp_min": round(temp - np.random.uniform(0, 2), 2),
            "temp_max": round(temp + np.random.uniform(0, 3), 2),
            "pressure": round(pressure, 1),
            "humidity": round(humidity, 1),
            "wind_speed": round(wind, 2),
            "precipitation": round(prcp, 2),
            "month": month,
            "is_wet_season": is_wet_season
        })
    
    return pd.DataFrame(data)


def main():
    parser = argparse.ArgumentParser(description="Generate sample OpenWeather historical data")
    parser.add_argument("--output", default="sample_ow_history.csv", help="Output CSV file path")
    parser.add_argument("--rows", type=int, default=1000, help="Number of hourly records to generate")
    parser.add_argument("--year", type=int, default=2024, help="Year for the data")
    
    args = parser.parse_args()
    
    print(f"🔧 Generating {args.rows} sample records for year {args.year}...")
    df = generate_sample_data(num_rows=args.rows, year=args.year)
    
    print(f"📊 Sample data statistics:")
    print(f"   Records: {len(df)}")
    print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"   Temp range: {df['temp'].min():.1f}°C to {df['temp'].max():.1f}°C")
    print(f"   Max precipitation: {df['precipitation'].max():.1f}mm")
    print(f"   Max wind: {df['wind_speed'].max():.1f}m/s")
    print(f"   Pressure range: {df['pressure'].min():.1f} to {df['pressure'].max():.1f}hPa")
    
    # Save to CSV
    df.to_csv(args.output, index=False)
    print(f"✅ Saved to {args.output}")


if __name__ == "__main__":
    main()
