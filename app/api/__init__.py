"""
API routes package
All API routers for the application
"""

from app.api.users import router as users_router
from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.notifications import router as notifications_router
from app.api.hotlines import router as hotlines_router
from app.api.safety_categories import router as safety_categories_router
from app.api.safety_tips import router as safety_tips_router
from app.api.otp import router as otp_router
from app.api.predictions import router as predictions_router
from app.api.weather import router as weather_router
from app.api.auto_predictor import router as auto_predictor_router
from app.api.evacuation_centers import router as evacuation_centers_router
from app.api.hazard_locations import router as hazard_locations_router
from app.api.government_agency import router as government_agency_router
from app.api.admin_invites import router as admin_invites_router
from app.api.auth_password_reset import router as auth_password_reset_router
from app.api.preventive_measures import router as preventive_measures_router
from app.api.user_emails import router as user_emails_router
from app.api.email_verification import router as email_verification_router
from app.api.barangays import router as barangays_router
from app.api.internal import router as internal_router
from app.api.analytics import router as analytics_router
from app.api.system_logs import router as system_logs_router
from app.api.earthquakes import router as earthquakes_router
from app.api.disasters import router as disasters_router

__all__ = [
    'users_router',
    'admin_router',
    'auth_router',
    'notifications_router',
    'hotlines_router',
    'safety_categories_router',
    'safety_tips_router',
    'otp_router',
    'predictions_router',
    'weather_router',
    'auto_predictor_router',
    'evacuation_centers_router',
    'hazard_locations_router',
    'government_agency_router',
    'admin_invites_router',
    'auth_password_reset_router',
    'preventive_measures_router',
    'user_emails_router',
    'email_verification_router',
    'barangays_router',
    'internal_router',
    'analytics_router',
    'system_logs_router',
    'earthquakes_router',
    'disasters_router',
]
