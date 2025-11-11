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
from backend.ml.hazard_analyzer import HazardAnalyzer
from backend.ml.model_manager import ModelManager
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/predictions", tags=["Weather Predictions"])

# Initialize predictor
predictor = WeatherPredictor()


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Check if ML model is ready and get model information
    
    Returns model metadata and readiness status
    """
    try:
        model_manager = ModelManager()
        model_info_dict = model_manager.get_model_info()
        
        return HealthCheckResponse(
            success=True,
            status="ready" if model_info_dict["ready"] else "not_ready",
            model_ready=model_info_dict["ready"],
            model_info=ModelInfo(**model_info_dict) if model_info_dict["ready"] else None,
            timestamp=datetime.utcnow().isoformat()
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
    
    Supports both OpenWeather and WeatherLink data formats
    
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
            "hazard_type": "Tropical Storm",
            "hazards": ["heavy rain", "strong wind"],
            "risk_level": "high"
        },
        "notification": {
            "title": "⛈️ Tropical Storm Warning",
            "in_app": "...",
            "sms": "..."
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
        
        # Make prediction
        prediction = predictor.predict(features)
        
        # Add risk level
        prediction["risk_level"] = HazardAnalyzer.get_risk_level(prediction)
        
        # Get notification template
        hazard_info = HazardAnalyzer.get_hazard_info(prediction["hazard_type"])
        
        logger.info(f"Prediction made: {prediction['hazard_type']} (risk={prediction['risk_level']})")
        
        return PredictionResponse(
            success=True,
            prediction=prediction,
            notification=hazard_info,
            features=features
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
    
    Use this when you have specific weather measurements
    
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
        
        # Make prediction
        prediction = predictor.predict(features)
        prediction["risk_level"] = HazardAnalyzer.get_risk_level(prediction)
        
        # Get notification template
        hazard_info = HazardAnalyzer.get_hazard_info(prediction["hazard_type"])
        
        return PredictionResponse(
            success=True,
            prediction=prediction,
            notification=hazard_info,
            features=request.features
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
    
    Analyzes a list of weather forecasts and predicts hazards
    
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
    
    Returns:
    - Training timestamp
    - Model accuracy
    - Cross-validation scores
    - Feature count
    - Model path
    """
    try:
        model_info = predictor.get_model_info()
        
        if not model_info["ready"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not trained yet. Please train the model first."
            )
        
        return ModelInfo(**model_info)
        
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