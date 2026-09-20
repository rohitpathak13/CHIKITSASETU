"""
Model Suite Evaluator and Benchmarking module.
Compares candidate models side-by-side and produces Markdown comparison tables.
"""

from typing import Dict, List, Any
import pandas as pd
from sklearn.pipeline import Pipeline
from ml.risk_prediction.evaluation.metrics import compute_multiclass_metrics, EvaluationResult


def evaluate_model_suite(
    trained_pipelines: Dict[str, Pipeline],
    X_test: pd.DataFrame,
    y_test: pd.Series,
    labels: List[str] = None
) -> List[EvaluationResult]:
    """
    Evaluates each candidate pipeline on the common test partition.

    Parameters:
        trained_pipelines: Dict mapping model_name -> fitted Scikit-Learn Pipeline.
        X_test: Test features.
        y_test: True test target labels.
        labels: Class labels list.

    Returns:
        List of EvaluationResult objects.
    """
    unique_labels = labels or ["Low", "Medium", "High"]
    results = []

    for name, pipeline in trained_pipelines.items():
        y_pred = pipeline.predict(X_test)
        
        classes = list(pipeline.classes_) if hasattr(pipeline, "classes_") else unique_labels
        
        y_proba = None
        if hasattr(pipeline, "predict_proba"):
            try:
                y_proba = pipeline.predict_proba(X_test)
            except Exception:
                y_proba = None

        res = compute_multiclass_metrics(
            y_true=y_test.to_numpy() if hasattr(y_test, "to_numpy") else y_test,
            y_pred=y_pred,
            y_proba=y_proba,
            labels=classes,
            model_name=name
        )
        results.append(res)

    return results


def generate_comparison_markdown(results: List[EvaluationResult]) -> str:
    """
    Renders an ASCII / GitHub Markdown comparison table for candidate models.
    """
    headers = [
        "Model",
        "Accuracy",
        "Precision (Macro)",
        "Recall (Macro)",
        "F1 (Macro)",
        "F1 (Weighted)",
        "ROC-AUC (OvR Macro)"
    ]
    
    rows = []
    for r in results:
        roc_str = f"{r.roc_auc_ovr_macro:.4f}" if r.roc_auc_ovr_macro is not None else "N/A"
        rows.append([
            f"**{r.model_name}**",
            f"{r.accuracy:.4f}",
            f"{r.precision_macro:.4f}",
            f"{r.recall_macro:.4f}",
            f"{r.f1_macro:.4f}",
            f"{r.f1_weighted:.4f}",
            roc_str
        ])

    table_lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |"
    ]
    for row in rows:
        table_lines.append("| " + " | ".join(row) + " |")

    return "\n".join(table_lines)
