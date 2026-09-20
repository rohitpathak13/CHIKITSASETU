"""Evaluation module for Patient Risk Prediction."""
from ml.risk_prediction.evaluation.metrics import (
    compute_multiclass_metrics,
    format_metrics_summary,
    EvaluationResult
)
from ml.risk_prediction.evaluation.evaluator import (
    evaluate_model_suite,
    generate_comparison_markdown
)

__all__ = [
    "compute_multiclass_metrics",
    "format_metrics_summary",
    "EvaluationResult",
    "evaluate_model_suite",
    "generate_comparison_markdown"
]
