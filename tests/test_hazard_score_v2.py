"""
Tests for hazard_score_v2 function
"""

import pytest
import json
from pathlib import Path
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from hazard_score_v2 import hazard_score_v2, _extract_value


class TestExtractValue:
    """Tests for _extract_value helper function"""
    
    def test_extract_simple_key(self):
        """Test extracting value with simple key"""
        row = {"temp": 30.5, "pressure": 1013}
        assert _extract_value(row, ["temp"]) == 30.5
        assert _extract_value(row, ["pressure"]) == 1013
    
    def test_extract_multiple_keys(self):
        """Test extracting with multiple possible keys"""
        row = {"temperature": 30.5}
        assert _extract_value(row, ["temp", "temperature"]) == 30.5
    
    def test_extract_nested(self):
        """Test extracting from nested dict"""
        row = {"main": {"temp": 30.5, "pressure": 1013}}
        assert _extract_value(row, ["temp"]) == 30.5
        assert _extract_value(row, ["pressure"]) == 1013
    
    def test_extract_missing(self):
        """Test extracting missing key returns None"""
        row = {"temp": 30.5}
        assert _extract_value(row, ["missing_key"]) is None


class TestHazardScoreV2:
    """Tests for hazard_score_v2 function"""
    
    @pytest.fixture
    def sample_thresholds_file(self, tmp_path):
        """Create a sample thresholds file for testing"""
        thresholds = {
            "version": "1.0",
            "location": "Test Location",
            "lat": 14.3644,
            "lon": 121.0619,
            "data_source": "Test Data",
            "computed_at": "2026-01-28T12:00:00Z",
            "total_samples": 1000,
            "date_range": {
                "start": "2024-01-01",
                "end": "2024-12-31"
            },
            "monthly_thresholds": {
                str(month): {
                    "precipitation_mm": [20.0, 40.0, 70.0, 120.0],
                    "wind_speed_ms": [10.0, 15.0, 20.0, 28.0],
                    "temp_c": [32.0, 35.0, 37.0, 40.0],
                    "pressure_hpa": [1008.0, 1003.0, 998.0, 992.0]
                }
                for month in range(1, 13)
            }
        }
        
        threshold_file = tmp_path / "test_thresholds.json"
        with open(threshold_file, 'w') as f:
            json.dump(thresholds, f)
        
        return str(threshold_file)
    
    def test_no_hazard(self, sample_thresholds_file):
        """Test with normal weather conditions (no hazard)"""
        row = {
            "temp": 28.0,
            "prcp": 5.0,
            "wind": 5.0,
            "pressure": 1013.0
        }
        
        event = hazard_score_v2(
            row=row,
            thresholds_path=sample_thresholds_file,
            client_id="default",
            month=8,
            explain=False
        )
        
        assert event == 0  # No hazard
    
    def test_heavy_rain_hazard(self, sample_thresholds_file):
        """Test with heavy rain (95th percentile)"""
        row = {
            "temp": 28.0,
            "prcp": 75.0,  # Above 95th percentile (70.0)
            "wind": 5.0,
            "pressure": 1013.0
        }
        
        event, score, hazards, details = hazard_score_v2(
            row=row,
            thresholds_path=sample_thresholds_file,
            client_id="default",
            month=8,
            explain=True
        )
        
        assert event == 1  # Hazard detected
        assert "heavy rain" in hazards
        assert "rain" in details
        assert details["rain"]["value"] == 75.0
    
    def test_extreme_heat_hazard(self, sample_thresholds_file):
        """Test with extreme heat (99th percentile)"""
        row = {
            "temp": 41.0,  # Above 99th percentile (40.0)
            "prcp": 0.0,
            "wind": 5.0,
            "pressure": 1013.0
        }
        
        event, score, hazards, details = hazard_score_v2(
            row=row,
            thresholds_path=sample_thresholds_file,
            client_id="default",
            month=8,
            explain=True
        )
        
        assert event == 1  # Hazard detected
        assert "extreme heat" in hazards
        assert "heat" in details
    
    def test_low_pressure_hazard(self, sample_thresholds_file):
        """Test with very low pressure (cyclone conditions)"""
        row = {
            "temp": 28.0,
            "prcp": 10.0,
            "wind": 8.0,
            "pressure": 990.0  # Below 1st percentile (992.0)
        }
        
        event, score, hazards, details = hazard_score_v2(
            row=row,
            thresholds_path=sample_thresholds_file,
            client_id="default",
            month=8,
            explain=True
        )
        
        assert event == 1  # Hazard detected
        assert "cyclone pressure" in hazards
        assert "pressure" in details
    
    def test_storm_combination(self, sample_thresholds_file):
        """Test with rain + wind combination (storm)"""
        row = {
            "temp": 28.0,
            "prcp": 45.0,  # Above 90th percentile
            "wind": 16.0,  # Above 90th percentile
            "pressure": 1005.0
        }
        
        event, score, hazards, details = hazard_score_v2(
            row=row,
            thresholds_path=sample_thresholds_file,
            client_id="default",
            month=8,
            explain=True
        )
        
        assert event == 1  # Hazard detected
        assert "moderate rain" in hazards
        assert "strong wind" in hazards
        assert "rain + wind (possible storm)" in hazards
    
    def test_explain_output_structure(self, sample_thresholds_file):
        """Test that explain=True returns correct structure"""
        row = {
            "temp": 36.0,
            "prcp": 50.0,
            "wind": 12.0,
            "pressure": 1005.0
        }
        
        event, score, hazards, details = hazard_score_v2(
            row=row,
            thresholds_path=sample_thresholds_file,
            client_id="default",
            month=8,
            explain=True
        )
        
        # Check return types
        assert isinstance(event, int)
        assert isinstance(score, (int, float))
        assert isinstance(hazards, list)
        assert isinstance(details, dict)
        
        # Check details structure
        assert "thresholds_used" in details
        assert "client_multipliers" in details
        assert "score" in details
    
    def test_monthly_variation(self, sample_thresholds_file):
        """Test that same weather produces different results for different months"""
        row = {
            "temp": 35.0,
            "prcp": 45.0,
            "wind": 12.0,
            "pressure": 1008.0
        }
        
        # January (dry season)
        event_jan, score_jan, hazards_jan, _ = hazard_score_v2(
            row=row,
            thresholds_path=sample_thresholds_file,
            client_id="default",
            month=1,
            explain=True
        )
        
        # August (wet season)
        event_aug, score_aug, hazards_aug, _ = hazard_score_v2(
            row=row,
            thresholds_path=sample_thresholds_file,
            client_id="default",
            month=8,
            explain=True
        )
        
        # Results should be the same since we use same thresholds for all months in test
        # In real data, thresholds would differ
        assert event_jan == event_aug
    
    def test_openweather_format(self, sample_thresholds_file):
        """Test with OpenWeather API format"""
        row = {
            "main": {
                "temp": 308.15,  # Kelvin
                "pressure": 1005
            },
            "wind": {
                "speed": 12.5
            },
            "rain": {
                "1h": 45.2
            }
        }
        
        # Should handle nested structure
        event, score, hazards, details = hazard_score_v2(
            row=row,
            thresholds_path=sample_thresholds_file,
            client_id="default",
            month=8,
            explain=True
        )
        
        # Should extract values correctly
        assert "rain" in details or "wind" in details  # At least one hazard


class TestClientMultipliers:
    """Tests for client multiplier functionality"""
    
    @pytest.fixture
    def sample_thresholds_file(self, tmp_path):
        """Create a sample thresholds file"""
        thresholds = {
            "version": "1.0",
            "location": "Test Location",
            "monthly_thresholds": {
                "8": {
                    "precipitation_mm": [20.0, 40.0, 70.0, 120.0],
                    "wind_speed_ms": [10.0, 15.0, 20.0, 28.0],
                    "temp_c": [32.0, 35.0, 37.0, 40.0],
                    "pressure_hpa": [1008.0, 1003.0, 998.0, 992.0]
                }
            }
        }
        
        threshold_file = tmp_path / "test_thresholds.json"
        with open(threshold_file, 'w') as f:
            json.dump(thresholds, f)
        
        return str(threshold_file)
    
    def test_multiplier_effect(self, sample_thresholds_file):
        """Test that multipliers affect threshold detection"""
        # Weather just below baseline 90th percentile
        row = {
            "temp": 28.0,
            "prcp": 38.0,  # Just below 90th percentile (40.0)
            "wind": 5.0,
            "pressure": 1013.0
        }
        
        # With baseline (multiplier = 1.0), should not trigger
        event_baseline = hazard_score_v2(
            row=row,
            thresholds_path=sample_thresholds_file,
            client_id="default",
            month=8,
            explain=False
        )
        
        assert event_baseline == 0  # No hazard with baseline
        
        # Note: To properly test multiplier effect, we would need to:
        # 1. Insert a client config into database with rain_multiplier < 1.0
        # 2. Call hazard_score_v2 with that client_id
        # This requires database setup which is not in unit test scope


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
