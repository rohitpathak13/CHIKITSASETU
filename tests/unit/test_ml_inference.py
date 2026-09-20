import pytest
from ml.inference.predictors import readmission_predictor, no_show_predictor

def test_readmission_predictor_normal_input():
    features = {
        "age": 68,
        "gender": "male",
        "admission_type": "emergency",
        "ward_type": "icu",
        "length_of_stay_days": 6.5,
        "previous_admissions_12m": 3,
        "chronic_conditions_count": 3,
        "abnormal_lab_count": 4,
        "vital_instability_index": 0.45,
        "medication_count": 8,
        "high_risk_medication_flag": 1
    }
    result = readmission_predictor.predict(features)

    assert "risk_score" in result
    assert 0.0 <= result["risk_score"] <= 1.0
    assert result["risk_level"] in ("Low", "Moderate", "High", "Severe")
    assert isinstance(result["top_drivers"], list)
    assert len(result["top_drivers"]) > 0

def test_readmission_predictor_fallback_and_edge_cases():
    # Empty input dictionary
    result = readmission_predictor.predict({})
    assert 0.0 <= result["risk_score"] <= 1.0
    assert result["risk_level"] in ("Low", "Moderate", "High", "Severe")

def test_no_show_predictor():
    features = {
        "age": 35,
        "gender": "female",
        "lead_time_days": 14,
        "day_of_week": "Mon",
        "appointment_hour": 16,
        "department": "General Medicine",
        "historical_appointments": 4,
        "historical_no_show_ratio": 0.50,
        "sms_reminder_sent": 0
    }
    result = no_show_predictor.predict(features)

    assert "no_show_probability" in result
    assert 0.0 <= result["no_show_probability"] <= 1.0
    assert result["risk_tier"] in ("Low", "Medium", "High")
    assert len(result["recommendation"]) > 0
