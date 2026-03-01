"""
Hydromet Weather & Alert System - Main API
Complete FastAPI application with ML predictions

Author: zjayarcena
Date: 2025-11-01
Version: 2.0.0
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
import os
from datetime import datetime

# Add backend to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.config import Config
from backend.database import init_connection_pool, close_connection_pool, test_connection
from backend.api import (
    users_router,
    admin_router,
    notifications_router,
    hotlines_router,
    safety_categories_router,
    safety_tips_router,
    otp_router,
    predictions_router,
    weather_router,
    auto_predictor_router,
    evacuation_centers_router,
    hazard_locations_router,
    government_agency_router,
    admin_invites_router,
    auth_password_reset_router,
    preventive_measures_router,
    user_emails_router,
    email_verification_router,
    barangays_router,
    internal_router,
)

# Validate configuration
Config.validate()

# Initialize database connection pool
init_connection_pool()

# Test database connection
test_connection()

# Create FastAPI app
app = FastAPI(
    title="Hydromet Weather & Alert System API",
    description="Complete API for weather monitoring, hazard prediction, and alert management",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    redirect_slashes=False,  # ✅ Fix 307 redirects at app level
    contact={
        "name": "zjayarcena",
        "email": "your-email@example.com"
    }
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ Change to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(users_router)              # /api/users/*
app.include_router(otp_router)                # /api/otp/*
app.include_router(predictions_router)        # /api/predictions/*
app.include_router(weather_router)            # /api/weather/*
app.include_router(admin_router)              # /api/admins/*
app.include_router(notifications_router)      # /api/notifications/*
app.include_router(hotlines_router)           # /api/hotlines/*
app.include_router(safety_categories_router)  # /api/safety/categories/*
app.include_router(safety_tips_router)        # /api/safety/tips/*
app.include_router(auto_predictor_router)
app.include_router(evacuation_centers_router)
app.include_router(hazard_locations_router)
app.include_router(government_agency_router)
app.include_router(admin_invites_router)
app.include_router(auth_password_reset_router)
app.include_router(preventive_measures_router)
app.include_router(user_emails_router)
app.include_router(email_verification_router)
app.include_router(barangays_router)
app.include_router(internal_router)  # /internal/*


@app.get("/")
async def root():
    """
    Root endpoint - API information and available endpoints
    """
    return {
        "success": True,
        "name": "Hydromet Weather & Alert System API",
        "version": "2.0.0",
        "description": "Weather monitoring, ML-based hazard prediction, and alert management",
        "author": "zjayarcena",
        "created": "2025-11-01",
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_spec": "/openapi.json"
        },
        "endpoints": {
            "authentication": {
                "check_user": "POST /api/users/check-user",
                "get_user": "POST /api/users/get-user",
                "list_users": "GET /api/users",
                "create_user": "POST /api/users"
            },
            "otp": {
                "send": "POST /api/otp/send",
                "send_registration": "POST /api/otp/send-registration",
                "verify": "POST /api/otp/verify",
                "resend": "POST /api/otp/resend",
                "health": "GET /api/otp/health"
            },
            "predictions": {
                "health": "GET /api/predictions/health",
                "predict": "POST /api/predictions/predict",
                "predict_custom": "POST /api/predictions/predict-custom",
                "forecast": "POST /api/predictions/forecast",
                "forecast_summary": "GET /api/predictions/forecast/summary",
                "model_info": "GET /api/predictions/model/info"
            },
            "weather": {
                "current": "GET /api/weather/current",
                "forecast": "GET /api/weather/forecast",
                "weatherlink_current": "GET /api/weather/weatherlink/current",
                "weatherlink_historic": "GET /api/weather/weatherlink/historic"
            },
            "admin": {
                "list": "GET /api/admins",
                "create": "POST /api/admins",
                "get": "GET /api/admins/{id}",
                "update": "PUT /api/admins/{id}",
                "delete": "DELETE /api/admins/{id}"
            },
            "notifications": {
                "list": "GET /api/notifications",
                "create": "POST /api/notifications",
                "get": "GET /api/notifications/{id}",
                "by_status": "GET /api/notifications/status/{status}"
            },
            "hotlines": {
                "list": "GET /api/hotlines",
                "create": "POST /api/hotlines",
                "by_category": "GET /api/hotlines/category/{category}"
            },
            "safety": {
                "categories": "GET /api/safety/categories",
                "tips": "GET /api/safety/tips",
                "tips_by_category": "GET /api/safety/tips/category/{category_id}"
            }
        },
        "features": [
            "OTP Authentication with SMS",
            "ML-based Weather Hazard Prediction",
            "Real-time Weather Data (OpenWeather & WeatherLink)",
            "5-Day Weather Forecast with Predictions",
            "Emergency Hotlines Management",
            "Safety Tips & Alerts",
            "User & Admin Management",
            "Rate Limiting & Security"
        ]
    }


@app.get("/health")
async def health():
    """
    Application health check
    Returns system status, database connection, and multi-model ML readiness
    """
    from backend.ml.multi_model_manager import MultiModelManager

    model_manager = MultiModelManager()
    model_status = model_manager.get_model_status()
    model_ready = model_status["ready"]

    return {
        "success": True,
        "message": "Hydromet API is running smoothly",
        "status": "healthy",
        "version": "2.0.0",
        "database": f"{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}",
        "ml_model_ready": model_ready,
        "ml_models_available": f"{model_status['available_count']}/{model_status['total_expected']}",
        "ml_model_status": "ready" if model_ready else (
            "not_ready - run: python scripts/train_multi_models.py --csv training_data.csv"
        ),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    print("\n" + "="*80)
    print("🌊 HYDROMET WEATHER & ALERT SYSTEM API")
    print("="*80)
    print(f"📅 Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"👤 Developer: zjayarcena")
    print(f"🔧 Version: 2.0.0")
    print("="*80)
    print("\n🎯 Features:")
    print("   ✅ User Authentication (OTP)")
    print("   ✅ ML Weather Hazard Prediction")
    print("   ✅ Real-time Weather Data")
    print("   ✅ 5-Day Forecast Predictions")
    print("   ✅ SMS Alerts (iProg)")
    print("   ✅ Emergency Hotlines")
    print("   ✅ Safety Tips & Alerts")
    print("="*80)


@app.on_event("shutdown")
async def shutdown_event():
    """Close database connections on shutdown"""
    close_connection_pool()
    print("\n✅ Application shutdown complete")
    print("="*80)


if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*80)
    print("🚀 STARTING HYDROMET API SERVER")
    print("="*80)
    print(f"✅ Database: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
    print(f"✅ iProg SMS: Configured")
    print(f"✅ OTP System: Active (Rate Limited)")
    print(f"✅ Connection Pool: Initialized")
    
    # Check ML models
    from backend.ml.multi_model_manager import MultiModelManager
    model_manager = MultiModelManager()
    model_status = model_manager.get_model_status()
    available = model_status["available_count"]
    total = model_status["total_expected"]
    if model_status["ready"]:
        print(f"✅ ML Models: All {total} models ready")
    else:
        print(f"⚠️  ML Models: {available}/{total} ready (run train_multi_models.py)")
    
    print("\n📍 API Endpoints:")
    print(f"   • Interactive Docs (Swagger): http://localhost:8000/docs")
    print(f"   • Alternative Docs (ReDoc):   http://localhost:8000/redoc")
    print(f"   • Health Check:               http://localhost:8000/health")
    print(f"   • API Root:                   http://localhost:8000/")
    
    print("\n🔐 Security Features:")
    print(f"   • OTP Hashing: bcrypt")
    print(f"   • Rate Limiting: 3 requests/hour")
    print(f"   • Attempt Limiting: 3 attempts/OTP")
    print(f"   • Connection Pooling: 1-20 connections")
    
    print("\n🤖 ML Prediction Features:")
    print(f"   • Hazard Types: 7 (Cyclone, Storm, Flood, etc.)")
    print(f"   • Data Sources: OpenWeather API, WeatherLink")
    print(f"   • Forecast Range: Up to 5 days (120 hours)")
    print(f"   • Risk Levels: 4 (Low, Moderate, High, Critical)")
    
    print("="*80 + "\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )