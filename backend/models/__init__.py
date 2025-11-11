"""
Pydantic models for request/response validation
"""

from backend.models.user import (
    User, UserCreate, UserUpdate, 
    CheckUserRequest, CheckUserResponse, 
    LoginRequest, LoginResponse
)
from backend.models.admin import Admin, AdminCreate, AdminUpdate, AdminResponse
from backend.models.notification import (
    Notification, NotificationCreate, NotificationUpdate, NotificationResponse
)
from backend.models.hotline import (
    EmergencyHotline, HotlineCreate, HotlineUpdate, HotlineResponse
)
from backend.models.safety import (
    SafetyCategory, CategoryCreate, CategoryUpdate, CategoryResponse,
    SafetyTip, TipCreate, TipUpdate, TipResponse
)
from backend.models.otp import OTPRequest, OTPVerifyRequest, OTPResponse
from backend.models.prediction import (
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
    'SafetyCategory', 'CategoryCreate', 'CategoryUpdate', 'CategoryResponse',
    'SafetyTip', 'TipCreate', 'TipUpdate', 'TipResponse',
    
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