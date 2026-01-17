from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from datetime import datetime, timedelta
import random
import requests
from typing import Optional

from backend.database import get_db_cursor
from backend.utils.validators import normalize_phone_number
from backend.config import Config 

router = APIRouter(prefix="/api/otp", tags=["OTP Authentication"])

class SendOTPRequest(BaseModel):
    phone_number: str

class VerifyOTPRequest(BaseModel):
    phone_number: str
    otp_code: str

class OTPResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


def to_e164_with_plus(phone_number: str) -> str:
    phone_number = phone_number.strip()
    return phone_number if phone_number.startswith("+") else f"+{phone_number}"


@router.post("/send", response_model=OTPResponse)
async def send_otp(request: SendOTPRequest):
    """Send OTP to phone number"""
    try:
        phone_number = normalize_phone_number(request.phone_number)
        
        print(f"📱 OTP request for: {phone_number}")
        
        # ✅ Check if user exists first
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, first_name, last_name, is_verified
                FROM users
                WHERE phone_number IN (%s, %s, %s)
                LIMIT 1
            """, (
                phone_number,
                phone_number.lstrip('63'),
                '0' + phone_number.lstrip('63')
            ))
            
            user = cur.fetchone()
            
            if not user:
                print(f"❌ User not found for phone: {phone_number}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found. Please register first."
                )
            
            print(f"✅ User found: {user['first_name']} {user['last_name']}")
        
        # Generate 6-digit OTP
        otp_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        # ✅ Hash the OTP
        import bcrypt
        otp_hash = bcrypt.hashpw(otp_code.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # ✅ Save OTP to database with correct schema
        with get_db_cursor() as cur:
            cur.execute("""
                INSERT INTO otp_requests (
                    phone_number, 
                    otp_hash, 
                    expires_at,
                    attempts_left,
                    is_verified,
                    is_invalidated
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                phone_number,
                otp_hash,
                expires_at,
                3,      # attempts_left
                False,  # is_verified
                False   # is_invalidated
            ))
            
            otp_id = cur.fetchone()['id']
        
        # ✅ Send OTP via TextBee API
        sms_sent = False
        try:
            if not Config.TEXTBEE_API_KEY or not Config.TEXTBEE_DEVICE_ID:
                raise Exception("Missing TEXTBEE_API_KEY or TEXTBEE_DEVICE_ID in environment")

            recipient = to_e164_with_plus(phone_number)

            textbee_response = requests.post(
                f"{Config.TEXTBEE_BASE_URL}/gateway/devices/{Config.TEXTBEE_DEVICE_ID}/send-sms",
                headers={
                    "x-api-key": Config.TEXTBEE_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "recipients": [recipient],
                    "message": f"Your HydroMet login code is: {otp_code}. Valid for 10 minutes. Do not share this code.",
                },
                timeout=10
            )
            
            print(f"📡 TextBee Response Status: {textbee_response.status_code}")
            print(f"📡 TextBee Response: {textbee_response.text}")
            
            if 200 <= textbee_response.status_code < 300:
                sms_sent = True
                print("✅ SMS sent successfully via TextBee")
            else:
                print(f"⚠️ TextBee error: HTTP {textbee_response.status_code}")
                
        except Exception as sms_error:
            print(f"⚠️ SMS service error: {sms_error}")
        
        # Testing fallback
        if not sms_sent:
            print(f"📱 OTP Code for testing (SMS failed): {otp_code}")
        
        return OTPResponse(
            success=True,
            message="OTP sent successfully" if sms_sent else "OTP generated (check console)",
            data={
                "otp_id": otp_id,
                "expires_at": expires_at.isoformat(),
                "phone_number": phone_number,
                "sms_sent": sms_sent
            }
        )        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error sending OTP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send OTP: {str(e)}"
        )

@router.post("/verify", response_model=OTPResponse)
async def verify_otp(request: VerifyOTPRequest):
    """Verify OTP code"""
    try:
        phone_number = normalize_phone_number(request.phone_number)
        
        print(f"🔍 Verifying OTP for phone: {phone_number}")
        print(f"🔍 OTP code: {request.otp_code}")
        
        with get_db_cursor() as cur:
            # ✅ Get latest OTP with correct column names
            cur.execute("""
                SELECT id, otp_hash, expires_at, is_verified, is_invalidated, attempts_left
                FROM otp_requests
                WHERE phone_number = %s AND is_invalidated = FALSE
                ORDER BY created_at DESC
                LIMIT 1
            """, (phone_number,))
            
            otp_record = cur.fetchone()
            
            if not otp_record:
                print(f"❌ No OTP found for phone: {phone_number}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No OTP request found for this phone number"
                )
            
            # Check if already verified
            if otp_record['is_verified']:
                print(f"⚠️ OTP already used")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OTP has already been used"
                )
            
            # Check if expired
            if datetime.utcnow() > otp_record['expires_at']:
                print(f"⚠️ OTP expired at {otp_record['expires_at']}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OTP has expired. Please request a new one."
                )
            
            # Check attempts left
            if otp_record['attempts_left'] <= 0:
                print(f"⚠️ Too many failed attempts")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Too many failed attempts. Please request a new OTP."
                )
            
            # ✅ Verify OTP using bcrypt
            import bcrypt
            otp_match = bcrypt.checkpw(
                request.otp_code.encode('utf-8'), 
                otp_record['otp_hash'].encode('utf-8')
            )
            
            if not otp_match:
                # Decrement attempts
                new_attempts = otp_record['attempts_left'] - 1
                cur.execute("""
                    UPDATE otp_requests
                    SET attempts_left = %s
                    WHERE id = %s
                """, (new_attempts, otp_record['id']))
                
                print(f"❌ Invalid OTP. Attempts left: {new_attempts}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid OTP code. {new_attempts} attempts remaining."
                )
            
            # ✅ Mark as verified
            cur.execute("""
                UPDATE otp_requests
                SET is_verified = TRUE, verified_at = %s
                WHERE id = %s
            """, (datetime.utcnow(), otp_record['id']))
            
            print(f"✅ OTP verified successfully")
            
            return OTPResponse(
                success=True,
                message="OTP verified successfully",
                data=None
            )
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error verifying OTP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error verifying OTP: {str(e)}"
        )
                
@router.post("/send-registration", response_model=OTPResponse)
async def send_otp_registration(request: SendOTPRequest):
    """Send OTP during registration (doesn't check if user exists)"""
    try:
        phone_number = normalize_phone_number(request.phone_number)
        
        print(f"📱 Registration OTP request for: {phone_number}")
        
        # Generate 6-digit OTP
        otp_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        print(f"🔢 Generated OTP: {otp_code}")
        
        # ✅ Hash the OTP before storing (use bcrypt)
        import bcrypt
        otp_hash = bcrypt.hashpw(otp_code.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # ✅ Save OTP to database with correct column names
        with get_db_cursor() as cur:
            cur.execute("""
                INSERT INTO otp_requests (
                    phone_number, 
                    otp_hash, 
                    expires_at, 
                    attempts_left,
                    is_verified,
                    is_invalidated
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                phone_number, 
                otp_hash,
                expires_at,
                3,
                False,
                False
            ))
            
            otp_id = cur.fetchone()['id']
            print(f"💾 OTP saved: ID {otp_id}")
        
        # ✅ Send OTP via TextBee API
        sms_sent = False
        try:
            if not Config.TEXTBEE_API_KEY or not Config.TEXTBEE_DEVICE_ID:
                raise Exception("Missing TEXTBEE_API_KEY or TEXTBEE_DEVICE_ID in environment")

            recipient = to_e164_with_plus(phone_number)

            textbee_response = requests.post(
                f"{Config.TEXTBEE_BASE_URL}/gateway/devices/{Config.TEXTBEE_DEVICE_ID}/send-sms",
                headers={
                    "x-api-key": Config.TEXTBEE_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "recipients": [recipient],
                    "message": f"Your HydroMet verification code is: {otp_code}. Valid for 10 minutes. Do not share this code.",
                },
                timeout=10
            )
            
            print(f"📡 TextBee Response Status: {textbee_response.status_code}")
            print(f"📡 TextBee Response: {textbee_response.text}")
            
            if 200 <= textbee_response.status_code < 300:
                sms_sent = True
                print("✅ SMS sent successfully via TextBee")
            else:
                print(f"⚠️ TextBee error: HTTP {textbee_response.status_code}")
                
        except Exception as sms_error:
            print(f"⚠️ SMS service error: {sms_error}")
        
        # Testing fallback: Show OTP in console if SMS failed
        if not sms_sent:
            print(f"📱 OTP Code for testing (SMS failed): {otp_code}")
        
        return OTPResponse(
            success=True,
            message="OTP sent successfully" if sms_sent else "OTP generated (check console)",
            data={
                "otp_id": otp_id,
                "expires_at": expires_at.isoformat(),
                "phone_number": phone_number,
                "otp_code": otp_code if not sms_sent else None,
                "sms_sent": sms_sent
            }
        )
    except Exception as e:
        print(f"❌ Error sending registration OTP: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send OTP: {str(e)}"
        )

@router.post("/resend", response_model=OTPResponse)
async def resend_otp(request: SendOTPRequest):
    """Resend OTP (invalidates previous OTP)"""
    try:
        phone_number = normalize_phone_number(request.phone_number)
        
        print(f"🔄 Resending OTP for: {phone_number}")
        
        # ✅ Check if user exists
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id FROM users
                WHERE phone_number IN (%s, %s, %s)
                LIMIT 1
            """, (
                phone_number,
                phone_number.lstrip('63'),
                '0' + phone_number.lstrip('63')
            ))
            
            if not cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found. Please register first."
                )
        
        # ✅ Invalidate previous OTPs
        with get_db_cursor() as cur:
            cur.execute("""
                UPDATE otp_requests
                SET is_invalidated = TRUE
                WHERE phone_number = %s AND is_verified = FALSE AND is_invalidated = FALSE
            """, (phone_number,))
        
        # Send new OTP (reuse send_otp logic)
        return await send_otp(request)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error resending OTP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resend OTP: {str(e)}"
        )
