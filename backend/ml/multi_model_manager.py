"""
Multi-Model Manager - Manage multiple hazard-specific ML models

Supports 4 hazard types × 3 horizons = 12 models:
- Hazard types: heat, heavy_rain, thunderstorm, severe_storm
- Horizons: 12h, 24h, 48h
"""

import os
import json
import joblib
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Define hazard types and prediction horizons
HAZARD_TYPES = ["heat", "heavy_rain", "thunderstorm", "severe_storm"]
HORIZONS = ["12h", "24h", "48h"]


class MultiModelManager:
    """Manage multiple hazard-specific ML models"""
    
    def __init__(self, model_dir: Optional[str] = None):
        # Default to scripts/models folder for multi-model artifacts
        if model_dir is None:
            self.model_dir = Path(__file__).parent.parent.parent / "scripts" / "models"
        else:
            self.model_dir = Path(model_dir)
        
        # Cache for loaded models and metadata
        self._models: Dict[str, Dict[str, Any]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"MultiModelManager initialized with model_dir: {self.model_dir}")
    
    def _get_model_path(self, hazard_type: str, horizon: str) -> Path:
        """Get path to model file for specific hazard and horizon"""
        return self.model_dir / f"{hazard_type}_{horizon}_model.pkl"
    
    def _get_metadata_path(self, hazard_type: str, horizon: str) -> Path:
        """Get path to metadata file for specific hazard and horizon"""
        return self.model_dir / f"{hazard_type}_{horizon}_metadata.json"
    
    def is_model_ready(self, hazard_type: str, horizon: str) -> bool:
        """Check if a specific model is ready for predictions"""
        model_path = self._get_model_path(hazard_type, horizon)
        metadata_path = self._get_metadata_path(hazard_type, horizon)
        return model_path.exists() and metadata_path.exists()
    
    def load_model(self, hazard_type: str, horizon: str) -> Optional[Any]:
        """Load a specific model from pickle file"""
        key = f"{hazard_type}_{horizon}"
        
        # Return cached model if available
        if key in self._models:
            return self._models[key]
        
        model_path = self._get_model_path(hazard_type, horizon)
        
        if not model_path.exists():
            logger.warning(f"Model not found: {model_path}")
            return None
        
        try:
            model = joblib.load(model_path)
            self._models[key] = model
            logger.info(f"✅ Loaded model: {hazard_type}/{horizon}")
            return model
        except Exception as e:
            logger.error(f"❌ Failed to load model {hazard_type}/{horizon}: {e}")
            return None
    
    def load_metadata(self, hazard_type: str, horizon: str) -> Dict[str, Any]:
        """Load metadata for a specific model"""
        key = f"{hazard_type}_{horizon}"
        
        # Return cached metadata if available
        if key in self._metadata:
            return self._metadata[key]
        
        metadata_path = self._get_metadata_path(hazard_type, horizon)
        
        if not metadata_path.exists():
            return {}
        
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            self._metadata[key] = metadata
            return metadata
        except Exception as e:
            logger.error(f"❌ Failed to load metadata {hazard_type}/{horizon}: {e}")
            return {}
    
    def get_model_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status of all models
        
        Returns:
            Dictionary with model availability, counts, and per-model status
        """
        status = {
            "total_models": len(HAZARD_TYPES) * len(HORIZONS),
            "available_count": 0,
            "models": {},
            "ready": False,
            "message": None
        }
        
        for hazard_type in HAZARD_TYPES:
            status["models"][hazard_type] = {}
            
            for horizon in HORIZONS:
                is_ready = self.is_model_ready(hazard_type, horizon)
                metadata = self.load_metadata(hazard_type, horizon) if is_ready else {}
                
                status["models"][hazard_type][horizon] = {
                    "available": is_ready,
                    "accuracy": metadata.get("accuracy"),
                    "trained_at": metadata.get("trained_at")
                }
                
                if is_ready:
                    status["available_count"] += 1
        
        # Set overall readiness
        status["ready"] = status["available_count"] > 0
        
        if status["available_count"] == 0:
            status["message"] = (
                "No ML models trained yet. Train models with:\n"
                "  cd scripts\n"
                "  python train_multi_model.py --csv training_data.csv"
            )
        elif status["available_count"] < status["total_models"]:
            status["message"] = (
                f"Partial models available ({status['available_count']}/{status['total_models']}). "
                "Run training to enable all hazard types and horizons."
            )
        
        return status
    
    def get_available_models(self) -> List[Dict[str, str]]:
        """Get list of available models"""
        available = []
        
        for hazard_type in HAZARD_TYPES:
            for horizon in HORIZONS:
                if self.is_model_ready(hazard_type, horizon):
                    available.append({
                        "hazard_type": hazard_type,
                        "horizon": horizon
                    })
        
        return available
    
    def get_aggregated_info(self) -> Dict[str, Any]:
        """
        Get aggregated model information across all available models
        
        Returns:
            Dictionary with average accuracy, earliest trained_at, etc.
        """
        available_models = self.get_available_models()
        
        if not available_models:
            return {
                "ready": False,
                "message": "No models available. Please train the models first."
            }
        
        accuracies = []
        trained_times = []
        
        for model_info in available_models:
            metadata = self.load_metadata(model_info["hazard_type"], model_info["horizon"])
            if metadata.get("accuracy"):
                accuracies.append(metadata["accuracy"])
            if metadata.get("trained_at"):
                trained_times.append(metadata["trained_at"])
        
        return {
            "ready": True,
            "total_models": len(HAZARD_TYPES) * len(HORIZONS),
            "available_count": len(available_models),
            "avg_accuracy": sum(accuracies) / len(accuracies) if accuracies else None,
            "earliest_trained_at": min(trained_times) if trained_times else None,
            "hazard_types": HAZARD_TYPES,
            "horizons": HORIZONS
        }
    
    def reload(self):
        """Clear caches and reload models"""
        self._models.clear()
        self._metadata.clear()
        logger.info("Multi-model caches cleared")
