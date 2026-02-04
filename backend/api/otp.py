from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional

from backend.services.otp_manager import OTPManager
from backend.services.email_service import EmailService
from backend.database import get_db_cursor
from backend.utils.validators import normalize_phone_number

router = APIRouter(prefix="/api/otp", tags=["OTP Authentication"])

# Initialize OTP Manager
otp_manager = OTPManager()

class SendOTPRequest(BaseModel):
    phone_number: str

class SendOTPEmailRequest(BaseModel):
    phone_number: str
    email: EmailStr
    delivery_method: str = "email"  # "sms", "email", or "both"

class VerifyOTPRequest(BaseModel):
    phone_number: str
    otp_code: str

class OTPResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


@router.post("/send", response_model=OTPResponse)
async def send_otp(request: SendOTPRequest):
    """Send OTP to phone number via SMS"""
    try:
        phone_number = normalize_phone_number(request.phone_number)

        print(f"📱 OTP request for: {phone_number}")

        # Check if user exists
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

        # Use OTPManager to send OTP
        success, message, data = otp_manager.send_otp(phone_number)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=message
            )

        return OTPResponse(
            success=True,
            message=message,
            data=data
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error sending OTP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send OTP: {str(e)}"
        )


@router.post("/send-email", response_model=OTPResponse)
async def send_otp_email(request: SendOTPEmailRequest):
    """Send OTP via email (or both SMS and email)"""
    try:
        phone_number = normalize_phone_number(request.phone_number)

        print(f"📧 OTP request for: {phone_number} / {request.email}")
        print(f"📧 Delivery method: {request.delivery_method}")

        # Check if user exists and has this email
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT u.id, u.first_name, u.last_name, ue.email
                FROM users u
                LEFT JOIN user_emails ue ON ue.user_id = u.id AND ue.email = %s
                WHERE u.phone_number IN (%s, %s, %s)
                LIMIT 1
            """, (
                        request.email,
                        phone_number,
                        phone_number.lstrip('63'),
                        '0' + phone_number.lstrip('63')
                        ))

            user = cur.fetchone()

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

            if not user['email']:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Email not registered for this account"
                )

        sms_sent = False
        email_sent = False
        otp_data = None

        # Send via SMS if requested
        if request.delivery_method in ["sms", "both"]:
            success, message, data = otp_manager.send_otp(phone_number)
            sms_sent = success
            otp_data = data

            if not success and request.delivery_method == "sms":
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=message
                )

        # Send via Email if requested
        if request.delivery_method in ["email", "both"]:
            # Get the OTP from database (most recent one)
            with get_db_cursor() as cur:
                cur.execute("""
                    SELECT id, otp_hash, expires_at
                    FROM otp_requests
                    WHERE phone_number = %s
                    AND is_verified = FALSE
                    AND is_invalidated = FALSE
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (phone_number,))

                otp_record = cur.fetchone()

                if otp_record:
                    # For email, we need to generate a new OTP since we can't decrypt the hash
                    # Option 1: Store OTP temporarily for email (less secure)
                    # Option 2: Generate email-specific OTP (what we'll do)

                    import random
                    email_otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])

                    email_result = EmailService.send_otp_email(request.email, email_otp)
                    email_sent = email_result["success"]

                    # Store email OTP separately
                    if email_sent:
                        import bcrypt
                        from datetime import datetime, timedelta

                        otp_hash = bcrypt.hashpw(email_otp.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                        expires_at = datetime.utcnow() + timedelta(minutes=10)

                        cur.execute("""
                            INSERT INTO otp_requests (
                                phone_number, email, otp_hash, expires_at,
                                attempts_left, is_verified, is_invalidated, delivery_method
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING id
                        """, (
                                    phone_number, request.email, otp_hash, expires_at,
                                    3, False, False, 'email'
                                    ))

                        email_otp_data = cur.fetchone()
                        otp_data = {
                            "otp_id": email_otp_data['id'],
                            "phone_number": phone_number,
                            "email": request.email,
                            "expires_at": expires_at.isoformat()
                        }

                    if not email_sent and request.delivery_method == "email":
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to send email OTP"
                        )

        delivery_status = []
        if request.delivery_method in ["sms", "both"]:
            delivery_status.append(f"SMS: {'✓' if sms_sent else '✗'}")
        if request.delivery_method in ["email", "both"]:
            delivery_status.append(f"Email: {'✓' if email_sent else '✗'}")

        return OTPResponse(
            success=True,
            message=f"OTP sent via {request.delivery_method} ({', '.join(delivery_status)})",
            data={
                **otp_data,
                "sms_sent": sms_sent,
                "email_sent": email_sent,
                "delivery_method": request.delivery_method
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error sending OTP: {e}")
        import traceback
        traceback.print_exc()
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

        # Use OTPManager to verify OTP
        success, message, data = otp_manager.verify_otp(phone_number, request.otp_code)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )

        return OTPResponse(
            success=True,
            message=message,
            data=data
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
    """Send OTP during registration (checks if user already exists)"""
    try:
        phone_number = normalize_phone_number(request.phone_number)

        print(f"📱 Registration OTP request for: {phone_number}")

        # ✅ Check if user already exists
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, first_name, last_name, phone_number
                FROM users
                WHERE phone_number IN (%s, %s, %s)
                LIMIT 1
            """, (
                        phone_number,
                        phone_number.lstrip('63'),
                        '0' + phone_number.lstrip('63')
                        ))

            existing_user = cur.fetchone()

            if existing_user:
                print(f"❌ User already exists: {existing_user['first_name']} {existing_user['last_name']}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Phone number already registered. Please login instead."
                )

        # ✅ User doesn't exist - send OTP
        print(f"✅ Phone number available: {phone_number}")

        # Use OTPManager to send OTP (it handles rate limiting, etc.)
        success, message, data = otp_manager.send_otp(phone_number)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=message
            )

        # ✅ FOR DEVELOPMENT: Get the OTP code from database to show in logs
        # Remove this in production!
        otp_code_for_testing = None
        if Config.ENVIRONMENT != "production":  # Only in dev/testing
            with get_db_cursor() as cur:
                cur.execute("""
                    SELECT otp_hash FROM otp_requests
                    WHERE phone_number = %s
                    AND is_verified = FALSE
                    AND is_invalidated = FALSE
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (phone_number,))

                # Note: We can't decrypt bcrypt hash, so we need to store plaintext temporarily
                # OR just rely on SMS delivery and console logs from OTPManager
                # For now, rely on OTPManager's SMS success/failure logs

        return OTPResponse(
            success=True,
            message=message,
            data={
                **data,
                # Don't include OTP in response for security
                # Client should check SMS or console logs
            }
        )

    except HTTPException:
        raise
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

        # Check if user exists
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

        # Use OTPManager to resend (it invalidates old OTPs automatically)
        success, message, data = otp_manager.resend_otp(phone_number)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=message
            )

        return OTPResponse(
            success=True,
            message=message,
            data=data
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error resending OTP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resend OTP: {str(e)}"
        )
