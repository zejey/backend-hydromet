import argparse
import json
from pathlib import Path

import joblib
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description="Run a single hazard+horizon model prediction from cached parquet.")
    parser.add_argument("--model-dir", required=True, help="Path like models/thunderstorm/12h")
    parser.add_argument("--cache", default="models/cache/prepared_labeled.parquet", help="Prepared+labeled parquet cache")
    parser.add_argument("--row", default="last", help="Which row to predict: 'last' or an integer index")
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    model_path = model_dir / "model.pkl"
    metadata_path = model_dir / "metadata.json"

    if not model_path.exists():
        raise FileNotFoundError(f"Missing model: {model_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing metadata: {metadata_path}")

    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    feature_names = metadata["feature_names"]

    df = pd.read_parquet(args.cache)

    if args.row == "last":
        row = df.iloc[[-1]].copy()
    else:
        idx = int(args.row)
        row = df.iloc[[idx]].copy()

    # Build X in the exact column order expected by the model
    missing = [c for c in feature_names if c not in row.columns]
    if missing:
        raise ValueError(f"Cached dataset is missing {len(missing)} required features, e.g.: {missing[:10]}")

    X = row[feature_names]

    model = joblib.load(model_path)
    proba = model.predict_proba(X)[0, 1]

    # Try to show the timestamp if present
    ts = None
    for tcol in ("dt", "timestamp"):
        if tcol in row.columns:
            ts = row.iloc[0][tcol]
            break

    print(f"Model: {model_dir}")
    if ts is not None:
        print(f"Row time: {ts}")
    print(f"Predicted probability (class=1): {proba:.6f}")


if __name__ == "__main__":
    main()