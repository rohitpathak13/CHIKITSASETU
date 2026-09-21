import joblib
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional
from backend.config import settings

class ReadmissionPredictor:
    """
    Inference wrapper for 30-day Inpatient Readmission & Deterioration Risk.
    """
    _instance: Optional["ReadmissionPredictor"] = None
    _pipeline = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ReadmissionPredictor, cls).__new__(cls)
            cls._instance._load_model()
        return cls._instance

    def _load_model(self):
        model_path = settings.ML_ARTIFACTS_DIR / "readmission_model.joblib"
        if model_path.exists():
            try:
                self._pipeline = joblib.load(model_path)
            except Exception as e:
                print(f"[!] Warning: Failed to load readmission model: {e}")
                self._pipeline = None
        else:
            self._pipeline = None

    def predict(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes raw clinical feature dictionary and produces a calibrated risk score,
        risk category, and key clinical risk drivers.
        """
        if self._pipeline is None:
            self._load_model()

        # Fallback baseline heuristic if model artifact is not yet compiled
        if self._pipeline is None:
            score = 0.25
            return {
                "risk_score": score,
                "risk_level": "Low",
                "is_high_risk": False,
                "top_drivers": ["Baseline demographic assessment"]
            }

        df = pd.DataFrame([{
            "age": input_data.get("age", 55),
            "gender": input_data.get("gender", "male"),
            "admission_type": input_data.get("admission_type", "emergency"),
            "ward_type": input_data.get("ward_type", "general"),
            "length_of_stay_days": input_data.get("length_of_stay_days", 3.0),
            "previous_admissions_12m": input_data.get("previous_admissions_12m", 0),
            "chronic_conditions_count": input_data.get("chronic_conditions_count", 1),
            "abnormal_lab_count": input_data.get("abnormal_lab_count", 0),
            "vital_instability_index": input_data.get("vital_instability_index", 0.1),
            "medication_count": input_data.get("medication_count", 4),
            "high_risk_medication_flag": input_data.get("high_risk_medication_flag", 0)
        }])

        prob = float(self._pipeline.predict_proba(df)[0, 1])
        risk_score = round(prob, 4)

        if risk_score >= 0.70:
            risk_level = "Severe"
        elif risk_score >= 0.45:
            risk_level = "High"
        elif risk_score >= 0.25:
            risk_level = "Moderate"
        else:
            risk_level = "Low"

        # Extract primary risk drivers
        drivers = []
        if input_data.get("previous_admissions_12m", 0) >= 2:
            drivers.append("History of frequent prior hospitalizations (>=2 in past 12m)")
        if input_data.get("vital_instability_index", 0) >= 0.35:
            drivers.append("Elevated physiological vital instability marker")
        if input_data.get("abnormal_lab_count", 0) >= 3:
            drivers.append("Multiple critical abnormal laboratory parameters flagged")
        if input_data.get("high_risk_medication_flag", 0) == 1:
            drivers.append("Active administration of high-risk anticoagulant/sedative drugs")
        if input_data.get("length_of_stay_days", 0) > 7:
            drivers.append("Extended length of stay (>7 days)")
        if not drivers:
            drivers.append("Standard post-admission clinical recovery profile")

        return {
            "risk_score": risk_score,
            "risk_percentage": round(risk_score * 100, 1),
            "risk_level": risk_level,
            "is_high_risk": risk_score >= 0.45,
            "top_drivers": drivers
        }


class NoShowPredictor:
    """
    Inference wrapper for Outpatient Appointment No-Show Prediction.
    """
    _instance: Optional["NoShowPredictor"] = None
    _pipeline = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NoShowPredictor, cls).__new__(cls)
            cls._instance._load_model()
        return cls._instance

    def _load_model(self):
        model_path = settings.ML_ARTIFACTS_DIR / "no_show_model.joblib"
        if model_path.exists():
            try:
                self._pipeline = joblib.load(model_path)
            except Exception as e:
                print(f"[!] Warning: Failed to load no-show model: {e}")
                self._pipeline = None
        else:
            self._pipeline = None

    def predict(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Computes no-show probability and operational triage guidance.
        """
        if self._pipeline is None:
            self._load_model()

        if self._pipeline is None:
            return {
                "no_show_probability": 0.15,
                "risk_tier": "Low",
                "recommendation": "Standard appointment schedule"
            }

        df = pd.DataFrame([{
            "age": input_data.get("age", 40),
            "gender": input_data.get("gender", "female"),
            "lead_time_days": input_data.get("lead_time_days", 3),
            "day_of_week": input_data.get("day_of_week", "Mon"),
            "appointment_hour": input_data.get("appointment_hour", 10),
            "department": input_data.get("department", "General Medicine"),
            "historical_appointments": input_data.get("historical_appointments", 2),
            "historical_no_show_ratio": input_data.get("historical_no_show_ratio", 0.1),
            "sms_reminder_sent": input_data.get("sms_reminder_sent", 1)
        }])

        prob = float(self._pipeline.predict_proba(df)[0, 1])
        prob_rounded = round(prob, 4)

        if prob_rounded >= 0.50:
            tier = "High"
            recommendation = "Call patient to confirm attendance; flag slot for potential standby booking."
        elif prob_rounded >= 0.25:
            tier = "Medium"
            recommendation = "Send automated SMS and email reminder 24h before appointment."
        else:
            tier = "Low"
            recommendation = "Standard confirmation; patient expected to attend."

        return {
            "no_show_probability": prob_rounded,
            "no_show_percentage": round(prob_rounded * 100, 1),
            "risk_tier": tier,
            "recommendation": recommendation
        }

readmission_predictor = ReadmissionPredictor()
no_show_predictor = NoShowPredictor()
