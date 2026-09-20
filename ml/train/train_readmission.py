import json
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix

from ml.data.synthetic_generator import generate_readmission_dataset, DATA_DIR
from ml.pipelines.readmission_pipeline import build_readmission_pipeline

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

def train():
    print("[*] Initiating 30-Day Hospital Readmission Model Training...")
    data_path = DATA_DIR / "readmission_training_data.csv"
    if not data_path.exists():
        df = generate_readmission_dataset(n_samples=5000)
    else:
        df = pd.read_csv(data_path)

    X = df.drop(columns=["readmitted_30d"])
    y = df["readmitted_30d"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, stratify=y, random_state=42
    )

    pipeline = build_readmission_pipeline()

    print("[*] Running 5-Fold Stratified Cross-Validation...")
    cv_scores = cross_val_score(pipeline, X_train, y_train, cv=5, scoring="roc_auc")
    print(f"    - Mean CV ROC-AUC: {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")

    print("[*] Fitting final model on training partition...")
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    y_prob = pipeline.predict_proba(X_test)[:, 1]

    test_auc = roc_auc_score(y_test, y_prob)
    cm = confusion_matrix(y_test, y_pred)
    report = classification_report(y_test, y_pred, output_dict=True)

    print(f"\n[+] Test Partition Performance Evaluation:")
    print(f"    - ROC-AUC: {test_auc:.4f}")
    print(f"    - Accuracy: {report['accuracy']:.4f}")
    print(f"    - Positive Recall (Readmitted): {report['1']['recall']:.4f}")
    print(f"    - Positive F1-Score: {report['1']['f1-score']:.4f}")
    print(f"    - Confusion Matrix:\n{cm}\n")

    artifact_path = ARTIFACTS_DIR / "readmission_model.joblib"
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

    metadata["readmission_model"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "algorithm": "RandomForestClassifier with Balanced Weights",
        "metrics": {
            "cv_roc_auc_mean": round(float(cv_scores.mean()), 4),
            "test_roc_auc": round(float(test_auc), 4),
            "test_accuracy": round(float(report["accuracy"]), 4),
            "recall_positive": round(float(report["1"]["recall"]), 4),
            "f1_positive": round(float(report["1"]["f1-score"]), 4)
        },
        "features": list(X.columns)
    }

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"[+] Metadata recorded in {metadata_path}")

if __name__ == "__main__":
    train()
