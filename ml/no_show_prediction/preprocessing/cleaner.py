"""
Data Cleaning and Imputation module for Appointment No-Show Prediction.
Normalizes heterogeneous weekday representations, department names,
imputes missing variables, and checks logical constraints without data leakage.
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd

WEEKDAY_MAP = {
    "mon": "Monday",
    "monday": "Monday",
    "tue": "Tuesday",
    "tues": "Tuesday",
    "tuesday": "Tuesday",
    "wed": "Wednesday",
    "wednesday": "Wednesday",
    "thu": "Thursday",
    "thur": "Thursday",
    "thurs": "Thursday",
    "thursday": "Thursday",
    "fri": "Friday",
    "friday": "Friday",
    "sat": "Saturday",
    "saturday": "Saturday",
    "sun": "Sunday",
    "sunday": "Sunday"
}

FEATURE_ALIASES = {
    "age": "patient_age",
    "day_of_week": "appointment_weekday",
    "weekday": "appointment_weekday",
    "lead_time_days": "appointment_lead_time",
    "lead_time": "appointment_lead_time",
    "historical_appointments": "previous_appointment_count",
    "prior_appointments": "previous_appointment_count",
    "historical_no_shows": "previous_no_show_count",
    "prior_no_shows": "previous_no_show_count"
}


def normalize_weekday(val: Any) -> str:
    """Standardizes weekday strings into canonical capitalized representation."""
    if val is None or pd.isna(val):
        return "Monday"
    clean = str(val).strip().lower()
    return WEEKDAY_MAP.get(clean, "Monday")


def clean_no_show_data(
    df: pd.DataFrame,
    imputation_stats: Optional[Dict[str, Any]] = None,
    is_training: bool = False
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Cleans raw appointment dataframe:
    - Remaps legacy or alias column names to canonical schema
    - Normalizes weekday and department strings
    - Imputes missing numerical values with median and categoricals with mode
    - Enforces logical consistency (e.g. prior no shows <= prior appointments)

    Parameters:
        df: Input appointment records.
        imputation_stats: Learned training imputation values.
        is_training: If True, computes and returns fresh training stats.

    Returns:
        Tuple of (cleaned_df, learned_imputation_stats)
    """
    cleaned = df.copy()

    # 1. Alias Resolution
    rename_dict = {}
    for col in cleaned.columns:
        low_col = col.lower()
        if low_col in FEATURE_ALIASES and FEATURE_ALIASES[low_col] not in cleaned.columns:
            rename_dict[col] = FEATURE_ALIASES[low_col]
    if rename_dict:
        cleaned = cleaned.rename(columns=rename_dict)

    # 2. Defaults for any completely omitted canonical features
    numeric_cols = [
        "patient_age",
        "appointment_lead_time",
        "previous_appointment_count",
        "previous_no_show_count",
        "sms_reminder_sent"
    ]
    categorical_cols = ["appointment_weekday", "department"]

    stats = {} if imputation_stats is None else dict(imputation_stats)

    if is_training or not stats:
        for col in numeric_cols:
            if col in cleaned.columns:
                v = cleaned[col].dropna()
                stats[col] = float(v.median()) if len(v) > 0 else 0.0
            else:
                stats[col] = 0.0

        for col in categorical_cols:
            if col in cleaned.columns:
                v = cleaned[col].dropna()
                stats[col] = str(v.mode().iloc[0]) if len(v) > 0 else "General Medicine"
            else:
                stats[col] = "General Medicine" if col == "department" else "Monday"

    # 3. Apply Imputation
    for col in numeric_cols:
        fill_val = stats.get(col, 0.0)
        if col not in cleaned.columns:
            cleaned[col] = fill_val
        else:
            cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce").fillna(fill_val)

    for col in categorical_cols:
        fill_val = stats.get(col, "General Medicine" if col == "department" else "Monday")
        if col not in cleaned.columns:
            cleaned[col] = fill_val
        else:
            cleaned[col] = cleaned[col].fillna(fill_val).astype(str).str.strip()

    # 4. Weekday Normalization
    cleaned["appointment_weekday"] = cleaned["appointment_weekday"].apply(normalize_weekday)

    # 5. Bounds & Constraints
    cleaned["patient_age"] = np.clip(cleaned["patient_age"], 0, 115)
    cleaned["appointment_lead_time"] = np.clip(cleaned["appointment_lead_time"], 0, 120)
    cleaned["previous_appointment_count"] = np.clip(cleaned["previous_appointment_count"], 0, 100)
    cleaned["previous_no_show_count"] = np.clip(cleaned["previous_no_show_count"], 0, 100)
    
    # Enforce previous_no_show_count <= previous_appointment_count
    invalid_mask = cleaned["previous_no_show_count"] > cleaned["previous_appointment_count"]
    if invalid_mask.any():
        cleaned.loc[invalid_mask, "previous_no_show_count"] = cleaned.loc[invalid_mask, "previous_appointment_count"]

    cleaned["sms_reminder_sent"] = (cleaned["sms_reminder_sent"] > 0).astype(int)

    return cleaned, stats
