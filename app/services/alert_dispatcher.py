"""
Alert Dispatcher with Throttling and Priority
Manages hazard alert notifications with intelligent throttling to avoid spam
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from app.database import get_db_cursor, get_db_connection
from app.services.semaphore_notification import get_semaphore_service
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


class AlertDispatcher:
    """
    Dispatch hazard alerts with throttling and priority
    
    Features:
    - Hazard priority ordering (severe storm > thunderstorm > heavy rain > heat)
    - Per-user × hazard × horizon throttling
    - Alert bundling for multiple hazards
    - Persistence via alert_dispatch_log table
    """
    
    # Hazard priority (lower = higher priority)
    HAZARD_PRIORITY = {
        "severe_storm": 0,
        "thunderstorm": 1,
        "heavy_rain": 2,
        "heat_stress": 3,
    }
    
    def __init__(
        self,
        throttle_hours: Optional[Dict[str, int]] = None,
        enable_bundling: bool = True
    ):
        """
        Initialize alert dispatcher
        
        Args:
            throttle_hours: Throttle window per hazard type (hours)
                           Format: {hazard: hours}
            enable_bundling: Whether to bundle multiple hazards into one SMS
        """
        # Default throttle windows (hours)
        self.throttle_hours = throttle_hours or {
            "severe_storm": 2,     # Re-alert every 2 hours
            "thunderstorm": 3,     # Re-alert every 3 hours
            "heavy_rain": 4,       # Re-alert every 4 hours
            "heat_stress": 6,      # Re-alert every 6 hours
        }
        
        self.enable_bundling = enable_bundling
        self.sms_service = get_semaphore_service()
        
        # Ensure alert_dispatch_log table exists
        self._ensure_dispatch_log_table()
    
    def _ensure_dispatch_log_table(self):
        """Create alert_dispatch_log table if it doesn't exist"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS alert_dispatch_log (
                            id SERIAL PRIMARY KEY,
                            user_id INTEGER,
                            phone_number VARCHAR(20) NOT NULL,
                            hazard VARCHAR(50) NOT NULL,
                            horizon INTEGER NOT NULL,
                            probability FLOAT,
                            message TEXT,
                            dispatched_at TIMESTAMP DEFAULT NOW(),
                            success BOOLEAN DEFAULT TRUE,
                            bundled BOOLEAN DEFAULT FALSE,
                            created_at TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    
                    # Create index for throttling lookups
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_alert_dispatch_throttle 
                        ON alert_dispatch_log (phone_number, hazard, horizon, dispatched_at DESC)
                    """)
                    
                    conn.commit()
                    logger.debug("alert_dispatch_log table ready")
        except Exception as e:
            logger.error(f"Failed to create alert_dispatch_log table: {e}")
    
    def check_throttle(
        self,
        phone_number: str,
        hazard: str,
        horizon: int
    ) -> Tuple[bool, Optional[datetime]]:
        """
        Check if alert should be throttled for this user/hazard/horizon
        
        Args:
            phone_number: User's phone number
            hazard: Hazard type
            horizon: Time horizon in hours
            
        Returns:
            Tuple of (should_throttle, last_alert_time)
        """
        throttle_window = self.throttle_hours.get(hazard, 4)  # Default 4 hours
        
        try:
            with get_db_cursor() as cur:
                # Get last alert for this combination
                cur.execute("""
                    SELECT dispatched_at 
                    FROM alert_dispatch_log
                    WHERE phone_number = %s 
                      AND hazard = %s 
                      AND horizon = %s
                      AND success = TRUE
                    ORDER BY dispatched_at DESC
                    LIMIT 1
                """, (phone_number, hazard, horizon))
                
                result = cur.fetchone()
                
                if not result:
                    # No previous alert - don't throttle
                    return False, None
                
                last_alert = result['dispatched_at']
                time_since = datetime.now() - last_alert
                
                should_throttle = time_since < timedelta(hours=throttle_window)
                
                if should_throttle:
                    logger.debug(
                        f"Throttling {hazard}_{horizon}h for {phone_number}: "
                        f"last alert {time_since.total_seconds()/3600:.1f}h ago "
                        f"(window: {throttle_window}h)"
                    )
                
                return should_throttle, last_alert
        
        except Exception as e:
            logger.error(f"Throttle check failed: {e}")
            # On error, don't throttle (better to send than miss alert)
            return False, None
    
    def log_dispatch(
        self,
        phone_number: str,
        hazard: str,
        horizon: int,
        probability: float,
        message: str,
        success: bool,
        bundled: bool = False,
        user_id: Optional[int] = None
    ):
        """
        Log alert dispatch to database
        
        Args:
            phone_number: Recipient phone number
            hazard: Hazard type
            horizon: Time horizon in hours
            probability: Hazard probability
            message: SMS message sent
            success: Whether SMS was sent successfully
            bundled: Whether this was part of a bundled alert
            user_id: User ID (if available)
        """
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO alert_dispatch_log 
                        (user_id, phone_number, hazard, horizon, probability, message, success, bundled)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (user_id, phone_number, hazard, horizon, probability, message, success, bundled))
                    
                    conn.commit()
        except Exception as e:
            logger.error(f"Failed to log dispatch: {e}")
    
    def get_eligible_recipients(
        self,
        hazard: str,
        horizon: int,
        all_users: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        Get list of users eligible for alert (not throttled)
        
        Args:
            hazard: Hazard type
            horizon: Time horizon in hours
            all_users: List of user dicts with phone_number (and optionally user_id)
                      If None, fetches all verified users from database
            
        Returns:
            List of eligible user dictionaries
        """
        # Get all users if not provided
        if all_users is None:
            all_users = self._get_verified_users()
        
        eligible = []
        
        for user in all_users:
            phone = user.get('phone_number')
            if not phone:
                continue
            
            # Check throttle
            should_throttle, _ = self.check_throttle(phone, hazard, horizon)
            
            if not should_throttle:
                eligible.append(user)
        
        logger.debug(f"Eligible recipients: {len(eligible)}/{len(all_users)} for {hazard}_{horizon}h")
        
        return eligible
    
    def _get_verified_users(self) -> List[Dict]:
        """Get all verified users from database"""
        try:
            with get_db_cursor() as cur:
                cur.execute("""
                    SELECT id as user_id, phone_number, email, first_name, last_name
                    FROM users
                    WHERE (phone_number IS NOT NULL OR email IS NOT NULL)
                      AND is_verified = TRUE
                """)
                
                users = cur.fetchall()
                return [dict(u) for u in users]
        
        except Exception as e:
            logger.error(f"Failed to fetch verified users: {e}")
            return []
    
    def dispatch_single_hazard(
        self,
        hazard: str,
        horizon: int,
        probability: float,
        location: str = "your area",
        recipients: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Dispatch alert for a single hazard
        
        Args:
            hazard: Hazard type
            horizon: Time horizon in hours
            probability: Hazard probability
            location: Location name
            recipients: Optional list of recipient dicts (phone_number, user_id)
                       If None, uses all verified users
            
        Returns:
            Dispatch results dictionary
        """
        logger.info(f"Dispatching {hazard} alert ({horizon}h, prob={probability:.2%})")
        
        # Get eligible recipients (not throttled)
        eligible = self.get_eligible_recipients(hazard, horizon, recipients)
        
        if not eligible:
            logger.info(f"No eligible recipients for {hazard}_{horizon}h (all throttled or no users)")
            return {
                "hazard": hazard,
                "horizon": horizon,
                "eligible_count": 0,
                "sent_count": 0,
                "throttled_count": len(recipients) if recipients else 0
            }
        
        # Send SMS via Semaphore
        phone_numbers = [u['phone_number'] for u in eligible if u.get('phone_number')]
        
        send_results = {"success": 0, "failed": 0, "details": []}
        if phone_numbers:
            send_results = self.sms_service.send_hazard_alert(
                phone_numbers=phone_numbers,
                hazard=hazard,
                horizon=horizon,
                probability=probability,
                location=location
            )
        
        # Send Emails concurrently (simple loop for now)
        for user in eligible:
            email = user.get('email')
            if email:
                # Fetch safety tips if possible, otherwise empty
                # For simplicity, we'll use a placeholder or basic tips
                EmailService.send_hazard_alert_email(
                    recipient_email=email,
                    hazard_name=hazard.replace("_", " ").title(),
                    horizon=horizon,
                    probability=probability,
                    safety_tips=["Stay indoors", "Monitor local news"]
                )
        
        # Log each dispatch
        message = self.sms_service.format_hazard_message(hazard, horizon, probability, location)
        
        for user in eligible:
            phone = user['phone_number']
            user_id = user.get('user_id')
            
            # Find if this send succeeded
            success = any(
                d['phone'] == phone and d['success']
                for d in send_results.get('details', [])
            )
            
            self.log_dispatch(
                phone_number=phone,
                hazard=hazard,
                horizon=horizon,
                probability=probability,
                message=message,
                success=success,
                bundled=False,
                user_id=user_id
            )
        
        result = {
            "hazard": hazard,
            "horizon": horizon,
            "probability": probability,
            "eligible_count": len(eligible),
            "sent_count": send_results['success'],
            "failed_count": send_results['failed'],
            "throttled_count": (len(recipients) if recipients else 0) - len(eligible)
        }
        
        logger.info(
            f"✓ {hazard}_{horizon}h dispatch complete: "
            f"{result['sent_count']}/{result['eligible_count']} sent, "
            f"{result['throttled_count']} throttled"
        )
        
        return result
    
    def dispatch_bundled_hazards(
        self,
        hazards: List[Dict[str, Any]],
        location: str = "your area",
        recipients: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Dispatch bundled alert for multiple hazards
        
        Sends one SMS containing summary of multiple hazards
        
        Args:
            hazards: List of hazard dicts with keys: hazard, horizon, probability
            location: Location name
            recipients: Optional list of recipient dicts
            
        Returns:
            Dispatch results dictionary
        """
        if not hazards:
            return {"bundled": False, "sent_count": 0}
        
        logger.info(f"Dispatching bundled alert for {len(hazards)} hazards")
        
        # Sort by priority
        sorted_hazards = sorted(
            hazards,
            key=lambda h: (self.HAZARD_PRIORITY.get(h['hazard'], 99), h['horizon'])
        )
        
        # Get eligible recipients for TOP PRIORITY hazard
        # (If user is throttled for highest priority, they're throttled for bundle)
        top_hazard = sorted_hazards[0]
        eligible = self.get_eligible_recipients(
            top_hazard['hazard'],
            top_hazard['horizon'],
            recipients
        )
        
        if not eligible:
            logger.info("No eligible recipients for bundled alert")
            return {
                "bundled": True,
                "eligible_count": 0,
                "sent_count": 0
            }
        
        # Send bundled SMS
        phone_numbers = [u['phone_number'] for u in eligible]
        
        send_results = self.sms_service.send_bundled_hazard_alert(
            phone_numbers=phone_numbers,
            hazards=sorted_hazards,
            location=location
        )
        
        # Log dispatch for EACH hazard in bundle
        for hazard_info in sorted_hazards:
            hazard = hazard_info['hazard']
            horizon = hazard_info['horizon']
            probability = hazard_info['probability']
            
            # Get message (just for logging - actual SMS is bundled)
            message = f"Bundled alert: {len(sorted_hazards)} hazards"
            
            for user in eligible:
                phone = user['phone_number']
                user_id = user.get('user_id')
                
                success = any(
                    d['phone'] == phone and d['success']
                    for d in send_results.get('details', [])
                )
                
                self.log_dispatch(
                    phone_number=phone,
                    hazard=hazard,
                    horizon=horizon,
                    probability=probability,
                    message=message,
                    success=success,
                    bundled=True,
                    user_id=user_id
                )
        
        result = {
            "bundled": True,
            "hazards_count": len(sorted_hazards),
            "eligible_count": len(eligible),
            "sent_count": send_results['success'],
            "failed_count": send_results['failed']
        }
        
        logger.info(f"✓ Bundled dispatch complete: {result['sent_count']}/{result['eligible_count']} sent")
        
        return result
    
    def dispatch_from_predictions(
        self,
        predictions: Dict[str, Any],
        location: str = "your area",
        recipients: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Dispatch alerts based on multi-hazard prediction results
        
        Automatically handles bundling and priority
        
        Args:
            predictions: Multi-hazard prediction results (from MultiHazardPredictor)
            location: Location name
            recipients: Optional list of recipients
            
        Returns:
            Dispatch summary
        """
        if not predictions.get("success"):
            logger.warning("Cannot dispatch from failed predictions")
            return {"success": False, "dispatched": 0}
        
        # Collect all detected hazards
        detected_hazards = []
        
        for hazard, horizons in predictions.get("predictions", {}).items():
            for horizon_key, pred_info in horizons.items():
                if pred_info.get("hazard_detected") and pred_info.get("available"):
                    horizon_hours = int(horizon_key.replace('h', ''))
                    
                    detected_hazards.append({
                        "hazard": hazard,
                        "horizon": horizon_hours,
                        "probability": pred_info.get("probability", 0.0)
                    })
        
        if not detected_hazards:
            logger.info("No hazards detected - no alerts to dispatch")
            return {"success": True, "dispatched": 0, "hazards_detected": 0}
        
        logger.info(f"Dispatching alerts for {len(detected_hazards)} detected hazards")
        
        # Decide: bundle or send individually
        if self.enable_bundling and len(detected_hazards) > 1:
            # Bundle multiple hazards
            result = self.dispatch_bundled_hazards(
                hazards=detected_hazards,
                location=location,
                recipients=recipients
            )
            result["dispatch_mode"] = "bundled"
        else:
            # Send individually
            dispatch_results = []
            
            for hazard_info in detected_hazards:
                result = self.dispatch_single_hazard(
                    hazard=hazard_info['hazard'],
                    horizon=hazard_info['horizon'],
                    probability=hazard_info['probability'],
                    location=location,
                    recipients=recipients
                )
                dispatch_results.append(result)
            
            # Aggregate results
            result = {
                "dispatch_mode": "individual",
                "hazards_count": len(detected_hazards),
                "results": dispatch_results,
                "total_sent": sum(r['sent_count'] for r in dispatch_results),
                "total_throttled": sum(r['throttled_count'] for r in dispatch_results)
            }
        
        result["success"] = True
        result["hazards_detected"] = len(detected_hazards)
        
        return result


# Singleton instance
_alert_dispatcher = None


def get_alert_dispatcher(
    throttle_hours: Optional[Dict[str, int]] = None,
    enable_bundling: bool = True
) -> AlertDispatcher:
    """
    Get or create singleton AlertDispatcher instance
    
    Args:
        throttle_hours: Optional custom throttle configuration
        enable_bundling: Whether to enable alert bundling
        
    Returns:
        AlertDispatcher instance
    """
    global _alert_dispatcher
    
    if _alert_dispatcher is None:
        _alert_dispatcher = AlertDispatcher(
            throttle_hours=throttle_hours,
            enable_bundling=enable_bundling
        )
    
    return _alert_dispatcher


if __name__ == "__main__":
    # Testing
    import logging
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "="*60)
    print("ALERT DISPATCHER - TESTING")
    print("="*60)
    
    dispatcher = get_alert_dispatcher()
    
    print(f"\nThrottle windows configured:")
    for hazard, hours in dispatcher.throttle_hours.items():
        print(f"  {hazard}: {hours}h")
    
    print(f"\nBundling enabled: {dispatcher.enable_bundling}")
    
    print("\n✅ Alert dispatcher test complete!")
    print("   (Full functionality requires database and Semaphore API)")