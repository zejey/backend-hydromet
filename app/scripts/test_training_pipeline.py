"""
Unit tests for the multi-hazard training pipeline.

Tests cover:
- dt column stays numeric and sorted after load_from_csv
- Thunderstorm labels produce positives on a synthetic dataset
- Column aliases (feels_like_c, temp_c, dew_point_c) are created by prepare_dataset
"""

import io
import pytest
import pandas as pd
import numpy as np

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from data_preparation import DataPreparator
from hazard_labeling import HazardLabeler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_csv_with_unix_dt(n_rows=20, thunderstorm_rows=None, rain_heavy_rows=None):
    """Build a minimal CSV string with unix-epoch 'dt' integers."""
    base_epoch = 1_000_000_000  # ~2001-09-09
    rows = []
    for i in range(n_rows):
        dt = base_epoch + i * 3600  # hourly
        weather_id = 800            # default: clear
        rain_1h = 0.0
        if thunderstorm_rows and i in thunderstorm_rows:
            weather_id = 210        # thunderstorm
        if rain_heavy_rows and i in rain_heavy_rows:
            rain_1h = 25.0          # heavy rain
        rows.append(
            f"{dt},25.0,27.0,26.0,1010,70,5.0,0.0,{rain_1h},{weather_id}"
        )
    header = "dt,temp,feels_like,dew_point,pressure,humidity,wind_speed,snow_1h,rain_1h,weather_id"
    return header + "\n" + "\n".join(rows)


# ---------------------------------------------------------------------------
# Tests: time column handling
# ---------------------------------------------------------------------------

class TestLoadFromCsv:
    def setup_method(self):
        self.preparator = DataPreparator()

    def test_dt_stays_numeric_not_parsed_as_datetime(self, tmp_path):
        """load_from_csv must NOT call parse_dates on integer 'dt' column."""
        csv_content = _make_csv_with_unix_dt(n_rows=5)
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        df = self.preparator.load_from_csv(str(csv_file), time_col='dt')

        # dt must remain numeric (int or float), not datetime
        assert pd.api.types.is_numeric_dtype(df['dt']), (
            f"Expected numeric dtype for 'dt', got {df['dt'].dtype}"
        )
        # Sanity: values should look like unix epoch seconds (~1e9)
        assert df['dt'].min() > 1_000_000_000 - 1

    def test_dt_sorted_ascending_after_load(self, tmp_path):
        """load_from_csv must return data sorted ascending by dt."""
        # Create CSV with intentionally reversed order
        base = 1_000_000_000
        rows = [f"{base - i*3600},25,27,26,1010,70,5,0,0,800" for i in range(10)]
        header = "dt,temp,feels_like,dew_point,pressure,humidity,wind_speed,snow_1h,rain_1h,weather_id"
        csv_content = header + "\n" + "\n".join(rows)

        csv_file = tmp_path / "reversed.csv"
        csv_file.write_text(csv_content)

        df = self.preparator.load_from_csv(str(csv_file), time_col='dt')

        assert df['dt'].is_monotonic_increasing, (
            "dt column must be monotonic increasing after load_from_csv"
        )

    def test_dt_monotonic_check_logged(self, tmp_path, caplog):
        """Monotonic check result should appear in logs."""
        import logging
        csv_content = _make_csv_with_unix_dt(n_rows=5)
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        with caplog.at_level(logging.INFO):
            self.preparator.load_from_csv(str(csv_file), time_col='dt')

        assert "Monotonic increasing" in caplog.text


# ---------------------------------------------------------------------------
# Tests: prepare_dataset column aliases
# ---------------------------------------------------------------------------

class TestPrepareDatasetAliases:
    def setup_method(self):
        self.preparator = DataPreparator()

    def _make_df(self, n=30):
        base = 1_000_000_000
        return pd.DataFrame({
            'dt': [base + i * 3600 for i in range(n)],
            'temp': np.random.uniform(20, 35, n),
            'feels_like': np.random.uniform(22, 40, n),
            'dew_point': np.random.uniform(15, 25, n),
            'pressure': np.random.uniform(990, 1020, n),
            'humidity': np.random.uniform(40, 90, n),
            'wind_speed': np.random.uniform(0, 10, n),
            'rain_1h': np.zeros(n),
            'weather_id': np.full(n, 800),
        })

    def test_creates_feels_like_c_alias(self):
        df = self._make_df()
        result, _ = self.preparator.prepare_dataset(df, time_col='dt')
        assert 'feels_like_c' in result.columns, (
            "prepare_dataset must create 'feels_like_c' alias when 'feels_like' present"
        )
        # Values should match
        pd.testing.assert_series_equal(
            result['feels_like_c'].reset_index(drop=True),
            result['feels_like'].reset_index(drop=True),
            check_names=False,
        )

    def test_creates_temp_c_alias(self):
        df = self._make_df()
        result, _ = self.preparator.prepare_dataset(df, time_col='dt')
        assert 'temp_c' in result.columns

    def test_creates_dew_point_c_alias(self):
        df = self._make_df()
        result, _ = self.preparator.prepare_dataset(df, time_col='dt')
        assert 'dew_point_c' in result.columns

    def test_does_not_overwrite_existing_feels_like_c(self):
        """If feels_like_c already exists, it should not be overwritten."""
        df = self._make_df()
        # Use a value within the valid range (clipping range is -50 to 70)
        df['feels_like_c'] = 45.0  # sentinel value, within valid range
        result, _ = self.preparator.prepare_dataset(df, time_col='dt')
        assert result['feels_like_c'].iloc[0] == 45.0, (
            "Existing feels_like_c should not be overwritten by the alias step"
        )


# ---------------------------------------------------------------------------
# Tests: thunderstorm label creation
# ---------------------------------------------------------------------------

class TestThunderstormLabeling:
    def setup_method(self):
        self.labeler = HazardLabeler()

    def _make_df_with_thunderstorm(self, n=48, thunderstorm_at=None):
        """
        Create synthetic hourly DataFrame.
        thunderstorm_at: list of integer row indices that should have weather_id=210.
        """
        base = 1_000_000_000
        df = pd.DataFrame({
            'dt': pd.to_datetime([base + i * 3600 for i in range(n)], unit='s'),
            'weather_id': [210 if thunderstorm_at and i in thunderstorm_at else 800
                           for i in range(n)],
        })
        return df

    def test_thunderstorm_produces_positives_when_events_present(self):
        """
        When thunderstorm events exist within the horizon, labels must be non-zero.
        Row 0 looks forward 12h (12 rows). Thunderstorm at row 5 should label row 0 = 1.
        """
        df = self._make_df_with_thunderstorm(n=48, thunderstorm_at=[5, 20, 35])
        labels = self.labeler.label_thunderstorm(df, horizon_hours=12)
        assert labels.sum() > 0, (
            "Expected at least one positive thunderstorm label when thunderstorm events "
            "are present within the horizon window"
        )

    def test_thunderstorm_all_zero_without_events(self):
        """No thunderstorm events → all labels must be 0."""
        df = self._make_df_with_thunderstorm(n=48, thunderstorm_at=None)
        labels = self.labeler.label_thunderstorm(df, horizon_hours=12)
        assert labels.sum() == 0

    def test_thunderstorm_label_is_binary_int(self):
        """Labels must only contain 0 and 1 (binary)."""
        df = self._make_df_with_thunderstorm(n=48, thunderstorm_at=[10])
        labels = self.labeler.label_thunderstorm(df, horizon_hours=12)
        unique_vals = set(labels.unique())
        assert unique_vals.issubset({0, 1}), f"Labels contain non-binary values: {unique_vals}"

    def test_create_all_labels_thunderstorm_positives(self):
        """create_all_labels must produce thunderstorm positives when events are present."""
        base = 1_000_000_000
        n = 72
        df = pd.DataFrame({
            'dt': [base + i * 3600 for i in range(n)],
            'temp': np.full(n, 25.0),
            'feels_like_c': np.full(n, 27.0),
            'pressure': np.full(n, 1010.0),
            'humidity': np.full(n, 70.0),
            'wind_speed': np.full(n, 5.0),
            'rain_1h': np.zeros(n),
            'weather_id': [210 if i % 12 == 0 else 800 for i in range(n)],
        })

        labeled = self.labeler.create_all_labels(df, horizons=[12], hazards=['thunderstorm'])

        col = 'thunderstorm_12h'
        assert col in labeled.columns, f"Expected label column '{col}' in output"
        assert labeled[col].sum() > 0, (
            f"Expected positive thunderstorm_12h labels; got all zeros. "
            f"Thunder rows in raw data: {(df['weather_id']==210).sum()}"
        )
        assert labeled[col].isna().sum() == 0, "Label column must not contain NaNs"

    def test_labels_survive_integer_dt(self):
        """
        When dt is integer (unix seconds, not datetime), the labeler must still
        produce correct labels by converting internally.
        """
        base = 1_000_000_000
        n = 48
        df = pd.DataFrame({
            'dt': [base + i * 3600 for i in range(n)],
            'weather_id': [210 if i == 6 else 800 for i in range(n)],
        })
        labels = self.labeler.label_thunderstorm(df, horizon_hours=12)
        # Row 0 looks ahead 12h → row 6 (t+6h) is in window → label should be 1
        assert labels.iloc[0] == 1, (
            "Row 0 should be labelled 1 because a thunderstorm occurs at row 6 "
            "(within the 12h horizon)"
        )