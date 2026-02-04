-- Migration: Create email_verification_requests table
-- Purpose: Support email verification OTP system separate from phone OTPs
-- Date: 2026-02-04

CREATE TABLE IF NOT EXISTS email_verification_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    email VARCHAR(255) NOT NULL,
    otp_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    attempts_left INTEGER NOT NULL DEFAULT 3,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at TIMESTAMP,
    is_invalidated BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Foreign key to users table
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_email_verification_user_id ON email_verification_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_email_verification_email ON email_verification_requests(email);
CREATE INDEX IF NOT EXISTS idx_email_verification_created_at ON email_verification_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_email_verification_verified ON email_verification_requests(is_verified, is_invalidated);

-- Add comment to table
COMMENT ON TABLE email_verification_requests IS 'Stores email verification OTP requests for user email verification';
