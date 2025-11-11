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
        self.api_token = Config.IPROG_API_TOKEN
        self.otp_validity_minutes = Config.OTP_VALIDITY_MINUTES
        self.max_attempts = Config.OTP_MAX_ATTEMPTS
        self.rate_limit_hours = Config.OTP_RATE_LIMIT_HOURS
        self.max_requests_per_period = Config.OTP_MAX_REQUESTS_PER_PERIOD
        self.sms_endpoint = "https://sms.iprogtech.com/api/v1/sms_messages"
    
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
    
    def _send_sms(self, phone_number: str, message: str) -> Tuple[bool, Optional[str]]:
        """Send SMS via iProg SMS API"""
        try:
            # Format phone number for SMS API (639XXXXXXXXX)
            formatted_phone = format_phone_for_sms(phone_number)
            
            params = {
                'api_token': self.api_token,
                'message': message,
                'phone_number': formatted_phone
            }
            
            response = requests.post(self.sms_endpoint, params=params, timeout=10)
            
            if response.status_code == 200:
                return True, None
            else:
                return False, f"SMS API error: {response.status_code} - {response.text}"
                
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
                
                # Send SMS
                message = f"Your OTP is: {otp_code}. Valid for {self.otp_validity_minutes} minutes. Do not share this code."
                sms_success, sms_error = self._send_sms(phone_number, message)
                
                if not sms_success:
                    return False, f"OTP generated but SMS failed: {sms_error}", None
                
                return True, "OTP sent successfully", {
                    "otp_id": result['id'],
                    "phone_number": phone_number,
                    "expires_at": result['expires_at'].isoformat(),
                    "validity_minutes": self.otp_validity_minutes
                }
                
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
                # Get the latest valid OTP
                cur.execute("""
                    SELECT id, otp_hash, expires_at, attempts_left, is_verified, is_invalidated
                    FROM otp_requests
                    WHERE phone_number = %s
                    AND is_verified = FALSE
                    AND is_invalidated = FALSE
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (phone_number,))
                
                otp_record = cur.fetchone()
                
                if not otp_record:
                    return False, "No valid OTP found. Please request a new one", None
                
                # Check if expired
                if datetime.utcnow() > otp_record['expires_at']:
                    cur.execute("""
                        UPDATE otp_requests 
                        SET is_invalidated = TRUE 
                        WHERE id = %s
                    """, (otp_record['id'],))
                    return False, "OTP has expired. Please request a new one", None
                
                # Check attempts left
                if otp_record['attempts_left'] <= 0:
                    cur.execute("""
                        UPDATE otp_requests 
                        SET is_invalidated = TRUE 
                        WHERE id = %s
                    """, (otp_record['id'],))
                    return False, "Maximum verification attempts exceeded. Please request a new OTP", None
                
                # Verify OTP
                if self._verify_otp_hash(otp_code, otp_record['otp_hash']):
                    # OTP is correct
                    cur.execute("""
                        UPDATE otp_requests 
                        SET is_verified = TRUE, verified_at = %s
                        WHERE id = %s
                    """, (datetime.utcnow(), otp_record['id']))
                    
                    return True, "OTP verified successfully", {
                        "otp_id": otp_record['id'],
                        "phone_number": phone_number,
                        "verified_at": datetime.utcnow().isoformat()
                    }
                else:
                    # OTP is incorrect, decrement attempts
                    new_attempts = otp_record['attempts_left'] - 1
                    cur.execute("""
                        UPDATE otp_requests 
                        SET attempts_left = %s
                        WHERE id = %s
                    """, (new_attempts, otp_record['id']))
                    
                    if new_attempts > 0:
                        return False, f"Invalid OTP. {new_attempts} attempt(s) remaining", None
                    else:
                        cur.execute("""
                            UPDATE otp_requests 
                            SET is_invalidated = TRUE 
                            WHERE id = %s
                        """, (otp_record['id'],))
                        return False, "Invalid OTP. Maximum attempts exceeded. Please request a new OTP", None
                
        except Exception as e:
            return False, f"Error verifying OTP: {str(e)}", None
    
    def resend_otp(self, phone_number: str) -> Tuple[bool, str, Optional[dict]]:
        """Resend OTP (generates new OTP and invalidates old one)"""
        return self.send_otp(phone_number)