"""
Email Verification API endpoints
Handles email verification OTP requests and verification
"""

from fastapi import APIRouter, HTTPException, status

from backend.models.email_verification_manager import (
    EmailVerificationRequest,
    EmailVerificationVerifyRequest,
    EmailVerificationResponse
)
from backend.services.email_verification_manager import EmailVerificationManager
from backend.database import get_db_cursor

router = APIRouter(prefix="/api/email-verification", tags=["Email Verification"])

# Initialize Email Verification Manager
email_verification_manager = EmailVerificationManager()


@router.post("/send", response_model=EmailVerificationResponse)
async def send_email_verification(request: EmailVerificationRequest):
    """
    Send email verification OTP to user's primary email
    """
    try:
        # Verify email belongs to user
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, email, is_primary 
                FROM user_emails 
                WHERE user_id = %s AND email = %s
                LIMIT 1
            """, (request.user_id, request.email))
            
            email_record = cur.fetchone()
            
            if not email_record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Email not found for this user"
                )
            
            # Only allow verification of primary email
            if not email_record['is_primary']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only primary email can be verified"
                )

        # Send verification OTP
        success, message, data = email_verification_manager.send_verification_email(
            request.user_id, 
            request.email
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=message
            )

        return EmailVerificationResponse(
            success=True,
            message=message,
            data=data
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error sending email verification: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email verification: {str(e)}"
        )


@router.post("/verify", response_model=EmailVerificationResponse)
async def verify_email_otp(request: EmailVerificationVerifyRequest):
    """
    Verify email OTP code
    """
    try:
        print(f"🔍 Verifying email OTP for user: {request.user_id}, email: {request.email}")
        print(f"🔍 OTP code: {request.otp_code}")

        # Use EmailVerificationManager to verify OTP
        success, message, data = email_verification_manager.verify_email_otp(
            request.user_id,
            request.email,
            request.otp_code
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )

        return EmailVerificationResponse(
            success=True,
            message=message,
            data=data
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error verifying email OTP: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error verifying email OTP: {str(e)}"
        )
