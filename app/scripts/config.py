"""
Configuration and constants for weather hazard prediction.
NO imports from naive, forecast_predictor, or other model modules.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# File paths
BASE_DIR = Path(__file__).parent
MODEL_PATH = os.getenv("MODEL_PATH", "model.pkl")
METADATA_PATH = os.getenv("METADATA_PATH", "model_metadata.json")

# Model configuration
MODEL_CONFIG = {
    "test_size": 0.2,
    "random_state": 42,
    "cv_splits": 5,
    "selector_k": 12,
    "use_mutual_info": True,
    "nb_var_smoothing": 1e-9
}

# Hazard thresholds (based on meteorological data)
HAZARD_THRESHOLDS = {
    "precipitation_mm": [20, 50, 100, 150],
    "wind_speed_ms": [15, 20, 25, 30],
    "temp_heat_c": [35, 38, 40, 42],
    "pressure_hpa": [975, 960, 940, 910]
}

# OpenWeather API defaults
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
OPENWEATHER_LAT = float(os.getenv("OPENWEATHER_LAT", "14.3644"))
OPENWEATHER_LON = float(os.getenv("OPENWEATHER_LON", "121.0619"))
OPENWEATHER_BASE_URL = os.getenv("OPENWEATHER_BASE_URL", "https://pro.openweathermap.org/data/2.5")

if __name__ == "__main__":
    print(f"📁 Configuration Paths:")
    print(f"   BASE_DIR: {BASE_DIR}")
    print(f"   MODEL_PATH: {MODEL_PATH}")
    print(f"   METADATA_PATH: {METADATA_PATH}")
    print(f"   Model exists: {Path(MODEL_PATH).exists()}")
    print(f"   Metadata exists: {Path(METADATA_PATH).exists()}")
    print(f"   OpenWeather Base URL: {OPENWEATHER_BASE_URL}")
