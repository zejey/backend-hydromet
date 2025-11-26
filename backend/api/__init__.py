"""
API routes package
All API routers for the application
"""

from backend.api.users import router as users_router
from backend.api.admin import router as admin_router
from backend.api.notifications import router as notifications_router
from backend.api.hotlines import router as hotlines_router
from backend.api.safety_categories import router as safety_categories_router
from backend.api.safety_tips import router as safety_tips_router
from backend.api.otp import router as otp_router
from backend.api.predictions import router as predictions_router
from backend.api.weather import router as weather_router
from backend.api.auto_predictor import router as auto_predictor_router
from backend.api.evacuation_centers import router as evacuation_centers_router
from backend.api.hazard_locations import router as hazard_locations_router
from backend.api.government_agency import router as government_agency_router
from backend.api.admin_invites import router as admin_invites_router
from backend.api.auth_password_reset import router as auth_password_reset_router

__all__ = [
    'users_router',
    'admin_router',
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
    'auth_password_reset_router'
]
