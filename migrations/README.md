# Database Migrations

This directory contains SQL migration scripts for the backend-hydromet database.

## Running Migrations

To apply migrations, connect to your PostgreSQL database and run the SQL files in order:

```bash
# Using psql
psql $DATABASE_URL -f migrations/001_create_email_verification_table.sql

# Or using the database connection from your environment
psql -h $PGHOST -U $PGUSER -d $PGDATABASE -f migrations/001_create_email_verification_table.sql
```

## Available Migrations

### 001_create_email_verification_table.sql
Creates the `email_verification_requests` table for the email verification OTP system.

**What it does:**
- Creates table with UUID primary key
- Adds foreign key to users table
- Creates indexes for performance
- Supports email verification OTP flow

**Required before:**
- Using `/api/email-verification/send` endpoint
- Using `/api/email-verification/verify` endpoint

## Migration Order

Migrations should be applied in numerical order:
1. 001_create_email_verification_table.sql
