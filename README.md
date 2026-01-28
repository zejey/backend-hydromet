# Backend Hydromet - Weather Hazard Detection System

A FastAPI-based backend system for detecting weather hazards using machine learning and data-driven thresholds.

## Features

- **ML-based Weather Hazard Prediction**: Uses Gaussian Naive Bayes with SMOTE oversampling
- **Data-Driven Thresholds**: Percentile-based thresholds computed from historical data
- **Client Configuration**: Per-client threshold multipliers for customized sensitivity
- **Real-time Monitoring**: OpenWeather API integration
- **Alert System**: In-app and SMS notifications via SendGrid
- **RESTful API**: FastAPI with automatic OpenAPI documentation

## New: Data-Driven Thresholds (Phase 1)

### What's New

Replace hardcoded hazard thresholds with **percentile-based thresholds** computed from OpenWeather historical data:

- ✅ **Monthly thresholds**: Different thresholds for each month (wet vs dry season)
- ✅ **Client multipliers**: Adjust sensitivity per-client (0.1–5.0x)
- ✅ **Alert rules**: Configurable duration and cooldown periods
- ✅ **Backward compatible**: Old `hazard_score` still works

### Quick Start

#### 1. Generate Sample Thresholds

```bash
# Generate sample historical data
python scripts/create_sample_ow_data.py --output sample_ow_history.csv --rows 1000

# Calculate thresholds
python scripts/calculate_thresholds.py \
    --csv sample_ow_history.csv \
    --output thresholds/sanpedro_monthly_v1.json \
    --location "San Pedro, Laguna"
```

#### 2. Set Environment Variable

```bash
export THRESHOLDS_PATH="thresholds/sanpedro_monthly_v1.json"
```

#### 3. Use New Hazard Score Function

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

print(f"Event: {event}, Hazards: {hazards}")
```

### Client Configuration API

Manage per-client threshold multipliers via REST API:

```bash
# Create client config
curl -X POST http://localhost:8000/api/client-config/ \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "san_pedro_zone_a",
    "location_name": "Zone A (Mountainous)",
    "rain_multiplier": 0.85,
    "wind_multiplier": 1.0,
    "heat_multiplier": 1.1,
    "description": "Poor drainage - 15% more sensitive to rain"
  }'

# List all configs
curl http://localhost:8000/api/client-config/

# Get specific config
curl http://localhost:8000/api/client-config/san_pedro_zone_a
```

### Documentation

- [Threshold System Guide](docs/THRESHOLDS.md) - How to generate and use thresholds
- [Client Configuration Guide](docs/CLIENT_CONFIG.md) - Managing per-client settings
- [Database Migration](migrations/001_add_client_threshold_config.sql) - Schema setup

## Installation

### Requirements

- Python 3.12+
- PostgreSQL 13+
- OpenWeather API key

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=hydromet_db
export DB_USER=weather_app
export DB_PASSWORD=your_password
export OPENWEATHER_API_KEY=your_api_key

# Run database migrations
psql -U weather_app -d hydromet_db -f migrations/001_add_client_threshold_config.sql

# Start the server
uvicorn py.main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

### Weather Predictions

- `POST /api/predictions/predict` - Predict from weather data
- `POST /api/predictions/predict-custom` - Predict from custom features
- `POST /api/predictions/forecast` - Batch forecast predictions
- `GET /api/predictions/forecast/summary` - Forecast summary
- `GET /api/predictions/health` - Health check

### Client Configuration (NEW)

- `GET /api/client-config/` - List all client configs
- `GET /api/client-config/{client_id}` - Get specific config
- `POST /api/client-config/` - Create config
- `PUT /api/client-config/{client_id}` - Update config
- `DELETE /api/client-config/{client_id}` - Delete config

### Weather Data

- `GET /api/weather/current` - Current weather
- `GET /api/weather/forecast` - Weather forecast

## Architecture

```
backend-hydromet/
├── backend/
│   ├── api/              # FastAPI routes
│   │   ├── predictions.py
│   │   ├── client_config.py  # NEW
│   │   └── ...
│   ├── models/           # Pydantic models
│   │   ├── client_config.py  # NEW
│   │   └── ...
│   ├── ml/               # ML components
│   └── services/
├── scripts/
│   ├── model.py                    # ML model training
│   ├── hazard_score_v2.py          # NEW: Dynamic thresholds
│   ├── threshold_loader.py         # NEW: Load thresholds
│   ├── client_config_db.py         # NEW: DB operations
│   ├── calculate_thresholds.py     # NEW: Compute thresholds
│   └── create_sample_ow_data.py    # NEW: Generate test data
├── migrations/
│   └── 001_add_client_threshold_config.sql  # NEW
├── thresholds/          # NEW: Threshold JSON files
├── docs/                # NEW: Documentation
├── tests/               # NEW: Unit tests
└── requirements.txt
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_thresholds.py -v
pytest tests/test_hazard_score_v2.py -v

# Test threshold calculation
python scripts/create_sample_ow_data.py --output sample.csv --rows 1000
python scripts/calculate_thresholds.py --csv sample.csv --output thresholds/test.json
```

## Migration Guide

### From Hardcoded to Dynamic Thresholds

1. **Generate thresholds** (when you have historical data):
   ```bash
   python scripts/calculate_thresholds.py \
       --csv openweather_history.csv \
       --output thresholds/sanpedro_monthly_v1.json
   ```

2. **Update environment**:
   ```bash
   export THRESHOLDS_PATH="thresholds/sanpedro_monthly_v1.json"
   ```

3. **Update code** to use `hazard_score_v2`:
   ```python
   # Old
   from scripts.model import hazard_score
   event = hazard_score(row)
   
   # New
   from scripts.hazard_score_v2 import hazard_score_v2
   event = hazard_score_v2(row, thresholds_path=..., client_id=...)
   ```

4. **Monitor and tune** for 2 weeks:
   - Track false alarm rate
   - Adjust client multipliers if needed

## Environment Variables

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=hydromet_db
DB_USER=weather_app
DB_PASSWORD=your_password

# Weather API
OPENWEATHER_API_KEY=your_api_key
OPENWEATHER_LAT=14.3644
OPENWEATHER_LON=121.0619

# Thresholds (NEW)
THRESHOLDS_PATH=thresholds/sanpedro_monthly_v1.json

# Model
MODEL_PATH=model.pkl
METADATA_PATH=model_metadata.json
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/ -v`
5. Submit a pull request

## License

[Add your license here]

## Support

For questions or issues, please open a GitHub issue or contact the maintainer.
