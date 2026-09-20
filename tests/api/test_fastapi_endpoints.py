import pytest

def test_fastapi_root(fastapi_client):
    response = fastapi_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "version" in data

def test_fastapi_auth_success_and_failure(fastapi_client, admin_user):
    # Valid login
    res_success = fastapi_client.post("/api/v1/auth/login", json={
        "email": admin_user.email,
        "password": "Password123!"
    })
    assert res_success.status_code == 200
    token_data = res_success.json()
    assert "access_token" in token_data
    assert token_data["role"] == "admin"

    # Invalid login
    res_fail = fastapi_client.post("/api/v1/auth/login", json={
        "email": admin_user.email,
        "password": "WrongPassword!"
    })
    assert res_fail.status_code == 401

def test_fastapi_ml_readmission_prediction(fastapi_client):
    payload = {
        "age": 62,
        "gender": "male",
        "admission_type": "emergency",
        "ward_type": "icu",
        "length_of_stay_days": 5.0,
        "previous_admissions_12m": 2,
        "chronic_conditions_count": 2,
        "abnormal_lab_count": 3,
        "vital_instability_index": 0.35,
        "medication_count": 6,
        "high_risk_medication_flag": 1
    }
    response = fastapi_client.post("/api/v1/predict/readmission", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "risk_score" in data
    assert 0.0 <= data["risk_score"] <= 1.0
    assert data["risk_level"] in ("Low", "Moderate", "High", "Severe")
    assert isinstance(data["top_drivers"], list)

def test_fastapi_ml_no_show_prediction(fastapi_client):
    payload = {
        "age": 28,
        "gender": "female",
        "lead_time_days": 10,
        "day_of_week": "Mon",
        "appointment_hour": 14,
        "department": "Cardiology",
        "historical_appointments": 2,
        "historical_no_show_ratio": 0.20,
        "sms_reminder_sent": 1
    }
    response = fastapi_client.post("/api/v1/predict/no-show", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "no_show_probability" in data
    assert 0.0 <= data["no_show_probability"] <= 1.0
    assert data["risk_tier"] in ("Low", "Medium", "High")
    assert len(data["recommendation"]) > 0

def test_fastapi_ml_metadata(fastapi_client):
    response = fastapi_client.get("/api/v1/predict/metadata")
    assert response.status_code == 200
    meta = response.json()
    assert "readmission_model" in meta or "no_show_model" in meta

def test_fastapi_clinical_record_creation(fastapi_client, admin_auth_headers, db_session):
    from core.models import User, Patient, RoleEnum, GenderEnum
    from datetime import date

    user = User(
        email="fastapi_pat@chikitsasetu.ai",
        password_hash="hashed",
        role=RoleEnum.PATIENT,
        first_name="Fast",
        last_name="Patient"
    )
    db_session.add(user)
    db_session.flush()

    pat = Patient(
        id=user.id,
        dob=date(1995, 3, 10),
        gender=GenderEnum.FEMALE
    )
    db_session.add(pat)
    db_session.commit()

    payload = {
        "patient_id": user.id,
        "symptoms": "High fever, chills",
        "diagnosis": "Malaria Plasmodium vivax",
        "vitals_bp": "110/70",
        "vitals_pulse": 82,
        "vitals_temp": 39.1,
        "vitals_spo2": 98,
        "vitals_weight": 58.0,
        "vitals_height": 165.0,
        "vitals_respiratory_rate": 18,
        "allergies": "Chloroquine",
        "treatment_plan": "Artemether-lumefantrine combination therapy, bed rest, hydration",
        "follow_up_date": "2026-10-01"
    }

    resp = fastapi_client.post("/api/v1/clinical/records", json=payload, headers=admin_auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["diagnosis"] == "Malaria Plasmodium vivax"
    assert data["treatment_plan"] == "Artemether-lumefantrine combination therapy, bed rest, hydration"
    assert data["allergies"] == "Chloroquine"
    assert data["vitals_bp"] == "110/70"
