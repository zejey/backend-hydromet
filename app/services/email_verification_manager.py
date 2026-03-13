"""
Email Verification Manager Service
Handles email verification OTP generation, verification, and rate limiting
"""

import random
import string
from datetime import datetime, timedelta
from typing import Optional, Tuple
import bcrypt

from app.database import get_db_cursor
from app.config import Config
from app.services.email_service import EmailService


class EmailVerificationManager:
    """
    Manages email verification OTP system
    """

    def __init__(self):
        self.otp_validity_minutes = 10  # Email OTP valid for 10 minutes
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

    def _check_rate_limit(self, user_id: str) -> Tuple[bool, Optional[str]]:
        """Check if user has exceeded rate limit for email verification"""
        with get_db_cursor() as cur:
            time_threshold = datetime.utcnow() - timedelta(hours=self.rate_limit_hours)

            cur.execute("""
                SELECT COUNT(*) as count 
                FROM email_verification_requests 
                WHERE user_id = %s 
                AND created_at > %s
            """, (user_id, time_threshold))

            result = cur.fetchone()
            count = result['count'] if result else 0

            if count >= self.max_requests_per_period:
                return False, f"Rate limit exceeded. Maximum {self.max_requests_per_period} email verification requests per {self.rate_limit_hours} hour(s)"

            return True, None

    def _invalidate_previous_requests(self, user_id: str, email: str):
        """Invalidate previous email verification requests for this user/email"""
        with get_db_cursor() as cur:
            cur.execute("""
                UPDATE email_verification_requests 
                SET is_invalidated = TRUE
                WHERE user_id = %s 
                AND email = %s
                AND is_verified = FALSE 
                AND is_invalidated = FALSE
            """, (user_id, email))

    def send_verification_email(self, user_id: str, email: str) -> Tuple[bool, str, Optional[dict]]:
        """Generate and send email verification OTP"""
        try:
            # Check rate limit
            is_allowed, rate_limit_msg = self._check_rate_limit(user_id)
            if not is_allowed:
                return False, rate_limit_msg, None

            # Verify user exists
            with get_db_cursor() as cur:
                cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
                if not cur.fetchone():
                    return False, "User not found", None

            # Invalidate previous requests
            self._invalidate_previous_requests(user_id, email)

            # Generate OTP
            otp_code = self._generate_otp()
            hashed_otp = self._hash_otp(otp_code)

            # Store in database
            with get_db_cursor() as cur:
                expires_at = datetime.utcnow() + timedelta(minutes=self.otp_validity_minutes)

                cur.execute("""
                    INSERT INTO email_verification_requests 
                    (user_id, email, otp_hash, expires_at, attempts_left, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, expires_at
                """, (user_id, email, hashed_otp, expires_at, self.max_attempts, datetime.utcnow()))

                result = cur.fetchone()

                # FOR DEVELOPMENT: Print OTP to console
                print(f"📧 EMAIL VERIFICATION OTP (DEV ONLY): {otp_code} for {email}")

                # Send email via Brevo
                email_result = EmailService.send_otp_email(email, otp_code)

                if not email_result["success"]:
                    print(f"⚠️ EMAIL FAILED - Use this OTP for testing: {otp_code}")
                    return False, f"Email verification OTP generated but email failed: {email_result.get('response', 'Unknown error')}", None

                return True, "Email verification OTP sent successfully", {
                    "verification_id": str(result['id']),
                    "email": email,
                    "expires_at": result['expires_at'].isoformat(),
                    "validity_minutes": self.otp_validity_minutes
                }

        except Exception as e:
            return False, f"Error sending email verification OTP: {str(e)}", None

    def verify_email_otp(self, user_id: str, email: str, otp_code: str) -> Tuple[bool, str, Optional[dict]]:
        """Verify email OTP code"""
        try:
            # Sanitize OTP code
            otp_code = ''.join(filter(str.isdigit, otp_code))

            if len(otp_code) != 6:
                return False, "Invalid OTP format. Must be 6 digits", None

            with get_db_cursor() as cur:
                # Get the latest valid OTP for this user/email
                cur.execute("""
                    SELECT id, otp_hash, expires_at, attempts_left, is_verified, is_invalidated
                    FROM email_verification_requests
                    WHERE user_id = %s
                    AND email = %s
                    AND is_verified = FALSE
                    AND is_invalidated = FALSE
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (user_id, email))

                verification_record = cur.fetchone()

                if not verification_record:
                    return False, "No valid verification request found. Please request a new one", None

                # Check if expired
                if datetime.utcnow() > verification_record['expires_at']:
                    cur.execute("""
                        UPDATE email_verification_requests 
                        SET is_invalidated = TRUE 
                        WHERE id = %s
                    """, (verification_record['id'],))
                    return False, "Verification OTP has expired. Please request a new one", None

                # Check attempts left
                if verification_record['attempts_left'] <= 0:
                    cur.execute("""
                        UPDATE email_verification_requests 
                        SET is_invalidated = TRUE 
                        WHERE id = %s
                    """, (verification_record['id'],))
                    return False, "Maximum verification attempts exceeded. Please request a new OTP", None

                # Verify OTP
                if self._verify_otp_hash(otp_code, verification_record['otp_hash']):
                    # OTP is correct - mark as verified
                    cur.execute("""
                        UPDATE email_verification_requests 
                        SET is_verified = TRUE, verified_at = %s
                        WHERE id = %s
                    """, (datetime.utcnow(), verification_record['id']))

                    # Update user_emails table to mark email as verified
                    cur.execute("""
                        UPDATE user_emails 
                        SET is_verified = TRUE
                        WHERE user_id = %s AND email = %s
                    """, (user_id, email))

                    return True, "Email verified successfully", {
                        "verification_id": str(verification_record['id']),
                        "email": email,
                        "verified_at": datetime.utcnow().isoformat()
                    }
                else:
                    # OTP is incorrect, decrement attempts
                    new_attempts = verification_record['attempts_left'] - 1
                    cur.execute("""
                        UPDATE email_verification_requests 
                        SET attempts_left = %s
                        WHERE id = %s
                    """, (new_attempts, verification_record['id']))

                    if new_attempts > 0:
                        return False, f"Invalid OTP. {new_attempts} attempt(s) remaining", None
                    else:
                        cur.execute("""
                            UPDATE email_verification_requests 
                            SET is_invalidated = TRUE 
                            WHERE id = %s
                        """, (verification_record['id'],))
                        return False, "Invalid OTP. Maximum attempts exceeded. Please request a new OTP", None

        except Exception as e:
            return False, f"Error verifying email OTP: {str(e)}", None
