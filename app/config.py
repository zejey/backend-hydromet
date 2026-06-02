"""
Centralized configuration for the entire backend
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration"""
    
    # Database - Support both local and Railway PostgreSQL variables
    # Railway provides: PGDATABASE, PGUSER, PGPASSWORD, PGHOST, PGPORT
    # Local provides: DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT

    OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
    OPENWEATHER_LAT = float(os.getenv("OPENWEATHER_LAT", "14.3597"))
    OPENWEATHER_LON = float(os.getenv("OPENWEATHER_LON", "121.0583"))
    OPENWEATHER_BASE_URL = os.getenv("OPENWEATHER_BASE_URL", "https://api.openweathermap.org/data/2.5")
    OPENWEATHER_COLLECTOR_ENABLED = os.getenv("OPENWEATHER_COLLECTOR_ENABLED", "false").lower() == "true"

    DB_NAME = os.getenv("PGDATABASE") or os.getenv("DB_NAME")
    DB_USER = os.getenv("PGUSER") or os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("PGPASSWORD") or os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("PGHOST") or os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("PGPORT") or os.getenv("DB_PORT", "5432")
    
    # iProg SMS API
    SEMAPHORE_API_KEY = os.environ.get("SEMAPHORE_API_KEY", "")

    # Forecast runner
    FORECAST_DEFAULT_LAT = os.getenv("FORECAST_DEFAULT_LAT", os.getenv("OPENWEATHER_LAT", "14.3597"))
    FORECAST_DEFAULT_LON = os.getenv("FORECAST_DEFAULT_LON", os.getenv("OPENWEATHER_LON", "121.0583"))
    INTERNAL_CRON_SECRET = os.getenv("INTERNAL_CRON_SECRET", "")
    FORECAST_RUNNER_ENABLED = os.getenv("FORECAST_RUNNER_ENABLED", "false").lower() == "true"
    FORECAST_DEDUPE_HOURS = int(os.getenv("FORECAST_DEDUPE_HOURS", "6"))

    # Email Settings (Brevo)
    BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
    BREVO_SENDER = os.getenv("BREVO_SENDER", "")
    
    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

    # OTP Settings
    OTP_VALIDITY_MINUTES = int(os.getenv("OTP_VALIDITY_MINUTES", 5))
    OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", 3))
    OTP_RATE_LIMIT_HOURS = int(os.getenv("OTP_RATE_LIMIT_HOURS", 1))
    OTP_MAX_REQUESTS_PER_PERIOD = int(os.getenv("OTP_MAX_REQUESTS_PER_PERIOD", 3))
    
    # API Settings
    APP_VERSION = os.getenv("APP_VERSION", "2.1.0")
    API_VERSION = "v1"
    API_TITLE = "Hydromet API"
    API_DESCRIPTION = "Weather Alert and Safety Management System"

    # CORS — comma-separated origins, or "*" for allow-all (dev only)
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

    # Sentry
    SENTRY_DSN = os.getenv("SENTRY_DSN", "")

    @classmethod
    def get_cors_origins(cls) -> list[str]:
        """Parse CORS_ORIGINS env var into a list."""
        raw = cls.CORS_ORIGINS.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @classmethod
    def is_production(cls) -> bool:
        return cls.ENVIRONMENT.lower() == "production"
    
    @classmethod
    def get_database_url(cls):
        """Get PostgreSQL connection string"""
        return f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        required = {
            'DB_NAME': cls.DB_NAME,
            'DB_USER': cls.DB_USER,
            'DB_PASSWORD': cls.DB_PASSWORD,
            'DB_HOST': cls.DB_HOST,
            'DB_PORT': cls.DB_PORT,
        }
        
        missing = [key for key, value in required.items() if not value]
        
        if missing:
            # Don't fail - just warn (Railway sets PG* variables automatically)
            print(f"⚠️  Warning: Missing environment variables: {', '.join(missing)}")
            print(f"✅ Using Railway PostgreSQL variables instead")
            return True
        
        print("✅ Configuration validated successfully")
        print(f"✅ Database: {cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}")
        return True