"""
CLI Script to execute the Appointment No-Show Prediction Training Pipeline.
Loads or generates historical appointment data, cleans features, performs stratified split,
trains and calibrates Logistic Regression, Random Forest, and Gradient Boosting,
evaluates models, and serializes the top-performing pipeline.
"""

import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from ml.no_show_prediction.datasets.loader import (
    load_no_show_dataset,
    DEMO_NO_SHOW_DATASET_PATH
)
from ml.no_show_prediction.training.trainer import NoShowModelTrainer
from ml.no_show_prediction.evaluation.evaluator import generate_no_show_comparison_markdown
from ml.no_show_prediction.predictions.predictor import NoShowPredictorService


def main():
    print("=" * 70)
    print("[CHIKITSASETU / MediCare AI] Appointment No-Show ML Pipeline")
    print("=" * 70)

    # 1. Dataset Loading
    print("\n[1/5] Loading or synthesizing historical appointment data...")
    df = load_no_show_dataset(auto_generate=True)
    print(f"      Loaded {len(df)} appointment records across {len(df.columns)} columns.")
    no_show_rate = (df["no_show"].sum() / len(df)) * 100
    print(f"      Overall No-Show Rate: {no_show_rate:.1f}%")

    # 2. Pipeline Execution & Model Training
    print("\n[2/5] Training, calibrating, and benchmarking candidate classification models...")
    trainer = NoShowModelTrainer(test_size=0.20, random_state=42)
    best_pipeline, results = trainer.run_training_pipeline(df=df, save_best=True)

    # 3. Print Benchmark Comparison Table
    print("\n[3/5] Candidate Model Benchmark Comparison:")
    print("-" * 70)
    markdown_table = generate_no_show_comparison_markdown(results)
    print(markdown_table)
    print("-" * 70)

    for r in results:
        auc_str = f"{r.roc_auc:.4f}" if r.roc_auc is not None else "N/A"
        brier_str = f"{r.brier_score:.4f}" if r.brier_score is not None else "N/A"
        print(f"  * {r.model_name:22} | Acc: {r.accuracy:.4f} | Prec: {r.precision:.4f} | Rec: {r.recall:.4f} | F1: {r.f1_score:.4f} | AUC: {auc_str} | Brier: {brier_str}")

    print(f"\n[4/5] Best Model Selected: {trainer.best_model_name}")
    print(f"      ROC-AUC:       {trainer.best_metrics.roc_auc:.4f}")
    print(f"      F1-Score:      {trainer.best_metrics.f1_score:.4f}")
    print(f"      Brier Score:   {trainer.best_metrics.brier_score:.4f}")
    print(f"      Artifacts saved in: {trainer.artifacts_dir}")

    # 5. Verification Inference
    print("\n[5/5] Testing serialized model inference via NoShowPredictorService...")
    predictor = NoShowPredictorService(models_dir=trainer.artifacts_dir)

    sample_booking = {
        "patient_age": 22,
        "appointment_weekday": "Monday",
        "appointment_lead_time": 18,
        "previous_appointment_count": 4,
        "previous_no_show_count": 2,
        "department": "Dermatology",
        "sms_reminder_sent": 0
    }
    pred_res = predictor.predict_single(sample_booking)
    print(f"      Sample Appointment No-Show Probability: {pred_res.no_show_probability * 100:.1f}%")
    print(f"      Triage Risk Tier:                       {pred_res.risk_tier}")
    print(f"      Operational Recommendation:             {pred_res.recommendation}")
    print(f"      Detected Friction Drivers:              {', '.join(pred_res.risk_factors)}")
    print(f"      Disclaimer Notice:                      {pred_res.disclaimer}")

    print("\n[SUCCESS] Appointment No-Show ML Pipeline completed successfully!")


if __name__ == "__main__":
    main()
