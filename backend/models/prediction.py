"""
Prediction Pydantic models
Request/response models for weather predictions
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ===== Weather Features Models =====

class WeatherFeatures(BaseModel):
    """Weather features for prediction"""
    temp_c: float = Field(..., description="Temperature in Celsius")
    temp_min_c: Optional[float] = Field(None, description="Minimum temperature")
    temp_max_c: Optional[float] = Field(None, description="Maximum temperature")
    pressure_hpa: float = Field(..., description="Atmospheric pressure in hPa")
    humidity_pct: float = Field(..., description="Humidity percentage")
    wind_speed_ms: float = Field(..., description="Wind speed in m/s")
    wind_deg: Optional[float] = Field(None, description="Wind direction in degrees")
    clouds_pct: Optional[float] = Field(None, description="Cloud coverage percentage")
    precipitation_mm: Optional[float] = Field(0, description="Precipitation in mm")
    heat_index_c: Optional[float] = Field(None, description="Heat index in Celsius")
    dew_point_c: Optional[float] = Field(None, description="Dew point in Celsius")


# ===== Prediction Request Models =====

class PredictionRequest(BaseModel):
    """Request for weather hazard prediction"""
    weather_data: Dict[str, Any] = Field(..., description="Raw weather data from API")
    source: str = Field(default="openweather", description="Data source: 'openweather' or 'weatherlink'")


class ForecastPredictionRequest(BaseModel):
    """Request for batch forecast predictions"""
    forecasts: List[Dict[str, Any]] = Field(..., description="List of forecast data points")
    source: str = Field(default="openweather", description="Data source")


class CustomFeaturesRequest(BaseModel):
    """Request with custom weather features"""
    features: WeatherFeatures


# ===== Prediction Response Models =====

class HazardPrediction(BaseModel):
    """Hazard prediction result"""
    event: int = Field(..., description="Hazard event (0=none, 1=hazard)")
    probability: float = Field(..., description="Prediction probability (0-1)")
    hazard_type: str = Field(..., description="Type of hazard detected")
    hazards: List[str] = Field(default=[], description="List of detected hazards")
    timestamp: Optional[str] = Field(None, description="Prediction timestamp")
    risk_level: Optional[str] = Field(None, description="Risk level: low/moderate/high/critical")


class NotificationTemplate(BaseModel):
    """Notification template for hazard"""
    title: str = Field(..., description="Notification title")
    in_app: str = Field(..., description="In-app notification message")
    sms: str = Field(..., description="SMS notification message")


class PredictionResponse(BaseModel):
    """Response for single prediction"""
    success: bool = Field(default=True)
    prediction: HazardPrediction
    notification: Optional[NotificationTemplate] = None
    features: Optional[Dict[str, Any]] = None


class ForecastPredictionResponse(BaseModel):
    """Response for forecast predictions"""
    success: bool = Field(default=True)
    total_predictions: int = Field(..., description="Total number of predictions")
    hazard_events: int = Field(..., description="Number of hazard events detected")
    predictions: List[Dict[str, Any]] = Field(default=[], description="List of predictions")
    summary: Optional[Dict[str, Any]] = Field(None, description="Summary of hazards")


# ===== Weather Data Models =====

class CurrentWeatherRequest(BaseModel):
    """Request for current weather"""
    lat: Optional[float] = Field(None, description="Latitude")
    lon: Optional[float] = Field(None, description="Longitude")
    source: str = Field(default="openweather", description="Weather data source")


class CurrentWeatherResponse(BaseModel):
    """Response with current weather and prediction"""
    success: bool = Field(default=True)
    location: Dict[str, float] = Field(..., description="Location coordinates")
    weather: Dict[str, Any] = Field(..., description="Current weather data")
    prediction: Optional[HazardPrediction] = None
    notification: Optional[NotificationTemplate] = None
    timestamp: str = Field(..., description="Response timestamp")


class ForecastSummary(BaseModel):
    """Summary of forecast predictions"""
    total_records: int
    hazard_events_count: int
    hazard_types: List[str]
    high_risk_count: int = Field(default=0, description="Number of high/critical risk events")
    next_hazard: Optional[Dict[str, Any]] = Field(None, description="Next upcoming hazard")
    timeline: List[Dict[str, Any]] = Field(default=[], description="Timeline of hazard events")


# ===== Model Info Models =====

class ModelInfo(BaseModel):
    """ML Model information"""
    ready: bool = Field(..., description="Whether model is ready")
    trained_at: Optional[str] = Field(None, description="Training timestamp")
    accuracy: Optional[float] = Field(None, description="Model accuracy")
    cv_mean: Optional[float] = Field(None, description="Cross-validation mean score")
    cv_std: Optional[float] = Field(None, description="Cross-validation std")
    features_count: Optional[int] = Field(None, description="Number of features")
    model_path: Optional[str] = Field(None, description="Path to model file")


class HealthCheckResponse(BaseModel):
    """Health check response"""
    success: bool = Field(default=True)
    status: str = Field(..., description="System status")
    model_ready: bool = Field(..., description="ML model status")
    model_info: Optional[ModelInfo] = None
    timestamp: str = Field(..., description="Check timestamp")