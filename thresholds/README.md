# Threshold Files

This directory contains JSON files with percentile-based thresholds computed from historical weather data.

## File Format

Threshold files follow this structure:

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

## Generating Thresholds

When you receive OpenWeather historical data, run:

```bash
python scripts/calculate_thresholds.py \
    --csv data/openweather_sanpedro_1979_2025.csv \
    --output thresholds/sanpedro_monthly_v1.json \
    --location "San Pedro, Laguna" \
    --lat 14.3644 \
    --lon 121.0619
```

## Versioning

- `v1` - Initial percentile thresholds (75th, 90th, 95th, 99th)
- Future versions may include different percentiles or seasonal adjustments
