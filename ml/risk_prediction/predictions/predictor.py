"""
Patient Risk Inference Engine.
Loads trained serialized model artifacts, validates input records,
transforms features, and computes risk category classifications
with confidence distributions and prominent educational disclaimers.

DISCLAIMER: This system provides purely statistical risk stratification for
demonstration purposes. It does NOT make clinical diagnoses or replace medical professionals.
"""

from typing import Dict, Any, List, Union, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import pandas as pd
import numpy as np

from ml.risk_prediction.models.model_registry import (
    load_model_artifacts,
    MEDICAL_DISCLAIMER,
    SAVED_MODELS_DIR
)
from ml.risk_prediction.preprocessing.cleaner import clean_patient_risk_data
from ml.risk_prediction.preprocessing.feature_engineer import engineer_patient_risk_features


@dataclass
class PatientRiskPredictionResult:
    risk_category: str
    confidence: float
    probabilities: Dict[str, float]
    risk_factors: List[str]
    model_version: str
    algorithm: str
    disclaimer: str = MEDICAL_DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PatientRiskPredictor:
    """
    Production-ready inference wrapper for patient risk categorization.
    """

    def __init__(self, models_dir: Optional[Path] = None):
        self.models_dir = models_dir or SAVED_MODELS_DIR
        self.pipeline = None
        self.preprocessor = None
        self.model_card = None
        self._load_artifacts()

    def _load_artifacts(self):
        self.pipeline, self.preprocessor, self.model_card = load_model_artifacts(self.models_dir)

    def _extract_risk_factors(self, row: pd.Series) -> List[str]:
        """Identifies specific physiological and behavioral flags contributing to elevated risk."""
        factors = []
        
        # Blood pressure
        if "bp_systolic" in row and row["bp_systolic"] >= 140:
            factors.append(f"Systolic Hypertension ({row['bp_systolic']:.0f} mmHg)")
        elif "bp_systolic" in row and row["bp_systolic"] >= 130:
            factors.append(f"Elevated Systolic Pressure ({row['bp_systolic']:.0f} mmHg)")

        if "bp_diastolic" in row and row["bp_diastolic"] >= 90:
            factors.append(f"Diastolic Hypertension ({row['bp_diastolic']:.0f} mmHg)")

        # Glucose
        if "glucose" in row and row["glucose"] >= 126.0:
            factors.append(f"Diabetic-range Fasting Glucose ({row['glucose']:.1f} mg/dL)")
        elif "glucose" in row and row["glucose"] >= 100.0:
            factors.append(f"Impaired Fasting Glucose ({row['glucose']:.1f} mg/dL)")

        # BMI
        if "bmi" in row and row["bmi"] >= 30.0:
            factors.append(f"Clinical Obesity (BMI {row['bmi']:.1f})")
        elif "bmi" in row and row["bmi"] >= 25.0:
            factors.append(f"Overweight Category (BMI {row['bmi']:.1f})")

        # Smoking
        if "smoking_status" in row and str(row["smoking_status"]).lower() == "current":
            factors.append("Active Tobacco Smoking")

        # Family history
        if "family_history_heart_disease" in row and row["family_history_heart_disease"] == 1:
            factors.append("Family History of Cardiovascular Disease")
        if "family_history_diabetes" in row and row["family_history_diabetes"] == 1:
            factors.append("Family History of Diabetes")

        if not factors:
            factors.append("No high-risk physiological or behavioral factors flagged")

        return factors

    def predict_single(self, patient_data: Dict[str, Any]) -> PatientRiskPredictionResult:
        """
        Generates risk prediction for an individual patient record.

        Parameters:
            patient_data: Dict containing features like 'age', 'blood_pressure', 'glucose', 'bmi', etc.

        Returns:
            PatientRiskPredictionResult with risk_category, confidence, probabilities, and disclaimer.
        """
        df_single = pd.DataFrame([patient_data])
        results = self.predict_batch(df_single)
        return results[0]

    def predict_batch(self, df: pd.DataFrame) -> List[PatientRiskPredictionResult]:
        """
        Performs batch prediction over multiple patient records.

        Parameters:
            df: DataFrame containing patient features.

        Returns:
            List of PatientRiskPredictionResult objects.
        """
        if self.pipeline is None:
            self._load_artifacts()

        # Clean using saved training imputation stats
        imputation_defaults = self.model_card.imputation_defaults if self.model_card else {}
        cleaned_df, _ = clean_patient_risk_data(
            df,
            imputation_stats=imputation_defaults,
            is_training=False
        )

        # Feature engineering
        feat_df = engineer_patient_risk_features(cleaned_df)

        # Predict classes and probabilities
        preds = self.pipeline.predict(feat_df)
        
        classes = list(self.pipeline.classes_)
        probas = None
        if hasattr(self.pipeline, "predict_proba"):
            try:
                probas = self.pipeline.predict_proba(feat_df)
            except Exception:
                probas = None

        results = []
        for i in range(len(feat_df)):
            cat = str(preds[i])
            
            prob_dict = {}
            confidence = 1.0
            if probas is not None:
                prob_row = probas[i]
                for c_idx, c_name in enumerate(classes):
                    prob_dict[str(c_name)] = round(float(prob_row[c_idx]), 4)
                confidence = round(float(np.max(prob_row)), 4)
            else:
                prob_dict = {cat: 1.0}

            factors = self._extract_risk_factors(feat_df.iloc[i])

            res = PatientRiskPredictionResult(
                risk_category=cat,
                confidence=confidence,
                probabilities=prob_dict,
                risk_factors=factors,
                model_version=self.model_card.model_version if self.model_card else "1.0.0",
                algorithm=self.model_card.algorithm if self.model_card else "Unknown",
                disclaimer=MEDICAL_DISCLAIMER
            )
            results.append(res)

        return results
