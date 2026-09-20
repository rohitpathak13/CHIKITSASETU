"""
Model Suite Evaluator for Appointment No-Show Prediction.
Evaluates candidate models side-by-side and produces Markdown comparison tables.
"""

from typing import Dict, List
import pandas as pd
from sklearn.pipeline import Pipeline
from ml.no_show_prediction.evaluation.metrics import (
    compute_binary_classification_metrics,
    NoShowEvaluationResult
)


def evaluate_no_show_models(
    trained_pipelines: Dict[str, Pipeline],
    X_test: pd.DataFrame,
    y_test: pd.Series
) -> List[NoShowEvaluationResult]:
    """
    Evaluates candidate no-show pipelines on held-out test data.
    """
    results = []
    y_arr = y_test.to_numpy() if hasattr(y_test, "to_numpy") else y_test

    for name, pipeline in trained_pipelines.items():
        y_pred = pipeline.predict(X_test)
        
        y_prob = None
        if hasattr(pipeline, "predict_proba"):
            try:
                # Column 1 is probability of no-show
                y_prob = pipeline.predict_proba(X_test)[:, 1]
            except Exception:
                y_prob = None

        res = compute_binary_classification_metrics(
            y_true=y_arr,
            y_pred=y_pred,
            y_prob=y_prob,
            model_name=name
        )
        results.append(res)

    return results


def generate_no_show_comparison_markdown(results: List[NoShowEvaluationResult]) -> str:
    """
    Renders an ASCII / GitHub Markdown comparison table for candidate models.
    """
    headers = [
        "Model",
        "Accuracy",
        "Precision (No-Show)",
        "Recall (No-Show)",
        "F1-Score",
        "ROC-AUC",
        "Brier Score (Calibration)"
    ]

    rows = []
    for r in results:
        auc_str = f"{r.roc_auc:.4f}" if r.roc_auc is not None else "N/A"
        brier_str = f"{r.brier_score:.4f}" if r.brier_score is not None else "N/A"
        rows.append([
            f"**{r.model_name}**",
            f"{r.accuracy:.4f}",
            f"{r.precision:.4f}",
            f"{r.recall:.4f}",
            f"{r.f1_score:.4f}",
            auc_str,
            brier_str
        ])

    table_lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |"
    ]
    for row in rows:
        table_lines.append("| " + " | ".join(row) + " |")

    return "\n".join(table_lines)


# Aliases for cross-module compatibility
evaluate_multiple_models = evaluate_no_show_models
generate_model_comparison_report = generate_no_show_comparison_markdown
