"""
Data Preparation Module
Handles duplicate timestamps, missing data, and dataset preparation for multi-hazard training
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DataPreparator:
    """
    Prepare weather data for multi-hazard, multi-horizon modeling
    
    Handles:
    - Duplicate timestamp aggregation
    - Missing precipitation handling
    - Feature missingness indicators
    - Data cleaning and validation
    """
    
    def __init__(self):
        """Initialize data preparator"""
        pass
    
    def aggregate_duplicates(
        self,
        df: pd.DataFrame,
        time_col: str = 'dt',
        strategy: Optional[Dict[str, str]] = None
    ) -> pd.DataFrame:
        """
        Aggregate duplicate timestamps using sensible strategies
        
        Strategies:
        - Numeric features (temp, pressure, humidity): mean
        - Critical features (rain_1h, snow_1h, wind_speed): max
        - Categorical (weather_id): most severe (minimum value for OpenWeather)
        
        Args:
            df: DataFrame with potential duplicate timestamps
            time_col: Name of timestamp column
            strategy: Optional custom aggregation strategy per column
                     Format: {column_name: 'mean'|'max'|'min'|'first'|'last'}
        
        Returns:
            DataFrame with aggregated records (unique timestamps)
        """
        # Check for duplicates
        if not df[time_col].duplicated().any():
            logger.info(f"No duplicate timestamps found in column '{time_col}'")
            return df
        
        dup_count = df[time_col].duplicated().sum()
        logger.info(f"Found {dup_count} duplicate timestamps. Aggregating...")
        
        # Default aggregation strategy
        default_strategy = {
            # Numeric averages
            'temp': 'mean',
            'temperature': 'mean',
            'feels_like': 'mean',
            'feels_like_c': 'mean',
            'temp_min': 'mean',
            'temp_max': 'mean',
            'dew_point': 'mean',
            'humidity': 'mean',
            'pressure': 'mean',
            'visibility': 'mean',
            'clouds_all': 'mean',
            'wind_deg': 'mean',
            
            # Critical maximums (for safety)
            'rain_1h': 'max',
            'rain_3h': 'max',
            'rain': 'max',
            'snow_1h': 'max',
            'snow_3h': 'max',
            'snow': 'max',
            'wind_speed': 'max',
            'wind_gust': 'max',
            
            # Weather condition (minimum = most severe in OpenWeather)
            'weather_id': 'min',
        }
        
        # Override with custom strategy if provided
        if strategy:
            default_strategy.update(strategy)
        
        # Separate time column for grouping
        df_copy = df.copy()
        
        # Build aggregation dict for available columns
        agg_dict = {}
        for col in df_copy.columns:
            if col == time_col:
                continue  # Skip time column
            
            if col in default_strategy:
                agg_dict[col] = default_strategy[col]
            else:
                # Default: first value for unmapped columns
                agg_dict[col] = 'first'
        
        # Group by timestamp and aggregate
        aggregated = df_copy.groupby(time_col, as_index=False).agg(agg_dict)
        
        logger.info(f"✓ Aggregated to {len(aggregated)} unique timestamps (from {len(df)})")
        
        return aggregated
    
    def handle_missing_precipitation(
        self,
        df: pd.DataFrame,
        precip_cols: Optional[List[str]] = None,
        add_indicators: bool = True
    ) -> pd.DataFrame:
        """
        Handle missing precipitation data
        
        Strategy:
        - Treat missing rain_1h / snow_1h as 0 (assumption: no precipitation)
        - Add missingness indicator features (rain_1h_missing, snow_1h_missing)
        
        Args:
            df: DataFrame with weather data
            precip_cols: List of precipitation columns to handle
                        Default: ['rain_1h', 'snow_1h', 'rain_3h', 'snow_3h']
            add_indicators: Whether to add missingness indicator columns
        
        Returns:
            DataFrame with handled precipitation missing values
        """
        if precip_cols is None:
            precip_cols = ['rain_1h', 'snow_1h', 'rain_3h', 'snow_3h']
        
        df_copy = df.copy()
        
        for col in precip_cols:
            if col not in df_copy.columns:
                continue
            
            # Count missing values
            missing_count = df_copy[col].isna().sum()
            
            if missing_count > 0:
                logger.info(f"Handling {missing_count} missing values in '{col}'")
                
                # Add missingness indicator if requested
                if add_indicators:
                    indicator_col = f"{col}_missing"
                    df_copy[indicator_col] = df_copy[col].isna().astype(int)
                    logger.info(f"  ✓ Added missingness indicator: {indicator_col}")
                
                # Fill missing with 0
                df_copy[col] = df_copy[col].fillna(0)
                logger.info(f"  ✓ Filled missing values with 0")
        
        return df_copy
    
    def clean_weather_data(
        self,
        df: pd.DataFrame,
        required_cols: Optional[List[str]] = None
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        Clean and validate weather data
        
        - Remove rows with missing critical features
        - Clip outliers to reasonable ranges
        - Log data quality issues
        
        Args:
            df: DataFrame with weather data
            required_cols: List of required columns (rows with missing will be dropped)
        
        Returns:
            Tuple of (cleaned_df, quality_report)
        """
        if required_cols is None:
            required_cols = ['dt', 'temp', 'pressure', 'humidity']
        
        df_copy = df.copy()
        initial_rows = len(df_copy)
        
        quality_report = {
            'initial_rows': initial_rows,
            'removed_rows': 0,
            'outliers_clipped': {},
            'warnings': []
        }
        
        # Check for required columns
        missing_cols = [col for col in required_cols if col not in df_copy.columns]
        if missing_cols:
            quality_report['warnings'].append(f"Missing required columns: {missing_cols}")
            logger.warning(f"Missing required columns: {missing_cols}")
        
        # Drop rows with missing required features
        available_required = [col for col in required_cols if col in df_copy.columns]
        if available_required:
            df_copy = df_copy.dropna(subset=available_required)
            removed = initial_rows - len(df_copy)
            if removed > 0:
                quality_report['removed_rows'] = removed
                logger.info(f"Removed {removed} rows with missing required features")
        
        # Clip outliers to reasonable ranges (metric units)
        outlier_ranges = {
            'temp': (-50, 60),           # Celsius
            'temperature': (-50, 60),
            'feels_like_c': (-50, 70),
            'temp_min': (-50, 60),
            'temp_max': (-50, 60),
            'humidity': (0, 100),        # Percentage
            'pressure': (850, 1100),     # hPa
            'wind_speed': (0, 100),      # m/s
            'rain_1h': (0, 500),         # mm
            'snow_1h': (0, 500),         # mm
            'visibility': (0, 50000),    # meters
            'clouds_all': (0, 100),      # Percentage
        }
        
        for col, (min_val, max_val) in outlier_ranges.items():
            if col in df_copy.columns:
                clipped_low = (df_copy[col] < min_val).sum()
                clipped_high = (df_copy[col] > max_val).sum()
                
                if clipped_low + clipped_high > 0:
                    df_copy[col] = df_copy[col].clip(lower=min_val, upper=max_val)
                    quality_report['outliers_clipped'][col] = {
                        'low': clipped_low,
                        'high': clipped_high
                    }
                    logger.info(f"Clipped {clipped_low + clipped_high} outliers in '{col}' to [{min_val}, {max_val}]")
        
        quality_report['final_rows'] = len(df_copy)
        
        return df_copy, quality_report
    
    def prepare_dataset(
        self,
        df: pd.DataFrame,
        time_col: str = 'dt',
        aggregate_dupes: bool = True,
        handle_precip: bool = True,
        clean_data: bool = True
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        Full dataset preparation pipeline
        
        Args:
            df: Raw weather DataFrame
            time_col: Name of timestamp column
            aggregate_dupes: Whether to aggregate duplicate timestamps
            handle_precip: Whether to handle missing precipitation
            clean_data: Whether to clean and validate data
        
        Returns:
            Tuple of (prepared_df, preparation_report)
        """
        logger.info("=" * 60)
        logger.info("Starting dataset preparation")
        logger.info("=" * 60)
        logger.info(f"Input shape: {df.shape}")
        
        report = {
            'input_shape': df.shape,
            'steps': []
        }
        
        result_df = df.copy()
        
        # Step 1: Aggregate duplicates
        if aggregate_dupes:
            logger.info("\n[1/3] Aggregating duplicate timestamps...")
            result_df = self.aggregate_duplicates(result_df, time_col=time_col)
            report['steps'].append({
                'step': 'aggregate_duplicates',
                'shape': result_df.shape
            })
        
        # Step 2: Handle missing precipitation
        if handle_precip:
            logger.info("\n[2/3] Handling missing precipitation...")
            result_df = self.handle_missing_precipitation(result_df, add_indicators=True)
            report['steps'].append({
                'step': 'handle_precipitation',
                'shape': result_df.shape
            })
        
        # Step 3: Clean data
        if clean_data:
            logger.info("\n[3/3] Cleaning and validating data...")
            result_df, quality_report = self.clean_weather_data(result_df)
            report['steps'].append({
                'step': 'clean_data',
                'shape': result_df.shape,
                'quality_report': quality_report
            })
        
        # Step 4: Ensure sorted by time column
        if time_col in result_df.columns:
            result_df = result_df.sort_values(time_col, ascending=True).reset_index(drop=True)
            logger.info(f"\n[4/4] Ensured ascending sort by '{time_col}'.")
        
        # Step 5: Create Celsius column aliases for compatibility.
        # OpenWeather CSV exports may use bare names ('temp', 'feels_like', 'dew_point')
        # while labelers/features expect '_c' suffixed names.
        celsius_aliases = [
            ('temp', 'temp_c'),
            ('feels_like', 'feels_like_c'),
            ('dew_point', 'dew_point_c'),
        ]
        for src_col, alias_col in celsius_aliases:
            if src_col in result_df.columns and alias_col not in result_df.columns:
                result_df[alias_col] = result_df[src_col]
                logger.info(f"  Created column alias: '{alias_col}' → '{src_col}'")
        
        report['output_shape'] = result_df.shape
        
        logger.info("\n" + "=" * 60)
        logger.info("Dataset preparation complete")
        logger.info("=" * 60)
        logger.info(f"Output shape: {result_df.shape}")
        logger.info(f"Rows processed: {df.shape[0]} → {result_df.shape[0]}")
        
        return result_df, report
    
    def load_from_csv(
        self,
        csv_path: str,
        time_col: str = 'dt',
        parse_dates: bool = True
    ) -> pd.DataFrame:
        csv_file = Path(csv_path)

        if not csv_file.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        logger.info(f"Loading weather data from {csv_path}...")

        # dt is unix seconds → never parse_dates on it
        if time_col == 'dt' or not parse_dates:
            df = pd.read_csv(csv_path)
        else:
            df = pd.read_csv(csv_path, parse_dates=[time_col])

        logger.info(f"✓ Loaded {len(df)} records from CSV")
        logger.info(f"  Columns: {list(df.columns)}")

        if time_col not in df.columns:
            logger.warning(f"Time column '{time_col}' not found in CSV columns!")
            return df

        # Coerce dt to numeric int64
        if time_col == 'dt':
            df[time_col] = pd.to_numeric(df[time_col], errors='coerce')
            before = len(df)
            df = df.dropna(subset=[time_col]).copy()
            dropped = before - len(df)
            if dropped:
                logger.warning(f"Dropped {dropped} rows with non-numeric '{time_col}'")
            df[time_col] = df[time_col].astype("int64")

        logger.info(f"  Time column '{time_col}' dtype: {df[time_col].dtype}")
        logger.info(f"  Time range: {df[time_col].min()} to {df[time_col].max()}")

        # Always sort by time_col for downstream horizon logic
        df = df.sort_values(time_col, ascending=True).reset_index(drop=True)
        logger.info(
            f"  Sorted ascending by '{time_col}'. Monotonic increasing: {df[time_col].is_monotonic_increasing}"
        )

        return df
    
    def save_to_csv(
        self,
        df: pd.DataFrame,
        output_path: str,
        index: bool = False
    ) -> None:
        """
        Save prepared data to CSV file
        
        Args:
            df: DataFrame to save
            output_path: Output CSV file path
            index: Whether to write DataFrame index
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Saving prepared data to {output_path}...")
        df.to_csv(output_path, index=index)
        logger.info(f"✓ Saved {len(df)} records to CSV")


def get_preparator() -> DataPreparator:
    """
    Factory function to create a DataPreparator instance
    
    Returns:
        Configured DataPreparator instance
    """
    return DataPreparator()


if __name__ == "__main__":
    # Example usage and testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("\n" + "="*60)
    print("DATA PREPARATION MODULE - TESTING")
    print("="*60)
    
    # Create sample data with duplicates and missing values
    print("\nCreating sample data with issues...")
    dates = pd.date_range(start='2024-01-01', periods=50, freq='1h')
    
    # Add some duplicate timestamps
    dates = list(dates) + [dates[10], dates[20], dates[30]]
    
    sample_data = pd.DataFrame({
        'dt': dates,
        'temp': np.random.uniform(20, 35, len(dates)),
        'feels_like_c': np.random.uniform(22, 40, len(dates)),
        'humidity': np.random.uniform(40, 90, len(dates)),
        'pressure': np.random.uniform(990, 1020, len(dates)),
        'wind_speed': np.random.uniform(0, 25, len(dates)),
        'rain_1h': [np.nan if i % 5 == 0 else np.random.uniform(0, 30, 1)[0] for i in range(len(dates))],
        'snow_1h': [np.nan if i % 7 == 0 else 0 for i in range(len(dates))],
        'weather_id': np.random.choice([800, 801, 200, 500], len(dates)),
    })
    
    print(f"\nSample data shape: {sample_data.shape}")
    print(f"Duplicate timestamps: {sample_data['dt'].duplicated().sum()}")
    print(f"Missing rain_1h: {sample_data['rain_1h'].isna().sum()}")
    print(f"Missing snow_1h: {sample_data['snow_1h'].isna().sum()}")
    
    # Create preparator and prepare data
    preparator = get_preparator()
    
    prepared_data, report = preparator.prepare_dataset(
        sample_data,
        time_col='dt',
        aggregate_dupes=True,
        handle_precip=True,
        clean_data=True
    )
    
    print("\n" + "="*60)
    print("PREPARATION REPORT")
    print("="*60)
    print(f"Input shape:  {report['input_shape']}")
    print(f"Output shape: {report['output_shape']}")
    print(f"\nProcessing steps:")
    for step_info in report['steps']:
        print(f"  - {step_info['step']}: {step_info['shape']}")
    
    print("\n" + "="*60)
    print("PREPARED DATA SAMPLE")
    print("="*60)
    print(prepared_data.head(10))
    
    print("\n" + "="*60)
    print("MISSING VALUES CHECK")
    print("="*60)
    missing_summary = prepared_data.isna().sum()
    print(missing_summary[missing_summary > 0] if (missing_summary > 0).any() else "No missing values!")
    
    print("\n" + "="*60)
    print("MISSINGNESS INDICATORS")
    print("="*60)
    indicator_cols = [col for col in prepared_data.columns if col.endswith('_missing')]
    if indicator_cols:
        for col in indicator_cols:
            count = prepared_data[col].sum()
            print(f"  {col}: {count} records flagged")
    else:
        print("  No indicator columns found")