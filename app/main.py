"""
Hydromet Weather & Alert System - Main API
Complete FastAPI application with ML predictions
"""

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import Config
from app.database import init_connection_pool, close_connection_pool, test_connection
from app.api import (
    users_router,
    admin_router,
    auth_router,
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
    analytics_router,
    system_logs_router,
    earthquakes_router,
    disasters_router,
)
from app.services.system_settings_service import SystemSettingsService

logger = logging.getLogger("hydromet.api")

# ---------------------------------------------------------------------------
# Sentry (optional — only activates if SENTRY_DSN is set)
# ---------------------------------------------------------------------------
if Config.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=Config.SENTRY_DSN,
        environment=Config.ENVIRONMENT,
        release=Config.APP_VERSION,
        traces_sample_rate=0.2,
        send_default_pii=False,
    )

# Validate configuration
Config.validate()

# Initialize database connection pool
try:
    init_connection_pool()
    if not test_connection():
        logger.warning(
            "Database connection test failed during startup. "
            "API will continue running and retry database access on demand."
        )
except Exception:
    logger.exception(
        "Database initialization failed during startup. "
        "API will continue running and retry database access on demand."
    )

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

# Create FastAPI app
app = FastAPI(
    title="Hydromet Weather & Alert System API",
    description="Complete API for weather monitoring, hazard prediction, and alert management",
    version=Config.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    redirect_slashes=False,  # ✅ Fix 307 redirects at app level
    contact={
        "name": "zjayarcena",
        "email": "your-email@example.com"
    }
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware — origins from CORS_ORIGINS env var
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed_ms = round((time.time() - start) * 1000, 1)
    logger.info(
        "%s %s %s %sms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response

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
app.include_router(internal_router)
app.include_router(auth_router)               # /api/auth/*
app.include_router(analytics_router)           # /api/analytics/*
app.include_router(system_logs_router)
app.include_router(earthquakes_router)           # /api/earthquakes/*
app.include_router(disasters_router)             # /api/disasters/*


@app.get("/")
async def root():
    """
    Root endpoint - API information and available endpoints
    """
    return {
        "success": True,
        "name": "Hydromet Weather & Alert System API",
        "version": Config.APP_VERSION,
        "description": "Early warning system with multi-disaster monitoring, ML-based hazard prediction, and localized barangay-level alerts",
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
            "disasters": {
                "active": "GET /api/disasters/active",
                "dashboard": "GET /api/disasters/dashboard",
                "detail": "GET /api/disasters/{id}",
                "history": "GET /api/disasters/history",
                "manual_create": "POST /api/disasters/manual",
                "resolve": "PUT /api/disasters/{id}/resolve",
                "monitor_run": "POST /api/disasters/monitor/run"
            },
            "earthquakes": {
                "recent": "GET /api/earthquakes/recent",
                "significant": "GET /api/earthquakes/significant",
                "nearest": "GET /api/earthquakes/nearest"
            },
            "barangays": {
                "list": "GET /api/barangays",
                "create": "POST /api/barangays",
                "update": "PUT /api/barangays/{id}",
                "vulnerability": "GET /api/barangays/{id}/vulnerability",
                "set_vulnerability": "PUT /api/barangays/{id}/vulnerability",
                "at_risk": "GET /api/barangays/at-risk",
                "evaluate_risk": "POST /api/barangays/evaluate-risk"
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
            "Multi-Disaster Early Warning System (Earthquake, Typhoon, Flood)",
            "Barangay-Level Localized Hazard Alerts",
            "Real-time Earthquake Monitoring (USGS)",
            "Global Disaster Tracking (GDACS)",
            "ML-based Weather Hazard Prediction",
            "Per-Barangay Vulnerability Profiles & Thresholds",
            "OTP Authentication with SMS",
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
    from app.ml.multi_model_manager import MultiModelManager

    model_manager = MultiModelManager()
    model_status = model_manager.get_model_status()
    model_ready = model_status["ready"]

    return {
        "success": True,
        "message": "Hydromet API is running smoothly",
        "status": "healthy",
        "version": Config.APP_VERSION,
        "environment": Config.ENVIRONMENT,
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
    # Initialize settings table
    try:
        SystemSettingsService.initialize_table()
    except Exception:
        logger.exception("Failed to initialize system settings table at startup")

    # Initialize vulnerability profiles table
    try:
        from app.services.vulnerability_resolver import VulnerabilityResolver
        VulnerabilityResolver.ensure_table()
    except Exception:
        logger.exception("Failed to initialize vulnerability profiles table")

    # Initialize disaster monitor (creates active_disasters table)
    try:
        from app.services.disaster_monitor import get_disaster_monitor
        get_disaster_monitor()
    except Exception:
        logger.exception("Failed to initialize disaster monitor")
    
    print("\n" + "="*80)
    print("🌊 HYDROMET WEATHER & ALERT SYSTEM API")
    print("="*80)
    print(f"📅 Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"👤 Developer: zjayarcena")
    print(f"🔧 Version: {Config.APP_VERSION}")
    print(f"🌍 Environment: {Config.ENVIRONMENT}")
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
    from app.ml.multi_model_manager import MultiModelManager
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
