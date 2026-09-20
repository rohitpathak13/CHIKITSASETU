"""
Operational Inference Service for Appointment No-Show Prediction.
Loads calibrated serialized model pipeline, transforms scheduling records,
and computes attendance probabilities, operational risk tiers, and reminder guidance.

DISCLAIMER: This system is strictly an operational scheduling decision-support tool.
It does NOT make clinical medical diagnoses or health claims.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import pandas as pd
import numpy as np

from ml.no_show_prediction.models.model_registry import (
    load_no_show_artifacts,
    OPERATIONAL_DISCLAIMER,
    SAVED_MODELS_DIR
)
from ml.no_show_prediction.preprocessing.cleaner import clean_no_show_data
from ml.no_show_prediction.preprocessing.feature_engineer import engineer_no_show_features


@dataclass
class NoShowPredictionResult:
    no_show_probability: float
    no_show_prediction: bool
    risk_tier: str
    confidence: float
    recommendation: str
    risk_factors: List[str]
    model_version: str
    algorithm: str
    disclaimer: str = OPERATIONAL_DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NoShowPredictorService:
    """
    Production inference engine for outpatient appointment attendance risk scoring.
    """

    def __init__(self, models_dir: Optional[Path] = None):
        self.models_dir = models_dir or SAVED_MODELS_DIR
        self.pipeline = None
        self.preprocessor = None
        self.model_card = None
        self._load_artifacts()

    def _load_artifacts(self):
        self.pipeline, self.preprocessor, self.model_card = load_no_show_artifacts(self.models_dir)

    def _extract_risk_drivers(self, row: pd.Series) -> List[str]:
        """Identifies primary scheduling and historical friction points."""
        drivers = []

        if "appointment_lead_time" in row and row["appointment_lead_time"] >= 14:
            drivers.append(f"Extended Lead Time ({row['appointment_lead_time']:.0f} days)")
        elif "appointment_lead_time" in row and row["appointment_lead_time"] >= 7:
            drivers.append(f"Moderate Lead Time ({row['appointment_lead_time']:.0f} days)")

        if "previous_no_show_count" in row and row["previous_no_show_count"] >= 2:
            drivers.append(f"Multiple Historical No-Shows ({row['previous_no_show_count']:.0f} missed)")
        elif "previous_no_show_count" in row and row["previous_no_show_count"] == 1:
            drivers.append("Single Prior Missed Appointment")

        if "sms_reminder_sent" in row and row["sms_reminder_sent"] == 0:
            drivers.append("No Pre-Appointment SMS Reminder Sent")

        if "appointment_weekday" in row and row["appointment_weekday"] in ("Monday", "Saturday"):
            drivers.append(f"High-Friction Day of Week ({row['appointment_weekday']})")

        if "patient_age" in row and 18 <= row["patient_age"] <= 30:
            drivers.append("Demographic Attendance Cohort (Young Adult 18-30)")

        if not drivers:
            drivers.append("Low scheduling friction; reliable historical attendance pattern")

        return drivers

    def predict_single(self, appointment_data: Dict[str, Any]) -> NoShowPredictionResult:
        """
        Computes no-show probability and operational recommendations for an individual booking.
        """
        df_single = pd.DataFrame([appointment_data])
        results = self.predict_batch(df_single)
        return results[0]

    def predict_batch(self, df: pd.DataFrame) -> List[NoShowPredictionResult]:
        """
        Performs batch inference over multiple appointment records.
        """
        if self.pipeline is None:
            self._load_artifacts()

        # Clean using saved training imputation defaults
        defaults = self.model_card.imputation_defaults if self.model_card else {}
        cleaned_df, _ = clean_no_show_data(
            df,
            imputation_stats=defaults,
            is_training=False
        )

        # Feature engineering
        feat_df = engineer_no_show_features(cleaned_df)

        # Calibrated predict_proba (column 1 is probability of no-show)
        probas = self.pipeline.predict_proba(feat_df)[:, 1]

        results = []
        for i in range(len(feat_df)):
            p = round(float(probas[i]), 4)
            is_no_show = bool(p >= 0.50)

            if p >= 0.50:
                tier = "High"
                rec = "Call patient directly to confirm attendance; flag slot for potential standby overbooking."
            elif p >= 0.25:
                tier = "Medium"
                rec = "Send automated interactive SMS reminder 24-48 hours before slot."
            else:
                tier = "Low"
                rec = "Standard confirmation; patient expected to attend."

            drivers = self._extract_risk_drivers(feat_df.iloc[i])
            conf = round(float(max(p, 1.0 - p)), 4)

            res = NoShowPredictionResult(
                no_show_probability=p,
                no_show_prediction=is_no_show,
                risk_tier=tier,
                confidence=conf,
                recommendation=rec,
                risk_factors=drivers,
                model_version=self.model_card.model_version if self.model_card else "1.0.0",
                algorithm=self.model_card.algorithm if self.model_card else "Unknown",
                disclaimer=OPERATIONAL_DISCLAIMER
            )
            results.append(res)

        return results
