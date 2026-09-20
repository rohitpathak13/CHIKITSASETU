"""
API Tests for the FastAPI Machine Learning Patient Risk Prediction endpoint:
POST /api/v1/ml/risk-prediction
Verifies Pydantic input validation, status codes, probability calibration,
error handling, and mandatory non-diagnostic medical disclaimer.
"""

import pytest


def test_ml_risk_prediction_high_risk_success(fastapi_client):
    """Verifies successful prediction for an elevated-risk patient profile."""
    payload = {
        "age": 68,
        "gender": "Male",
        "blood_pressure": "162/100",
        "glucose": 178.0,
        "bmi": 34.2,
        "heart_rate": 88,
        "smoking_status": "current",
        "family_history_diabetes": 1,
        "family_history_hypertension": 1,
        "family_history_heart_disease": 1
    }

    res = fastapi_client.post("/api/v1/ml/risk-prediction", json=payload)
    assert res.status_code == 200
    data = res.json()

    # Core required fields
    assert "risk_category" in data
    assert data["risk_category"] in ["Low", "Medium", "High"]
    assert "confidence" in data
    assert 0.0 <= data["confidence"] <= 1.0

    # Probabilities distribution
    assert "probabilities" in data
    probs = data["probabilities"]
    assert len(probs) == 3
    prob_sum = sum(probs.values())
    assert abs(prob_sum - 1.0) < 0.05

    # Model provenance
    assert "model_version" in data
    assert "algorithm" in data
    assert len(data["risk_factors"]) >= 1

    # Explicit Non-Diagnostic Medical Disclaimer
    assert data["is_medical_diagnosis"] is False
    assert "DISCLAIMER" in data["disclaimer"]
    assert "DOES NOT provide medical diagnosis" in data["disclaimer"]


def test_ml_risk_prediction_low_risk_profile(fastapi_client):
    """Verifies inference and probability distribution for a low-risk healthy profile."""
    payload = {
        "age": 25,
        "gender": "Female",
        "blood_pressure": "110/70",
        "glucose": 84.0,
        "bmi": 21.2,
        "heart_rate": 64,
        "smoking_status": "never",
        "family_history_diabetes": 0,
        "family_history_hypertension": 0,
        "family_history_heart_disease": 0
    }

    res = fastapi_client.post("/api/v1/ml/risk-prediction", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["risk_category"] == "Low"
    assert data["probabilities"]["Low"] > data["probabilities"]["High"]
    assert data["is_medical_diagnosis"] is False


def test_ml_risk_prediction_input_validation_errors(fastapi_client):
    """Verifies that Pydantic properly catches invalid inputs with 422 Unprocessable Entity."""
    # 1. Negative age
    res_age = fastapi_client.post("/api/v1/ml/risk-prediction", json={
        "age": -10,
        "glucose": 95.0,
        "bmi": 22.0
    })
    assert res_age.status_code == 422

    # 2. Impossible glucose value
    res_glu = fastapi_client.post("/api/v1/ml/risk-prediction", json={
        "age": 45,
        "glucose": -5.0,
        "bmi": 24.0
    })
    assert res_glu.status_code == 422

    # 3. Impossible BMI value
    res_bmi = fastapi_client.post("/api/v1/ml/risk-prediction", json={
        "age": 45,
        "glucose": 90.0,
        "bmi": 120.0
    })
    assert res_bmi.status_code == 422

    # 4. Missing required field (bmi)
    res_missing = fastapi_client.post("/api/v1/ml/risk-prediction", json={
        "age": 40,
        "glucose": 90.0
    })
    assert res_missing.status_code == 422


def test_ml_risk_prediction_safe_handling_of_unusual_formats(fastapi_client):
    """Verifies that the cleaner/pipeline gracefully handles non-standard BP formats."""
    payload = {
        "age": 50,
        "gender": "UnknownGender",
        "blood_pressure": "135 - 85",
        "glucose": 110.0,
        "bmi": 26.5,
        "smoking_status": "irregular_string"
    }

    res = fastapi_client.post("/api/v1/ml/risk-prediction", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["risk_category"] in ["Low", "Medium", "High"]


def test_ml_risk_model_card_endpoint(fastapi_client):
    """Verifies retrieval of model card metadata and performance metrics."""
    res = fastapi_client.get("/api/v1/ml/risk-prediction/model-card")
    assert res.status_code == 200
    card = res.json()

    assert "model_name" in card
    assert "algorithm" in card
    assert "evaluation_metrics" in card
    assert "disclaimer" in card
    assert "DOES NOT provide medical diagnosis" in card["disclaimer"]
