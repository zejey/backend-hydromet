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
from feature_engineering import engineer_extended_features, get_feature_columns_for_hazard

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
        
        # Default training configuration
        self.config = config or {
            "test_size": 0.2,
            "random_state": 42,
            "cv_splits": 5,
            "selector_k": 15,  # Increased for more features
            "use_mutual_info": True,
            "nb_var_smoothing": 1e-9,
            "use_smote": True,
            "smote_k_neighbors": 3,  # Lower for smaller positive class
        }
        
        # Supported hazards and horizons
        self.hazards = ["heat_stress", "heavy_rain", "thunderstorm", "severe_storm"]
        self.horizons = [12, 24, 48]
        
        self.labeler = HazardLabeler()
        self.preparator = DataPreparator()
    
    def prepare_training_data(
        self,
        csv_path: Optional[str] = None,
        df: Optional[pd.DataFrame] = None,
        time_col: str = 'dt'
    ) -> pd.DataFrame:
        """
        Prepare training data from CSV or DataFrame
        
        Args:
            csv_path: Path to CSV file with weather observations
            df: DataFrame with weather observations (alternative to CSV)
            time_col: Name of timestamp column
            
        Returns:
            Prepared DataFrame with features and labels
        """
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
        
        # Prepare data (handle duplicates, missing values, etc.)
        logger.info("\nStep 1: Data preparation...")
        data, prep_report = self.preparator.prepare_dataset(
            data,
            time_col=time_col,
            aggregate_dupes=True,
            handle_precip=True,
            clean_data=True
        )
        
        # Add extended features
        logger.info("\nStep 2: Feature engineering...")
        data = engineer_extended_features(
            data,
            lag_hours=[3, 6],
            rolling_hours=[3, 6, 12],
            add_deltas=True,
            time_col='timestamp' if 'timestamp' in data.columns else time_col
        )
        
        # Create labels for all hazards and horizons
        logger.info("\nStep 3: Label generation...")
        data = self.labeler.create_all_labels(
            data,
            horizons=self.horizons,
            hazards=self.hazards
        )
        
        logger.info(f"\n✓ Training data prepared: {data.shape}")
        logger.info(f"  Records: {len(data)}")
        logger.info(f"  Features: {len([c for c in data.columns if not c.endswith('h') and c not in ['dt', 'timestamp']])}")
        logger.info(f"  Labels: {len([c for c in data.columns if c.endswith('h')])}")
        
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
        Train a single Naive Bayes model for one hazard-horizon combination
        
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
        
        # Build pipeline
        use_smote = self.config["use_smote"] and pos_count >= self.config["smote_k_neighbors"] + 1
        
        if use_smote:
            logger.info("Using SMOTE for class balancing...")
            pipeline_steps = [
                ('smote', SMOTE(k_neighbors=self.config["smote_k_neighbors"], random_state=self.config["random_state"])),
                ('scaler', PowerTransformer(method='yeo-johnson')),
                ('selector', SelectKBest(
                    score_func=mutual_info_classif if self.config["use_mutual_info"] else None,
                    k=min(self.config["selector_k"], X_train.shape[1])
                )),
                ('nb', GaussianNB(var_smoothing=self.config["nb_var_smoothing"]))
            ]
            pipeline = ImbPipeline(pipeline_steps)
        else:
            logger.info("SMOTE disabled (not enough positive samples). Using standard pipeline...")
            pipeline_steps = [
                ('scaler', PowerTransformer(method='yeo-johnson')),
                ('selector', SelectKBest(
                    score_func=mutual_info_classif if self.config["use_mutual_info"] else None,
                    k=min(self.config["selector_k"], X_train.shape[1])
                )),
                ('nb', GaussianNB(var_smoothing=self.config["nb_var_smoothing"]))
            ]
            pipeline = Pipeline(pipeline_steps)
        
        # Train model
        logger.info("Training model...")
        pipeline.fit(X_train, y_train)
        
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
        if len(y_train) >= self.config["cv_splits"] * 10:  # Need enough data for CV
            try:
                logger.info(f"\nRunning {self.config['cv_splits']}-fold time series cross-validation...")
                tscv = TimeSeriesSplit(n_splits=self.config["cv_splits"])
                cv_scores = cross_val_score(pipeline, X_train, y_train, cv=tscv, scoring='accuracy')
                logger.info(f"  CV Accuracy: {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")
            except Exception as e:
                logger.warning(f"Cross-validation failed: {e}")
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
        save_models: bool = True
    ) -> Dict:
        """
        Train all 12 models (4 hazards × 3 horizons)
        
        Args:
            data: Prepared DataFrame with features and labels
            save_models: Whether to save trained models to disk
            
        Returns:
            Dictionary with training results for all models
        """
        logger.info("\n" + "=" * 80)
        logger.info("TRAINING ALL MODELS (4 hazards × 3 horizons = 12 models)")
        logger.info("=" * 80)
        
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
        
        # Train each model
        for hazard in self.hazards:
            for horizon in self.horizons:
                label_col = f"{hazard}_{horizon}h"
                
                if label_col not in data.columns:
                    logger.error(f"Label column '{label_col}' not found in data!")
                    continue
                
                # Get features and labels
                feature_cols = get_feature_columns_for_hazard(data, hazard)
                
                # Filter to only features that exist
                feature_cols = [f for f in feature_cols if f in data.columns]
                
                logger.info(f"\nFeatures for {hazard}: {len(feature_cols)}")
                
                X = data[feature_cols].copy()
                y = data[label_col].copy()
                
                # Drop rows with NaN in features or labels
                valid_mask = ~(X.isna().any(axis=1) | y.isna())
                X = X[valid_mask]
                y = y[valid_mask]
                
                logger.info(f"Valid samples after NaN removal: {len(X)}")
                
                # Skip if not enough data
                if len(X) < 50:
                    logger.warning(f"Not enough data to train {label_col} (only {len(X)} samples). Skipping.")
                    continue
                
                # Time series split (chronological)
                split_idx = int(len(X) * (1 - self.config["test_size"]))
                X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
                y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
                
                # Train model
                try:
                    model, metrics = self.train_single_model(
                        X_train, y_train, X_test, y_test,
                        hazard, horizon
                    )
                    
                    # Save model
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
                json.dump(results, f, indent=2)
            logger.info(f"\n✓ Training summary saved to {summary_path}")
        
        logger.info("\n" + "=" * 80)
        logger.info("ALL MODELS TRAINING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Successfully trained: {len([m for m in results['models'].values() if 'error' not in m])}/{len(results['models'])} models")
        
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
            json.dump(metadata, f, indent=2)
        
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
    data = trainer.prepare_training_data(csv_path=args.csv, time_col=args.time_col)
    
    # Train all models
    results = trainer.train_all_models(data, save_models=True)
    
    logger.info("\n✅ Training complete!")
    logger.info(f"Models saved to: {args.models_dir}")


if __name__ == "__main__":
    main()
