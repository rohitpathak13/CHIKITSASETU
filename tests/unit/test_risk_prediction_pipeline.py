"""
Unit and Integration Tests for Patient Risk Prediction Machine Learning Pipeline.
Tests data generation, cleaning, feature engineering, leak-free pipeline,
multi-model training (Logistic Regression, Random Forest, Gradient Boosting),
evaluation metrics, artifact serialization, and inference with medical disclaimer.
"""

import os
import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from ml.risk_prediction.datasets.loader import (
    generate_synthetic_patient_risk_data,
    load_patient_risk_dataset,
    FEATURE_COLUMNS,
    TARGET_COLUMN
)
from ml.risk_prediction.preprocessing.cleaner import (
    parse_blood_pressure,
    clean_patient_risk_data
)
from ml.risk_prediction.preprocessing.feature_engineer import engineer_patient_risk_features
from ml.risk_prediction.preprocessing.pipeline import (
    build_preprocessing_pipeline,
    extract_processed_feature_names
)
from ml.risk_prediction.evaluation.metrics import compute_multiclass_metrics
from ml.risk_prediction.training.trainer import RiskModelTrainer
from ml.risk_prediction.models.model_registry import (
    load_model_artifacts,
    MEDICAL_DISCLAIMER
)
from ml.risk_prediction.predictions.predictor import (
    PatientRiskPredictor,
    PatientRiskPredictionResult
)


@pytest.fixture
def sample_raw_df():
    """Generates a small synthetic patient risk dataframe for fast testing."""
    return generate_synthetic_patient_risk_data(n_samples=250, random_state=42, inject_missing=True)


# ===========================================================================
# 1. Dataset Generation & Loading Tests
# ===========================================================================

def test_synthetic_dataset_generation(sample_raw_df):
    """Verifies synthetic dataset structure, features, target classes, and safe ranges."""
    df = sample_raw_df
    assert len(df) == 250
    assert TARGET_COLUMN in df.columns
    for feat in FEATURE_COLUMNS:
        assert feat in df.columns

    # Verify target distribution has all 3 classes
    targets = set(df[TARGET_COLUMN].unique())
    assert targets == {"Low", "Medium", "High"}

    # Verify realistic biological bounds
    valid_ages = df["age"].dropna()
    assert (valid_ages >= 18).all() and (valid_ages <= 86).all()


# ===========================================================================
# 2. Data Cleaning & BP Parsing Tests
# ===========================================================================

def test_bp_parsing():
    """Verifies parsing of standard and irregular blood pressure string representations."""
    assert parse_blood_pressure("120/80") == (120.0, 80.0)
    assert parse_blood_pressure(" 140 / 90 ") == (140.0, 90.0)
    assert parse_blood_pressure("130-85") == (130.0, 85.0)
    
    # Missing / Malformed
    sys, dia = parse_blood_pressure(None)
    assert np.isnan(sys) and np.isnan(dia)
    sys2, dia2 = parse_blood_pressure("invalid_bp")
    assert np.isnan(sys2) and np.isnan(dia2)


def test_clean_patient_risk_data_and_leak_prevention(sample_raw_df):
    """Verifies missing value imputation and leak-free train/test imputation stats."""
    # Split into mock train and test
    train_df = sample_raw_df.iloc[:200].copy()
    test_df = sample_raw_df.iloc[200:].copy()

    # Clean train: learns stats
    cleaned_train, stats = clean_patient_risk_data(train_df, is_training=True)
    assert "bp_systolic" in cleaned_train.columns
    assert "bp_diastolic" in cleaned_train.columns
    assert "blood_pressure" not in cleaned_train.columns
    assert cleaned_train["glucose"].isna().sum() == 0
    assert cleaned_train["bmi"].isna().sum() == 0
    assert len(stats) > 0

    # Clean test using learned training stats (prevents data leakage)
    cleaned_test, _ = clean_patient_risk_data(test_df, imputation_stats=stats, is_training=False)
    assert cleaned_test["glucose"].isna().sum() == 0
    assert cleaned_test["bmi"].isna().sum() == 0


# ===========================================================================
# 3. Feature Engineering Tests
# ===========================================================================

def test_feature_engineering():
    """Verifies derived physiological features: MAP, pulse pressure, BMI/glucose categories."""
    mock_cleaned = pd.DataFrame([{
        "age": 55,
        "gender": "Male",
        "bp_systolic": 140.0,
        "bp_diastolic": 90.0,
        "glucose": 135.0,
        "bmi": 32.0,
        "heart_rate": 78,
        "smoking_status": "Current",
        "family_history_diabetes": 1,
        "family_history_hypertension": 1,
        "family_history_heart_disease": 0
    }])

    feat_df = engineer_patient_risk_features(mock_cleaned)
    assert "pulse_pressure" in feat_df.columns
    assert feat_df["pulse_pressure"].iloc[0] == 50.0  # 140 - 90
    
    # MAP = 90 + 1/3 * 50 = ~106.7
    assert 106.0 <= feat_df["mean_arterial_pressure"].iloc[0] <= 107.0
    assert feat_df["bmi_category"].iloc[0] == "Obese"
    assert feat_df["glucose_category"].iloc[0] == "Diabetic_Range"
    assert feat_df["hypertension_stage"].iloc[0] == "Stage_2"
    assert feat_df["metabolic_risk_score"].iloc[0] >= 3


# ===========================================================================
# 4. Evaluation Metrics Tests
# ===========================================================================

def test_metrics_computation():
    """Verifies multiclass Accuracy, Precision, Recall, F1, and ROC-AUC calculation."""
    y_true = np.array(["Low", "Medium", "High", "Low", "High"])
    y_pred = np.array(["Low", "Medium", "High", "Medium", "High"])
    
    # Mock probabilities for 3 classes
    y_proba = np.array([
        [0.8, 0.1, 0.1],
        [0.1, 0.8, 0.1],
        [0.1, 0.2, 0.7],
        [0.3, 0.5, 0.2],
        [0.1, 0.1, 0.8]
    ])
    
    res = compute_multiclass_metrics(
        y_true=y_true,
        y_pred=y_pred,
        y_proba=y_proba,
        labels=["Low", "Medium", "High"],
        model_name="TestModel"
    )

    assert res.accuracy == 0.8  # 4/5 correct
    assert res.precision_macro > 0.0
    assert res.recall_macro > 0.0
    assert res.f1_macro > 0.0
    assert res.roc_auc_ovr_macro is not None
    assert len(res.confusion_matrix) == 3


# ===========================================================================
# 5. Model Training & Comparison Tests
# ===========================================================================

def test_model_training_and_comparison(sample_raw_df, tmp_path):
    """Verifies training of Logistic Regression, Random Forest, and Gradient Boosting."""
    trainer = RiskModelTrainer(test_size=0.25, random_state=42, artifacts_dir=tmp_path)
    best_pipeline, results = trainer.run_training_pipeline(df=sample_raw_df, save_best=True)

    assert best_pipeline is not None
    assert len(results) == 3
    
    model_names = {r.model_name for r in results}
    assert "Logistic Regression" in model_names
    assert "Random Forest" in model_names
    assert "Gradient Boosting" in model_names

    for r in results:
        assert 0.0 <= r.accuracy <= 1.0
        assert 0.0 <= r.f1_weighted <= 1.0
        assert r.roc_auc_ovr_macro is not None

    # Verify artifacts were saved
    assert (tmp_path / "best_risk_model.joblib").exists()
    assert (tmp_path / "preprocessor.joblib").exists()
    assert (tmp_path / "model_card.json").exists()


# ===========================================================================
# 6. Prediction Engine & Medical Disclaimer Tests
# ===========================================================================

def test_patient_risk_predictor_inference_and_disclaimer(sample_raw_df, tmp_path):
    """Verifies inference output format, probability calibration, and mandatory disclaimer."""
    trainer = RiskModelTrainer(test_size=0.25, random_state=42, artifacts_dir=tmp_path)
    trainer.run_training_pipeline(df=sample_raw_df, save_best=True)

    predictor = PatientRiskPredictor(models_dir=tmp_path)

    # 1. High Risk Candidate Patient
    high_risk_patient = {
        "age": 68,
        "gender": "Male",
        "blood_pressure": "165/102",
        "glucose": 185.0,
        "bmi": 36.0,
        "heart_rate": 92,
        "smoking_status": "current",
        "family_history_diabetes": 1,
        "family_history_hypertension": 1,
        "family_history_heart_disease": 1
    }
    res_high = predictor.predict_single(high_risk_patient)
    assert isinstance(res_high, PatientRiskPredictionResult)
    assert res_high.risk_category in ["Low", "Medium", "High"]
    assert len(res_high.probabilities) == 3
    # Probabilities sum to 1.0
    prob_sum = sum(res_high.probabilities.values())
    assert abs(prob_sum - 1.0) < 0.05
    assert len(res_high.risk_factors) >= 1
    # Check explicit medical disclaimer
    assert "DISCLAIMER" in res_high.disclaimer
    assert "DOES NOT provide medical diagnosis" in res_high.disclaimer

    # 2. Healthy Candidate Patient
    healthy_patient = {
        "age": 24,
        "gender": "Female",
        "blood_pressure": "112/72",
        "glucose": 82.0,
        "bmi": 21.0,
        "heart_rate": 62,
        "smoking_status": "never",
        "family_history_diabetes": 0,
        "family_history_hypertension": 0,
        "family_history_heart_disease": 0
    }
    res_healthy = predictor.predict_single(healthy_patient)
    assert res_healthy.risk_category in ["Low", "Medium", "High"]
    assert res_healthy.probabilities["Low"] > res_healthy.probabilities["High"]
