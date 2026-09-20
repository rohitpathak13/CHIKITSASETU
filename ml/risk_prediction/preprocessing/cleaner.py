"""
Data cleaning and missing-value imputation module for patient risk features.
Handles format variations in blood pressure, biological outlier clipping,
and statistical imputation without introducing future data leakage.
"""

import re
from typing import Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd

BP_PATTERN = re.compile(r"^(\d{2,3})\s*/\s*(\d{2,3})$")

# Physiological plausibility bounds
PHYSIOLOGICAL_BOUNDS = {
    "age": (18, 105),
    "bp_systolic": (65, 250),
    "bp_diastolic": (40, 150),
    "glucose": (45.0, 450.0),
    "bmi": (14.0, 65.0),
    "heart_rate": (40, 180),
}


def parse_blood_pressure(bp_val: Any) -> Tuple[float, float]:
    """
    Parses blood pressure string 'systolic/diastolic' into numerical pair.
    Returns (np.nan, np.nan) if unparseable.
    """
    if bp_val is None or pd.isna(bp_val):
        return np.nan, np.nan

    bp_str = str(bp_val).strip()
    match = BP_PATTERN.match(bp_str)
    if match:
        sys_val = float(match.group(1))
        dia_val = float(match.group(2))
        return sys_val, dia_val

    # Fallback if already numeric or separated by space/dash
    parts = re.split(r"[\s\-_/]+", bp_str)
    if len(parts) >= 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            pass

    return np.nan, np.nan


def clean_patient_risk_data(
    df: pd.DataFrame,
    imputation_stats: Optional[Dict[str, Any]] = None,
    is_training: bool = False
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Cleans raw patient dataframe:
    - Parses blood pressure into bp_systolic and bp_diastolic
    - Clips values to biological physiological bounds
    - Imputes missing numerical values with median and categoricals with mode/unknown
    - Returns cleaned copy and fitted imputation dictionary to prevent test leakage

    Parameters:
        df: Raw DataFrame containing patient features.
        imputation_stats: Learned medians/modes from training set (used during inference).
        is_training: If True, computes and returns fresh imputation statistics from df.

    Returns:
        Tuple of (cleaned_df, learned_imputation_stats)
    """
    cleaned = df.copy()

    # 1. Parse Blood Pressure if string column exists
    if "blood_pressure" in cleaned.columns:
        parsed = cleaned["blood_pressure"].apply(parse_blood_pressure)
        cleaned["bp_systolic"] = [p[0] for p in parsed]
        cleaned["bp_diastolic"] = [p[1] for p in parsed]
        cleaned = cleaned.drop(columns=["blood_pressure"])
    elif "bp_systolic" not in cleaned.columns:
        # Defaults if completely missing
        cleaned["bp_systolic"] = np.nan
        cleaned["bp_diastolic"] = np.nan

    # 2. Compute or load imputation statistics
    stats = {} if imputation_stats is None else dict(imputation_stats)

    numeric_cols = [
        "age", "bp_systolic", "bp_diastolic", "glucose", "bmi", "heart_rate",
        "family_history_diabetes", "family_history_hypertension", "family_history_heart_disease"
    ]
    categorical_cols = ["gender", "smoking_status"]

    if is_training or not stats:
        # Compute medians for numeric
        for col in numeric_cols:
            if col in cleaned.columns:
                val = cleaned[col].dropna()
                stats[col] = float(val.median()) if len(val) > 0 else 0.0
            else:
                stats[col] = 0.0

        # Compute modes for categoricals
        for col in categorical_cols:
            if col in cleaned.columns:
                val = cleaned[col].dropna()
                stats[col] = str(val.mode().iloc[0]) if len(val) > 0 else "unknown"
            else:
                stats[col] = "unknown"

    # 3. Apply Imputation
    for col in numeric_cols:
        if col in cleaned.columns:
            fill_val = stats.get(col, 0.0)
            cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce").fillna(fill_val)

    for col in categorical_cols:
        if col in cleaned.columns:
            fill_val = stats.get(col, "unknown")
            cleaned[col] = cleaned[col].fillna(fill_val).astype(str).str.strip().str.capitalize()
            # Standardize 'Other' / 'Unknown'
            cleaned[col] = cleaned[col].replace({"": "Unknown", "Nan": "Unknown"})

    # 4. Clip to physiological bounds to guard against extreme outliers
    for col, (b_low, b_high) in PHYSIOLOGICAL_BOUNDS.items():
        if col in cleaned.columns:
            cleaned[col] = np.clip(cleaned[col], b_low, b_high)

    # 5. Ensure valid physiological systolic/diastolic difference
    if "bp_systolic" in cleaned.columns and "bp_diastolic" in cleaned.columns:
        # If diastolic >= systolic, enforce minimal physiological pulse pressure of 15 mmHg
        invalid_mask = cleaned["bp_diastolic"] >= cleaned["bp_systolic"]
        if invalid_mask.any():
            cleaned.loc[invalid_mask, "bp_diastolic"] = cleaned.loc[invalid_mask, "bp_systolic"] - 20.0

    return cleaned, stats
