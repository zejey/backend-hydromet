-- Migration: Add client threshold configuration system
-- Description: Creates table for per-client threshold multipliers and alert rules
-- Date: 2026-01-28

CREATE TABLE IF NOT EXISTS client_threshold_config (
    client_id TEXT PRIMARY KEY,
    location_name TEXT NOT NULL,
    barangay TEXT,
    
    -- Threshold multipliers (1.0 = baseline)
    rain_multiplier FLOAT DEFAULT 1.0 CHECK (rain_multiplier > 0),
    wind_multiplier FLOAT DEFAULT 1.0 CHECK (wind_multiplier > 0),
    heat_multiplier FLOAT DEFAULT 1.0 CHECK (heat_multiplier > 0),
    pressure_multiplier FLOAT DEFAULT 1.0 CHECK (pressure_multiplier > 0),
    
    -- Alert rules
    alert_duration_hours INT DEFAULT 2 CHECK (alert_duration_hours >= 0),
    cooldown_hours INT DEFAULT 6 CHECK (cooldown_hours >= 0),
    
    -- Metadata
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by TEXT,
    
    -- Constraints
    CONSTRAINT valid_multipliers CHECK (
        rain_multiplier BETWEEN 0.1 AND 5.0 AND
        wind_multiplier BETWEEN 0.1 AND 5.0 AND
        heat_multiplier BETWEEN 0.1 AND 5.0 AND
        pressure_multiplier BETWEEN 0.1 AND 5.0
    )
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_client_location ON client_threshold_config(location_name);
CREATE INDEX IF NOT EXISTS idx_client_barangay ON client_threshold_config(barangay);

-- Insert default baseline config
INSERT INTO client_threshold_config (
    client_id, 
    location_name, 
    description
) VALUES (
    'default', 
    'San Pedro (Baseline)', 
    'Default thresholds for San Pedro area - no adjustments'
) ON CONFLICT (client_id) DO NOTHING;

-- Comments for documentation
COMMENT ON TABLE client_threshold_config IS 'Per-client threshold multipliers and alert rules for weather hazard detection';
COMMENT ON COLUMN client_threshold_config.rain_multiplier IS 'Multiplier for rain thresholds (< 1.0 = more sensitive, > 1.0 = less sensitive)';
COMMENT ON COLUMN client_threshold_config.wind_multiplier IS 'Multiplier for wind thresholds (< 1.0 = more sensitive, > 1.0 = less sensitive)';
COMMENT ON COLUMN client_threshold_config.heat_multiplier IS 'Multiplier for heat thresholds (< 1.0 = more sensitive, > 1.0 = less sensitive)';
COMMENT ON COLUMN client_threshold_config.pressure_multiplier IS 'Multiplier for pressure thresholds (< 1.0 = more sensitive, > 1.0 = less sensitive)';
COMMENT ON COLUMN client_threshold_config.alert_duration_hours IS 'How long alert stays active (hours)';
COMMENT ON COLUMN client_threshold_config.cooldown_hours IS 'Cooldown period before next alert can be sent (hours)';
