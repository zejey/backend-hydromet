import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    confusion_matrix,
    average_precision_score,
    roc_auc_score,
)

from train_multi_models import MultiModelTrainer
from feature_engineering import get_feature_columns_for_hazard


HAZARDS = ["heat_stress", "heavy_rain", "thunderstorm", "severe_storm"]
HORIZONS = [12, 24, 48]


def load_model(models_dir: Path, hazard: str, horizon: int):
    model_path = models_dir / hazard / f"{horizon}h" / "model.pkl"
    if not model_path.exists():
        return None, str(model_path)
    return joblib.load(model_path), str(model_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Historical hourly CSV used for training/eval.")
    ap.add_argument("--models-dir", default="models", help="Directory where models/* are saved.")
    ap.add_argument("--time-col", default="dt")
    ap.add_argument("--test-size", type=float, default=0.2)
    ap.add_argument("--use-cache", action="store_true")
    ap.add_argument("--cache-path", default="models/cache/prepared_labeled.parquet")
    ap.add_argument("--out", default="models/eval_report.json")
    args = ap.parse_args()

    models_dir = Path(args.models_dir)

    # Prepare data exactly like training does (prep + features + labels)
    trainer = MultiModelTrainer(models_dir=args.models_dir, config={"test_size": args.test_size})
    data = trainer.prepare_training_data(
        csv_path=args.csv,
        time_col=args.time_col,
        use_cache=args.use_cache,
        refresh_cache=False,
        cache_path=args.cache_path,
    )

    report = {
        "csv": args.csv,
        "test_size": args.test_size,
        "rows_prepared": int(len(data)),
        "models": {},
    }

    for hazard in HAZARDS:
        feature_cols = get_feature_columns_for_hazard(data, hazard)
        feature_cols = [c for c in feature_cols if c in data.columns]

        for horizon in HORIZONS:
            label_col = f"{hazard}_{horizon}h"
            key = label_col

            model, model_path = load_model(models_dir, hazard, horizon)
            if model is None:
                report["models"][key] = {"error": "model not found", "model_path": model_path}
                continue

            if label_col not in data.columns:
                report["models"][key] = {"error": "label missing in prepared data", "model_path": model_path}
                continue

            X = data[feature_cols].copy()
            y = data[label_col].copy()

            # Match training-time NaN handling roughly (the training loop does more per-hazard cleanup).
            # For evaluation, drop rows with any NaN in X or y so results are comparable.
            valid = ~(X.isna().any(axis=1) | y.isna())
            X = X[valid]
            y = y[valid]

            if len(X) < 50:
                report["models"][key] = {"error": "not enough samples after NaN filtering", "n": int(len(X))}
                continue

            split_idx = int(len(X) * (1 - args.test_size))
            X_test = X.iloc[split_idx:]
            y_test = y.iloc[split_idx:]

            # Predict
            y_pred = model.predict(X_test)

            # Probabilities if available
            y_proba = None
            try:
                y_proba = model.predict_proba(X_test)[:, 1]
            except Exception:
                pass

            acc = accuracy_score(y_test, y_pred)
            prec, rec, f1, _ = precision_recall_fscore_support(
                y_test, y_pred, average="binary", zero_division=0
            )
            cm = confusion_matrix(y_test, y_pred).tolist()

            metrics = {
                "model_path": model_path,
                "test_samples": int(len(y_test)),
                "pos_rate_test": float(np.mean(y_test)) if len(y_test) else None,
                "accuracy": float(acc),
                "precision": float(prec),
                "recall": float(rec),
                "f1": float(f1),
                "confusion_matrix": cm,
            }

            # Add threshold-free metrics (better for imbalanced hazards)
            if y_proba is not None and len(np.unique(y_test)) == 2:
                metrics["pr_auc"] = float(average_precision_score(y_test, y_proba))
                metrics["roc_auc"] = float(roc_auc_score(y_test, y_proba))

            report["models"][key] = metrics

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Wrote evaluation report to: {args.out}")


if __name__ == "__main__":
    main()