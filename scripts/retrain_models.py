"""
Retraining Script for Multi-Hazard Models
Retrains all 12 models with updated weather observations
"""

import argparse
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from train_multi_models import MultiModelTrainer

logger = logging.getLogger(__name__)


def compare_metrics(old_metadata_path: Path, new_results: dict) -> dict:
    """
    Compare old and new model metrics
    
    Args:
        old_metadata_path: Path to old training_summary.json
        new_results: New training results
        
    Returns:
        Comparison dictionary
    """
    comparison = {
        "timestamp": datetime.now().isoformat(),
        "models": {}
    }
    
    # Load old metrics if available
    old_results = {}
    if old_metadata_path.exists():
        try:
            with open(old_metadata_path, 'r') as f:
                old_results = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load old metrics: {e}")
    
    # Compare each model
    for model_key in new_results.get("models", {}):
        new_metrics = new_results["models"][model_key]
        old_metrics = old_results.get("models", {}).get(model_key, {})
        
        comparison["models"][model_key] = {
            "old_accuracy": old_metrics.get("accuracy"),
            "new_accuracy": new_metrics.get("accuracy"),
            "old_f1": old_metrics.get("f1_score"),
            "new_f1": new_metrics.get("f1_score"),
            "improvement": None
        }
        
        # Calculate improvement
        if old_metrics.get("accuracy") and new_metrics.get("accuracy"):
            old_acc = old_metrics["accuracy"]
            new_acc = new_metrics["accuracy"]
            improvement = ((new_acc - old_acc) / old_acc) * 100
            comparison["models"][model_key]["improvement"] = improvement
    
    return comparison


def retrain_models(
    csv_path: str,
    models_dir: str = "models",
    backup_old: bool = True,
    time_col: str = "dt"
) -> dict:
    """
    Retrain all multi-hazard models
    
    Args:
        csv_path: Path to training data CSV
        models_dir: Directory to save models
        backup_old: Whether to backup old models
        time_col: Name of timestamp column
        
    Returns:
        Retraining results dictionary
    """
    logger.info("=" * 80)
    logger.info("MULTI-HAZARD MODEL RETRAINING")
    logger.info("=" * 80)
    logger.info(f"Training data: {csv_path}")
    logger.info(f"Models directory: {models_dir}")
    logger.info(f"Backup old models: {backup_old}")
    
    models_path = Path(models_dir)
    
    # Backup old models if requested
    if backup_old and models_path.exists():
        backup_dir = models_path.parent / f"models_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Backing up old models to: {backup_dir}")
        
        try:
            import shutil
            shutil.copytree(models_path, backup_dir)
            logger.info("✓ Backup complete")
        except Exception as e:
            logger.error(f"✗ Backup failed: {e}")
            logger.info("Continuing with retraining...")
    
    # Initialize trainer
    trainer = MultiModelTrainer(models_dir=models_dir)
    
    # Prepare data
    logger.info("\nPreparing training data...")
    data = trainer.prepare_training_data(csv_path=csv_path, time_col=time_col)
    
    logger.info(f"✓ Training data ready: {data.shape}")
    logger.info(f"  Records: {len(data)}")
    logger.info(f"  Date range: {data['timestamp'].min()} to {data['timestamp'].max()}")
    
    # Train all models
    logger.info("\nTraining all models...")
    results = trainer.train_all_models(data, save_models=True)
    
    # Compare with old metrics
    old_summary_path = models_path / "training_summary.json"
    if old_summary_path.exists():
        logger.info("\nComparing with previous model performance...")
        comparison = compare_metrics(old_summary_path, results)
        
        # Log improvements
        improved = 0
        degraded = 0
        
        for model_key, metrics in comparison["models"].items():
            improvement = metrics.get("improvement")
            
            if improvement is not None:
                if improvement > 0:
                    improved += 1
                    logger.info(f"  ✓ {model_key}: +{improvement:.2f}% accuracy")
                elif improvement < -1:  # Only flag significant degradation
                    degraded += 1
                    logger.warning(f"  ⚠ {model_key}: {improvement:.2f}% accuracy")
        
        logger.info(f"\nSummary: {improved} improved, {degraded} degraded")
        
        # Save comparison
        comparison_path = models_path / f"retraining_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(comparison_path, 'w') as f:
            json.dump(comparison, f, indent=2)
        logger.info(f"Comparison saved to: {comparison_path}")
    
    logger.info("\n" + "=" * 80)
    logger.info("RETRAINING COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Models saved to: {models_path}")
    
    return results


def main():
    """Main retraining script"""
    parser = argparse.ArgumentParser(
        description='Retrain multi-hazard, multi-horizon models'
    )
    parser.add_argument(
        '--csv',
        type=str,
        required=True,
        help='Path to training data CSV (updated with new observations)'
    )
    parser.add_argument(
        '--models-dir',
        type=str,
        default='models',
        help='Directory to save models (default: models)'
    )
    parser.add_argument(
        '--time-col',
        type=str,
        default='dt',
        help='Name of timestamp column (default: dt)'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Do not backup old models'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run retraining
    try:
        results = retrain_models(
            csv_path=args.csv,
            models_dir=args.models_dir,
            backup_old=not args.no_backup,
            time_col=args.time_col
        )
        
        logger.info("\n✅ Retraining successful!")
        
    except Exception as e:
        logger.error(f"\n❌ Retraining failed: {e}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    main()