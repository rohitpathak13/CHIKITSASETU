"""Predictions module for Appointment No-Show Prediction."""
from ml.no_show_prediction.predictions.predictor import (
    NoShowPredictorService,
    NoShowPredictionResult
)

__all__ = [
    "NoShowPredictorService",
    "NoShowPredictionResult"
]
