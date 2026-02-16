# Multi-Hazard Multi-Horizon Naive Bayes Prediction System

## Overview

This system provides multi-hazard, multi-horizon weather hazard prediction using an ensemble of 12 Naive Bayes models (4 hazards × 3 horizons), integrated with SMS notifications via Semaphore API.

## Features

### 1. Multi-Hazard Detection
- **Heat Stress**: High feels-like temperature conditions
- **Heavy Rain**: Significant precipitation events
- **Thunderstorm**: Electrical storm conditions (OpenWeather ID 200-232)
- **Severe Storm**: Low pressure + high wind combinations (cyclone proxy)

### 2. Multi-Horizon Forecasting
- **12-hour horizon**: Short-term immediate threats
- **24-hour horizon**: Next-day planning
- **48-hour horizon**: Multi-day advanced warning

### 3. Intelligent Alert System
- **Priority-based dispatching**: Severe storm > Thunderstorm > Heavy rain > Heat
- **Throttling**: Prevents SMS spam with configurable cooldown windows
- **Bundling**: Combines multiple hazards into single SMS when appropriate
- **Semaphore SMS**: Production-ready SMS via Semaphore API

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   PREDICTION PIPELINE                        │
├─────────────────────────────────────────────────────────────┤
│  OpenWeather API                                            │
│         ↓                                                   │
│  Enhanced Auto-Predictor (hourly)                          │
│         ↓                                                   │
│  Multi-Hazard Predictor                                    │
│    ├─ Feature Extraction (48 extended features)           │
│    ├─ Model Manager (loads 12 models)                     │
│    └─ Prediction (4 hazards × 3 horizons)                 │
│         ↓                                                   │
│  Alert Dispatcher                                          │
│    ├─ Throttle Check (per user × hazard × horizon)       │
│    ├─ Priority Sorting                                     │
│    ├─ Bundling (if multiple hazards)                      │
│    └─ Semaphore SMS Send                                   │
│         ↓                                                   │
│  Database Logging (alert_dispatch_log)                     │
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
backend-hydromet/
├── scripts/
│   ├── hazard_labeling.py         # Label generation for training
│   ├── data_preparation.py         # Handle duplicates, missing data
│   ├── feature_engineering.py      # Lag/delta/rolling features
│   ├── train_multi_models.py       # Train all 12 models
│   ├── retrain_models.py           # Weekly retraining script
│   └── models/                     # Trained model artifacts
│       ├── heat_stress/
│       │   ├── 12h/model.pkl
│       │   ├── 24h/model.pkl
│       │   └── 48h/model.pkl
│       ├── heavy_rain/...
│       ├── thunderstorm/...
│       └── severe_storm/...
│
└── backend/
    ├── ml/
    │   ├── multi_model_manager.py      # Model loading & caching
    │   └── multi_hazard_predictor.py   # Main prediction engine
    │
    └── services/
        ├── semaphore_notification.py   # Semaphore SMS service
        ├── alert_dispatcher.py          # Throttling & priority logic
        └── enhanced_auto_predictor.py   # Background service
```

## Usage

### 1. Training Models

```bash
cd scripts

# Initial training
python train_multi_models.py --csv training_data.csv --models-dir models

# Retraining (weekly)
python retrain_models.py --csv updated_training_data.csv --models-dir models
```

### 2. Making Predictions

```python
from backend.ml.multi_hazard_predictor import get_multi_hazard_predictor

# Initialize predictor
predictor = get_multi_hazard_predictor()

# Predict from OpenWeather data
weather_data = {...}  # OpenWeather API response
results = predictor.predict_from_weather_data(weather_data)

# Results include:
# - predictions: Dict[hazard][horizon] -> {prediction, probability}
# - summary: {total_hazards_detected, highest_risk_hazard, ...}
# - success: bool
```

### 3. Running Background Service

```python
from backend.services.enhanced_auto_predictor import get_enhanced_auto_predictor
import asyncio

# Initialize with alerts enabled
predictor = get_enhanced_auto_predictor(
    use_multi_hazard=True,
    enable_alerts=True
)

# Run once
summary = predictor.run_once(location="Manila")

# Run continuously (hourly)
asyncio.run(predictor.run_continuous(interval_hours=1, location="Manila"))
```

### 4. Manual Alert Dispatch

```python
from backend.services.alert_dispatcher import get_alert_dispatcher

dispatcher = get_alert_dispatcher()

# Dispatch single hazard
dispatcher.dispatch_single_hazard(
    hazard="thunderstorm",
    horizon=12,
    probability=0.85,
    location="Manila"
)

# Dispatch from predictions
dispatcher.dispatch_from_predictions(
    predictions=prediction_results,
    location="Manila"
)
```

## Configuration

### Hazard Thresholds (scripts/hazard_labeling.py)

```python
thresholds = {
    "heat_stress": {
        "feels_like_c": 38.0,  # Celsius
    },
    "heavy_rain": {
        "rain_1h_mm": 20.0,    # mm
    },
    "thunderstorm": {
        "weather_id_range": (200, 232),  # OpenWeather codes
    },
    "severe_storm": {
        "pressure_hpa": 980.0,  # hPa
        "wind_speed_ms": 20.0,  # m/s
    }
}
```

### Throttle Windows (backend/services/alert_dispatcher.py)

```python
throttle_hours = {
    "severe_storm": 2,   # Re-alert every 2 hours
    "thunderstorm": 3,   # Re-alert every 3 hours
    "heavy_rain": 4,     # Re-alert every 4 hours
    "heat_stress": 6,    # Re-alert every 6 hours
}
```

### Environment Variables

```bash
# Semaphore SMS API
SEMAPHORE_API_KEY=your_api_key_here

# OpenWeather API (metric units)
OPENWEATHER_API_KEY=your_api_key_here
OPENWEATHER_LAT=14.3644
OPENWEATHER_LON=121.0619
OPENWEATHER_BASE_URL=https://pro.openweathermap.org/data/2.5

# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname
```

## Database Schema

### alert_dispatch_log Table

```sql
CREATE TABLE alert_dispatch_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    phone_number VARCHAR(20) NOT NULL,
    hazard VARCHAR(50) NOT NULL,
    horizon INTEGER NOT NULL,
    probability FLOAT,
    message TEXT,
    dispatched_at TIMESTAMP DEFAULT NOW(),
    success BOOLEAN DEFAULT TRUE,
    bundled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_alert_dispatch_throttle 
ON alert_dispatch_log (phone_number, hazard, horizon, dispatched_at DESC);
```

## Model Training Details

### Training Pipeline
1. **Data Preparation**: Handle duplicates (aggregate), missing values (fill with 0, add indicators)
2. **Feature Engineering**: 48+ features including lag (3h, 6h), delta, rolling (3h, 6h, 12h)
3. **Labeling**: Create binary labels per hazard per horizon using thresholds
4. **Training**: Naive Bayes with SMOTE, PowerTransformer, SelectKBest
5. **Validation**: Time series split (80/20), 5-fold cross-validation
6. **Metrics**: Accuracy, precision, recall, F1-score, confusion matrix

### Model Performance Tracking
- Metrics saved with each model in `metadata.json`
- Retraining compares old vs new performance
- Backup old models before retraining

## API Integration (Planned)

### New Endpoint: /api/predictions/predict-multi-hazard

```json
POST /api/predictions/predict-multi-hazard
{
  "weather_data": {...},
  "source": "openweather"
}

Response:
{
  "success": true,
  "predictions": {
    "heat_stress": {
      "12h": {"prediction": 0, "probability": 0.15},
      "24h": {"prediction": 1, "probability": 0.82},
      "48h": {"prediction": 1, "probability": 0.75}
    },
    "thunderstorm": {
      "12h": {"prediction": 1, "probability": 0.88},
      ...
    },
    ...
  },
  "summary": {
    "total_hazards_detected": 3,
    "highest_risk_hazard": {
      "hazard": "thunderstorm",
      "horizon": 12,
      "probability": 0.88
    },
    "hazards_by_horizon": {
      "12h": ["thunderstorm"],
      "24h": ["heat_stress", "thunderstorm"],
      ...
    }
  }
}
```

## Monitoring & Maintenance

### Weekly Retraining
```bash
# Cron job (every Sunday at 2 AM)
0 2 * * 0 cd /path/to/scripts && python retrain_models.py --csv /data/observations.csv
```

### Model Status Check
```python
from backend.ml.multi_model_manager import get_multi_model_manager

manager = get_multi_model_manager()
status = manager.get_model_status()

print(f"Models ready: {status['available_count']}/{status['total_expected']}")
```

### Alert Dispatch Logs
```sql
-- Recent alerts
SELECT hazard, horizon, COUNT(*) as count, AVG(probability) as avg_prob
FROM alert_dispatch_log
WHERE dispatched_at > NOW() - INTERVAL '24 hours'
GROUP BY hazard, horizon;

-- Throttled users
SELECT phone_number, hazard, horizon, MAX(dispatched_at) as last_alert
FROM alert_dispatch_log
WHERE success = TRUE
GROUP BY phone_number, hazard, horizon
HAVING MAX(dispatched_at) > NOW() - INTERVAL '6 hours';
```

## Troubleshooting

### No models available
```bash
# Train models first
cd scripts
python train_multi_models.py --csv training_data.csv
```

### SMS not sending
- Check `SEMAPHORE_API_KEY` is set
- Verify phone number format (639XXXXXXXXX)
- Check Semaphore account balance
- Review logs: `backend/services/semaphore_notification.py`

### Throttling too aggressive
- Adjust `throttle_hours` in `alert_dispatcher.py`
- Check `alert_dispatch_log` table for recent alerts

### Poor model performance
- Collect more training data (especially positive samples)
- Adjust hazard thresholds in `hazard_labeling.py`
- Retrain with updated data
- Review confusion matrices in model metadata

## License

See main repository LICENSE file.
