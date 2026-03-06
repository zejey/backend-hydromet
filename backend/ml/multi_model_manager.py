"""
Extended Multi-Model Manager
Manages loading and caching of multiple Naive Bayes models (4 hazards × 3 horizons)
"""

import os
import json
import joblib
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MultiModelManager:
    """
    Manage multiple ML models for multi-hazard, multi-horizon prediction
    
    Models organized as: models/{hazard}/{horizon}h/model.pkl
    """
    
    def __init__(self, models_dir: Optional[str] = None):
        """
        Initialize multi-model manager
        
        Args:
            models_dir: Directory containing trained models
                       Default: scripts/models or backend/ml/models
        """
        if models_dir is None:
            # Try multiple default locations
            candidates = [
                Path(__file__).parent.parent.parent / "models",
                Path(__file__).parent.parent / "scripts" / "models",
                Path(__file__).parent.parent.parent / "scripts" / "models",
                Path(__file__).parent / "models",
            ]
            for candidate in candidates:
                if candidate.exists():
                    self.models_dir = candidate
                    break
            else:
                # Use first candidate as default (will be created if needed)
                self.models_dir = candidates[0]
        else:
            p = Path(models_dir)
            if not p.is_absolute():
                p = Path(__file__).parent.parent.parent / p
            self.models_dir = p
        
        logger.info(f"MultiModelManager initialized with models_dir: {self.models_dir}")
        
        # Cache for loaded models
        self._models_cache: Dict[str, Any] = {}
        self._metadata_cache: Dict[str, Dict] = {}
        
        # Supported hazards and horizons
        self.hazards = ["heat_stress", "heavy_rain", "thunderstorm", "severe_storm"]
        self.horizons = [12, 24, 48]
    
    def get_model_path(self, hazard: str, horizon: int) -> Tuple[Path, Path]:
        """
        Get paths to model and metadata files
        
        Args:
            hazard: Hazard type
            horizon: Time horizon in hours
            
        Returns:
            Tuple of (model_path, metadata_path)
        """
        model_dir = self.models_dir / hazard / f"{horizon}h"
        model_path = model_dir / "model.pkl"
        metadata_path = model_dir / "metadata.json"
        
        return model_path, metadata_path
    
    def is_model_available(self, hazard: str, horizon: int) -> bool:
        """
        Check if a specific model is available
        
        Args:
            hazard: Hazard type
            horizon: Time horizon in hours
            
        Returns:
            True if model exists and is loadable
        """
        model_path, metadata_path = self.get_model_path(hazard, horizon)
        return model_path.exists() and metadata_path.exists()
    
    def load_model(self, hazard: str, horizon: int, use_cache: bool = True) -> Any:
        """
        Load a specific model
        
        Args:
            hazard: Hazard type
            horizon: Time horizon in hours
            use_cache: Whether to use cached model if available
            
        Returns:
            Loaded model pipeline
            
        Raises:
            FileNotFoundError: If model files don't exist
        """
        model_key = f"{hazard}_{horizon}h"
        
        # Check cache
        if use_cache and model_key in self._models_cache:
            logger.debug(f"Using cached model: {model_key}")
            return self._models_cache[model_key]
        
        # Load from disk
        model_path, metadata_path = self.get_model_path(hazard, horizon)
        
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found: {model_path}\n"
                f"Please train the model first:\n"
                f"  cd scripts\n"
                f"  python train_multi_models.py --csv training_data.csv"
            )
        
        try:
            logger.info(f"Loading model: {model_key} from {model_path}")
            model = joblib.load(model_path)
            
            # Cache the model
            if use_cache:
                self._models_cache[model_key] = model
            
            return model
            
        except Exception as e:
            logger.error(f"Failed to load model {model_key}: {e}")
            raise
    
    def load_metadata(self, hazard: str, horizon: int, use_cache: bool = True) -> Dict:
        """
        Load metadata for a specific model
        
        Args:
            hazard: Hazard type
            horizon: Time horizon in hours
            use_cache: Whether to use cached metadata if available
            
        Returns:
            Metadata dictionary
        """
        model_key = f"{hazard}_{horizon}h"
        
        # Check cache
        if use_cache and model_key in self._metadata_cache:
            logger.debug(f"Using cached metadata: {model_key}")
            return self._metadata_cache[model_key]
        
        # Load from disk
        model_path, metadata_path = self.get_model_path(hazard, horizon)
        
        if not metadata_path.exists():
            logger.warning(f"Metadata not found: {metadata_path}")
            return {}
        
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            # Cache the metadata
            if use_cache:
                self._metadata_cache[model_key] = metadata
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to load metadata {model_key}: {e}")
            return {}
    
    def load_all_models(self) -> Dict[str, Any]:
        """
        Load all available models
        
        Returns:
            Dictionary mapping model_key to loaded model
        """
        logger.info("Loading all available models...")
        
        models = {}
        
        for hazard in self.hazards:
            for horizon in self.horizons:
                model_key = f"{hazard}_{horizon}h"
                
                if self.is_model_available(hazard, horizon):
                    try:
                        model = self.load_model(hazard, horizon, use_cache=True)
                        models[model_key] = model
                        logger.info(f"  ✓ Loaded: {model_key}")
                    except Exception as e:
                        logger.error(f"  ✗ Failed to load {model_key}: {e}")
                else:
                    logger.warning(f"  ⊘ Not available: {model_key}")
        
        logger.info(f"Loaded {len(models)}/{len(self.hazards) * len(self.horizons)} models")
        
        return models
    
    def get_all_metadata(self) -> Dict[str, Dict]:
        """
        Get metadata for all available models
        
        Returns:
            Dictionary mapping model_key to metadata
        """
        metadata_dict = {}
        
        for hazard in self.hazards:
            for horizon in self.horizons:
                model_key = f"{hazard}_{horizon}h"
                
                if self.is_model_available(hazard, horizon):
                    metadata = self.load_metadata(hazard, horizon, use_cache=True)
                    metadata_dict[model_key] = metadata
        
        return metadata_dict
    
    def get_model_status(self) -> Dict[str, Any]:
        """
        Get status of all models
        
        Returns:
            Dictionary with model availability and metadata
        """
        status = {
            "models_dir": str(self.models_dir),
            "timestamp": datetime.now().isoformat(),
            "hazards": self.hazards,
            "horizons": self.horizons,
            "total_expected": len(self.hazards) * len(self.horizons),
            "models": {}
        }
        
        available_count = 0
        
        for hazard in self.hazards:
            for horizon in self.horizons:
                model_key = f"{hazard}_{horizon}h"
                is_available = self.is_model_available(hazard, horizon)
                
                if is_available:
                    available_count += 1
                    metadata = self.load_metadata(hazard, horizon, use_cache=True)
                    
                    status["models"][model_key] = {
                        "available": True,
                        "accuracy": metadata.get("accuracy"),
                        "f1_score": metadata.get("f1_score"),
                        "trained_at": metadata.get("trained_at"),
                        "train_samples": metadata.get("train_samples"),
                        "feature_count": metadata.get("feature_count"),
                    }
                else:
                    status["models"][model_key] = {
                        "available": False
                    }
        
        status["available_count"] = available_count
        status["ready"] = available_count == status["total_expected"]
        
        return status
    
    def clear_cache(self):
        """Clear the model and metadata cache"""
        self._models_cache.clear()
        self._metadata_cache.clear()
        logger.info("Model cache cleared")
    
    def predict(
        self,
        hazard: str,
        horizon: int,
        features: Any
    ) -> Tuple[int, float]:
        """
        Make prediction with a specific model
        
        Args:
            hazard: Hazard type
            horizon: Time horizon in hours
            features: Feature array/DataFrame for prediction
            
        Returns:
            Tuple of (prediction, probability)
        """
        model = self.load_model(hazard, horizon, use_cache=True)
        
        prediction = model.predict(features)[0]
        probability = model.predict_proba(features)[0, 1]
        
        return int(prediction), float(probability)
    
    def predict_all_hazards(
        self,
        features: Any,
        horizon: int
    ) -> Dict[str, Dict]:
        """
        Predict all hazards for a specific horizon
        
        Args:
            features: Feature array/DataFrame for prediction
            horizon: Time horizon in hours
            
        Returns:
            Dictionary mapping hazard to prediction result
        """
        results = {}
        
        for hazard in self.hazards:
            if self.is_model_available(hazard, horizon):
                try:
                    prediction, probability = self.predict(hazard, horizon, features)
                    results[hazard] = {
                        "prediction": prediction,
                        "probability": probability,
                        "hazard_detected": bool(prediction == 1)
                    }
                except Exception as e:
                    logger.error(f"Prediction failed for {hazard}_{horizon}h: {e}")
                    results[hazard] = {
                        "error": str(e)
                    }
            else:
                results[hazard] = {
                    "available": False
                }
        
        return results
    
    def predict_all_horizons(
        self,
        features: Any,
        hazard: str
    ) -> Dict[int, Dict]:
        """
        Predict all horizons for a specific hazard
        
        Args:
            features: Feature array/DataFrame for prediction
            hazard: Hazard type
            
        Returns:
            Dictionary mapping horizon to prediction result
        """
        results = {}
        
        for horizon in self.horizons:
            if self.is_model_available(hazard, horizon):
                try:
                    prediction, probability = self.predict(hazard, horizon, features)
                    results[horizon] = {
                        "prediction": prediction,
                        "probability": probability,
                        "hazard_detected": bool(prediction == 1)
                    }
                except Exception as e:
                    logger.error(f"Prediction failed for {hazard}_{horizon}h: {e}")
                    results[horizon] = {
                        "error": str(e)
                    }
            else:
                results[horizon] = {
                    "available": False
                }
        
        return results


# Singleton instance for global use
_multi_model_manager = None


def get_multi_model_manager(models_dir: Optional[str] = None) -> MultiModelManager:
    """
    Get or create singleton MultiModelManager instance
    
    Args:
        models_dir: Optional models directory
        
    Returns:
        MultiModelManager instance
    """
    global _multi_model_manager

    if models_dir is None:
        models_dir = os.getenv("MODELS_DIR")
    
    if _multi_model_manager is None or models_dir is not None:
        _multi_model_manager = MultiModelManager(models_dir=models_dir)
    
    return _multi_model_manager


if __name__ == "__main__":
    # Testing
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "="*60)
    print("MULTI-MODEL MANAGER - TESTING")
    print("="*60)
    
    # Create manager
    manager = get_multi_model_manager()
    
    # Check status
    print("\nChecking model status...")
    status = manager.get_model_status()
    
    print(f"\nModels Directory: {status['models_dir']}")
    print(f"Expected Models: {status['total_expected']}")
    print(f"Available Models: {status['available_count']}")
    print(f"System Ready: {status['ready']}")
    
    print("\n" + "="*60)
    print("Model Availability:")
    print("="*60)
    
    for model_key, info in status['models'].items():
        if info['available']:
            print(f"✓ {model_key:25s} - Accuracy: {info.get('accuracy', 'N/A'):.4f if info.get('accuracy') else 'N/A'}")
        else:
            print(f"✗ {model_key:25s} - NOT AVAILABLE")
    
    if status['available_count'] > 0:
        print("\n" + "="*60)
        print("Sample Model Metadata:")
        print("="*60)
        
        # Show details of first available model
        for model_key, info in status['models'].items():
            if info['available']:
                hazard, horizon_str = model_key.rsplit('_', 1)
                horizon = int(horizon_str.replace('h', ''))
                
                metadata = manager.load_metadata(hazard, horizon)
                print(f"\n{model_key}:")
                print(f"  Trained: {metadata.get('trained_at', 'Unknown')}")
                print(f"  Samples: {metadata.get('train_samples', 'Unknown')}")
                print(f"  Features: {metadata.get('feature_count', 'Unknown')}")
                print(f"  Accuracy: {metadata.get('accuracy', 'Unknown')}")
                print(f"  F1-Score: {metadata.get('f1_score', 'Unknown')}")
                break
    
    print("\n✅ Multi-model manager test complete!")