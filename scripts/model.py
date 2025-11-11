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

from config import HAZARD_THRESHOLDS, MODEL_CONFIG, MODEL_PATH, METADATA_PATH
from hazard_type_mapping import determine_hazard_type
from notification_mapping import hazard_notification_templates
from notification_util import NotificationService

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
        print("Dropping columns with all zeros/NaNs:", to_drop)
        feature_cols = [col for col in feature_cols if col not in to_drop]

    # Prepare data
    X = df[feature_cols].values
    y = df["event"].values

    print(f"\n✓ Loaded {len(df)} days of training data")
    print(f"  Features: {len(feature_cols)}")
    print(f"  Hazard events: {y.sum()} ({y.mean()*100:.1f}%)")

    # Handle imbalance with SMOTE if events < 30%
    event_rate = np.mean(y)
    if event_rate < 0.3:
        print(f"⚠ Dataset imbalanced (event rate: {event_rate:.2%}), applying SMOTE")
        smote = SMOTE(random_state=MODEL_CONFIG["random_state"])
        X, y = smote.fit_resample(X, y)
        print(f"✓ After SMOTE: {len(y)} samples")

    # Adjust selector_k if needed
    selector_k = min(MODEL_CONFIG["selector_k"], X.shape[1])
    score_func = mutual_info_classif if MODEL_CONFIG["use_mutual_info"] else f_classif
    # Set priors for NB to balance
    priors = [1 - event_rate, event_rate] if event_rate > 0 else None
    pipeline = Pipeline([
        ("scaler", PowerTransformer(method="yeo-johnson", standardize=True)),
        ("selector", SelectKBest(score_func, k=selector_k)),
        ("classifier", GaussianNB(var_smoothing=MODEL_CONFIG["nb_var_smoothing"], priors=priors))
    ])

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=MODEL_CONFIG["test_size"],
        random_state=MODEL_CONFIG["random_state"], shuffle=False
    )
    pipeline.fit(X_train, y_train)

    # Evaluation
    y_pred = pipeline.predict(X_test)
    acc = pipeline.score(X_test, y_test)
    report = classification_report(y_test, y_pred, output_dict=True)
    confusion = pd.crosstab(y_test, y_pred, rownames=["Actual"], colnames=["Predicted"])
    # Cross-validation with F1
    tscv = TimeSeriesSplit(n_splits=MODEL_CONFIG["cv_splits"])
    cv_scores = cross_val_score(pipeline, X_train, y_train, cv=tscv, scoring="f1")

    # Save model + metadata
    joblib.dump(pipeline, MODEL_PATH)
    meta = {
        "feature_columns": feature_cols,
        "accuracy": acc,
        "classification_report": report,
        "confusion_matrix": confusion.to_dict(),
        "cv_mean": float(np.mean(cv_scores)),
        "cv_std": float(np.std(cv_scores)),
        "trained_at": datetime.now().isoformat(),
        "training_data_source": "Meteostat (NAIA Station)",
        "training_samples": len(df)
    }
    with open(METADATA_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    return meta

def predict_from_features(features_dict):
    """Takes weather features dict (parsed from OpenWeather JSON), returns prediction & probability."""
    print(f"\n🔍 DEBUG: predict_from_features called")
    print(f"   Features: {list(features_dict.keys())}")
    
    # Load model and metadata
    try:
        pipeline = joblib.load(MODEL_PATH)
        print(f"   ✅ Model loaded from {MODEL_PATH}")
    except Exception as e:
        print(f"   ❌ Model load failed: {e}")
        raise
    
    try:
        with open(METADATA_PATH) as f:
            meta = json.load(f)
        print(f"   ✅ Metadata loaded: {len(meta.get('feature_columns', []))} features")
    except Exception as e:
        print(f"   ❌ Metadata load failed: {e}")
        raise
    
    feature_cols = meta["feature_columns"]
    print(f"   Expected features: {feature_cols[:5]}...")  # Show first 5

    df = pd.DataFrame([features_dict])
    print(f"   ✅ DataFrame created: {df.shape}")
    
    df = engineer_features(df)
    print(f"   ✅ Features engineered: {df.shape}")
    
    for col in feature_cols:
        if col not in df.columns:
            df[col] = 60.0 if col == "humidity" else 0.0
    
    X = df[feature_cols].values
    print(f"   ✅ Feature matrix: {X.shape}")

    try:
        pred = pipeline.predict(X)[0]
        proba = pipeline.predict_proba(X)[0].tolist()
        print(f"   ✅ ML Prediction: event={pred}, probability={proba[1]:.2f}")
    except Exception as e:
        print(f"   ❌ Prediction failed: {e}")
        raise

    event, hazards = hazard_score(features_dict, explain=True)
    hazard_type = determine_hazard_type(hazards) if event else "None"
    print(f"   Rules: event={event}, hazard_type={hazard_type}")

    # Fallback: If the MODEL predicts an event, but the rules don't trigger any hazard
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
    
    print(f"   ✅ Final result: {result['event']}, {result['hazard_type']}, {result['probability']:.2f}")
    
    # ✅ SEND NOTIFICATION IF HAZARD
    if int(pred) == 1 and hazard_type in hazard_notification_templates:
        print(f"   📧 Sending notification for {hazard_type}")
        template = hazard_notification_templates[hazard_type]

        notif_service = NotificationService()

        notif_service.send_notification(
            title=template["in_app"]["title"],
            message=template["in_app"]["message"],
            notif_type="Alert",
            status="Active",
            send_sms=True,
            sms_recipients=None
        )
    else:
        print(f"   ℹ️  No notification sent (pred={pred}, hazard_type={hazard_type})")

    return result

def features_from_openweather_json(weather_json):
    """Parses OpenWeather API JSON to model feature dict."""
    main = weather_json.get("main", {})
    wind = weather_json.get("wind", {})
    rain = weather_json.get("rain", {})
    snow = weather_json.get("snow", {})
    dt = weather_json.get("dt", None)
    timestamp = pd.to_datetime(dt, unit="s") if dt else pd.Timestamp.now()

    # Convert Kelvin to Celsius if needed
    temp_k = main.get("temp", 298)
    temp_min_k = main.get("temp_min", 298)
    temp_max_k = main.get("temp_max", 298)

    features = {
        "temperature": temp_k - 273.15,  # Kelvin to Celsius
        "temp_min": temp_min_k - 273.15,
        "temp_max": temp_max_k - 273.15,
        "pressure": main.get("pressure", 1013),
        "humidity": main.get("humidity", 60),
        "wind_speed": wind.get("speed", 0),
        "wind_gust": wind.get("gust", wind.get("speed", 0)),
        "wind_direction": wind.get("deg", 180),
        "precipitation": rain.get("1h", 0) + snow.get("1h", 0),
        "timestamp": timestamp
    }
    return features