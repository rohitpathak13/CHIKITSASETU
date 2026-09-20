"""
Appointment No-Show Prediction Machine Learning Package.
Provides end-to-end pipelines for historical appointment dataset generation,
preprocessing, feature engineering, training, evaluation, model serialization,
and operational triage prediction.

DISCLAIMER: This system is designed solely as an operational scheduling decision-support tool.
It does NOT make medical diagnoses or clinical health claims.
"""

from ml.no_show_prediction.datasets.loader import (
    load_no_show_dataset,
    generate_synthetic_no_show_data
)
from ml.no_show_prediction.preprocessing.cleaner import clean_no_show_data
from ml.no_show_prediction.preprocessing.feature_engineer import engineer_no_show_features
from ml.no_show_prediction.preprocessing.pipeline import build_no_show_preprocessing_pipeline
from ml.no_show_prediction.training.trainer import NoShowModelTrainer
from ml.no_show_prediction.evaluation.evaluator import evaluate_no_show_models
from ml.no_show_prediction.models.model_registry import (
    save_no_show_artifacts,
    load_no_show_artifacts,
    NoShowModelCard
)
from ml.no_show_prediction.predictions.predictor import NoShowPredictorService

__all__ = [
    "load_no_show_dataset",
    "generate_synthetic_no_show_data",
    "clean_no_show_data",
    "engineer_no_show_features",
    "build_no_show_preprocessing_pipeline",
    "NoShowModelTrainer",
    "evaluate_no_show_models",
    "save_no_show_artifacts",
    "load_no_show_artifacts",
    "NoShowModelCard",
    "NoShowPredictorService"
]
