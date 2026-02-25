"""
Weather Hazard Prediction API Endpoints
ML-based weather hazard prediction and forecasting
"""

from fastapi import APIRouter, HTTPException, status, Query
from typing import Optional
from datetime import datetime

from backend.models.prediction import (
    PredictionRequest,
    PredictionResponse,
    ForecastPredictionRequest,
    ForecastPredictionResponse,
    ForecastSummary,
    ModelInfo,
    HealthCheckResponse,
    CustomFeaturesRequest
)
from backend.ml.predictor import WeatherPredictor
from backend.ml.multi_hazard_predictor import MultiHazardPredictor
from backend.ml.multi_model_manager import MultiModelManager
from backend.ml.hazard_analyzer import HazardAnalyzer
from backend.services.alert_dispatcher import get_alert_dispatcher
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/predictions", tags=["Weather Predictions"])

# Legacy predictor kept for /predict-custom and /forecast endpoints
predictor = WeatherPredictor()

# Primary multi-hazard predictor for /predict endpoint
multi_predictor = MultiHazardPredictor()

# Hazard priority mapping: lower value = higher priority
# Order: severe_storm > thunderstorm > heavy_rain > heat_stress
_HAZARD_PRIORITY = {"severe_storm": 0, "thunderstorm": 1, "heavy_rain": 2, "heat_stress": 3}

# Default time horizon (hours) used when dispatching legacy-format prediction alerts
_DEFAULT_LEGACY_HORIZON = 24

# Map legacy hazard_type strings to multi-hazard keys
_HAZARD_TYPE_DISPLAY = {
    "heat_stress": "Heat Stress",
    "heavy_rain": "Heavy Rain",
    "thunderstorm": "Thunderstorm",
    "severe_storm": "Severe Storm",
}


def _map_legacy_hazard_to_key(hazard_type: str) -> str:
    """Map a legacy hazard_type string to a multi-hazard key for AlertDispatcher."""
    h = hazard_type.lower()
    if any(k in h for k in ("severe", "typhoon", "cyclone")):
        return "severe_storm"
    if "thunder" in h:
        return "thunderstorm"
    if any(k in h for k in ("rain", "flood")):
        return "heavy_rain"
    if "heat" in h:
        return "heat_stress"
    logger.warning(
        f"Could not map legacy hazard_type '{hazard_type}' to a multi-hazard key; "
        "defaulting to 'thunderstorm'"
    )
    return "thunderstorm"  # safe default


def _dispatch_legacy_alert(prediction: dict):
    """
    Dispatch a Semaphore SMS alert for a legacy-format prediction.
    Uses AlertDispatcher (with throttling and DB logging).
    """
    try:
        hazard_key = _map_legacy_hazard_to_key(prediction.get("hazard_type", ""))
        probability = float(prediction.get("probability") or 0.5)
        dispatcher = get_alert_dispatcher()
        dispatcher.dispatch_single_hazard(
            hazard=hazard_key,
            horizon=_DEFAULT_LEGACY_HORIZON,
            probability=probability,
        )
    except Exception as e:
        logger.error(f"Failed to dispatch legacy hazard alert: {e}", exc_info=True)


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Check multi-hazard ML model readiness (4 hazards × 3 horizons = 12 models).

    Returns per-model availability and overall readiness status.
    If models are missing, status is 'not_ready' with instructions to train them.
    """
    try:
        model_manager = MultiModelManager()
        model_status = model_manager.get_model_status()

        ready = model_status["ready"]
        available = model_status["available_count"]
        total = model_status["total_expected"]

        message = (
            None
            if ready
            else (
                f"{available}/{total} models available. "
                "Run: python scripts/train_multi_models.py --csv training_data.csv"
            )
        )

        return HealthCheckResponse(
            success=True,
            status="ready" if ready else "not_ready",
            model_ready=ready,
            message=message,
            multi_model_status=model_status,
            timestamp=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}",
        )


@router.post("/predict", response_model=PredictionResponse)
async def predict_from_weather_data(request: PredictionRequest):
    """
    Predict weather hazards from raw weather API data using the multi-hazard system.

    Returns predictions for heat_stress / heavy_rain / thunderstorm / severe_storm
    across 12h / 24h / 48h horizons, plus backwards-compatible summary fields.

    ✅ Sends Semaphore SMS alerts (with throttling) when hazards are detected.
    ✅ Returns HTTP 503 with instructions when models have not been trained yet.
    """
    try:
        # Validate source
        if request.source not in ("openweather", "weatherlink"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid source: {request.source}. Use 'openweather' or 'weatherlink'",
            )

        # Guard: require at least some models to be ready
        model_info = multi_predictor.get_model_info()
        if model_info.get("available_count", 0) == 0:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "Multi-hazard models have not been trained yet.",
                    "next_steps": (
                        "Run: python scripts/train_multi_models.py --csv training_data.csv"
                    ),
                    "models_available": 0,
                    "models_expected": model_info.get("total_expected", 12),
                },
            )

        # Run multi-hazard prediction
        results = multi_predictor.predict_from_weather_data(
            request.weather_data, source=request.source
        )

        if not results.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Prediction failed: {results.get('error', 'Unknown error')}",
            )

        # ── Derive backwards-compatible fields ──────────────────────────────
        detected_hazards = []
        for hazard, horizons in results.get("predictions", {}).items():
            for horizon_key, pred_info in horizons.items():
                if pred_info.get("hazard_detected") and pred_info.get("available"):
                    detected_hazards.append({
                        "hazard": hazard,
                        "horizon": int(horizon_key.replace("h", "")),
                        "probability": pred_info.get("probability", 0.0),
                    })

        event = 1 if detected_hazards else 0

        if detected_hazards:
            sorted_h = sorted(
                detected_hazards,
                key=lambda h: (_HAZARD_PRIORITY.get(h["hazard"], 99), -h["probability"]),
            )
            top = sorted_h[0]
            hazard_type = _HAZARD_TYPE_DISPLAY.get(
                top["hazard"], top["hazard"].replace("_", " ").title()
            )
            probability = top["probability"]
            hazards_list = list({h["hazard"].replace("_", " ") for h in detected_hazards})
        else:
            hazard_type = "None"
            probability = 0.0
            hazards_list = []

        risk_level = multi_predictor.get_risk_level(results)

        prediction = {
            "event": event,
            "probability": probability,
            "hazard_type": hazard_type,
            "hazards": hazards_list,
            "timestamp": results.get("timestamp"),
            "risk_level": risk_level,
        }

        # Get notification template for backwards compatibility
        hazard_info = HazardAnalyzer.get_hazard_info(hazard_type)

        logger.info(
            f"Multi-hazard prediction: event={event}, "
            f"top_hazard={hazard_type}, risk={risk_level}, "
            f"detected={len(detected_hazards)}"
        )

        # ✅ Dispatch Semaphore SMS alerts when hazards detected
        if event == 1:
            try:
                logger.info(f"🚨 {len(detected_hazards)} hazard(s) detected. Dispatching alerts...")
                dispatcher = get_alert_dispatcher()
                dispatch_result = dispatcher.dispatch_from_predictions(results)
                logger.info(f"✅ Alert dispatch complete: {dispatch_result}")
            except Exception as notify_error:
                logger.error(
                    f"❌ Failed to dispatch notifications: {notify_error}", exc_info=True
                )
                # Never fail the prediction request due to notification errors
        else:
            logger.info("ℹ️ No hazards detected, skipping notifications")

        return PredictionResponse(
            success=True,
            prediction=prediction,
            notification=hazard_info,
            multi_hazard=results,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {str(e)}",
        )


@router.post("/predict-custom", response_model=PredictionResponse)
async def predict_from_custom_features(request: CustomFeaturesRequest):
    """
    Predict weather hazards from custom weather features
    Sends Semaphore SMS notification when hazard detected (event == 1)
    """
    try:
        # Convert Pydantic model to dict (Pydantic v2)
        features = request.features.model_dump()
        features["timestamp"] = datetime.utcnow()

        # Make prediction
        prediction = predictor.predict(features)
        prediction["risk_level"] = HazardAnalyzer.get_risk_level(prediction)

        # Get notification template
        hazard_info = HazardAnalyzer.get_hazard_info(prediction["hazard_type"])

        logger.info(
            f"Custom prediction: {prediction['hazard_type']} "
            f"(event={prediction.get('event')}, risk={prediction['risk_level']})"
        )

        # ✅ Send Semaphore notification if hazard detected
        if prediction.get("event") == 1:
            try:
                logger.info("🚨 Hazard detected! Dispatching Semaphore notification...")
                _dispatch_legacy_alert(prediction)
                logger.info("✅ Notification dispatched")
            except Exception as notify_error:
                logger.error(f"❌ Failed to dispatch notifications: {notify_error}", exc_info=True)
        else:
            logger.info("ℹ️ No hazard detected, skipping notifications")

        return PredictionResponse(
            success=True,
            prediction=prediction,
            notification=hazard_info,
            features=request.features.model_dump(),
        )

    except Exception as e:
        logger.error(f"Custom prediction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {str(e)}",
        )


@router.post("/forecast", response_model=ForecastPredictionResponse)
async def predict_forecast(request: ForecastPredictionRequest):
    """
    Predict hazards for multiple forecast time points

    Analyzes a list of weather forecasts and predicts hazards
    ✅ SENDS SEMAPHORE NOTIFICATION FOR FORECAST HAZARDS
    """
    try:
        # Make batch predictions
        predictions = predictor.predict_batch(request.forecasts, request.source)

        # Count hazard events
        hazard_events = [p for p in predictions if p["prediction"]["event"] == 1]

        # Add risk levels and notifications
        for pred in predictions:
            pred["prediction"]["risk_level"] = HazardAnalyzer.get_risk_level(pred["prediction"])
            pred["notification"] = HazardAnalyzer.get_hazard_info(pred["prediction"]["hazard_type"])

        # Create summary
        summary = _create_forecast_summary(predictions, hazard_events)

        logger.info(f"Forecast predictions: {len(hazard_events)}/{len(predictions)} hazard events")

        # ✅ Send Semaphore notification for forecast hazards
        if hazard_events:
            try:
                first_hazard = hazard_events[0]["prediction"]
                logger.info(
                    f"🚨 Forecast hazards detected ({len(hazard_events)}). "
                    f"Dispatching Semaphore notification..."
                )
                _dispatch_legacy_alert(first_hazard)
                logger.info("✅ Forecast notification dispatched")
            except Exception as notify_error:
                logger.error(
                    f"❌ Failed to dispatch forecast notifications: {notify_error}", exc_info=True
                )
        else:
            logger.info("ℹ️ No forecast hazards detected, skipping notifications")

        return ForecastPredictionResponse(
            success=True,
            total_predictions=len(predictions),
            hazard_events=len(hazard_events),
            predictions=predictions,
            summary=summary,
        )

    except Exception as e:
        logger.error(f"Forecast prediction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Forecast prediction failed: {str(e)}",
        )


@router.get("/forecast/summary", response_model=ForecastSummary)
async def get_forecast_summary(
    source: str = Query(default="openweather", description="Weather data source"),
    hours: int = Query(
        default=120, description="Forecast duration in hours (default 120 = 5 days)"
    ),
):
    """
    Get summary of hazards in upcoming forecast period

    Fetches forecast from OpenWeather API and summarizes hazards
    """
    try:
        from backend.ml.weather_client import OpenWeatherClient

        # Fetch forecast
        client = OpenWeatherClient()
        cnt = min(hours // 3, 40)  # OpenWeather gives 3-hour intervals, max 40 points
        forecasts = client.get_forecast(cnt=cnt)

        # Make predictions
        predictions = predictor.predict_batch(forecasts, source)

        # Filter hazard events
        hazard_events = [p for p in predictions if p["prediction"]["event"] == 1]

        # Add risk levels
        for pred in hazard_events:
            pred["prediction"]["risk_level"] = HazardAnalyzer.get_risk_level(pred["prediction"])

        # Create summary
        summary = _create_forecast_summary(predictions, hazard_events)

        return ForecastSummary(**summary)

    except Exception as e:
        logger.error(f"Forecast summary failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Forecast summary failed: {str(e)}",
        )


@router.get("/model/info", response_model=ModelInfo)
async def get_model_info():
    """
    Get multi-hazard ML model information.

    Returns aggregate readiness across all 12 hazard/horizon combinations.
    """
    try:
        model_info = multi_predictor.get_model_info()

        if model_info.get("available_count", 0) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "No models trained yet. "
                    "Run: python scripts/train_multi_models.py --csv training_data.csv"
                ),
            )

        # Aggregate accuracy across available models
        accuracies = [
            m.get("accuracy")
            for m in model_info.get("models", {}).values()
            if m.get("available") and m.get("accuracy") is not None
        ]
        avg_accuracy = sum(accuracies) / len(accuracies) if accuracies else None

        # Use earliest trained_at as reference
        trained_ats = [
            m.get("trained_at")
            for m in model_info.get("models", {}).values()
            if m.get("available") and m.get("trained_at")
        ]
        trained_at = min(trained_ats) if trained_ats else None

        return ModelInfo(
            ready=model_info.get("ready", False),
            trained_at=trained_at,
            accuracy=avg_accuracy,
            cv_mean=None,
            cv_std=None,
            features_count=None,
            model_path=model_info.get("models_dir"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get model info: {str(e)}",
        )


def _create_forecast_summary(predictions: list, hazard_events: list) -> dict:
    """Create summary of forecast predictions"""

    # Get unique hazard types
    hazard_types = list(
        set([
            p["prediction"]["hazard_type"]
            for p in hazard_events
            if p["prediction"]["hazard_type"] != "None"
        ])
    )

    # Count high-risk events
    high_risk_count = len([
        p
        for p in hazard_events
        if HazardAnalyzer.get_risk_level(p["prediction"]) in ["high", "critical"]
    ])

    # Get next hazard
    next_hazard = hazard_events[0] if hazard_events else None

    # Create timeline of hazard events
    timeline = [
        {
            "timestamp": p["timestamp"],
            "hazard_type": p["prediction"]["hazard_type"],
            "risk_level": HazardAnalyzer.get_risk_level(p["prediction"]),
            "probability": p["prediction"]["probability"],
        }
        for p in hazard_events
    ]

    return {
        "total_records": len(predictions),
        "hazard_events_count": len(hazard_events),
        "hazard_types": hazard_types,
        "high_risk_count": high_risk_count,
        "next_hazard": next_hazard,
        "timeline": timeline,
    }