"""
Model Manager - Load and manage ML models
"""

import os
import json
import joblib  # Changed from pickle to joblib (same as your model.py)
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from backend.utils.logger import get_logger

logger = get_logger(__name__)


class ModelManager:
    """Manage ML model loading and metadata"""
    
    def __init__(self, model_dir: Optional[str] = None):
        # Default to scripts/ folder where model.pkl is created
        if model_dir is None:
            self.model_dir = Path(__file__).parent.parent.parent / "scripts"
        else:
            self.model_dir = Path(model_dir)
            
        self.model_path = self.model_dir / "model.pkl"
        self.metadata_path = self.model_dir / "model_metadata.json"
        
        self._model = None
        self._metadata = None
    
    @property
    def model(self):
        """Lazy load model"""
        if self._model is None:
            self._model = self.load_model()
        return self._model
    
    @property
    def metadata(self):
        """Lazy load metadata"""
        if self._metadata is None:
            self._metadata = self.load_metadata()
        return self._metadata
    
    def load_model(self):
        """Load trained model from pickle file"""
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model not found at {self.model_path}. "
                f"Please train the model first:\n"
                f"  cd scripts\n"
                f"  python train_model.py --csv training_data.csv"
            )
        
        try:
            # Use joblib (same as your model.py)
            model = joblib.load(self.model_path)
            
            logger.info(f"✅ Model loaded from {self.model_path}")
            return model
            
        except Exception as e:
            logger.error(f"❌ Failed to load model: {e}")
            raise
    
    def load_metadata(self) -> Dict[str, Any]:
        """Load model metadata"""
        if not self.metadata_path.exists():
            logger.warning(f"Metadata not found at {self.metadata_path}")
            return {}
        
        try:
            with open(self.metadata_path, 'r') as f:
                metadata = json.load(f)
            
            logger.info(f"✅ Metadata loaded: Accuracy={metadata.get('accuracy', 'N/A'):.4f}")
            return metadata
            
        except Exception as e:
            logger.error(f"❌ Failed to load metadata: {e}")
            return {}
    
    def is_model_ready(self) -> bool:
        """Check if model is ready for predictions"""
        return self.model_path.exists() and self.metadata_path.exists()
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        if not self.is_model_ready():
            return {
                "ready": False,
                "message": "Model not trained yet. Run: cd scripts && python train_model.py --csv training_data.csv"
            }
        
        metadata = self.metadata
        
        return {
            "ready": True,
            "trained_at": metadata.get("trained_at"),
            "accuracy": metadata.get("accuracy"),
            "cv_mean": metadata.get("cv_mean"),
            "cv_std": metadata.get("cv_std"),
            "features_count": len(metadata.get("feature_columns", [])),
            "training_samples": metadata.get("training_samples"),
            "training_data_source": metadata.get("training_data_source"),
            "model_path": str(self.model_path),
            "metadata_path": str(self.metadata_path),
        }
    
    def get_feature_columns(self):
        """Get list of feature columns used by the model"""
        return self.metadata.get("feature_columns", [])
    
    def reload(self):
        """Reload model and metadata"""
        self._model = None
        self._metadata = None
        logger.info("Model and metadata reloaded")