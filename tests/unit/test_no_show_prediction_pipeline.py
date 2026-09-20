"""
Unit and Integration Tests for Outpatient Appointment No-Show Prediction Pipeline.
Validates synthetic data generation, leakage-free preprocessing, feature engineering,
multi-model training (Logistic Regression, Random Forest, Gradient Boosting),
probability calibration, evaluation metrics, artifact serialization, and
operational triage inference with non-diagnostic disclaimers.
"""

import os
import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from ml.no_show_prediction.datasets.loader import (
    generate_synthetic_no_show_data,
    load_no_show_dataset,
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    DEPARTMENTS,
    WEEKDAYS
)
from ml.no_show_prediction.preprocessing.cleaner import (
    normalize_weekday,
    clean_no_show_data,
    FEATURE_ALIASES
)
from ml.no_show_prediction.preprocessing.feature_engineer import engineer_no_show_features
from ml.no_show_prediction.preprocessing.pipeline import (
    build_appointment_preprocessing_pipeline,
    extract_processed_feature_names
)
from ml.no_show_prediction.evaluation.metrics import compute_binary_classification_metrics
from ml.no_show_prediction.evaluation.evaluator import (
    evaluate_multiple_models,
    generate_model_comparison_report
)
from ml.no_show_prediction.training.trainer import AppointmentNoShowTrainer
from ml.no_show_prediction.models.model_registry import (
    save_no_show_model_artifacts,
    load_no_show_artifacts,
    NoShowModelCard,
    OPERATIONAL_DISCLAIMER
)
from ml.no_show_prediction.predictions.predictor import (
    NoShowPredictorService,
    NoShowPredictionResult
)


@pytest.fixture
def sample_no_show_df():
    """Generates a small synthetic appointment dataframe for rapid unit testing."""
    return generate_synthetic_no_show_data(n_samples=250, random_state=42, inject_missing=True)


# ===========================================================================
# 1. Dataset Generation & Loading Tests
# ===========================================================================

def test_synthetic_no_show_dataset_generation(sample_no_show_df):
    """Verifies synthetic dataset structure, features, target classes, and valid bounds."""
    df = sample_no_show_df
    assert len(df) == 250
    assert TARGET_COLUMN in df.columns
    for feat in FEATURE_COLUMNS:
        assert feat in df.columns

    # Target must be binary (0 or 1)
    target_values = set(df[TARGET_COLUMN].dropna().unique())
    assert target_values.issubset({0, 1})

    # Historical appointments and no-shows logic
    valid_records = df.dropna(subset=["previous_appointment_count", "previous_no_show_count"])
    assert (valid_records["previous_appointment_count"] >= 0).all()
    assert (valid_records["previous_no_show_count"] >= 0).all()
    assert (valid_records["previous_no_show_count"] <= valid_records["previous_appointment_count"]).all()


def test_load_no_show_dataset_fallback(tmp_path):
    """Verifies dataset loader correctly auto-generates data when CSV is missing."""
    temp_csv = tmp_path / "custom_no_show.csv"
    assert not temp_csv.exists()

    df = load_no_show_dataset(csv_path=temp_csv, auto_generate=True)
    assert temp_csv.exists()
    assert len(df) > 0
    assert TARGET_COLUMN in df.columns


# ===========================================================================
# 2. Data Cleaning & Normalization Tests
# ===========================================================================

def test_normalize_weekday():
    """Verifies weekday string standardizations and default fallbacks."""
    assert normalize_weekday("mon") == "Monday"
    assert normalize_weekday("MONDAY") == "Monday"
    assert normalize_weekday(" fri ") == "Friday"
    assert normalize_weekday("Saturday") == "Saturday"
    assert normalize_weekday(None) == "Monday"
    assert normalize_weekday("random_string") == "Monday"


def test_clean_no_show_data_and_leak_prevention(sample_no_show_df):
    """Verifies missing value imputation and leak-free train/test imputation stats."""
    train_df = sample_no_show_df.iloc[:200].copy()
    test_df = sample_no_show_df.iloc[200:].copy()

    # Clean training set: computes and returns learned stats
    cleaned_train, stats = clean_no_show_data(train_df, is_training=True)
    assert cleaned_train["appointment_lead_time"].isna().sum() == 0
    assert cleaned_train["previous_appointment_count"].isna().sum() == 0
    assert cleaned_train["department"].isna().sum() == 0
    assert len(stats) > 0

    # Clean test set: reuses learned training stats without looking at test distribution
    cleaned_test, stats_returned = clean_no_show_data(test_df, imputation_stats=stats, is_training=False)
    assert cleaned_test["appointment_lead_time"].isna().sum() == 0
    assert stats_returned == stats


def test_clean_no_show_data_aliases_and_bounds():
    """Verifies alias column renaming and logical invariant enforcement."""
    raw_df = pd.DataFrame([{
        "age": 42,
        "day_of_week": "wed",
        "lead_time_days": 14,
        "historical_appointments": 4,
        "historical_no_shows": 9,  # Invariant violation: 9 > 4
        "department": "Cardiology",
        "sms_reminder_sent": 1
    }])

    cleaned, _ = clean_no_show_data(raw_df, is_training=False)
    assert "patient_age" in cleaned.columns
    assert "appointment_weekday" in cleaned.columns
    assert cleaned["appointment_weekday"].iloc[0] == "Wednesday"
    assert "appointment_lead_time" in cleaned.columns
    assert cleaned["appointment_lead_time"].iloc[0] == 14
    # Invariant should be clamped: no_shows capped at appointments (4)
    assert cleaned["previous_no_show_count"].iloc[0] == 4


# ===========================================================================
# 3. Feature Engineering Tests
# ===========================================================================

def test_engineer_no_show_features():
    """Verifies engineered features: ratios, flags, buckets, and interaction terms."""
    df = pd.DataFrame([
        {
            "patient_age": 22,
            "appointment_weekday": "Monday",
            "appointment_lead_time": 10,
            "previous_appointment_count": 5,
            "previous_no_show_count": 2,
            "department": "General Medicine",
            "sms_reminder_sent": 0
        },
        {
            "patient_age": 70,
            "appointment_weekday": "Saturday",
            "appointment_lead_time": 0,
            "previous_appointment_count": 0,
            "previous_no_show_count": 0,
            "department": "Pediatrics",
            "sms_reminder_sent": 1
        }
    ])

    feat_df = engineer_no_show_features(df)

    # 1. Historical ratio
    assert feat_df["historical_no_show_ratio"].iloc[0] == 0.4
    assert feat_df["historical_no_show_ratio"].iloc[1] == 0.0  # safe division by zero

    # 2. Prior no-show flag
    assert feat_df["has_prior_no_show"].iloc[0] == 1
    assert feat_df["has_prior_no_show"].iloc[1] == 0

    # 3. Frequent patient flag
    assert feat_df["frequent_patient"].iloc[0] == 1
    assert feat_df["frequent_patient"].iloc[1] == 0

    # 4. Weekend indicator
    assert feat_df["is_weekend"].iloc[0] == 0
    assert feat_df["is_weekend"].iloc[1] == 1

    # 5. Lead time bucket
    assert feat_df["lead_time_bucket"].iloc[0] == "Long"
    assert feat_df["lead_time_bucket"].iloc[1] == "SameDay"

    # 6. Age cohorts
    assert feat_df["age_cohort"].iloc[0] == "YoungAdult"
    assert feat_df["age_cohort"].iloc[1] == "Senior"

    # 7. Unreminded long lead interaction
    assert feat_df["unreminded_long_lead"].iloc[0] == 1
    assert feat_df["unreminded_long_lead"].iloc[1] == 0


# ===========================================================================
# 4. Preprocessing Pipeline Tests
# ===========================================================================

def test_preprocessing_pipeline_fit_transform():
    """Verifies that Scikit-Learn ColumnTransformer processes numerical and categorical columns."""
    df = pd.DataFrame([
        {
            "patient_age": 28,
            "appointment_weekday": "Monday",
            "appointment_lead_time": 5,
            "previous_appointment_count": 2,
            "previous_no_show_count": 1,
            "department": "Cardiology",
            "sms_reminder_sent": 1
        },
        {
            "patient_age": 55,
            "appointment_weekday": "Friday",
            "appointment_lead_time": 12,
            "previous_appointment_count": 8,
            "previous_no_show_count": 0,
            "department": "Orthopedics",
            "sms_reminder_sent": 0
        }
    ])
    feat_df = engineer_no_show_features(df)
    pipeline = build_appointment_preprocessing_pipeline()

    transformed = pipeline.fit_transform(feat_df)
    assert transformed.shape[0] == 2
    assert transformed.shape[1] > 0
    assert not np.isnan(transformed).any()

    feature_names = extract_processed_feature_names(pipeline)
    assert len(feature_names) == transformed.shape[1]


# ===========================================================================
# 5. Evaluation Metrics Tests
# ===========================================================================

def test_compute_binary_classification_metrics():
    """Verifies accuracy, precision, recall, f1, roc_auc, and brier score calculation."""
    y_true = np.array([0, 0, 1, 1, 0, 1, 0, 0])
    y_pred = np.array([0, 0, 1, 0, 0, 1, 0, 1])
    y_prob = np.array([0.1, 0.2, 0.85, 0.4, 0.15, 0.9, 0.2, 0.65])

    res = compute_binary_classification_metrics(y_true, y_pred, y_prob, model_name="TestClassifier")

    assert 0.0 <= res.accuracy <= 1.0
    assert 0.0 <= res.roc_auc <= 1.0
    assert 0.0 <= res.brier_score <= 1.0
    assert res.f1_score >= 0.0
    assert len(res.confusion_matrix) == 2

    metrics_dict = res.to_dict()
    assert "accuracy" in metrics_dict
    assert "precision" in metrics_dict
    assert "recall" in metrics_dict
    assert "f1_score" in metrics_dict
    assert "roc_auc" in metrics_dict
    assert "brier_score" in metrics_dict


# ===========================================================================
# 6. Multi-Model Trainer & Calibrator Tests
# ===========================================================================

def test_appointment_no_show_trainer_execution(tmp_path):
    """Verifies complete training flow across Logistic Regression, Random Forest, and Gradient Boosting."""
    trainer = AppointmentNoShowTrainer(
        n_samples=200,
        random_state=42,
        models_dir=tmp_path
    )
    result = trainer.run_pipeline(save_artifacts=True)

    # Verify best model and artifacts
    assert result.best_model_name in ["Logistic Regression", "Random Forest", "Gradient Boosting"]
    assert result.best_metrics.roc_auc >= 0.50
    assert (tmp_path / "best_no_show_model.joblib").exists()
    assert (tmp_path / "preprocessor.joblib").exists()
    assert (tmp_path / "model_card.json").exists()

    # Verify all 3 models benchmarked
    assert len(result.evaluation_results) == 3
    evaluated_names = [r.model_name for r in result.evaluation_results]
    for name in ["Logistic Regression", "Random Forest", "Gradient Boosting"]:
        assert name in evaluated_names


# ===========================================================================
# 7. Model Serialization & Deserialization Tests
# ===========================================================================

def test_artifact_serialization_roundtrip(tmp_path):
    """Verifies that model artifacts serialize and deserialize with full fidelity."""
    trainer = AppointmentNoShowTrainer(n_samples=150, models_dir=tmp_path)
    train_res = trainer.run_pipeline(save_artifacts=True)

    loaded_pipeline, loaded_preprocessor, loaded_card = load_no_show_artifacts(tmp_path)
    assert loaded_pipeline is not None
    assert loaded_card is not None
    assert loaded_card.algorithm == train_res.best_model_name
    assert loaded_card.disclaimer == OPERATIONAL_DISCLAIMER


# ===========================================================================
# 8. Operational Inference Service Tests
# ===========================================================================

def test_no_show_predictor_service_high_risk(tmp_path):
    """Verifies that a high-friction profile triggers elevated risk tier and actionable guidance."""
    trainer = AppointmentNoShowTrainer(n_samples=250, models_dir=tmp_path)
    trainer.run_pipeline(save_artifacts=True)

    service = NoShowPredictorService(models_dir=tmp_path)

    high_risk_record = {
        "patient_age": 24,
        "appointment_weekday": "Monday",
        "appointment_lead_time": 25,
        "previous_appointment_count": 4,
        "previous_no_show_count": 3,
        "department": "Cardiology",
        "sms_reminder_sent": 0
    }

    pred: NoShowPredictionResult = service.predict_single(high_risk_record)
    assert 0.0 <= pred.no_show_probability <= 1.0
    assert pred.risk_tier in ["Low", "Medium", "High"]
    assert len(pred.risk_factors) >= 1
    assert "Extended Lead Time" in pred.risk_factors[0] or any("Lead Time" in f for f in pred.risk_factors)
    assert "Call patient directly" in pred.recommendation or "interactive SMS" in pred.recommendation or "Standard" in pred.recommendation
    assert pred.disclaimer == OPERATIONAL_DISCLAIMER


def test_no_show_predictor_service_low_risk(tmp_path):
    """Verifies that a same-day, reliable attender yields low no-show probability."""
    trainer = AppointmentNoShowTrainer(n_samples=250, models_dir=tmp_path)
    trainer.run_pipeline(save_artifacts=True)

    service = NoShowPredictorService(models_dir=tmp_path)

    low_risk_record = {
        "patient_age": 52,
        "appointment_weekday": "Wednesday",
        "appointment_lead_time": 0,
        "previous_appointment_count": 8,
        "previous_no_show_count": 0,
        "department": "General Medicine",
        "sms_reminder_sent": 1
    }

    pred: NoShowPredictionResult = service.predict_single(low_risk_record)
    assert 0.0 <= pred.no_show_probability <= 1.0
    assert pred.risk_tier in ["Low", "Medium"]
    assert "DISCLAIMER" in pred.disclaimer
