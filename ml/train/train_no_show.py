import json
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, roc_auc_score, brier_score_loss, confusion_matrix

from ml.data.synthetic_generator import generate_no_show_dataset, DATA_DIR
from ml.pipelines.no_show_pipeline import build_no_show_pipeline

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

def train():
    print("[*] Initiating Appointment No-Show Prediction Model Training...")
    data_path = DATA_DIR / "no_show_training_data.csv"
    if not data_path.exists():
        df = generate_no_show_dataset(n_samples=6000)
    else:
        df = pd.read_csv(data_path)

    X = df.drop(columns=["no_show"])
    y = df["no_show"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, stratify=y, random_state=42
    )

    pipeline = build_no_show_pipeline()

    print("[*] Fitting Calibrated HistGradientBoosting pipeline...")
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    y_prob = pipeline.predict_proba(X_test)[:, 1]

    test_auc = roc_auc_score(y_test, y_prob)
    brier = brier_score_loss(y_test, y_prob)
    report = classification_report(y_test, y_pred, output_dict=True)
    cm = confusion_matrix(y_test, y_pred)

    print(f"\n[+] No-Show Model Evaluation:")
    print(f"    - ROC-AUC: {test_auc:.4f}")
    print(f"    - Brier Score (Calibration Quality): {brier:.4f}")
    print(f"    - Accuracy: {report['accuracy']:.4f}")
    print(f"    - Positive Recall (No-Show): {report['1']['recall']:.4f}")
    print(f"    - Positive F1-Score: {report['1']['f1-score']:.4f}")
    print(f"    - Confusion Matrix:\n{cm}\n")

    artifact_path = ARTIFACTS_DIR / "no_show_model.joblib"
    joblib.dump(pipeline, artifact_path)
    print(f"[+] Serialized model exported to: {artifact_path}")

    # Metadata
    metadata_path = ARTIFACTS_DIR / "model_metadata.json"
    metadata = {}
    if metadata_path.exists():
        try:
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
        except Exception:
            metadata = {}

    metadata["no_show_model"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "algorithm": "CalibratedClassifierCV(HistGradientBoostingClassifier)",
        "metrics": {
            "test_roc_auc": round(float(test_auc), 4),
            "brier_score": round(float(brier), 4),
            "test_accuracy": round(float(report["accuracy"]), 4),
            "recall_positive": round(float(report["1"]["recall"]), 4),
            "f1_positive": round(float(report["1"]["f1-score"]), 4)
        },
        "features": list(X.columns)
    }

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"[+] Metadata updated in {metadata_path}")

if __name__ == "__main__":
    train()
