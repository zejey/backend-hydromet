"""
Tests for threshold calculation and loading
"""

import pytest
import json
import pandas as pd
from pathlib import Path
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from threshold_loader import ThresholdLoader
from calculate_thresholds import calculate_thresholds


class TestThresholdLoader:
    """Tests for ThresholdLoader class"""
    
    def test_validate_valid_structure(self):
        """Test validation with valid threshold structure"""
        valid_thresholds = {
            "version": "1.0",
            "location": "Test Location",
            "monthly_thresholds": {
                str(month): {
                    "precipitation_mm": [10.0, 20.0, 30.0, 40.0],
                    "wind_speed_ms": [5.0, 10.0, 15.0, 20.0],
                    "temp_c": [30.0, 32.0, 35.0, 38.0],
                    "pressure_hpa": [1010.0, 1005.0, 1000.0, 995.0]
                }
                for month in range(1, 13)
            }
        }
        
        assert ThresholdLoader.validate(valid_thresholds) is True
    
    def test_validate_missing_month(self):
        """Test validation fails with missing month"""
        invalid_thresholds = {
            "version": "1.0",
            "location": "Test Location",
            "monthly_thresholds": {
                "1": {
                    "precipitation_mm": [10.0, 20.0, 30.0, 40.0],
                    "wind_speed_ms": [5.0, 10.0, 15.0, 20.0],
                    "temp_c": [30.0, 32.0, 35.0, 38.0],
                    "pressure_hpa": [1010.0, 1005.0, 1000.0, 995.0]
                }
                # Missing months 2-12
            }
        }
        
        assert ThresholdLoader.validate(invalid_thresholds) is False
    
    def test_validate_missing_variable(self):
        """Test validation fails with missing weather variable"""
        invalid_thresholds = {
            "version": "1.0",
            "location": "Test Location",
            "monthly_thresholds": {
                str(month): {
                    "precipitation_mm": [10.0, 20.0, 30.0, 40.0],
                    "wind_speed_ms": [5.0, 10.0, 15.0, 20.0],
                    "temp_c": [30.0, 32.0, 35.0, 38.0]
                    # Missing pressure_hpa
                }
                for month in range(1, 13)
            }
        }
        
        assert ThresholdLoader.validate(invalid_thresholds) is False
    
    def test_validate_wrong_percentile_count(self):
        """Test validation fails with wrong number of percentiles"""
        invalid_thresholds = {
            "version": "1.0",
            "location": "Test Location",
            "monthly_thresholds": {
                str(month): {
                    "precipitation_mm": [10.0, 20.0, 30.0],  # Only 3 values
                    "wind_speed_ms": [5.0, 10.0, 15.0, 20.0],
                    "temp_c": [30.0, 32.0, 35.0, 38.0],
                    "pressure_hpa": [1010.0, 1005.0, 1000.0, 995.0]
                }
                for month in range(1, 13)
            }
        }
        
        assert ThresholdLoader.validate(invalid_thresholds) is False
    
    def test_get_for_month_valid(self):
        """Test getting thresholds for a specific month"""
        thresholds = {
            "version": "1.0",
            "location": "Test Location",
            "monthly_thresholds": {
                "8": {
                    "precipitation_mm": [25.0, 45.0, 75.0, 120.0],
                    "wind_speed_ms": [8.0, 12.0, 18.0, 25.0],
                    "temp_c": [32.0, 34.0, 36.0, 38.0],
                    "pressure_hpa": [1008.0, 1003.0, 998.0, 992.0]
                }
            }
        }
        
        month_8 = ThresholdLoader.get_for_month(thresholds, 8)
        assert month_8["precipitation_mm"] == [25.0, 45.0, 75.0, 120.0]
        assert month_8["wind_speed_ms"] == [8.0, 12.0, 18.0, 25.0]
    
    def test_get_for_month_invalid(self):
        """Test getting thresholds with invalid month number"""
        thresholds = {
            "version": "1.0",
            "location": "Test Location",
            "monthly_thresholds": {}
        }
        
        with pytest.raises(ValueError):
            ThresholdLoader.get_for_month(thresholds, 13)  # Invalid month
        
        with pytest.raises(ValueError):
            ThresholdLoader.get_for_month(thresholds, 0)  # Invalid month


class TestCalculateThresholds:
    """Tests for calculate_thresholds function"""
    
    def test_calculate_with_sample_data(self):
        """Test threshold calculation with sample data"""
        # Create sample DataFrame
        dates = pd.date_range('2024-01-01', periods=100, freq='h')
        df = pd.DataFrame({
            'timestamp': dates,
            'temp': [28 + i % 10 for i in range(100)],
            'precipitation': [i % 20 for i in range(100)],
            'wind_speed': [5 + i % 15 for i in range(100)],
            'pressure': [1013 - i % 30 for i in range(100)]
        })
        
        thresholds = calculate_thresholds(df, percentiles=[75, 90, 95, 99])
        
        # Check structure
        assert 'monthly_thresholds' in thresholds
        assert len(thresholds) > 0
        
        # Check all months present
        for month in range(1, 13):
            assert str(month) in thresholds
    
    def test_seasonal_differences(self):
        """Test that wet and dry season have different thresholds"""
        # Create data with seasonal patterns
        dates = pd.date_range('2024-01-01', periods=8760, freq='h')  # Full year
        df = pd.DataFrame({
            'timestamp': dates,
            'temp': [28] * 8760,
            'precipitation': [50 if 5 <= dt.month <= 10 else 10 for dt in dates],  # Wet vs dry
            'wind_speed': [10] * 8760,
            'pressure': [1013] * 8760
        })
        
        thresholds = calculate_thresholds(df, percentiles=[75, 90, 95, 99])
        
        # Wet season (August) should have higher rain thresholds than dry season (January)
        jan_rain = thresholds["1"]["precipitation_mm"]
        aug_rain = thresholds["8"]["precipitation_mm"]
        
        # August rain thresholds should be higher (rain is more common)
        assert aug_rain[1] > jan_rain[1]  # 90th percentile


class TestIntegration:
    """Integration tests for threshold system"""
    
    def test_end_to_end_workflow(self, tmp_path):
        """Test complete workflow: generate data -> calculate thresholds -> load thresholds"""
        # Step 1: Create sample data
        dates = pd.date_range('2024-01-01', periods=1000, freq='h')
        df = pd.DataFrame({
            'timestamp': dates,
            'temp': [28 + (i % 10) for i in range(1000)],
            'precipitation': [(i % 30) for i in range(1000)],
            'wind_speed': [5 + (i % 20) for i in range(1000)],
            'pressure': [1013 - (i % 25) for i in range(1000)]
        })
        
        # Step 2: Calculate thresholds
        thresholds = calculate_thresholds(df, percentiles=[75, 90, 95, 99])
        
        # Add required metadata
        output = {
            "version": "1.0",
            "location": "Test Location",
            "lat": 14.3644,
            "lon": 121.0619,
            "data_source": "Test Data",
            "computed_at": "2026-01-28T12:00:00Z",
            "total_samples": len(df),
            "date_range": {
                "start": "2024-01-01",
                "end": "2024-12-31"
            },
            "monthly_thresholds": thresholds
        }
        
        # Step 3: Save to file
        output_file = tmp_path / "test_thresholds.json"
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        # Step 4: Load and validate
        loaded = ThresholdLoader.load(str(output_file))
        
        assert ThresholdLoader.validate(loaded) is True
        assert loaded["location"] == "Test Location"
        assert len(loaded["monthly_thresholds"]) == 12
        
        # Step 5: Get thresholds for a specific month
        month_5 = ThresholdLoader.get_for_month(loaded, 5)
        assert "precipitation_mm" in month_5
        assert len(month_5["precipitation_mm"]) == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
