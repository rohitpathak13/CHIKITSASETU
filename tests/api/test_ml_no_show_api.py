"""
API Tests for the FastAPI Machine Learning Appointment No-Show Prediction endpoints:
- POST /api/v1/ml/no-show-prediction
- GET /api/v1/ml/no-show-prediction/model-card

Verifies Pydantic input validation, status codes, probability calculation,
triage recommendations, risk factors, and mandatory operational non-diagnostic disclaimers.
"""

import pytest


def test_ml_no_show_prediction_high_risk_success(fastapi_client):
    """Verifies successful prediction for an elevated no-show risk appointment profile."""
    payload = {
        "patient_age": 22,
        "appointment_weekday": "Monday",
        "appointment_lead_time": 21,
        "previous_appointment_count": 4,
        "previous_no_show_count": 3,
        "department": "Cardiology",
        "sms_reminder_sent": 0
    }

    res = fastapi_client.post("/api/v1/ml/no-show-prediction", json=payload)
    assert res.status_code == 200
    data = res.json()

    # Core response fields
    assert "no_show_probability" in data
    assert 0.0 <= data["no_show_probability"] <= 1.0
    assert "no_show_percentage" in data
    assert 0.0 <= data["no_show_percentage"] <= 100.0
    assert "no_show_prediction" in data
    assert isinstance(data["no_show_prediction"], bool)

    # Operational triage tier & guidance
    assert "risk_tier" in data
    assert data["risk_tier"] in ["Low", "Medium", "High"]
    assert "confidence" in data
    assert 0.0 <= data["confidence"] <= 1.0
    assert "recommendation" in data
    assert len(data["recommendation"]) > 0

    # Friction factors & model provenance
    assert "risk_factors" in data
    assert isinstance(data["risk_factors"], list)
    assert len(data["risk_factors"]) >= 1
    assert "model_version" in data
    assert "algorithm" in data

    # Strict operational non-diagnostic disclaimer
    assert data["is_medical_diagnosis"] is False
    assert "DISCLAIMER" in data["disclaimer"]
    assert "DOES NOT make clinical diagnoses" in data["disclaimer"]


def test_ml_no_show_prediction_low_risk_success(fastapi_client):
    """Verifies inference and probability distribution for a reliable same-day attender."""
    payload = {
        "patient_age": 55,
        "appointment_weekday": "Wednesday",
        "appointment_lead_time": 0,
        "previous_appointment_count": 8,
        "previous_no_show_count": 0,
        "department": "General Medicine",
        "sms_reminder_sent": 1
    }

    res = fastapi_client.post("/api/v1/ml/no-show-prediction", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["risk_tier"] in ["Low", "Medium"]
    assert data["no_show_probability"] < 0.50
    assert data["no_show_prediction"] is False
    assert data["is_medical_diagnosis"] is False


def test_ml_no_show_prediction_legacy_aliases(fastapi_client):
    """Verifies that requests using legacy or alternate parameter names resolve correctly."""
    payload = {
        "age": 34,
        "day_of_week": "Friday",
        "lead_time_days": 4,
        "historical_appointments": 3,
        "historical_no_shows": 1,
        "department": "Orthopedics",
        "sms_reminder_sent": 1
    }

    res = fastapi_client.post("/api/v1/ml/no-show-prediction", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert 0.0 <= data["no_show_probability"] <= 1.0
    assert data["risk_tier"] in ["Low", "Medium", "High"]
    assert data["is_medical_diagnosis"] is False


def test_ml_no_show_prediction_validation_errors(fastapi_client):
    """Verifies that Pydantic validation rejects physiologically or logically impossible values."""
    # 1. Negative age
    res_age = fastapi_client.post("/api/v1/ml/no-show-prediction", json={
        "patient_age": -10,
        "appointment_lead_time": 5
    })
    assert res_age.status_code == 422

    # 2. Out of bounds age (> 120)
    res_old = fastapi_client.post("/api/v1/ml/no-show-prediction", json={
        "patient_age": 145,
        "appointment_lead_time": 2
    })
    assert res_old.status_code == 422

    # 3. Negative lead time
    res_lead = fastapi_client.post("/api/v1/ml/no-show-prediction", json={
        "patient_age": 30,
        "appointment_lead_time": -5
    })
    assert res_lead.status_code == 422

    # 4. Out of bounds lead time (> 180)
    res_long_lead = fastapi_client.post("/api/v1/ml/no-show-prediction", json={
        "patient_age": 30,
        "appointment_lead_time": 250
    })
    assert res_long_lead.status_code == 422


def test_ml_no_show_model_card_endpoint(fastapi_client):
    """Verifies retrieval of training metadata, algorithm provenance, and evaluation metrics."""
    res = fastapi_client.get("/api/v1/ml/no-show-prediction/model-card")
    assert res.status_code == 200
    data = res.json()

    assert "model_name" in data
    assert "model_version" in data
    assert "algorithm" in data
    assert "training_sample_count" in data
    assert data["training_sample_count"] > 0
    assert "evaluation_metrics" in data
    assert "accuracy" in data["evaluation_metrics"]
    assert "roc_auc" in data["evaluation_metrics"]
    assert "disclaimer" in data
    assert "DOES NOT make clinical diagnoses" in data["disclaimer"]
