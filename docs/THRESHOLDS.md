# Data-Driven Threshold System

This document explains how the percentile-based threshold system works and how to generate, update, and use thresholds.

## Overview

The system replaces hardcoded hazard thresholds with **data-driven percentile-based thresholds** computed from historical weather data. This allows for:

- **Seasonal sensitivity**: Different thresholds for each month (wet vs dry season)
- **Statistical rigor**: Thresholds based on actual weather patterns, not assumptions
- **Client customization**: Per-client multipliers to adjust sensitivity
- **Easy updates**: Recalculate when new data becomes available

## How Thresholds Are Computed

### Data Source

Thresholds are calculated from OpenWeather historical data (hourly observations, 1979–present) for San Pedro, Laguna.

### Methodology

For each month (1-12) and each weather variable:

1. **Precipitation, Wind, Temperature**: Calculate 75th, 90th, 95th, and 99th percentiles
   - Higher values = more extreme conditions
   
2. **Pressure**: Calculate inverted percentiles (25th, 10th, 5th, 1st)
   - Lower pressure = more hazardous (cyclones, storms)

### Filtering (Optional)

You can optionally exclude known hazard days (e.g., PAGASA-reported typhoons) to get "baseline" thresholds that represent normal conditions only.

## File Structure

```json
{
  "version": "1.0",
  "location": "San Pedro, Laguna",
  "lat": 14.3644,
  "lon": 121.0619,
  "data_source": "OpenWeather History Bulk 1979-2025",
  "computed_at": "2026-01-28T12:00:00Z",
  "total_samples": 400000,
  "date_range": {
    "start": "1979-01-01",
    "end": "2025-12-31"
  },
  "percentiles": [75, 90, 95, 99],
  "monthly_thresholds": {
    "1": {
      "precipitation_mm": [8.2, 22.5, 38.1, 65.3],
      "wind_speed_ms": [6.8, 11.2, 14.7, 19.4],
      "temp_c": [31.5, 33.8, 35.2, 37.1],
      "pressure_hpa": [1008.3, 1004.1, 1000.5, 995.2]
    },
    ...
  }
}
```

### Interpretation

For **January**:
- Rain at 22.5mm = 90th percentile (only 10% of January hours have more rain)
- Wind at 14.7m/s = 95th percentile (very strong for January)
- Temp at 35.2°C = 95th percentile (extreme heat for January)
- Pressure at 1000.5hPa = 5th percentile (very low pressure, storm warning)

## Generating Thresholds

### Step 1: Generate Sample Data (for testing)

```bash
python scripts/create_sample_ow_data.py --output sample_ow_history.csv --rows 1000 --year 2024
```

### Step 2: Calculate Thresholds

```bash
python scripts/calculate_thresholds.py \
    --csv sample_ow_history.csv \
    --output thresholds/test_thresholds.json \
    --location "San Pedro, Laguna" \
    --lat 14.3644 \
    --lon 121.0619
```

### Step 3: Verify Output

```bash
cat thresholds/test_thresholds.json
```

Check that:
- All 12 months are present
- All 4 weather variables (precipitation_mm, wind_speed_ms, temp_c, pressure_hpa) exist for each month
- Values are in ascending order (except pressure, which is descending)

## Using Thresholds in Code

### Option 1: Direct Use (hazard_score_v2)

```python
from scripts.hazard_score_v2 import hazard_score_v2

weather_data = {
    "temp": 36.5,
    "prcp": 45.2,
    "wind": 8.3,
    "pressure": 1003.1
}

event, score, hazards, details = hazard_score_v2(
    row=weather_data,
    thresholds_path="thresholds/sanpedro_monthly_v1.json",
    client_id="default",
    month=8,  # August
    explain=True
)

print(f"Event: {event}")
print(f"Hazards: {hazards}")
print(f"Details: {details}")
```

### Option 2: Via Predictions API

```bash
curl -X POST http://localhost:8000/api/predictions/predict \
  -H "Content-Type: application/json" \
  -d '{
    "weather_data": {...},
    "source": "openweather",
    "client_id": "san_pedro_zone_a"
  }'
```

## Updating Thresholds

### When to Update

- New historical data arrives (e.g., OpenWeather updates their bulk archive)
- Data quality improves (better sensors, more stations)
- Significant climate change detected

### How to Update

1. **Download new data** (when available):
   ```bash
   # This is a placeholder - actual command depends on data source
   wget https://openweather.org/history/bulk/sanpedro_1979_2026.csv
   ```

2. **Recalculate thresholds**:
   ```bash
   python scripts/calculate_thresholds.py \
       --csv sanpedro_1979_2026.csv \
       --output thresholds/sanpedro_monthly_v2.json \
       --location "San Pedro, Laguna" \
       --lat 14.3644 \
       --lon 121.0619
   ```

3. **Update environment variable**:
   ```bash
   export THRESHOLDS_PATH="thresholds/sanpedro_monthly_v2.json"
   # Or update .env file
   ```

4. **Restart application** to load new thresholds

5. **Monitor for 2 weeks**:
   - Track false alarm rate
   - Compare old vs new system performance
   - Adjust client multipliers if needed

## Versioning Strategy

### Naming Convention

- `sanpedro_monthly_v1.json` - Initial version (baseline)
- `sanpedro_monthly_v2.json` - Updated with 2026 data
- `sanpedro_monthly_v2_filtered.json` - Version 2 with hazard days excluded

### Version History (Future Enhancement)

Consider adding a `threshold_version_history` table:

```sql
CREATE TABLE threshold_version_history (
    version_id SERIAL PRIMARY KEY,
    file_name TEXT NOT NULL,
    location TEXT NOT NULL,
    data_source TEXT,
    total_samples INT,
    date_range_start DATE,
    date_range_end DATE,
    deployed_at TIMESTAMP DEFAULT NOW(),
    deployed_by TEXT,
    notes TEXT
);
```

## Seasonal Behavior

### Wet Season (May–October)

- Higher precipitation thresholds (rain is normal)
- Storm combinations (rain + wind) more common
- Lower pressure values typical

### Dry Season (November–April)

- Lower precipitation thresholds (any rain is notable)
- Higher temperature thresholds (summer months)
- Higher pressure values typical

### Example Comparison

**Rain at 30mm**:
- In January (dry): Likely above 99th percentile → EXTREME EVENT
- In August (wet): Likely around 90th percentile → MODERATE EVENT

This is why monthly thresholds are critical for accurate hazard detection.

## Troubleshooting

### "Threshold file not found"

```
FileNotFoundError: Threshold file not found: thresholds/sanpedro_monthly_v1.json
```

**Solution**: Generate thresholds using `calculate_thresholds.py` or check `THRESHOLDS_PATH` environment variable.

### "Invalid threshold structure"

```
ValueError: Invalid threshold structure in: thresholds/test.json
```

**Solution**: Verify JSON structure. All 12 months must be present, each with 4 weather variables, each with 4 percentile values.

### "No data for month X"

```
Warning: No data for month 12, using default values
```

**Solution**: Ensure your historical CSV has data for all 12 months. If missing, add more data or use multi-year dataset.

## See Also

- [Client Configuration Guide](CLIENT_CONFIG.md) - Per-client threshold multipliers
- [API Documentation](../backend/api/client_config.py) - Client config CRUD endpoints
- [Migration Guide](../migrations/001_add_client_threshold_config.sql) - Database setup
