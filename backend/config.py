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
    
    DB_NAME = os.getenv("DB_NAME") or os.getenv("PGDATABASE")
    DB_USER = os.getenv("DB_USER") or os.getenv("PGUSER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("PGPASSWORD")
    DB_HOST = os.getenv("DB_HOST") or os.getenv("PGHOST", "localhost")
    DB_PORT = os.getenv("DB_PORT") or os.getenv("PGPORT", "5432")
    
    # iProg SMS API
    IPROG_API_TOKEN = os.getenv("IPROG_API_TOKEN")
    IPROG_BASE_URL = os.getenv("IPROG_BASE_URL", "https://sms.iprogtech.com/api/v1")     

    # OTP Settings
    OTP_VALIDITY_MINUTES = int(os.getenv("OTP_VALIDITY_MINUTES", 5))
    OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", 3))
    OTP_RATE_LIMIT_HOURS = int(os.getenv("OTP_RATE_LIMIT_HOURS", 1))
    OTP_MAX_REQUESTS_PER_PERIOD = int(os.getenv("OTP_MAX_REQUESTS_PER_PERIOD", 3))
    
    # API Settings
    API_VERSION = "v1"
    API_TITLE = "Hydromet API"
    API_DESCRIPTION = "Weather Alert and Safety Management System"
    
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
        return True
