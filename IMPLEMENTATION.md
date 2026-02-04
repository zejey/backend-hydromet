# OTP Email Fallback and Email Verification Implementation

This document describes the implementation of OTP email fallback and email verification features.

## Overview

This implementation adds two main features:
1. **Multiple Active OTPs**: Fixes delayed SMS issues by keeping the last 3 OTPs active
2. **Email Verification System**: Separate OTP system for verifying user emails

## Changes Made

### 1. Configuration (`backend/config.py`)
Added email configuration:
- `BREVO_API_KEY`: API key for Brevo email service
- `BREVO_SENDER`: Sender email address
- `ENVIRONMENT`: Environment indicator (development/production)

### 2. OTP Manager Updates (`backend/services/otp_manager.py`)

#### Multiple Active OTPs
- Modified `_invalidate_previous_otps()` to keep last 3 OTPs instead of invalidating all
- Updated `verify_otp()` to accept any valid (unexpired, unverified, uninvalidated) OTP
- This fixes the issue where delayed SMS OTPs would fail verification

#### Email Fallback Metadata
- Added `_get_verified_primary_email()` helper to check for verified primary email
- Added `_mask_email()` helper to mask emails for privacy (e.g., j***@example.com)
- Updated `send_otp()` to return:
  - `fallback_email_possible`: Boolean indicating if user has verified primary email
  - `masked_email`: Masked version of email if available
  - `resend_wait_seconds`: Fixed at 60 seconds

### 3. Email Verification System

#### Database (`migrations/001_create_email_verification_table.sql`)
New table: `email_verification_requests`
- Stores email verification OTP requests
- Similar structure to `otp_requests` but for email verification
- Links to `users` table via foreign key
- Includes indexes for performance

#### Service (`backend/services/email_verification_manager.py`)
New service: `EmailVerificationManager`
- Generates and sends email verification OTPs
- Verifies email OTP codes
- Rate limits email verification requests
- Updates `user_emails.is_verified` on successful verification

#### API Models (`backend/models/email_verification.py`)
New Pydantic models:
- `EmailVerificationRequest`: Request to send verification email
- `EmailVerificationVerifyRequest`: Request to verify email OTP
- `EmailVerificationResponse`: Standard response format

#### API Endpoints (`backend/api/email_verification.py`)
New endpoints:
- `POST /api/email-verification/send`: Send verification OTP to email
- `POST /api/email-verification/verify`: Verify email OTP code

### 4. User Emails Safety (`backend/api/user_emails.py`)
Updated `check_user_has_email()` endpoint to only return verified primary emails.

## API Usage

### OTP with Email Fallback Metadata

**Request:**
```bash
POST /api/otp/send
{
  "phone_number": "09171234567"
}
```

**Response:**
```json
{
  "success": true,
  "message": "OTP sent successfully",
  "data": {
    "otp_id": "uuid",
    "phone_number": "639171234567",
    "expires_at": "2026-02-04T12:00:00",
    "validity_minutes": 5,
    "resend_wait_seconds": 60,
    "fallback_email_possible": true,
    "masked_email": "j***@example.com"
  }
}
```

### Email Verification Flow

#### Step 1: Send Verification Email
**Request:**
```bash
POST /api/email-verification/send
{
  "user_id": "user-uuid-123",
  "email": "john@example.com"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Email verification OTP sent successfully",
  "data": {
    "verification_id": "uuid",
    "email": "john@example.com",
    "expires_at": "2026-02-04T12:10:00",
    "validity_minutes": 10
  }
}
```

#### Step 2: Verify Email OTP
**Request:**
```bash
POST /api/email-verification/verify
{
  "user_id": "user-uuid-123",
  "email": "john@example.com",
  "otp_code": "123456"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Email verified successfully",
  "data": {
    "verification_id": "uuid",
    "email": "john@example.com",
    "verified_at": "2026-02-04T12:05:00"
  }
}
```

## Security Features

1. **Rate Limiting**: Both phone and email OTP systems have rate limits (3 requests per hour)
2. **Attempt Limiting**: Maximum 3 verification attempts per OTP
3. **OTP Hashing**: All OTPs are hashed with bcrypt before storage
4. **Expiration**: Phone OTPs expire in 5 minutes, email OTPs in 10 minutes
5. **Invalidation**: Old OTPs are properly invalidated
6. **Email Masking**: Emails are masked in responses for privacy

## Testing

Run the test script to verify the implementation:
```bash
python /tmp/test_otp_implementation.py
```

## Database Migration

Before using the email verification endpoints, run the migration:
```bash
psql $DATABASE_URL -f migrations/001_create_email_verification_table.sql
```

See `migrations/README.md` for more details.

## Environment Variables

Required environment variables:
- `BREVO_API_KEY`: Brevo API key for sending emails
- `BREVO_SENDER`: Sender email address
- `ENVIRONMENT`: Set to "production" in production (defaults to "development")

## Notes

- Email verification is only available for primary emails
- Only verified primary emails can be used for OTP fallback
- The `check_user_has_email()` endpoint now only returns verified primary emails
- Multiple active OTPs (last 3) help prevent SMS delay issues
- Email OTPs are separate from phone OTPs for better security
