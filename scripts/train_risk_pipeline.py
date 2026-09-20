"""
CLI Script to execute the Patient Risk Prediction ML Training Pipeline.
Runs data loading, cleaning, feature engineering, train/test split,
multi-model training (Logistic Regression, Random Forest, Gradient Boosting),
evaluation, and model serialization.
"""

import sys
from pathlib import Path

# Add workspace root to sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from ml.risk_prediction.datasets.loader import (
    generate_synthetic_patient_risk_data,
    load_patient_risk_dataset,
    RAW_DATASET_PATH
)
from ml.risk_prediction.training.trainer import RiskModelTrainer
from ml.risk_prediction.evaluation.evaluator import generate_comparison_markdown
from ml.risk_prediction.predictions.predictor import PatientRiskPredictor


def main():
    print("=" * 70)
    print("[CHIKITSASETU / MediCare AI] Patient Risk ML Pipeline")
    print("=" * 70)

    # 1. Dataset Generation & Loading
    print("\n[1/5] Loading or generating educational demo dataset...")
    df = load_patient_risk_dataset(auto_generate=True)
    print(f"      Dataset successfully loaded: {len(df)} samples across {len(df.columns)} columns.")
    print(f"      Target distribution:\n{df['risk_category'].value_counts().to_string()}")

    # 2. Training & Comparison
    print("\n[2/5] Executing leak-free training pipeline & evaluating candidate models...")
    trainer = RiskModelTrainer(test_size=0.20, random_state=42)
    best_pipeline, results = trainer.run_training_pipeline(df=df, save_best=True)

    # 3. Print Evaluation Table
    print("\n[3/5] Candidate Model Evaluation Benchmark:")
    print("-" * 70)
    markdown_table = generate_comparison_markdown(results)
    print(markdown_table)
    print("-" * 70)

    for r in results:
        roc_disp = f"{r.roc_auc_ovr_macro:.4f}" if r.roc_auc_ovr_macro is not None else "N/A"
        print(f"  * {r.model_name:22} | Acc: {r.accuracy:.4f} | Prec: {r.precision_macro:.4f} | Rec: {r.recall_macro:.4f} | F1: {r.f1_macro:.4f} | ROC-AUC: {roc_disp}")

    print(f"\n[4/5] Best Model Selected: {trainer.best_model_name}")
    print(f"      F1 (Weighted): {trainer.best_metrics.f1_weighted:.4f}")
    print(f"      Accuracy:      {trainer.best_metrics.accuracy:.4f}")
    print(f"      Artifacts saved in: {trainer.artifacts_dir}")

    # 5. Verification Inference
    print("\n[5/5] Testing serialized model inference via PatientRiskPredictor...")
    predictor = PatientRiskPredictor(models_dir=trainer.artifacts_dir)
    
    sample_patient = {
        "age": 62,
        "gender": "Male",
        "blood_pressure": "148/94",
        "glucose": 142.0,
        "bmi": 31.5,
        "heart_rate": 84,
        "smoking_status": "current",
        "family_history_diabetes": 1,
        "family_history_hypertension": 1,
        "family_history_heart_disease": 1
    }
    pred_res = predictor.predict_single(sample_patient)
    print(f"      Sample Patient Risk Category: {pred_res.risk_category} (Confidence: {pred_res.confidence * 100:.1f}%)")
    print(f"      Probabilities: {pred_res.probabilities}")
    print(f"      Key Risk Factors: {', '.join(pred_res.risk_factors)}")
    print(f"      Notice: {pred_res.disclaimer}")

    print("\n[SUCCESS] Patient Risk ML Pipeline completed successfully!")


if __name__ == "__main__":
    main()
