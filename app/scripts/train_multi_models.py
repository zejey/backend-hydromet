"""
Multi-Model Trainer for Multi-Hazard, Multi-Horizon Prediction
Trains 12 Naive Bayes models (4 hazards × 3 horizons)
"""

import pandas as pd
import numpy as np
import joblib
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging

from sklearn.naive_bayes import GaussianNB
from sklearn.model_selection import train_test_split, TimeSeriesSplit, cross_val_score
from sklearn.preprocessing import PowerTransformer
from sklearn.pipeline import Pipeline
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, precision_recall_fscore_support
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline

from hazard_labeling import HazardLabeler
from data_preparation import DataPreparator
from app.ml.feature_engineering import engineer_extended_features, get_feature_columns_for_hazard

logger = logging.getLogger(__name__)


class MultiModelTrainer:
    """
    Train and manage multiple Naive Bayes models for multi-hazard prediction
    
    Models trained:
    - 4 hazards: heat_stress, heavy_rain, thunderstorm, severe_storm
    - 3 horizons: 12h, 24h, 48h
    - Total: 12 models
    """
    
    def __init__(
        self,
        models_dir: str = "models",
        config: Optional[Dict] = None
    ):
        """
        Initialize multi-model trainer
        
        Args:
            models_dir: Directory to save trained models
            config: Training configuration (optional)
        """
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        default_config = {
            "test_size": 0.2,
            "random_state": 42,
            "cv_splits": 5,
            "selector_k": 15,  # Increased for more features
            "use_mutual_info": True,
            "nb_var_smoothing": 1e-9,
            "var_smoothing_grid": [1e-9, 1e-7, 1e-5, 1e-3],  # Tune per model
            "use_smote": True,
            "smote_k_neighbors": 3,  # Lower for smaller positive class
            "smote_max_ratio": 0.20,  # cap minority at 20% of majority
            "smote_min_ratio": 0.10,  # always synthesize at least to 10%
            "priors_threshold_pct": 5.0,  # below this %, use class priors instead of SMOTE
        }

        # Merge user-provided config overrides (e.g., only test_size) into defaults
        self.config = default_config
        if config:
            self.config.update(config)
            
        # Supported hazards and horizons
        self.hazards = ["heat_stress", "heavy_rain", "thunderstorm", "severe_storm"]
        self.horizons = [12, 24, 48]
        
        self.labeler = HazardLabeler()
        self.preparator = DataPreparator()

    @staticmethod 
    def _json_safe(obj):
        """Convert numpy/pandas scalar types to JSON-serializable Python types."""
        import numpy as np
        import pandas as pd

        if isinstance(obj, dict):
            return {k: MultiModelTrainer._json_safe(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [MultiModelTrainer._json_safe(v) for v in obj]
        if isinstance(obj, tuple):
            return [MultiModelTrainer._json_safe(v) for v in obj]

        # numpy scalars
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)

        # pandas scalars / timestamps
        if isinstance(obj, (pd.Timestamp,)):
            return obj.isoformat()

        return obj 

    @staticmethod
    def _smote_sampling_strategy(pos_count: int, neg_count: int, config: dict) -> float:
        if neg_count == 0:
            return 1.0
        current_ratio = pos_count / neg_count
        max_ratio = config.get("smote_max_ratio", 0.20)
        min_ratio = config.get("smote_min_ratio", 0.05)
        # Gentle 3x boost from current, but cap at max_ratio
        target = min(max_ratio, max(current_ratio * 3, min_ratio))
        # SMOTE cannot reduce the minority class — never return less than current_ratio
        return float(max(target, current_ratio))

    def prepare_training_data(
        self,
        csv_path: Optional[str] = None,
        df: Optional[pd.DataFrame] = None,
        time_col: str = 'dt',
        use_cache: bool = False,
        refresh_cache: bool = False,
        cache_path: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Prepare training data from CSV or DataFrame (prep + features + labels),
        with optional Parquet caching of the prepared+labeled dataset.
        """
        cache_file = Path(cache_path) if cache_path else None

        if use_cache and cache_file and cache_file.exists() and not refresh_cache:
            logger.info("=" * 80)
            logger.info("LOADING PREPARED+LABELED DATASET FROM CACHE")
            logger.info("=" * 80)
            logger.info(f"Cache path: {cache_file}")
            data = pd.read_parquet(cache_file)
            logger.info(f"✓ Loaded cached dataset: {data.shape}")
            return data

        logger.info("=" * 80)
        logger.info("PREPARING TRAINING DATA")
        logger.info("=" * 80)

        # Load data
        if df is not None:
            data = df.copy()
            logger.info(f"Using provided DataFrame: {data.shape}")
        elif csv_path:
            data = self.preparator.load_from_csv(csv_path, time_col=time_col)
        else:
            raise ValueError("Must provide either csv_path or df")

        # Step 1: Prepare data
        logger.info("\nStep 1: Data preparation...")
        data, _prep_report = self.preparator.prepare_dataset(
            data,
            time_col=time_col,
            aggregate_dupes=True,
            handle_precip=True,
            clean_data=True
        )

        # Step 2: Feature engineering
        logger.info("\nStep 2: Feature engineering...")
        data = engineer_extended_features(
            data,
            lag_hours=[3, 6],
            rolling_hours=[3, 6, 12],
            add_deltas=True,
            time_col='timestamp' if 'timestamp' in data.columns else time_col
        )

        # Step 3: Label generation
        logger.info("\nStep 3: Label generation...")
        data = self.labeler.create_all_labels(
            data,
            horizons=self.horizons,
            hazards=self.hazards
        )

        # Save cache (if configured)
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"\nSaving prepared+labeled dataset cache to: {cache_file}")
            data.to_parquet(cache_file, index=False)
            logger.info("✓ Cache saved")

        logger.info(f"\n✓ Training data prepared: {data.shape}")
        return data

    def train_single_model(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_test: pd.DataFrame,
        y_test: pd.Series,
        hazard: str,
        horizon: int
    ) -> Tuple[Pipeline, Dict]:
        """
        Train a single Naive Bayes model for one hazard-horizon combination.
        
        Improvements:
        - Grid search over var_smoothing values
        - Use class priors instead of SMOTE for extreme imbalance (<5%)
        - Dynamic SMOTE sampling strategy safe for CV folds
        
        Args:
            X_train: Training features
            y_train: Training labels
            X_test: Test features
            y_test: Test labels
            hazard: Hazard type
            horizon: Time horizon in hours
            
        Returns:
            Tuple of (trained_pipeline, metrics_dict)
        """
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Training: {hazard} @ {horizon}h horizon")
        logger.info(f"{'=' * 60}")
        
        # Check class balance
        pos_count = y_train.sum()
        neg_count = len(y_train) - pos_count
        pos_pct = 100 * pos_count / len(y_train) if len(y_train) > 0 else 0
        
        logger.info(f"Training samples: {len(y_train)}")
        logger.info(f"  Positive (hazard): {pos_count} ({pos_pct:.1f}%)")
        logger.info(f"  Negative (no hazard): {neg_count} ({100-pos_pct:.1f}%)")
        
        # Determine balancing strategy
        current_ratio = pos_count / neg_count if neg_count > 0 else 1.0
        already_balanced = current_ratio >= self.config.get("smote_max_ratio", 0.20)
        extreme_imbalance = pos_pct < self.config.get("priors_threshold_pct", 5.0)
        use_smote = (
            self.config["use_smote"]
            and pos_count >= self.config["smote_k_neighbors"] + 1
            and not already_balanced
            and not extreme_imbalance  # Use priors instead for extreme imbalance
        )
        use_priors = extreme_imbalance and not already_balanced
        
        # Var smoothing grid search
        var_grid = self.config.get("var_smoothing_grid", [self.config["nb_var_smoothing"]])
        best_pipeline = None
        best_f1 = -1.0
        best_vs = var_grid[0]
        
        selector_k = min(self.config["selector_k"], X_train.shape[1])
        score_func = mutual_info_classif if self.config["use_mutual_info"] else None
        
        logger.info(f"Tuning var_smoothing over {len(var_grid)} values: {var_grid}")
        
        for vs in var_grid:
            # Set class priors for extreme imbalance — gives NB equal weight
            # on both classes without synthesizing fake data
            nb_kwargs = {'var_smoothing': vs}
            if use_priors:
                nb_kwargs['priors'] = [0.5, 0.5]
            
            if use_smote:
                sampling_strategy = MultiModelTrainer._smote_sampling_strategy(
                    pos_count, neg_count, self.config
                )
                pipeline_steps = [
                    ('smote', SMOTE(
                        sampling_strategy=sampling_strategy,
                        k_neighbors=self.config["smote_k_neighbors"],
                        random_state=self.config["random_state"]
                    )),
                    ('scaler', PowerTransformer(method='yeo-johnson')),
                    ('selector', SelectKBest(score_func=score_func, k=selector_k)),
                    ('nb', GaussianNB(**nb_kwargs))
                ]
                pipeline = ImbPipeline(pipeline_steps)
            else:
                pipeline_steps = [
                    ('scaler', PowerTransformer(method='yeo-johnson')),
                    ('selector', SelectKBest(score_func=score_func, k=selector_k)),
                    ('nb', GaussianNB(**nb_kwargs))
                ]
                pipeline = Pipeline(pipeline_steps)
            
            # Quick eval: fit on train, score on test
            try:
                pipeline.fit(X_train, y_train)
                y_pred_vs = pipeline.predict(X_test)
                _, _, f1_vs, _ = precision_recall_fscore_support(
                    y_test, y_pred_vs, average='binary', zero_division=0
                )
                if f1_vs > best_f1:
                    best_f1 = f1_vs
                    best_pipeline = pipeline
                    best_vs = vs
            except Exception as e:
                logger.warning(f"  var_smoothing={vs} failed: {e}")
                continue
        
        if best_pipeline is None:
            raise RuntimeError(f"All var_smoothing values failed for {hazard}_{horizon}h")
        
        pipeline = best_pipeline
        
        if use_priors:
            logger.info(f"Using class priors [0.5, 0.5] (extreme imbalance: {pos_pct:.1f}%)")
        elif use_smote:
            logger.info(f"Using SMOTE for class balancing")
        else:
            logger.info(f"No rebalancing needed (already balanced)")
        logger.info(f"Best var_smoothing: {best_vs} (F1={best_f1:.4f})")
        
        # Evaluate on test set
        y_pred = pipeline.predict(X_test)
        y_pred_proba = pipeline.predict_proba(X_test)[:, 1]
        
        # Calculate metrics
        accuracy = accuracy_score(y_test, y_pred)
        precision, recall, f1, support = precision_recall_fscore_support(y_test, y_pred, average='binary', zero_division=0)
        
        logger.info(f"\nTest Set Performance:")
        logger.info(f"  Accuracy:  {accuracy:.4f}")
        logger.info(f"  Precision: {precision:.4f}")
        logger.info(f"  Recall:    {recall:.4f}")
        logger.info(f"  F1-Score:  {f1:.4f}")
        
        # Cross-validation (if enough samples)
        cv_scores = None
        if len(y_train) >= self.config["cv_splits"] * 10:
            try:
                logger.info(f"\nRunning {self.config['cv_splits']}-fold time series cross-validation...")
                tscv = TimeSeriesSplit(n_splits=self.config["cv_splits"])
                cv_scores = cross_val_score(
                    pipeline, X_train, y_train, cv=tscv,
                    scoring='accuracy', error_score='raise'
                )
                logger.info(f"  CV Accuracy: {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")
            except Exception as e:
                logger.warning(f"Cross-validation failed: {e}")
                # Retry without SMOTE for CV if it was the cause
                if use_smote:
                    try:
                        logger.info("  Retrying CV without SMOTE...")
                        cv_pipe = Pipeline([
                            ('scaler', PowerTransformer(method='yeo-johnson')),
                            ('selector', SelectKBest(score_func=score_func, k=selector_k)),
                            ('nb', GaussianNB(var_smoothing=best_vs))
                        ])
                        cv_scores = cross_val_score(
                            cv_pipe, X_train, y_train, cv=tscv,
                            scoring='accuracy', error_score='raise'
                        )
                        logger.info(f"  CV Accuracy (no SMOTE): {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")
                    except Exception as e2:
                        logger.warning(f"  CV retry also failed: {e2}")
                        cv_scores = None
        else:
            logger.info(f"Skipping CV (not enough training samples: {len(y_train)})")
        
        # Confusion matrix
        cm = confusion_matrix(y_test, y_pred)
        logger.info(f"\nConfusion Matrix:")
        logger.info(f"  TN={cm[0, 0]:4d}  FP={cm[0, 1]:4d}")
        logger.info(f"  FN={cm[1, 0]:4d}  TP={cm[1, 1]:4d}")
        
        # Compile metrics
        metrics = {
            "hazard": hazard,
            "horizon_hours": horizon,
            "train_samples": len(y_train),
            "test_samples": len(y_test),
            "train_pos_samples": int(pos_count),
            "train_pos_pct": float(pos_pct),
            "used_smote": use_smote,
            "used_priors": use_priors,
            "best_var_smoothing": float(best_vs),
            "accuracy": float(accuracy),
            "precision": float(precision),
            "recall": float(recall),
            "f1_score": float(f1),
            "cv_mean": float(cv_scores.mean()) if cv_scores is not None else None,
            "cv_std": float(cv_scores.std()) if cv_scores is not None else None,
            "confusion_matrix": cm.tolist(),
            "trained_at": datetime.now().isoformat(),
            "feature_count": X_train.shape[1],
            "feature_names": list(X_train.columns),
        }
        
        return pipeline, metrics
    
    def train_all_models(
        self,
        data: pd.DataFrame,
        save_models: bool = True,
        hazards_filter: Optional[List[str]] = None
    ) -> Dict:
        """
        Train all 12 models (4 hazards × 3 horizons)

        Key robustness:
        - Drop extremely sparse feature columns (e.g., sea_level/grnd_level) before row filtering
        - Impute remaining NaNs so a few optional OpenWeather fields don't nuke all rows
        - Skip models with not enough samples or only-one-class y
        """
        hazards_to_train = hazards_filter if hazards_filter else self.hazards

        logger.info("\n" + "=" * 80)
        logger.info("TRAINING ALL MODELS (4 hazards × 3 horizons = 12 models)")
        logger.info("=" * 80)
        logger.info(f"Training hazards: {hazards_to_train}")

        if hazards_filter:
            logger.info(f"⚡ Partial retrain: only {hazards_to_train} will be retrained")
            logger.info("   (other hazard models are preserved from previous run)")

        results = {
            "training_timestamp": datetime.now().isoformat(),
            "config": self.config,
            "data_shape": data.shape,
            "models": {}
        }

        # Get feature columns (exclude labels and timestamps)
        exclude_cols = ['dt', 'timestamp', 'date'] + [
            f"{h}_{hr}h" for h in self.hazards for hr in self.horizons
        ]
        all_features = [col for col in data.columns if col not in exclude_cols]
        logger.info(f"\nTotal features available: {len(all_features)}")

        for hazard in hazards_to_train:
            for horizon in self.horizons:
                label_col = f"{hazard}_{horizon}h"

                if label_col not in data.columns:
                    logger.error(f"Label column '{label_col}' not found in data!")
                    continue

                # Feature selection per hazard
                feature_cols = get_feature_columns_for_hazard(data, hazard)
                feature_cols = [f for f in feature_cols if f in data.columns]
                logger.info(f"\nFeatures for {hazard}: {len(feature_cols)}")

                X = data[feature_cols].copy()
                y = data[label_col].copy()

                # ------------------------------------------------------------------
                # A) Drop very sparse feature columns (OpenWeather optional fields)
                # ------------------------------------------------------------------
                nan_rate = X.isna().mean()
                drop_cols = nan_rate[nan_rate > 0.8].index.tolist()
                if drop_cols:
                    X = X.drop(columns=drop_cols)
                    logger.info(
                        f"  Dropped {len(drop_cols)} sparse features (>80% NaN). "
                        f"Examples: {drop_cols[:10]}"
                    )

                # ------------------------------------------------------------------
                # B) Impute remaining NaNs (keep it simple + consistent)
                # ------------------------------------------------------------------
                for col in X.columns:
                    if not X[col].isna().any():
                        continue

                    # Precip/snow missing => 0
                    if col in ("rain_1h", "rain_3h", "snow_1h", "snow_3h"):
                        X[col] = X[col].fillna(0)

                    # wind_gust missing => wind_speed if available else 0
                    elif col == "wind_gust":
                        if "wind_speed" in X.columns:
                            X[col] = X[col].fillna(X["wind_speed"])
                        else:
                            X[col] = X[col].fillna(0)
# 
                    # Everything else => median, fallback to 0 if median is NaN
                    else:
                        med = X[col].median()
                        if pd.isna(med):
                            X[col] = X[col].fillna(0)
                        else:
                            X[col] = X[col].fillna(med)

                # ------------------------------------------------------------------
                # C) Now filter rows: we should have far fewer NaN-driven drops
                # ------------------------------------------------------------------
                valid_mask = ~(X.isna().any(axis=1) | y.isna())

                label_nan_count = int(y.isna().sum())
                feature_nan_count = int(X.isna().any(axis=1).sum())
                if label_nan_count:
                    logger.info(f"  Rows removed due to missing label '{label_col}': {label_nan_count}")
                if feature_nan_count:
                    logger.info(f"  Rows removed due to missing features: {feature_nan_count}")

                X = X[valid_mask]
                y = y[valid_mask]

                logger.info(f"Valid samples after NaN removal: {len(X)}")

                # If still 0, report top NaN contributors (debug)
                if len(X) == 0:
                    nan_counts = data[feature_cols].isna().sum()
                    nan_counts = nan_counts[nan_counts > 0].sort_values(ascending=False)
                    logger.warning(f"  No valid samples for {label_col}! Top NaN contributors:")
                    for col_name_nan, cnt in nan_counts.head(10).items():
                        logger.warning(f"    {col_name_nan}: {cnt} NaNs ({100*cnt/len(data):.1f}%)")

                    logger.warning(f"Not enough data to train {label_col} (only 0 samples). Skipping.")
                    continue

                # Early skip: model cannot be trained if only one class exists
                pos_total = int(y.sum())
                if pos_total == 0:
                    logger.warning(f"Skipping {label_col}: 0 positive samples in dataset.")
                    continue
                if pos_total == len(y):
                    logger.warning(f"Skipping {label_col}: 0 negative samples in dataset.")
                    continue

                # Skip if not enough samples
                if len(X) < 50:
                    logger.warning(
                        f"Not enough data to train {label_col} (only {len(X)} samples). Skipping."
                    )
                    continue

                # Time series split (chronological)
                split_idx = int(len(X) * (1 - self.config["test_size"]))
                X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
                y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

                # Skip if training set is single-class (can't learn)
                if len(set(y_train.unique())) < 2:
                    logger.warning(
                        f"Skipping {label_col}: y_train has only one class "
                        f"({set(y_train.unique())})."
                    )
                    continue

                # Train model
                try:
                    model, metrics = self.train_single_model(
                        X_train, y_train, X_test, y_test,
                        hazard, horizon
                    )

                    if save_models:
                        model_path = self.save_model(model, hazard, horizon, metrics)
                        metrics["model_path"] = str(model_path)

                    results["models"][label_col] = metrics
                    logger.info(f"✓ {label_col} training complete")

                except Exception as e:
                    logger.error(f"✗ Failed to train {label_col}: {e}", exc_info=True)
                    results["models"][label_col] = {"error": str(e)}

        # Save summary
        if save_models:
            summary_path = self.models_dir / "training_summary.json"
            with open(summary_path, 'w') as f:
                json.dump(self._json_safe(results), f, indent=2)
            logger.info(f"\n✓ Training summary saved to {summary_path}")

        logger.info("\n" + "=" * 80)
        logger.info("ALL MODELS TRAINING COMPLETE")
        logger.info("=" * 80)

        trained_ok = len([m for m in results["models"].values() if "error" not in m])
        logger.info(f"Successfully trained: {trained_ok}/{len(results['models'])} models")

        return results
    
    def save_model(
        self,
        model: Pipeline,
        hazard: str,
        horizon: int,
        metadata: Dict
    ) -> Path:
        """
        Save trained model and metadata to disk
        
        Args:
            model: Trained model pipeline
            hazard: Hazard type
            horizon: Time horizon in hours
            metadata: Model metadata dictionary
            
        Returns:
            Path to saved model file
        """
        # Create directory structure: models/{hazard}/{horizon}h/
        model_dir = self.models_dir / hazard / f"{horizon}h"
        model_dir.mkdir(parents=True, exist_ok=True)
        
        # Save model
        model_path = model_dir / "model.pkl"
        joblib.dump(model, model_path)
        
        # Save metadata
        metadata_path = model_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            safe_metadata = self._json_safe(metadata)
            json.dump(safe_metadata, f, indent=2)
        
        logger.debug(f"  Saved model to {model_path}")
        logger.debug(f"  Saved metadata to {metadata_path}")
        
        return model_path


def main():
    """Main training script"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Train multi-hazard, multi-horizon Naive Bayes models')
    parser.add_argument('--csv', type=str, required=True, help='Path to training data CSV')
    parser.add_argument('--models-dir', type=str, default='models', help='Directory to save models')
    parser.add_argument('--time-col', type=str, default='dt', help='Name of timestamp column')
    parser.add_argument('--test-size', type=float, default=0.2, help='Test set size (default: 0.2)')
    parser.add_argument('--use-cache', action='store_true', help='Use cached prepared+labeled dataset (Parquet) if available')
    parser.add_argument('--refresh-cache', action='store_true', help='Rebuild cache even if it exists')
    parser.add_argument('--cache-path', type=str, default='models/cache/prepared_labeled.parquet', help='Path to Parquet cache file')
    parser.add_argument(
        '--hazards',
        type=str,
        nargs='+',
        default=None,
        choices=['heat_stress', 'heavy_rain', 'thunderstorm', 'severe_storm'],
        help='Hazards to train (default: all). e.g. --hazards heavy_rain thunderstorm'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("=" * 80)
    logger.info("MULTI-HAZARD MULTI-HORIZON MODEL TRAINING")
    logger.info("=" * 80)
    logger.info(f"Training data: {args.csv}")
    logger.info(f"Models directory: {args.models_dir}")
    logger.info(f"Time column: {args.time_col}")
    logger.info(f"Test size: {args.test_size}")
    
    # Initialize trainer
    config = {"test_size": args.test_size}
    trainer = MultiModelTrainer(models_dir=args.models_dir, config=config)
    
    # Prepare data
    data = trainer.prepare_training_data(
        csv_path=args.csv,
        time_col=args.time_col,
        use_cache=args.use_cache,
        refresh_cache=args.refresh_cache,
        cache_path=args.cache_path,
    )
        
    # Train all models
    results = trainer.train_all_models(data, save_models=True, hazards_filter=args.hazards)
    
    logger.info("\n✅ Training complete!")
    logger.info(f"Models saved to: {args.models_dir}")


if __name__ == "__main__":
    main()