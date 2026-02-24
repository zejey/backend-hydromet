"""
Weather Hazard Prediction API Endpoints
ML-based weather hazard prediction and forecasting

Now supports multi-hazard/multi-horizon Naive Bayes system with:
- 4 hazard types: heat, heavy_rain, thunderstorm, severe_storm
- 3 horizons: 12h, 24h, 48h
- Semaphore SMS integration with throttling
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
from backend.ml.hazard_analyzer import HazardAnalyzer
from backend.ml.multi_model_manager import MultiModelManager
from backend.services.alert_dispatcher import AlertDispatcher
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/predictions", tags=["Weather Predictions"])

# Initialize predictors
predictor = WeatherPredictor()  # Legacy predictor for fallback
multi_hazard_predictor = MultiHazardPredictor()  # New multi-hazard system
alert_dispatcher = AlertDispatcher()  # Semaphore SMS alerts


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Check if ML models are ready and get model information
    
    Returns multi-model status for all 12 hazard/horizon combinations
    """
    try:
        model_manager = MultiModelManager()
        model_status = model_manager.get_model_status()
        
        # Build response
        status_str = "ready" if model_status["ready"] else "not_ready"
        
        # Get aggregated model info if any models are available
        model_info = None
        if model_status["available_count"] > 0:
            aggregated = model_manager.get_aggregated_info()
            model_info = ModelInfo(
                ready=True,
                trained_at=aggregated.get("earliest_trained_at"),
                accuracy=aggregated.get("avg_accuracy"),
                features_count=None,
                model_path=None
            )
        
        return HealthCheckResponse(
            success=True,
            status=status_str,
            model_ready=model_status["ready"],
            model_info=model_info,
            timestamp=datetime.utcnow().isoformat(),
            message=model_status.get("message"),
            multi_model_status={
                "total_models": model_status["total_models"],
                "available_count": model_status["available_count"],
                "models": model_status["models"]
            }
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}"
        )


@router.post("/predict", response_model=PredictionResponse)
async def predict_from_weather_data(request: PredictionRequest):
    """
    Predict weather hazards from raw weather API data
    
    Uses multi-hazard/multi-horizon system with backwards-compatible output.
    Sends SMS alerts via Semaphore with throttling.
    
    Request Body:
    {
        "weather_data": {...},  // Raw API response
        "source": "openweather"  // or "weatherlink"
    }
    
    Response:
    {
        "success": true,
        "prediction": {
            "event": 1,
            "probability": 0.87,
            "hazard_type": "Severe Storm",
            "hazards": ["severe_storm", "heavy_rain"],
            "risk_level": "critical"
        },
        "multi_hazard": {
            "predictions": {
                "severe_storm": { "12h": {...}, "24h": {...}, "48h": {...} },
                "thunderstorm": {...},
                ...
            },
            "summary": { "total_hazards_detected": 3, "highest_risk_hazard": {...} }
        }
    }
    """
    try:
        # Extract features based on source
        if request.source == "openweather":
            features = predictor.extract_features_from_openweather(request.weather_data)
        elif request.source == "weatherlink":
            features = predictor.extract_features_from_weatherlink(request.weather_data)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid source: {request.source}. Use 'openweather' or 'weatherlink'"
            )
        
        # Check multi-hazard model availability
        model_manager = MultiModelManager()
        model_status = model_manager.get_model_status()
        
        if model_status["available_count"] == 0:
            # No models available - return 503
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "ML models not ready",
                    "training_required": True,
                    "instructions": model_status.get("message")
                }
            )
        
        # Make multi-hazard prediction
        multi_hazard_result = multi_hazard_predictor.predict(features)
        
        # Get backwards-compatible prediction
        prediction = multi_hazard_predictor.get_backwards_compatible_prediction(multi_hazard_result)
        
        # Add timestamp
        prediction["timestamp"] = features.get("timestamp").isoformat() if features.get("timestamp") else datetime.utcnow().isoformat()
        
        # Get notification template
        hazard_info = HazardAnalyzer.get_hazard_info(prediction["hazard_type"])
        
        logger.info(f"Multi-hazard prediction: {prediction['hazard_type']} (risk={prediction['risk_level']})")
        
        # Dispatch SMS alert if hazard detected
        if prediction.get("event") == 1:
            try:
                summary = multi_hazard_result.get("summary", {})
                total_hazards = summary.get("total_hazards_detected", 0)
                
                logger.info(f"🚨 {total_hazards} hazard(s) detected! Dispatching alerts...")
                
                # Build alert message
                alert_message = hazard_info.get(
                    "sms", 
                    f"Weather hazard detected: {prediction['hazard_type']}"
                )
                
                # Dispatch via AlertDispatcher (includes throttling)
                alert_result = alert_dispatcher.dispatch_alert(
                    hazard_type=prediction["hazard_type"].lower().replace(" ", "_"),
                    risk_level=prediction["risk_level"],
                    message=alert_message,
                    title=hazard_info.get("title", f"⚠️ {prediction['hazard_type']} Alert")
                )
                
                if alert_result.get("success"):
                    logger.info(f"✅ Alert dispatched to {alert_result.get('recipients_count', 0)} recipients")
                elif alert_result.get("reason") == "throttled":
                    logger.info("ℹ️ Alert throttled (cooldown active)")
                else:
                    logger.warning(f"⚠️ Alert dispatch failed: {alert_result.get('reason')}")
                    
            except Exception as notify_error:
                logger.error(f"❌ Failed to dispatch alert: {notify_error}", exc_info=True)
        else:
            logger.info("ℹ️ No hazard detected, skipping alerts")
        
        return PredictionResponse(
            success=True,
            prediction=prediction,
            notification=hazard_info,
            multi_hazard=multi_hazard_result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {str(e)}"
        )


@router.post("/predict-custom", response_model=PredictionResponse)
async def predict_from_custom_features(request: CustomFeaturesRequest):
    """
    Predict weather hazards from custom weather features
    
    Use this when you have specific weather measurements.
    Uses multi-hazard system with Semaphore SMS alerts.
    
    Request Body:
    {
        "features": {
            "temp_c": 28.5,
            "pressure_hpa": 1005,
            "humidity_pct": 85,
            "wind_speed_ms": 15,
            "precipitation_mm": 50
        }
    }
    """
    try:
        # Convert Pydantic model to dict
        features = request.features.dict()
        features["timestamp"] = datetime.utcnow()
        
        # Make multi-hazard prediction
        multi_hazard_result = multi_hazard_predictor.predict(features)
        
        # Get backwards-compatible prediction
        prediction = multi_hazard_predictor.get_backwards_compatible_prediction(multi_hazard_result)
        prediction["timestamp"] = datetime.utcnow().isoformat()
        
        # Get notification template
        hazard_info = HazardAnalyzer.get_hazard_info(prediction["hazard_type"])
        
        logger.info(f"Custom prediction: {prediction['hazard_type']} (risk={prediction['risk_level']})")
        
        # Dispatch SMS alert if hazard detected
        if prediction.get("event") == 1:
            try:
                logger.info(f"🚨 Hazard detected! Dispatching alert...")
                
                alert_result = alert_dispatcher.dispatch_alert(
                    hazard_type=prediction["hazard_type"].lower().replace(" ", "_"),
                    risk_level=prediction["risk_level"],
                    message=hazard_info.get("sms", f"Weather hazard: {prediction['hazard_type']}"),
                    title=hazard_info.get("title")
                )
                
                if alert_result.get("success"):
                    logger.info("✅ Alert dispatched")
                elif alert_result.get("reason") == "throttled":
                    logger.info("ℹ️ Alert throttled")
                    
            except Exception as notify_error:
                logger.error(f"❌ Failed to dispatch alert: {notify_error}", exc_info=True)
        else:
            logger.info("ℹ️ No hazard detected, skipping alerts")
        
        return PredictionResponse(
            success=True,
            prediction=prediction,
            notification=hazard_info,
            features=request.features,
            multi_hazard=multi_hazard_result
        )
        
    except Exception as e:
        logger.error(f"Custom prediction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {str(e)}"
        )


@router.post("/forecast", response_model=ForecastPredictionResponse)
async def predict_forecast(request: ForecastPredictionRequest):
    """
    Predict hazards for multiple forecast time points
    
    Analyzes a list of weather forecasts and predicts hazards.
    Uses Semaphore SMS for alerts with throttling.
    
    Request Body:
    {
        "forecasts": [
            {...},  // OpenWeather forecast data point 1
            {...},  // OpenWeather forecast data point 2
            ...
        ],
        "source": "openweather"
    }
    
    Response includes:
    - Total predictions
    - Number of hazard events
    - List of all predictions
    - Summary of hazards
    """
    try:
        # Make batch predictions using legacy predictor for forecast
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
        
        # Dispatch alert for forecast hazards
        if hazard_events:
            try:
                first_hazard = hazard_events[0]["prediction"]
                
                logger.info(f"🚨 {len(hazard_events)} forecast hazard(s) detected!")
                
                # Build hazards list for multi-hazard alert
                hazards_for_alert = [
                    {
                        "hazard_type": h["prediction"]["hazard_type"].lower().replace(" ", "_"),
                        "risk_level": h["prediction"]["risk_level"],
                        "probability": h["prediction"].get("probability", 0)
                    }
                    for h in hazard_events[:5]  # Limit to top 5
                ]
                
                alert_result = alert_dispatcher.dispatch_multi_hazard_alert(hazards_for_alert)
                
                if alert_result.get("success"):
                    logger.info("✅ Forecast alert dispatched")
                elif alert_result.get("reason") == "throttled":
                    logger.info("ℹ️ Forecast alert throttled")
                    
            except Exception as notify_error:
                logger.error(f"❌ Failed to dispatch forecast alert: {notify_error}", exc_info=True)
        else:
            logger.info("ℹ️ No forecast hazards detected, skipping alerts")
        
        return ForecastPredictionResponse(
            success=True,
            total_predictions=len(predictions),
            hazard_events=len(hazard_events),
            predictions=predictions,
            summary=summary
        )
        
    except Exception as e:
        logger.error(f"Forecast prediction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Forecast prediction failed: {str(e)}"
        )


@router.get("/forecast/summary", response_model=ForecastSummary)
async def get_forecast_summary(
    source: str = Query(default="openweather", description="Weather data source"),
    hours: int = Query(default=120, description="Forecast duration in hours (default 120 = 5 days)")
):
    """
    Get summary of hazards in upcoming forecast period
    
    Fetches forecast from OpenWeather API and summarizes hazards
    
    Query Parameters:
    - source: "openweather" or "weatherlink"
    - hours: Forecast duration (default 120 hours = 5 days)
    
    Response:
    {
        "total_records": 40,
        "hazard_events_count": 5,
        "hazard_types": ["Flood Risk", "Windstorm"],
        "high_risk_count": 2,
        "next_hazard": {...},
        "timeline": [...]
    }
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
            detail=f"Forecast summary failed: {str(e)}"
        )


@router.get("/model/info", response_model=ModelInfo)
async def get_model_info():
    """
    Get detailed ML model information
    
    Returns aggregated info across all available multi-hazard models:
    - Average accuracy
    - Earliest training timestamp
    - Available model count
    """
    try:
        model_info = multi_hazard_predictor.get_model_info()
        
        if not model_info.get("ready"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=model_info.get("message", "Models not trained yet. Please train the models first.")
            )
        
        return ModelInfo(
            ready=True,
            trained_at=model_info.get("earliest_trained_at"),
            accuracy=model_info.get("avg_accuracy"),
            features_count=model_info.get("available_count"),
            model_path=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get model info: {str(e)}"
        )


def _create_forecast_summary(predictions: list, hazard_events: list) -> dict:
    """Create summary of forecast predictions"""
    
    # Get unique hazard types
    hazard_types = list(set([
        p["prediction"]["hazard_type"] 
        for p in hazard_events 
        if p["prediction"]["hazard_type"] != "None"
    ]))
    
    # Count high-risk events
    high_risk_count = len([
        p for p in hazard_events 
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
            "probability": p["prediction"]["probability"]
        }
        for p in hazard_events
    ]
    
    return {
        "total_records": len(predictions),
        "hazard_events_count": len(hazard_events),
        "hazard_types": hazard_types,
        "high_risk_count": high_risk_count,
        "next_hazard": next_hazard,
        "timeline": timeline
    }
