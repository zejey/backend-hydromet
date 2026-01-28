# Client Configuration Guide

This guide explains how to create and manage client-specific threshold configurations.

## Overview

Client configurations allow you to adjust hazard detection sensitivity for different areas, use cases, or users. Each client can have:

- **Threshold multipliers** (0.1–5.0) for rain, wind, heat, and pressure
- **Alert rules** (duration, cooldown periods)
- **Metadata** (location, barangay, description)

## Why Client Multipliers?

Different locations have different risk profiles:

### Example Scenarios

**Zone A (Mountainous area, poor drainage)**
- `rain_multiplier: 0.85` (15% more sensitive to rain)
- Rationale: Poor drainage means less rain causes flooding

**Zone B (Coastal area)**
- `wind_multiplier: 0.9` (10% more sensitive to wind)
- Rationale: Exposed to strong winds from the sea

**Zone C (Urban heat island)**
- `heat_multiplier: 1.1` (10% less sensitive to heat)
- Rationale: Residents are more accustomed to high temperatures

**Risk-averse client**
- All multipliers at 0.8 (20% more sensitive to everything)
- Rationale: Prefer early warnings, accept more false alarms

## API Endpoints

Base URL: `http://localhost:8000/api/client-config`

### 1. List All Configs

```bash
GET /api/client-config/
```

**Response:**
```json
{
  "success": true,
  "total": 3,
  "configs": [
    {
      "client_id": "default",
      "location_name": "San Pedro (Baseline)",
      "barangay": null,
      "rain_multiplier": 1.0,
      "wind_multiplier": 1.0,
      "heat_multiplier": 1.0,
      "pressure_multiplier": 1.0,
      "alert_duration_hours": 2,
      "cooldown_hours": 6,
      "description": "Default thresholds - no adjustments",
      "created_at": "2026-01-28T12:00:00Z",
      "updated_at": "2026-01-28T12:00:00Z",
      "created_by": "system"
    },
    ...
  ]
}
```

### 2. Get Specific Config

```bash
GET /api/client-config/san_pedro_zone_a
```

**Response:**
```json
{
  "client_id": "san_pedro_zone_a",
  "location_name": "Zone A (Mountainous)",
  "barangay": "San Antonio",
  "rain_multiplier": 0.85,
  "wind_multiplier": 1.0,
  "heat_multiplier": 1.1,
  "pressure_multiplier": 1.0,
  "alert_duration_hours": 2,
  "cooldown_hours": 6,
  "description": "Zone A has poor drainage - 15% more sensitive to rain",
  "created_at": "2026-01-28T13:00:00Z",
  "updated_at": "2026-01-28T13:00:00Z",
  "created_by": "admin"
}
```

### 3. Create New Config

```bash
POST /api/client-config/
Content-Type: application/json

{
  "client_id": "san_pedro_zone_b",
  "location_name": "Zone B (Coastal)",
  "barangay": "Rosario",
  "rain_multiplier": 1.0,
  "wind_multiplier": 0.9,
  "heat_multiplier": 1.0,
  "pressure_multiplier": 0.95,
  "alert_duration_hours": 3,
  "cooldown_hours": 8,
  "description": "Coastal area - more sensitive to wind and low pressure"
}
```

**Response:** `201 Created` with the created config

### 4. Update Config

```bash
PUT /api/client-config/san_pedro_zone_a
Content-Type: application/json

{
  "rain_multiplier": 0.8,
  "description": "Updated: 20% more sensitive to rain after recent floods"
}
```

**Response:** Updated config object

### 5. Delete Config

```bash
DELETE /api/client-config/san_pedro_zone_b
```

**Response:**
```json
{
  "success": true,
  "message": "Client configuration deleted successfully",
  "client_id": "san_pedro_zone_b"
}
```

**Note:** Cannot delete the `default` config (protected).

## Using Configs in Predictions

### Via API

Include `client_id` in prediction request:

```bash
curl -X POST http://localhost:8000/api/predictions/predict \
  -H "Content-Type: application/json" \
  -d '{
    "weather_data": {
      "temp": 36.5,
      "prcp": 45.2,
      "wind": 8.3,
      "pressure": 1003.1
    },
    "source": "openweather",
    "client_id": "san_pedro_zone_a"
  }'
```

### In Python Code

```python
from scripts.hazard_score_v2 import hazard_score_v2

event, score, hazards, details = hazard_score_v2(
    row=weather_data,
    thresholds_path="thresholds/sanpedro_monthly_v1.json",
    client_id="san_pedro_zone_a",  # Uses custom multipliers
    month=8,
    explain=True
)
```

## Multiplier Effects

### How Multipliers Work

Base threshold × multiplier = adjusted threshold

**Example** (August rain thresholds):
- Base 90th percentile: 50mm
- With `rain_multiplier: 0.8`:
  - Adjusted threshold: 50 × 0.8 = **40mm**
  - Hazard triggers at 40mm instead of 50mm (20% more sensitive)

- With `rain_multiplier: 1.2`:
  - Adjusted threshold: 50 × 1.2 = **60mm**
  - Hazard triggers at 60mm instead of 50mm (20% less sensitive)

### Multiplier Ranges

- **< 1.0**: More sensitive (triggers earlier)
  - 0.8 = 20% more sensitive
  - 0.5 = 50% more sensitive (very aggressive)
  
- **= 1.0**: Baseline (no adjustment)

- **> 1.0**: Less sensitive (triggers later)
  - 1.2 = 20% less sensitive
  - 1.5 = 50% less sensitive (very conservative)

**Valid range:** 0.1 to 5.0 (enforced by database constraints)

## Alert Rules

### Duration Hours

How long an alert stays active after being triggered.

- **Default:** 2 hours
- **Use cases:**
  - Short duration (1-2h): Fast-moving weather events
  - Medium duration (3-6h): Persistent conditions
  - Long duration (12-24h): Extended hazards (heat waves)

### Cooldown Hours

Minimum time before the same client can receive another alert.

- **Default:** 6 hours
- **Rationale:** Prevent alert fatigue
- **Use cases:**
  - Short cooldown (1-2h): High-risk areas, frequent updates needed
  - Medium cooldown (6-12h): Normal monitoring
  - Long cooldown (24h+): Low-risk areas, daily summaries only

## Configuration Strategies

### By Risk Profile

**High Risk (Schools, Hospitals)**
```json
{
  "rain_multiplier": 0.8,
  "wind_multiplier": 0.8,
  "heat_multiplier": 0.9,
  "pressure_multiplier": 0.9,
  "alert_duration_hours": 4,
  "cooldown_hours": 4
}
```

**Medium Risk (Residential)**
```json
{
  "rain_multiplier": 1.0,
  "wind_multiplier": 1.0,
  "heat_multiplier": 1.0,
  "pressure_multiplier": 1.0,
  "alert_duration_hours": 2,
  "cooldown_hours": 6
}
```

**Low Risk (Industrial)**
```json
{
  "rain_multiplier": 1.2,
  "wind_multiplier": 1.1,
  "heat_multiplier": 1.3,
  "pressure_multiplier": 1.1,
  "alert_duration_hours": 1,
  "cooldown_hours": 12
}
```

### By Geography

**Mountainous (Flood-prone)**
```json
{
  "rain_multiplier": 0.85,
  "wind_multiplier": 1.0,
  "heat_multiplier": 1.0,
  "pressure_multiplier": 1.0,
  "description": "Poor drainage - flash flood risk"
}
```

**Coastal (Wind-exposed)**
```json
{
  "rain_multiplier": 1.0,
  "wind_multiplier": 0.9,
  "heat_multiplier": 1.0,
  "pressure_multiplier": 0.95,
  "description": "Exposed to sea winds and storm surge"
}
```

**Urban (Heat island)**
```json
{
  "rain_multiplier": 1.0,
  "wind_multiplier": 1.0,
  "heat_multiplier": 1.1,
  "pressure_multiplier": 1.0,
  "description": "Urban heat island - residents adapted"
}
```

## Best Practices

### 1. Start Conservative

Begin with multipliers close to 1.0 and adjust based on feedback.

### 2. Monitor False Alarms

Track alert accuracy for first 2 weeks:
- If too many false alarms → increase multipliers (less sensitive)
- If missing hazards → decrease multipliers (more sensitive)

### 3. Document Changes

Use the `description` field to explain why multipliers were chosen:

```json
{
  "description": "Zone A: 0.85 rain multiplier due to 3 flood events in 2025 with <45mm rain"
}
```

### 4. Version Control

When making significant changes, consider creating a new client_id:

- `san_pedro_zone_a_v1` → Initial config
- `san_pedro_zone_a_v2` → After tuning period

### 5. Regular Review

Review configurations quarterly:
- Have risk profiles changed?
- New infrastructure (improved drainage)?
- Climate patterns shifting?

## Database Schema

```sql
CREATE TABLE client_threshold_config (
    client_id TEXT PRIMARY KEY,
    location_name TEXT NOT NULL,
    barangay TEXT,
    
    -- Multipliers (1.0 = baseline)
    rain_multiplier FLOAT DEFAULT 1.0 CHECK (rain_multiplier > 0),
    wind_multiplier FLOAT DEFAULT 1.0 CHECK (wind_multiplier > 0),
    heat_multiplier FLOAT DEFAULT 1.0 CHECK (heat_multiplier > 0),
    pressure_multiplier FLOAT DEFAULT 1.0 CHECK (pressure_multiplier > 0),
    
    -- Alert rules
    alert_duration_hours INT DEFAULT 2,
    cooldown_hours INT DEFAULT 6,
    
    -- Metadata
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by TEXT,
    
    -- Constraints
    CONSTRAINT valid_multipliers CHECK (
        rain_multiplier BETWEEN 0.1 AND 5.0 AND
        wind_multiplier BETWEEN 0.1 AND 5.0 AND
        heat_multiplier BETWEEN 0.1 AND 5.0 AND
        pressure_multiplier BETWEEN 0.1 AND 5.0
    )
);
```

## Troubleshooting

### "Client configuration not found"

```
HTTPException: 404 - Client configuration not found: my_client
```

**Solution:** Create the client config first using POST `/api/client-config/`

### "Cannot delete the default configuration"

```
HTTPException: 403 - Cannot delete the default configuration
```

**Solution:** The `default` config is protected. Create a new config instead of deleting default.

### "Client configuration already exists"

```
HTTPException: 409 - Client configuration already exists: my_client
```

**Solution:** Use PUT to update, or choose a different `client_id`.

## See Also

- [Threshold System Guide](THRESHOLDS.md) - How percentile thresholds work
- [API Reference](../backend/api/client_config.py) - Full API documentation
- [Database Migration](../migrations/001_add_client_threshold_config.sql) - Schema details
