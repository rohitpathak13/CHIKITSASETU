"""
Comprehensive evaluation metrics computation for multi-class Patient Risk Prediction.
Calculates Accuracy, Precision, Recall, F1, and Multiclass ROC-AUC (One-vs-Rest).
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report
)


@dataclass
class EvaluationResult:
    model_name: str
    accuracy: float
    precision_macro: float
    precision_weighted: float
    recall_macro: float
    recall_weighted: float
    f1_macro: float
    f1_weighted: float
    roc_auc_ovr_macro: Optional[float]
    roc_auc_ovr_weighted: Optional[float]
    confusion_matrix: List[List[int]]
    labels: List[str]
    classification_report: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_multiclass_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_proba: Optional[np.ndarray] = None,
    labels: Optional[List[str]] = None,
    model_name: str = "Model"
) -> EvaluationResult:
    """
    Computes standard classification metrics for multi-class risk categories.

    Parameters:
        y_true: True class labels.
        y_pred: Predicted class labels.
        y_proba: Predicted probability matrix of shape (n_samples, n_classes).
        labels: Ordered list of class labels.
        model_name: Human readable identifier for the model.

    Returns:
        EvaluationResult dataclass with precision, recall, f1, accuracy, and roc-auc.
    """
    unique_labels = labels or sorted(list(set(y_true)))

    acc = float(accuracy_score(y_true, y_pred))
    prec_macro = float(precision_score(y_true, y_pred, labels=unique_labels, average="macro", zero_division=0))
    prec_weight = float(precision_score(y_true, y_pred, labels=unique_labels, average="weighted", zero_division=0))
    rec_macro = float(recall_score(y_true, y_pred, labels=unique_labels, average="macro", zero_division=0))
    rec_weight = float(recall_score(y_true, y_pred, labels=unique_labels, average="weighted", zero_division=0))
    f1_mac = float(f1_score(y_true, y_pred, labels=unique_labels, average="macro", zero_division=0))
    f1_weight = float(f1_score(y_true, y_pred, labels=unique_labels, average="weighted", zero_division=0))

    roc_macro = None
    roc_weighted = None
    if y_proba is not None:
        try:
            # Multi-class ROC AUC with One-vs-Rest strategy
            # Scikit-learn requires labels parameter to be strictly ordered
            sorted_indices = np.argsort(unique_labels)
            sorted_labels = [unique_labels[i] for i in sorted_indices]
            aligned_proba = np.asarray(y_proba)[:, sorted_indices]
            roc_macro = float(roc_auc_score(y_true, aligned_proba, labels=sorted_labels, multi_class="ovr", average="macro"))
            roc_weighted = float(roc_auc_score(y_true, aligned_proba, labels=sorted_labels, multi_class="ovr", average="weighted"))
        except Exception:
            roc_macro = None
            roc_weighted = None

    cm = confusion_matrix(y_true, y_pred, labels=unique_labels).tolist()
    cr = classification_report(y_true, y_pred, labels=unique_labels, output_dict=True, zero_division=0)

    return EvaluationResult(
        model_name=model_name,
        accuracy=round(acc, 4),
        precision_macro=round(prec_macro, 4),
        precision_weighted=round(prec_weight, 4),
        recall_macro=round(rec_macro, 4),
        recall_weighted=round(rec_weight, 4),
        f1_macro=round(f1_mac, 4),
        f1_weighted=round(f1_weight, 4),
        roc_auc_ovr_macro=round(roc_macro, 4) if roc_macro is not None else None,
        roc_auc_ovr_weighted=round(roc_weighted, 4) if roc_weighted is not None else None,
        confusion_matrix=cm,
        labels=unique_labels,
        classification_report=cr
    )


def format_metrics_summary(result: EvaluationResult) -> str:
    """Formats a concise text summary of model performance."""
    roc_str = f"{result.roc_auc_ovr_macro:.4f}" if result.roc_auc_ovr_macro is not None else "N/A"
    return (
        f"[{result.model_name}] "
        f"Accuracy: {result.accuracy:.4f} | "
        f"F1 (Macro): {result.f1_macro:.4f} | "
        f"Precision (Macro): {result.precision_macro:.4f} | "
        f"Recall (Macro): {result.recall_macro:.4f} | "
        f"ROC-AUC (OvR): {roc_str}"
    )
