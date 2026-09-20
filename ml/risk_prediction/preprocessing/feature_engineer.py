"""
Feature Engineering module for Patient Risk Prediction.
Derives clinically recognized cardiovascular, metabolic, and physiological indicators.
"""

import numpy as np
import pandas as pd


def engineer_patient_risk_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes domain-specific physiological and metabolic features:
    - Pulse Pressure (PP = SBP - DBP)
    - Mean Arterial Pressure (MAP = DBP + 1/3 * PP)
    - BMI clinical category ('Underweight', 'Normal', 'Overweight', 'Obese')
    - Fasting Glucose category ('Normal', 'Impaired', 'Diabetic_Range')
    - AHA/ACC Hypertension stage classification
    - Composite Metabolic Risk Index

    Parameters:
        df: Cleaned patient DataFrame with numerical vitals.

    Returns:
        pd.DataFrame enriched with derived engineered features.
    """
    feat_df = df.copy()

    # 1. Hemodynamic Indicators
    if "bp_systolic" in feat_df.columns and "bp_diastolic" in feat_df.columns:
        sys = feat_df["bp_systolic"]
        dia = feat_df["bp_diastolic"]
        
        # Pulse Pressure: Indicator of vascular stiffness
        feat_df["pulse_pressure"] = (sys - dia).round(1)
        
        # Mean Arterial Pressure (MAP): Organ perfusion pressure
        feat_df["mean_arterial_pressure"] = (dia + (1.0 / 3.0) * feat_df["pulse_pressure"]).round(1)

        # Hypertension Staging (ACC/AHA Guidelines)
        ht_stages = []
        for s, d in zip(sys, dia):
            if s < 120 and d < 80:
                ht_stages.append("Normal")
            elif 120 <= s < 130 and d < 80:
                ht_stages.append("Elevated")
            elif (130 <= s < 140) or (80 <= d < 90):
                ht_stages.append("Stage_1")
            else:
                ht_stages.append("Stage_2")
        feat_df["hypertension_stage"] = ht_stages

    # 2. BMI Clinical Bins
    if "bmi" in feat_df.columns:
        bmi = feat_df["bmi"]
        bmi_bins = []
        for b in bmi:
            if b < 18.5:
                bmi_bins.append("Underweight")
            elif b < 25.0:
                bmi_bins.append("Normal")
            elif b < 30.0:
                bmi_bins.append("Overweight")
            else:
                bmi_bins.append("Obese")
        feat_df["bmi_category"] = bmi_bins

    # 3. Glycemic Categories (ADA Fasting Plasma Glucose criteria)
    if "glucose" in feat_df.columns:
        glu = feat_df["glucose"]
        glu_bins = []
        for g in glu:
            if g < 100.0:
                glu_bins.append("Normal")
            elif g < 126.0:
                glu_bins.append("Impaired")
            else:
                glu_bins.append("Diabetic_Range")
        feat_df["glucose_category"] = glu_bins

    # 4. Composite Metabolic Risk Score (Count of high-risk flags)
    risk_flags = np.zeros(len(feat_df), dtype=int)
    
    if "glucose" in feat_df.columns:
        risk_flags += (feat_df["glucose"] >= 100.0).astype(int)
    if "bmi" in feat_df.columns:
        risk_flags += (feat_df["bmi"] >= 25.0).astype(int)
    if "mean_arterial_pressure" in feat_df.columns:
        risk_flags += (feat_df["mean_arterial_pressure"] >= 100.0).astype(int)
    if "smoking_status" in feat_df.columns:
        risk_flags += (feat_df["smoking_status"].str.lower() == "current").astype(int)
    if "family_history_heart_disease" in feat_df.columns:
        risk_flags += (feat_df["family_history_heart_disease"] == 1).astype(int)
    if "family_history_diabetes" in feat_df.columns:
        risk_flags += (feat_df["family_history_diabetes"] == 1).astype(int)

    feat_df["metabolic_risk_score"] = risk_flags

    return feat_df
