# model.py
import numpy as np
import pandas as pd
import joblib
import json
from datetime import datetime
from sklearn.naive_bayes import GaussianNB
from sklearn.model_selection import train_test_split, TimeSeriesSplit, cross_val_score
from sklearn.preprocessing import PowerTransformer
from sklearn.pipeline import Pipeline
from sklearn.feature_selection import SelectKBest, mutual_info_classif, f_classif
from sklearn.metrics import classification_report
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline

from app.scripts.config import HAZARD_THRESHOLDS, MODEL_CONFIG, MODEL_PATH, METADATA_PATH
from app.ml.hazard_type_mapping import determine_hazard_type
from app.ml.notification_mapping import hazard_notification_templates
from app.services.notification_util import NotificationService
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ----------- Feature Engineering & Hazard Scoring -----------

def hazard_score(row, thresholds=HAZARD_THRESHOLDS, explain=False):
    score = 0.0
    hazards = []

    # Precipitation
    prcp = (
        row.get("rain", {}).get("1h", 0)
        if "rain" in row
        else row.get("precipitation", row.get("prcp", 0)) or 0
    )

    if prcp >= thresholds["precipitation_mm"][3]:  # Extreme
        score += 4
        hazards.append("extreme rain")
    elif prcp >= thresholds["precipitation_mm"][2]:
        score += 3
        hazards.append("heavy rain")
    elif prcp >= thresholds["precipitation_mm"][1]:
        score += 2
        hazards.append("moderate rain")
    elif prcp >= thresholds["precipitation_mm"][0]:
        score += 1
        hazards.append("light rain")

    # Wind
    wind = (
        row.get("wind_speed", row.get("wind", {}).get("speed", row.get("wspd", 0))) or 0
    )
    if wind >= thresholds["wind_speed_ms"][3]:  # Extreme
        score += 3
        hazards.append("extreme wind")
    elif wind >= thresholds["wind_speed_ms"][2]:
        score += 2.5
        hazards.append("very strong wind")
    elif wind >= thresholds["wind_speed_ms"][1]:
        score += 1.5
        hazards.append("strong wind")
    elif wind >= thresholds["wind_speed_ms"][0]:
        score += 1
        hazards.append("moderate wind")

    # Heat
    tmax = (
        row.get("temp_max", row.get("main", {}).get("temp_max", row.get("tmax", row.get("temperature", row.get("temp", 0)))))
    )
    if tmax >= thresholds["temp_heat_c"][3]:  # Extreme
        score += 3
        hazards.append("extreme heat")
    elif tmax >= thresholds["temp_heat_c"][2]:
        score += 2.5
        hazards.append("very extreme heat")
    elif tmax >= thresholds["temp_heat_c"][1]:
        score += 1.5
        hazards.append("very hot")
    elif tmax >= thresholds["temp_heat_c"][0]:
        score += 1
        hazards.append("hot")

    # Pressure
    pres = (
        row.get("pressure", row.get("main", {}).get("pressure", row.get("pres", 1013)))
    )
    try:
        pres = float(pres)
    except:
        pres = 1013

    if pres < thresholds["pressure_hpa"][3]:  # Cyclone-level
        score += 3
        hazards.append("cyclone pressure")
    elif pres < thresholds["pressure_hpa"][2]:
        score += 2.5
        hazards.append("very low pressure")
    elif pres < thresholds["pressure_hpa"][1]:
        score += 1.5
        hazards.append("low pressure")
    elif pres < thresholds["pressure_hpa"][0]:
        score += 1
        hazards.append("moderate low pressure")

    # Combination (storm)
    if prcp >= thresholds["precipitation_mm"][1] and wind >= thresholds["wind_speed_ms"][1]:
        score += 1
        hazards.append("rain + wind (possible storm)")

    event = int(score >= 2.0)
    if explain:
        return event, hazards
    else:
        return event
    
def engineer_features(df):
    """Add features used for both training and prediction."""
    df = df.copy()
    
    # ===== METEOSTAT COLUMN MAPPING =====
    # Meteostat uses: date, tavg, tmin, tmax, prcp, snow, wdir, wspd, wpgt, pres, tsun
    # Map to standard names
    col_map = {
        "tavg": "temperature",
        "tmin": "temp_min", 
        "tmax": "temp_max",
        "prcp": "precipitation",
        "wspd": "wind_speed",
        "wpgt": "wind_gust",
        "wdir": "wind_direction",
        "pres": "pressure",
        # Also support other formats
        "temp": "temperature",
        "temp_lo": "temp_min",
        "temp_hi": "temp_max",
        "wind_speed_avg": "wind_speed",
        "wind_speed_hi": "wind_gust",
    }
    df = df.rename(columns=col_map)

    # Ensure all expected columns exist and are numeric
    for col in ["temperature", "temp_min", "temp_max", "precipitation", "wind_speed", "wind_gust", "wind_direction", "pressure", "humidity"]:
        if col not in df.columns:
            if col in ["temp_max", "temp_min"] and "temperature" in df.columns:
                df[col] = df["temperature"]
            elif col == "humidity":
                df[col] = 60.0
            else:
                df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(60 if col == "humidity" else 0)

    # Robust timestamp handling
    if "date" in df.columns:
        df["timestamp"] = pd.to_datetime(df["date"], errors="coerce")
    elif "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["timestamp"] = pd.Timestamp.now()

    # Sort by timestamp for rolling features
    df = df.sort_values("timestamp")

    # Derived features
    df["temp_range"] = df["temp_max"] - df["temp_min"]
    df["day_of_year"] = df["timestamp"].dt.dayofyear
    df["month"] = df["timestamp"].dt.month
    df["season"] = ((df["month"] % 12 + 3) // 3)
    df["is_weekend"] = (df["timestamp"].dt.weekday >= 5).astype(int)

    # Humidity estimation if not available
    df["humidity_est"] = np.clip(60 + (df["precipitation"] * 10) - (df["temperature"] - 20) * 2, 0, 100)
    if "humidity" not in df.columns or df["humidity"].isna().all():
        df["humidity"] = df["humidity_est"]
    else:
        df["humidity"] = df["humidity"].fillna(df["humidity_est"])
    
    df["heat_index"] = np.where(df["temperature"] > 25,
                                df["temperature"] + 0.5 * (df["humidity"] - 10),
                                df["temperature"])

    # Rolling features for trends (3-day averages)
    df["precip_rolling_3"] = df["precipitation"].rolling(3, min_periods=1).mean()
    df["temp_rolling_3"] = df["temperature"].rolling(3, min_periods=1).mean()
    df["wind_rolling_3"] = df["wind_speed"].rolling(3, min_periods=1).mean()

    return df

def get_feature_columns(df):
    exclude = {"event", "hazard_level", "label", "timestamp", "date"}
    return [col for col in df.columns if col not in exclude and df[col].dtype in [np.float64, np.int64, np.float32, np.int32]]

# ----------- Model Training & Evaluation -----------

def train_from_csv(csv_path):
    df = pd.read_csv(csv_path)
    df = engineer_features(df)
    # Label with hazard scorer
    df["event"] = df.apply(hazard_score, axis=1)
    feature_cols = get_feature_columns(df)

    # Drop columns with all zeros or all NaNs
    to_drop = []
    for col in feature_cols:
        col_data = df[col]
        if (col_data.isna() | (col_data == 0)).all():
            to_drop.append(col)
    if to_drop:
        logger.info("Dropping columns with all zeros/NaNs: %s", to_drop)
        feature_cols = [col for col in feature_cols if col not in to_drop]

    # Prepare data (keep as arrays for modeling)
    X_all = df[feature_cols].values
    y_all = df["event"].values

    logger.info("✓ Loaded %d days of training data", len(df))
    logger.info("  Features: %d", len(feature_cols))
    logger.info("  Hazard events: %d (%.2f%%)", int(y_all.sum()), y_all.mean()*100)

    # Chronological train/test split (no shuffling)
    X_train, X_test, y_train, y_test = train_test_split(
        X_all, y_all, test_size=MODEL_CONFIG["test_size"],
        random_state=MODEL_CONFIG["random_state"], shuffle=False
    )

    # Adjust selector_k if needed and choose score function
    selector_k = min(MODEL_CONFIG["selector_k"], X_train.shape[1])
    score_func = mutual_info_classif if MODEL_CONFIG["use_mutual_info"] else f_classif

    # Build imblearn pipeline (SMOTE applied inside CV folds)
    imb_pipeline = ImbPipeline([
        ('smote', SMOTE(random_state=MODEL_CONFIG["random_state"])),
        ('scaler', PowerTransformer(method="yeo-johnson", standardize=True)),
        ('selector', SelectKBest(score_func, k=selector_k)),
        ('nb', GaussianNB(var_smoothing=MODEL_CONFIG["nb_var_smoothing"], priors=None))
    ])

    # TimeSeries CV object
    tscv = TimeSeriesSplit(n_splits=MODEL_CONFIG["cv_splits"])

    # Try CV with SMOTE-in-pipeline; if that fails (e.g., not enough positive samples), fall back to no-SMOTE pipeline
    cv_scores = np.array([np.nan])
    best_pipeline = None

    try:
        logger.info("Training partition event rate: %.2f%%", np.mean(y_train) * 100)
        cv_scores = cross_val_score(imb_pipeline, X_train, y_train, cv=tscv, scoring="f1")
        logger.info("CV f1 scores (with SMOTE): %s", cv_scores.tolist())
        best_pipeline = imb_pipeline
    except Exception as e:
        logger.warning("SMOTE pipeline CV failed: %s. Falling back to pipeline without SMOTE.", e)
        # Build pipeline without SMOTE
        pipeline_no_smote = Pipeline([
            ('scaler', PowerTransformer(method="yeo-johnson", standardize=True)),
            ('selector', SelectKBest(score_func, k=selector_k)),
            ('nb', GaussianNB(var_smoothing=MODEL_CONFIG["nb_var_smoothing"], priors=None))
        ])
        try:
            cv_scores = cross_val_score(pipeline_no_smote, X_train, y_train, cv=tscv, scoring="f1")
            logger.info("CV f1 scores (no SMOTE): %s", cv_scores.tolist())
            best_pipeline = pipeline_no_smote
        except Exception as e2:
            logger.error("CV failed for pipeline without SMOTE: %s", e2)
            raise

    # Fit the chosen pipeline on the full training partition
    try:
        best_pipeline.fit(X_train, y_train)
    except Exception as e:
        logger.error("Final pipeline fit failed: %s", e)
        raise

    # Use the fitted pipeline for evaluation and saving
    pipeline = best_pipeline

    # Evaluation on holdout test partition using the trained pipeline
    y_pred = pipeline.predict(X_test)
    acc = pipeline.score(X_test, y_test)
    report = classification_report(y_test, y_pred, output_dict=True)
    confusion = pd.crosstab(y_test, y_pred, rownames=["Actual"], colnames=["Predicted"])

    # Save model + metadata (include additional metrics optionally later)
    joblib.dump(pipeline, MODEL_PATH)
    meta = {
        "feature_columns": feature_cols,
        "accuracy": acc,
        "classification_report": report,
        "confusion_matrix": confusion.to_dict(),
        "cv_mean": float(np.nanmean(cv_scores)),
        "cv_std": float(np.nanstd(cv_scores)),
        "trained_at": datetime.now().isoformat(),
        "training_data_source": "Meteostat (NAIA Station)",
        "training_samples": len(df)
    }
    with open(METADATA_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("✓ Model training complete. Model saved to %s", MODEL_PATH)
    return meta

def predict_from_features(features_dict):
    """Takes weather features dict (parsed from OpenWeather JSON), returns prediction & probability."""
    logger.debug("🔍 predict_from_features called")
    logger.debug("   Input feature keys: %s", list(features_dict.keys()))

    # Load model and metadata
    try:
        pipeline = joblib.load(MODEL_PATH)
        logger.debug("   ✅ Model loaded from %s", MODEL_PATH)
    except Exception as e:
        logger.error("   ❌ Model load failed: %s", e)
        raise

    try:
        with open(METADATA_PATH) as f:
            meta = json.load(f)
        logger.debug("   ✅ Metadata loaded: %d features", len(meta.get('feature_columns', [])))
    except Exception as e:
        logger.error("   ❌ Metadata load failed: %s", e)
        raise

    feature_cols = meta["feature_columns"]
    logger.debug("   Expected features preview: %s", feature_cols[:5])

    df = pd.DataFrame([features_dict])
    logger.debug("   ✅ DataFrame created: %s", df.shape)

    df = engineer_features(df)
    logger.debug("   ✅ Features engineered: %s", df.shape)

    # Strict validation: ensure all expected feature columns exist and are numeric
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        logger.error("Missing required feature columns: %s", missing)
        raise ValueError(f"Missing required feature columns: {missing}")

    # Ensure numeric dtype and finite values
    for c in feature_cols:
        if not pd.api.types.is_numeric_dtype(df[c]):
            try:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            except Exception:
                logger.error("Feature %s cannot be coerced to numeric", c)
                raise

        if not np.all(np.isfinite(df[c].values)):
            logger.error("Feature %s contains non-finite values after coercion", c)
            raise ValueError(f"Feature {c} contains non-finite values")

    X = df[feature_cols].values
    logger.debug("   ✅ Feature matrix prepared: %s", X.shape)

    try:
        pred = pipeline.predict(X)[0]
        proba = pipeline.predict_proba(X)[0].tolist()
        logger.info("   ✅ ML Prediction: event=%s, probability=%.3f", pred, proba[1])
    except Exception as e:
        logger.error("   ❌ Prediction failed: %s", e)
        raise

    event, hazards = hazard_score(features_dict, explain=True)
    hazard_type = determine_hazard_type(hazards) if event else "None"
    logger.debug("   Rules: event=%s, hazard_type=%s", event, hazard_type)

    if pred and not hazards:
        hazard_type = "General Hazard (AI detected, not matched to rules)"

    result = {
        "event": int(pred),
        "probability": proba[1],
        "probabilities": {"no_event": proba[0], "event": proba[1]},
        "features_used": feature_cols,
        "hazards_triggered": hazards if event else [],
        "hazard_type": hazard_type
    }

    return result

# Replace the existing features_from_openweather_json function in scripts/model.py with the version below.
# Also add the helper function _to_celsius_if_needed near the top of the file (below imports).

def _to_celsius_if_needed(temp):
    """
    Convert a temperature value to Celsius if it looks like Kelvin.

    Heuristic:
    - If temp is None -> return None
    - If numeric value > 200 -> assume Kelvin and convert to Celsius
    - Otherwise assume the value is already Celsius
    """
    if temp is None:
        return None
    try:
        t = float(temp)
    except (TypeError, ValueError):
        return None

    # Kelvin values will be >> 200 (e.g., ~273-320). Celsius values are typically within -100..+100
    return t - 273.15 if t > 200.0 else t


def features_from_openweather_json(weather_json):
    """Parses OpenWeather API JSON to model feature dict (robust to metric/Kelvin differences)."""
    main = weather_json.get("main", {}) or {}
    wind = weather_json.get("wind", {}) or {}
    rain = weather_json.get("rain", {}) or {}
    snow = weather_json.get("snow", {}) or {}
    dt = weather_json.get("dt", None)
    timestamp = pd.to_datetime(dt, unit="s") if dt else pd.Timestamp.now()

    # Try to obtain temps; don't assume units — convert only if they look like Kelvin
    temp_val = main.get("temp", None)
    temp_min_val = main.get("temp_min", None)
    temp_max_val = main.get("temp_max", None)

    temp_c = _to_celsius_if_needed(temp_val)
    temp_min_c = _to_celsius_if_needed(temp_min_val)
    temp_max_c = _to_celsius_if_needed(temp_max_val)

    # Fallback logic to ensure we have reasonable numeric values
    if temp_c is None and temp_min_c is not None:
        temp_c = temp_min_c
    if temp_c is None and temp_max_c is not None:
        temp_c = temp_max_c
    if temp_min_c is None and temp_c is not None:
        temp_min_c = temp_c
    if temp_max_c is None and temp_c is not None:
        temp_max_c = temp_c

    # Final conservative defaults (avoid absurd missing data causing exceptions)
    temperature = temp_c if temp_c is not None else 0.0
    temp_min = temp_min_c if temp_min_c is not None else temperature
    temp_max = temp_max_c if temp_max_c is not None else temperature

    features = {
        "temperature": temperature,
        "temp_min": temp_min,
        "temp_max": temp_max,
        "pressure": main.get("pressure", 1013),
        "humidity": main.get("humidity", 60),
        "wind_speed": wind.get("speed", 0),
        "wind_gust": wind.get("gust", wind.get("speed", 0)),
        "wind_direction": wind.get("deg", 180),
        "precipitation": float(rain.get("1h", 0) or 0) + float(snow.get("1h", 0) or 0),
        "timestamp": timestamp
    }
    return features
