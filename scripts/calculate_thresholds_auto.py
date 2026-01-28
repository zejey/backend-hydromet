#!/usr/bin/env python3
"""
Auto-detecting threshold calculator for OpenWeather historical data
Handles various OpenWeather bulk formats including Kelvin temperatures
"""

import pandas as pd
import numpy as np
import json
import argparse
from pathlib import Path
from datetime import datetime

def load_and_prepare_data(csv_path):
    """Load CSV and standardize column names"""
    
    print(f"📁 Loading: {csv_path}")
    df = pd.read_csv(csv_path)
    
    print(f"   Total rows: {len(df):,}")
    print(f"   Columns: {list(df.columns[:10])}...")  # Show first 10
    
    # Column mapping for OpenWeather bulk format
    column_map = {}
    
    # Timestamp
    if 'dt' in df.columns:
        column_map['time'] = 'dt'
    elif 'dt_iso' in df.columns:
        column_map['time'] = 'dt_iso'
    
    # Temperature (might be in Kelvin!)
    if 'temp' in df.columns:
        column_map['temp'] = 'temp'
    
    # Precipitation
    if 'rain_1h' in df.columns:
        column_map['precipitation'] = 'rain_1h'
    elif 'rain' in df.columns:
        column_map['precipitation'] = 'rain'
    elif 'prcp' in df.columns:
        column_map['precipitation'] = 'prcp'
    
    # Wind speed
    if 'wind_speed' in df.columns:
        column_map['wind_speed'] = 'wind_speed'
    elif 'wspd' in df.columns:
        column_map['wind_speed'] = 'wspd'
    
    # Pressure
    if 'pressure' in df.columns:
        column_map['pressure'] = 'pressure'
    elif 'pres' in df.columns:
        column_map['pressure'] = 'pres'
    
    print(f"\n🔍 Column mapping:")
    for standard, actual in column_map.items():
        print(f"   {standard:15s} <- {actual}")
    
    # Check required columns
    required = ['time', 'temp', 'wind_speed', 'pressure']
    missing = [col for col in required if col not in column_map]
    
    if missing:
        print(f"\n❌ Missing required columns: {missing}")
        print(f"   Available: {list(df.columns)}")
        raise ValueError(f"Cannot proceed without: {missing}")
    
    # Rename columns
    reverse_map = {v: k for k, v in column_map.items()}
    df = df.rename(columns=reverse_map)
    
    # Handle missing precipitation
    if 'precipitation' not in df.columns:
        print("   ⚠️  No precipitation column - setting to 0")
        df['precipitation'] = 0
    
    # Convert timestamp
    if df['time'].dtype == 'int64':
        # Unix timestamp (seconds)
        print("   Converting Unix timestamp to datetime...")
        df['time'] = pd.to_datetime(df['time'], unit='s')
    else:
        # ISO string
        df['time'] = pd.to_datetime(df['time'])
    
    # Check if temperature is in Kelvin (values > 100 suggest Kelvin)
    temp_sample = df['temp'].dropna().iloc[:100].mean()
    if temp_sample > 100:
        print(f"   🌡️  Temperature appears to be in Kelvin (avg={temp_sample:.1f}K)")
        print("   Converting to Celsius...")
        df['temp'] = df['temp'] - 273.15
        print(f"   ✅ Converted (new avg={df['temp'].mean():.1f}°C)")
    else:
        print(f"   Temperature already in Celsius (avg={temp_sample:.1f}°C)")
    
    # Add month column
    df['month'] = df['time'].dt.month
    df['year'] = df['time'].dt.year
    
    # Clean data
    print(f"\n🧹 Cleaning data...")
    
    # Fill NaN precipitation with 0
    df['precipitation'] = df['precipitation'].fillna(0)
    
    # Fill NaN wind with median
    if df['wind_speed'].isna().any():
        median_wind = df['wind_speed'].median()
        df['wind_speed'] = df['wind_speed'].fillna(median_wind)
        print(f"   Filled {df['wind_speed'].isna().sum()} missing wind values with median: {median_wind:.1f} m/s")
    
    # Forward-fill pressure
    if df['pressure'].isna().any():
        df['pressure'] = df['pressure'].fillna(method='ffill')
        print(f"   Forward-filled pressure gaps")
    
    # Drop rows still missing critical data
    before = len(df)
    df = df.dropna(subset=['temp', 'wind_speed', 'pressure'])
    after = len(df)
    
    if before > after:
        print(f"   Dropped {before - after:,} rows with missing critical data")
    
    print(f"\n✅ Data prepared: {len(df):,} valid rows")
    print(f"   Date range: {df['time'].min()} to {df['time'].max()}")
    print(f"   Years: {df['year'].min()} - {df['year'].max()}")
    
    # Show data summary
    print(f"\n📊 Data summary:")
    print(f"   Temperature: {df['temp'].min():.1f}°C to {df['temp'].max():.1f}°C (mean: {df['temp'].mean():.1f}°C)")
    print(f"   Precipitation: 0 to {df['precipitation'].max():.1f} mm (mean: {df['precipitation'].mean():.1f} mm)")
    print(f"   Wind: {df['wind_speed'].min():.1f} to {df['wind_speed'].max():.1f} m/s (mean: {df['wind_speed'].mean():.1f} m/s)")
    print(f"   Pressure: {df['pressure'].min():.1f} to {df['pressure'].max():.1f} hPa (mean: {df['pressure'].mean():.1f} hPa)")
    
    return df

def calculate_monthly_thresholds(df, percentiles=[75, 90, 95, 99]):
    """Calculate percentile thresholds for each month"""
    
    monthly_thresholds = {}
    
    print(f"\n📊 Computing monthly percentiles ({percentiles}):")
    print(f"{'Month':<10} {'Samples':>10} {'Rain 99%':>10} {'Wind 99%':>10} {'Temp 99%':>10} {'Pres 1%':>10}")
    print("-" * 70)
    
    for month in range(1, 13):
        month_data = df[df['month'] == month]
        
        if len(month_data) == 0:
            print(f"   ⚠️  Month {month:2d}: No data")
            continue
        
        # Calculate percentiles
        rain_pct = np.percentile(month_data['precipitation'], percentiles)
        wind_pct = np.percentile(month_data['wind_speed'], percentiles)
        temp_pct = np.percentile(month_data['temp'], percentiles)
        
        # Pressure is inverted (low pressure = hazard)
        # So 1st percentile is most dangerous, 99th is safe
        pres_pct = np.percentile(month_data['pressure'], [100-p for p in percentiles[::-1]])[::-1]
        
        thresholds = {
            'precipitation_mm': rain_pct.tolist(),
            'wind_speed_ms': wind_pct.tolist(),
            'temp_c': temp_pct.tolist(),
            'pressure_hpa': pres_pct.tolist()
        }
        
        monthly_thresholds[str(month)] = thresholds
        
        month_name = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][month-1]
        
        print(f"{month_name:>3} ({month:2d}) {len(month_data):>10,} "
              f"{rain_pct[3]:>10.1f} {wind_pct[3]:>10.1f} "
              f"{temp_pct[3]:>10.1f} {pres_pct[0]:>10.1f}")
    
    return monthly_thresholds

def main():
    parser = argparse.ArgumentParser(description='Calculate data-driven hazard thresholds from OpenWeather history')
    parser.add_argument('--csv', required=True, help='Path to OpenWeather history CSV')
    parser.add_argument('--output', required=True, help='Output JSON file path')
    parser.add_argument('--location', default='San Pedro, Laguna', help='Location name')
    parser.add_argument('--lat', type=float, default=14.3644, help='Latitude')
    parser.add_argument('--lon', type=float, default=121.0619, help='Longitude')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("THRESHOLD CALCULATION - OpenWeather History Bulk")
    print("=" * 80)
    
    # Load and prepare data
    df = load_and_prepare_data(args.csv)
    
    # Calculate thresholds
    monthly_thresholds = calculate_monthly_thresholds(df)
    
    # Build output
    output = {
        'version': '1.0',
        'location': args.location,
        'lat': args.lat,
        'lon': args.lon,
        'data_source': f'OpenWeather History Bulk - {Path(args.csv).name}',
        'computed_at': datetime.utcnow().isoformat() + 'Z',
        'total_samples': len(df),
        'date_range': {
            'start': df['time'].min().strftime('%Y-%m-%d'),
            'end': df['time'].max().strftime('%Y-%m-%d')
        },
        'percentiles': [75, 90, 95, 99],
        'percentile_labels': ['75th (light)', '90th (moderate)', '95th (heavy)', '99th (extreme)'],
        'monthly_thresholds': monthly_thresholds,
        'notes': {
            'precipitation': 'mm per hour',
            'wind_speed': 'm/s',
            'temperature': 'degrees Celsius',
            'pressure': 'hPa (low pressure = hazard, values are inverted percentiles)'
        }
    }
    
    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n💾 Output saved to: {output_path}")
    print("\n" + "=" * 80)
    print("✅ THRESHOLD CALCULATION COMPLETE!")
    print("=" * 80)
    
    # Show sample from one month
    print(f"\n📋 Sample thresholds (August - wet season):")
    aug_thresholds = monthly_thresholds.get('8', {})
    if aug_thresholds:
        print(f"   Rain (mm):     {aug_thresholds['precipitation_mm']}")
        print(f"   Wind (m/s):    {aug_thresholds['wind_speed_ms']}")
        print(f"   Temp (°C):     {aug_thresholds['temp_c']}")
        print(f"   Pressure (hPa): {aug_thresholds['pressure_hpa']}")
    
    print(f"\n💡 Next steps:")
    print(f"   1. Review the thresholds in: {output_path}")
    print(f"   2. Update .env: THRESHOLDS_PATH={output_path}")
    print(f"   3. Test with: python test_scoring.py")

if __name__ == '__main__':
    main()