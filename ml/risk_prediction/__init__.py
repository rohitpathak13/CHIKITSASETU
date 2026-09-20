"""
Patient Risk Prediction Machine Learning Package.
Provides end-to-end pipelines for dataset generation, preprocessing,
model training, evaluation, registry, and inference.

DISCLAIMER: This machine learning model is intended strictly for educational
and operational demonstration purposes. It DOES NOT provide medical diagnosis
or clinical treatment advice.
"""

from ml.risk_prediction.datasets.loader import (
    load_patient_risk_dataset,
    generate_synthetic_patient_risk_data
)
from ml.risk_prediction.preprocessing.cleaner import clean_patient_risk_data
from ml.risk_prediction.preprocessing.feature_engineer import engineer_patient_risk_features
from ml.risk_prediction.preprocessing.pipeline import build_preprocessing_pipeline
from ml.risk_prediction.training.trainer import RiskModelTrainer
from ml.risk_prediction.evaluation.evaluator import evaluate_model_suite
from ml.risk_prediction.models.model_registry import (
    save_model_artifacts,
    load_model_artifacts,
    ModelCard
)
from ml.risk_prediction.predictions.predictor import PatientRiskPredictor

__all__ = [
    "load_patient_risk_dataset",
    "generate_synthetic_patient_risk_data",
    "clean_patient_risk_data",
    "engineer_patient_risk_features",
    "build_preprocessing_pipeline",
    "RiskModelTrainer",
    "evaluate_model_suite",
    "save_model_artifacts",
    "load_model_artifacts",
    "ModelCard",
    "PatientRiskPredictor"
]
