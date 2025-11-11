"""
Model training script.
Loads exported CSV data from database and trains the ML model.

Usage:
    python train_model.py --csv training_data.csv
    python train_model.py --csv training_data.csv --eval
"""
import os
import sys
import argparse
from datetime import datetime
from dotenv import load_dotenv

from model import train_from_csv
from logger_util import get_logger

load_dotenv()
logger = get_logger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Train weather hazard model from CSV")
    parser.add_argument("--csv", type=str, required=True, help="Path to training CSV file")
    parser.add_argument("--eval", action="store_true", help="Print evaluation metrics after training")
    
    args = parser.parse_args()
    csv_path = args.csv
    
    # Validate CSV file exists
    if not os.path.exists(csv_path):
        logger.error(f"❌ CSV file not found: {csv_path}")
        sys.exit(1)
    
    logger.info("=" * 70)
    logger.info(f"🚀 Starting Model Training: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    logger.info(f"CSV Path: {csv_path}")
    logger.info(f"CSV Size: {os.path.getsize(csv_path) / (1024*1024):.2f} MB")
    
    try:
        # Train the model
        logger.info("Training model from CSV...")
        metadata = train_from_csv(csv_path)
        
        logger.info("=" * 70)
        logger.info("✅ Model Training Complete!")
        logger.info("=" * 70)
        
        # Display metrics
        logger.info(f"Accuracy: {metadata['accuracy']:.4f}")
        logger.info(f"CV Mean Score: {metadata['cv_mean']:.4f} (+/- {metadata['cv_std']:.4f})")
        logger.info(f"Trained At: {metadata['trained_at']}")
        logger.info(f"Features Used: {len(metadata['feature_columns'])}")
        logger.info(f"Feature Names: {', '.join(metadata['feature_columns'][:10])}...")
        
        if args.eval:
            logger.info("-" * 70)
            logger.info("Classification Report:")
            logger.info("-" * 70)
            report = metadata['classification_report']
            for key in ['0', '1', 'accuracy', 'macro avg', 'weighted avg']:
                if key in report:
                    val = report[key]
                    if isinstance(val, dict):
                        logger.info(f"{key}: P={val.get('precision', 0):.4f} R={val.get('recall', 0):.4f} F1={val.get('f1-score', 0):.4f}")
                    else:
                        logger.info(f"{key}: {val:.4f}")
        
        logger.info("=" * 70)
        logger.info("Model saved to: model.pkl")
        logger.info("Metadata saved to: model_metadata.json")
        logger.info("=" * 70)
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Training failed: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())