"""
OTP Manager Service
Handles OTP generation, verification, and rate limiting
"""

import os
import random
import string
import requests
from datetime import datetime, timedelta
from typing import Optional, Tuple
import bcrypt

from backend.database import get_db_cursor
from backend.config import Config
from backend.utils.validators import format_phone_for_sms


class OTPManager:
    """
    Secure OTP Manager with industry-standard security practices
    """

    def __init__(self):
        self.otp_validity_minutes = Config.OTP_VALIDITY_MINUTES
        self.max_attempts = Config.OTP_MAX_ATTEMPTS
        self.rate_limit_hours = Config.OTP_RATE_LIMIT_HOURS
        self.max_requests_per_period = Config.OTP_MAX_REQUESTS_PER_PERIOD

    def _generate_otp(self, length: int = 6) -> str:
        """Generate a random numeric OTP"""
        return ''.join(random.choices(string.digits, k=length))

    def _hash_otp(self, otp: str) -> str:
        """Hash OTP using bcrypt for secure storage"""
        return bcrypt.hashpw(otp.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _verify_otp_hash(self, otp: str, hashed: str) -> bool:
        """Verify OTP against hashed version"""
        return bcrypt.checkpw(otp.encode('utf-8'), hashed.encode('utf-8'))

    def _check_rate_limit(self, phone_number: str) -> Tuple[bool, Optional[str]]:
        """Check if phone number has exceeded rate limit"""
        with get_db_cursor() as cur:
            time_threshold = datetime.utcnow() - timedelta(hours=self.rate_limit_hours)

            cur.execute("""
                SELECT COUNT(*) as count 
                FROM otp_requests 
                WHERE phone_number = %s 
                AND created_at > %s
            """, (phone_number, time_threshold))

            result = cur.fetchone()
            count = result['count'] if result else 0

            if count >= self.max_requests_per_period:
                return False, f"Rate limit exceeded. Maximum {self.max_requests_per_period} OTP requests per {self.rate_limit_hours} hour(s)"

            return True, None

    def _invalidate_previous_otps(self, phone_number: str):
        """Invalidate all previous OTPs for this phone number"""
        with get_db_cursor() as cur:
            cur.execute("""
                UPDATE otp_requests 
                SET is_verified = TRUE, is_invalidated = TRUE
                WHERE phone_number = %s 
                AND is_verified = FALSE 
                AND is_invalidated = FALSE
            """, (phone_number,))

    def _send_sms(self, phone_number: str, message: str):
        try:
            from backend.utils.validators import format_phone_for_semaphore

            formatted_phone = format_phone_for_semaphore(phone_number)

            if not Config.SEMAPHORE_API_KEY:
                return False, "Semaphore API key missing (SEMAPHORE_API_KEY)"

            url = "https://api.semaphore.co/api/v4/messages"
            payload = {
                "apikey": Config.SEMAPHORE_API_KEY,
                "number": formatted_phone,
                "message": message,
                "sendername": "HydroMET",  # try removing this to test default sender
            }

            response = requests.post(url, data=payload, timeout=10)

            # Always inspect body
            content_type = response.headers.get("Content-Type", "")
            body_text = response.text

            if "application/json" in content_type:
                try:
                    body = response.json()
                except Exception:
                    body = None
            else:
                body = None

            if not (200 <= response.status_code < 300):
                return False, f"HTTP {response.status_code}: {body or body_text}"

            # Semaphore typically returns a list of message objects; check for error fields/status
            return True, body or body_text

        except requests.exceptions.RequestException as e:
            return False, f"SMS sending failed: {str(e)}"

    def send_otp(self, phone_number: str) -> Tuple[bool, str, Optional[dict]]:
        """Generate and send OTP to phone number"""
        try:
            # Check rate limit
            is_allowed, rate_limit_msg = self._check_rate_limit(phone_number)
            if not is_allowed:
                return False, rate_limit_msg, None

            # Invalidate previous OTPs
            self._invalidate_previous_otps(phone_number)

            # Generate OTP
            otp_code = self._generate_otp()
            hashed_otp = self._hash_otp(otp_code)

            # Store in database
            with get_db_cursor() as cur:
                expires_at = datetime.utcnow() + timedelta(minutes=self.otp_validity_minutes)

                cur.execute("""
                    INSERT INTO otp_requests 
                    (phone_number, otp_hash, expires_at, attempts_left, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, expires_at
                """, (phone_number, hashed_otp, expires_at, self.max_attempts, datetime.utcnow()))

                result = cur.fetchone()

                # ✅ FOR DEVELOPMENT: Print OTP to console
                print(f"🔐 OTP CODE (DEV ONLY): {otp_code} for {phone_number}")

                # Send SMS
                message = f"Your OTP is: {otp_code}. Valid for {self.otp_validity_minutes} minutes. Do not share this code."
                sms_success, sms_error = self._send_sms(phone_number, message)

                if not sms_success:
                    # ✅ Still show OTP in console if SMS fails
                    print(f"⚠️ SMS FAILED - Use this OTP for testing: {otp_code}")
                    return False, f"OTP generated but SMS failed: {sms_error}", None

                return True, "OTP sent successfully", {
                    "otp_id": result['id'],
"""
OTP Manager Service
Handles OTP generation, verification, and rate limiting
"""

import os
import random
import string
import requests
from datetime import datetime, timedelta
from typing import Optional, Tuple
import bcrypt

from backend.database import get_db_cursor
from backend.config import Config
from backend.utils.validators import format_phone_for_sms


class OTPManager:
    """
    Secure OTP Manager with industry-standard security practices
    """

    def __init__(self):
        self.otp_validity_minutes = Config.OTP_VALIDITY_MINUTES
        self.max_attempts = Config.OTP_MAX_ATTEMPTS
        self.rate_limit_hours = Config.OTP_RATE_LIMIT_HOURS
        self.max_requests_per_period = Config.OTP_MAX_REQUESTS_PER_PERIOD

    def _generate_otp(self, length: int = 6) -> str:
        """Generate a random numeric OTP"""
        return ''.join(random.choices(string.digits, k=length))

    def _hash_otp(self, otp: str) -> str:
        """Hash OTP using bcrypt for secure storage"""
        return bcrypt.hashpw(otp.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _verify_otp_hash(self, otp: str, hashed: str) -> bool:
        """Verify OTP against hashed version"""
        return bcrypt.checkpw(otp.encode('utf-8'), hashed.encode('utf-8'))

    def _check_rate_limit(self, phone_number: str) -> Tuple[bool, Optional[str]]:
        """Check if phone number has exceeded rate limit"""
        with get_db_cursor() as cur:
            time_threshold = datetime.utcnow() - timedelta(hours=self.rate_limit_hours)

            cur.execute("""
                SELECT COUNT(*) as count 
                FROM otp_requests 
                WHERE phone_number = %s 
                AND created_at > %s
            """, (phone_number, time_threshold))

            result = cur.fetchone()
            count = result['count'] if result else 0

            if count >= self.max_requests_per_period:
                return False, f"Rate limit exceeded. Maximum {self.max_requests_per_period} OTP requests per {self.rate_limit_hours} hour(s)"

            return True, None
    
    def _get_verified_primary_email(self, phone_number: str) -> Optional[str]:
        """Get the verified primary email for a user by phone number"""
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT ue.email 
                FROM users u
                JOIN user_emails ue ON ue.user_id = u.id
                WHERE u.phone_number = %s
                AND ue.is_primary = TRUE
                AND ue.is_verified = TRUE
                LIMIT 1
            """, (phone_number,))
            
            result = cur.fetchone()
            return result['email'] if result else None
    
    def _mask_email(self, email: str) -> str:
        """Mask email for privacy (e.g., j***@example.com)"""
        if not email or '@' not in email:
            return email
        
        local, domain = email.split('@', 1)
        if len(local) <= 2:
            masked_local = local[0] + '*'
        else:
            masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
        
        return f"{masked_local}@{domain}"

    def _invalidate_previous_otps(self, phone_number: str):
        """Keep last N (3) most recent OTPs, invalidate older ones"""
        with get_db_cursor() as cur:
            # First, get IDs of the last 3 unverified, uninvalidated OTPs
            cur.execute("""
                SELECT id FROM otp_requests
                WHERE phone_number = %s
                AND is_verified = FALSE
                AND is_invalidated = FALSE
                ORDER BY created_at DESC
                LIMIT 3
            """, (phone_number,))
            
            recent_otps = cur.fetchall()
            recent_ids = [row['id'] for row in recent_otps] if recent_otps else []
            
            # Invalidate all OTPs that are NOT in the recent list
            if recent_ids:
                placeholders = ','.join(['%s'] * len(recent_ids))
                cur.execute(f"""
                    UPDATE otp_requests 
                    SET is_invalidated = TRUE
                    WHERE phone_number = %s 
                    AND is_verified = FALSE 
                    AND is_invalidated = FALSE
                    AND id NOT IN ({placeholders})
                """, (phone_number, *recent_ids))
            else:
                # No recent OTPs, invalidate all
                cur.execute("""
                    UPDATE otp_requests 
                    SET is_invalidated = TRUE
                    WHERE phone_number = %s 
                    AND is_verified = FALSE 
                    AND is_invalidated = FALSE
                """, (phone_number,))

    def _send_sms(self, phone_number: str, message: str):
        try:
            from backend.utils.validators import format_phone_for_semaphore

            formatted_phone = format_phone_for_semaphore(phone_number)

            if not Config.SEMAPHORE_API_KEY:
                return False, "Semaphore API key missing (SEMAPHORE_API_KEY)"

            url = "https://api.semaphore.co/api/v4/messages"
            payload = {
                "apikey": Config.SEMAPHORE_API_KEY,
                "number": formatted_phone,
                "message": message,
                "sendername": "HydroMET",  # try removing this to test default sender
            }

            response = requests.post(url, data=payload, timeout=10)

            # Always inspect body
            content_type = response.headers.get("Content-Type", "")
            body_text = response.text

            if "application/json" in content_type:
                try:
                    body = response.json()
                except Exception:
                    body = None
            else:
                body = None

            if not (200 <= response.status_code < 300):
                return False, f"HTTP {response.status_code}: {body or body_text}"

            # Semaphore typically returns a list of message objects; check for error fields/status
            return True, body or body_text

        except requests.exceptions.RequestException as e:
            return False, f"SMS sending failed: {str(e)}"

    def send_otp(self, phone_number: str) -> Tuple[bool, str, Optional[dict]]:
        """Generate and send OTP to phone number"""
        try:
            # Check rate limit
            is_allowed, rate_limit_msg = self._check_rate_limit(phone_number)
            if not is_allowed:
                return False, rate_limit_msg, None

            # Invalidate previous OTPs (keeping last 3)
            self._invalidate_previous_otps(phone_number)

            # Generate OTP
            otp_code = self._generate_otp()
            hashed_otp = self._hash_otp(otp_code)

            # Check if user has verified primary email
            verified_email = self._get_verified_primary_email(phone_number)
            fallback_email_possible = verified_email is not None

            # Store in database
            with get_db_cursor() as cur:
                expires_at = datetime.utcnow() + timedelta(minutes=self.otp_validity_minutes)

                cur.execute("""
                    INSERT INTO otp_requests 
                    (phone_number, otp_hash, expires_at, attempts_left, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, expires_at
                """, (phone_number, hashed_otp, expires_at, self.max_attempts, datetime.utcnow()))

                result = cur.fetchone()

                # ✅ FOR DEVELOPMENT: Print OTP to console
                print(f"🔐 OTP CODE (DEV ONLY): {otp_code} for {phone_number}")

                # Send SMS
                message = f"Your OTP is: {otp_code}. Valid for {self.otp_validity_minutes} minutes. Do not share this code."
                sms_success, sms_error = self._send_sms(phone_number, message)

                if not sms_success:
                    # ✅ Still show OTP in console if SMS fails
                    print(f"⚠️ SMS FAILED - Use this OTP for testing: {otp_code}")
                    return False, f"OTP generated but SMS failed: {sms_error}", None

                response_data = {
                    "otp_id": result['id'],
                    "phone_number": phone_number,
                    "expires_at": result['expires_at'].isoformat(),
                    "validity_minutes": self.otp_validity_minutes,
                    "resend_wait_seconds": 60,
                    "fallback_email_possible": fallback_email_possible
                }
                
                if fallback_email_possible and verified_email:
                    response_data["masked_email"] = self._mask_email(verified_email)

                return True, "OTP sent successfully", response_data

        except Exception as e:
            return False, f"Error sending OTP: {str(e)}", None

    def verify_otp(self, phone_number: str, otp_code: str) -> Tuple[bool, str, Optional[dict]]:
        """Verify OTP code for phone number"""
        try:
            # Sanitize OTP code
            otp_code = ''.join(filter(str.isdigit, otp_code))

            if len(otp_code) != 6:
                return False, "Invalid OTP format. Must be 6 digits", None

            with get_db_cursor() as cur:
                # Get all valid OTPs (not just the latest)
                cur.execute("""
                    SELECT id, otp_hash, expires_at, attempts_left, is_verified, is_invalidated
                    FROM otp_requests
                    WHERE phone_number = %s
                    AND is_verified = FALSE
                    AND is_invalidated = FALSE
                    ORDER BY created_at DESC
                """, (phone_number,))

                otp_records = cur.fetchall()

                if not otp_records:
                    return False, "No valid OTP found. Please request a new one", None

                # Try to match OTP against all valid records
                for otp_record in otp_records:
                    # Check if expired
                    if datetime.utcnow() > otp_record['expires_at']:
                        continue

                    # Check attempts left
                    if otp_record['attempts_left'] <= 0:
                        continue

                    # Verify OTP
                    if self._verify_otp_hash(otp_code, otp_record['otp_hash']):
                        # OTP is correct - mark it as verified
                        cur.execute("""
                            UPDATE otp_requests 
                            SET is_verified = TRUE, verified_at = %s
                            WHERE id = %s
                        """, (datetime.utcnow(), otp_record['id']))

                        # Invalidate all other unverified OTPs for this phone
                        cur.execute("""
                            UPDATE otp_requests 
                            SET is_invalidated = TRUE
                            WHERE phone_number = %s 
                            AND is_verified = FALSE 
                            AND id != %s
                        """, (phone_number, otp_record['id']))

                        return True, "OTP verified successfully", {
                            "otp_id": otp_record['id'],
                            "phone_number": phone_number,
                            "verified_at": datetime.utcnow().isoformat()
                        }

                # If we reach here, no OTP matched - decrement attempts on the most recent one
                most_recent = otp_records[0]
                
                # Check if most recent is expired or has no attempts
                if datetime.utcnow() > most_recent['expires_at']:
                    cur.execute("""
                        UPDATE otp_requests 
                        SET is_invalidated = TRUE 
                        WHERE id = %s
                    """, (most_recent['id'],))
                    return False, "OTP has expired. Please request a new one", None

                if most_recent['attempts_left'] <= 0:
                    cur.execute("""
                        UPDATE otp_requests 
                        SET is_invalidated = TRUE 
                        WHERE id = %s
                    """, (most_recent['id'],))
                    return False, "Maximum verification attempts exceeded. Please request a new OTP", None

                # Decrement attempts
                new_attempts = most_recent['attempts_left'] - 1
                cur.execute("""
                    UPDATE otp_requests 
                    SET attempts_left = %s
                    WHERE id = %s
                """, (new_attempts, most_recent['id']))

                if new_attempts > 0:
                    return False, f"Invalid OTP. {new_attempts} attempt(s) remaining", None
                else:
                    cur.execute("""
                        UPDATE otp_requests 
                        SET is_invalidated = TRUE 
                        WHERE id = %s
                    """, (most_recent['id'],))
                    return False, "Invalid OTP. Maximum attempts exceeded. Please request a new OTP", None

        except Exception as e:
            return False, f"Error verifying OTP: {str(e)}", None

    def resend_otp(self, phone_number: str) -> Tuple[bool, str, Optional[dict]]:
        """Resend OTP (generates new OTP and invalidates old one)"""
        return self.send_otp(phone_number)
