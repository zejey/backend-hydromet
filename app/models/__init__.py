"""
Pydantic models for request/response validation
"""

from app.models.user import (
    User, UserCreate, UserUpdate, 
    CheckUserRequest, CheckUserResponse, 
    LoginRequest, LoginResponse
)
from app.models.admin import Admin, AdminCreate, AdminUpdate, AdminResponse
from app.models.notification import (
    Notification, NotificationCreate, NotificationUpdate, NotificationResponse
)
from app.models.hotline import (
    EmergencyHotline, HotlineCreate, HotlineUpdate, HotlineResponse
)
from app.models.safety import (
    SafetyCategory,
    CategoryCreate,
    CategoryUpdate,
    SafetyTip,
    SafetyTipWithDetails,
    SafetyTipDetail,
    TipCreate,
    TipUpdate,
    PreventiveMeasure,
    MeasureCreate,
    MeasureUpdate,
)
from app.models.otp import OTPRequest, OTPVerifyRequest, OTPResponse
from app.models.prediction import (
    WeatherFeatures,
    PredictionRequest,
    PredictionResponse,
    ForecastPredictionRequest,
    ForecastPredictionResponse,
    ForecastSummary,
    ModelInfo,
    HealthCheckResponse,
    HazardPrediction,
    NotificationTemplate,
    CurrentWeatherRequest,
    CurrentWeatherResponse
)

__all__ = [
    # User models
    'User', 'UserCreate', 'UserUpdate', 
    'CheckUserRequest', 'CheckUserResponse',
    'LoginRequest', 'LoginResponse',
    
    # Admin models
    'Admin', 'AdminCreate', 'AdminUpdate', 'AdminResponse',
    
    # Notification models
    'Notification', 'NotificationCreate', 'NotificationUpdate', 'NotificationResponse',
    
    # Hotline models
    'EmergencyHotline', 'HotlineCreate', 'HotlineUpdate', 'HotlineResponse',
    
    # Safety models
    "SafetyCategory",
    "CategoryCreate",
    "CategoryUpdate",
    "SafetyTip",
    "SafetyTipWithDetails",
    "SafetyTipDetail",
    "TipCreate",
    "TipUpdate",
    "PreventiveMeasure",
    "MeasureCreate",
    "MeasureUpdate",
    
    # OTP models
    'OTPRequest', 'OTPVerifyRequest', 'OTPResponse',
    
    # Prediction models
    'WeatherFeatures',
    'PredictionRequest',
    'PredictionResponse',
    'ForecastPredictionRequest',
    'ForecastPredictionResponse',
    'ForecastSummary',
    'ModelInfo',
    'HealthCheckResponse',
    'HazardPrediction',
    'NotificationTemplate',
    'CurrentWeatherRequest',
    'CurrentWeatherResponse',
]