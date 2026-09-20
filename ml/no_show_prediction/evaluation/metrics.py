"""
Evaluation metrics module for binary Appointment No-Show Prediction.
Calculates Accuracy, Precision, Recall, F1, ROC-AUC, Brier score, and Confusion Matrix.
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
    brier_score_loss,
    confusion_matrix,
    classification_report
)


@dataclass
class NoShowEvaluationResult:
    model_name: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    roc_auc: Optional[float]
    brier_score: Optional[float]
    confusion_matrix: List[List[int]]
    classification_report: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_binary_classification_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: Optional[np.ndarray] = None,
    model_name: str = "Model"
) -> NoShowEvaluationResult:
    """
    Computes standard evaluation metrics for binary attendance/no-show classification.

    Parameters:
        y_true: Binary ground truth (0 = Attended, 1 = No-Show).
        y_pred: Predicted binary classes.
        y_prob: Predicted continuous probability of no-show (class 1).
        model_name: Descriptive name for the classifier.

    Returns:
        NoShowEvaluationResult with complete metrics suite.
    """
    y_t = np.asarray(y_true).astype(int)
    y_p = np.asarray(y_pred).astype(int)

    acc = float(accuracy_score(y_t, y_p))
    prec = float(precision_score(y_t, y_p, zero_division=0))
    rec = float(recall_score(y_t, y_p, zero_division=0))
    f1 = float(f1_score(y_t, y_p, zero_division=0))

    auc = None
    brier = None
    if y_prob is not None:
        try:
            auc = float(roc_auc_score(y_t, y_prob))
            brier = float(brier_score_loss(y_t, y_prob))
        except Exception:
            auc = None
            brier = None

    cm = confusion_matrix(y_t, y_p).tolist()
    cr = classification_report(y_t, y_p, output_dict=True, zero_division=0)

    return NoShowEvaluationResult(
        model_name=model_name,
        accuracy=round(acc, 4),
        precision=round(prec, 4),
        recall=round(rec, 4),
        f1_score=round(f1, 4),
        roc_auc=round(auc, 4) if auc is not None else None,
        brier_score=round(brier, 4) if brier is not None else None,
        confusion_matrix=cm,
        classification_report=cr
    )
