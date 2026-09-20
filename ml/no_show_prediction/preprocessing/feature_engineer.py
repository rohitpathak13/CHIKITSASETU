"""
Feature Engineering module for Outpatient Appointment No-Show Prediction.
Derives behavioral, temporal, and interaction indicators that correlate with attendance.
"""

import numpy as np
import pandas as pd


def engineer_no_show_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Constructs domain-specific features from cleaned appointment data:
    - Historical No-Show Ratio
    - Weekend Appointment Indicator
    - Lead Time Duration Buckets ('SameDay', 'Short', 'Medium', 'Long')
    - Patient Age Cohorts ('Pediatric', 'YoungAdult', 'Adult', 'Senior')
    - Frequent Attender Indicator
    - Prior No-Show Flag
    - High Friction Risk: Unreminded Long Lead Time Appointment

    Parameters:
        df: Cleaned appointment DataFrame.

    Returns:
        pd.DataFrame enriched with engineered features.
    """
    feat_df = df.copy()

    prev_appts = feat_df["previous_appointment_count"]
    prev_no_shows = feat_df["previous_no_show_count"]
    lead_time = feat_df["appointment_lead_time"]
    age = feat_df["patient_age"]
    weekday = feat_df["appointment_weekday"]
    sms = feat_df["sms_reminder_sent"]

    # 1. Historical No-Show Ratio
    feat_df["historical_no_show_ratio"] = (prev_no_shows / np.maximum(1.0, prev_appts)).round(4)

    # 2. Prior No-Show Flag
    feat_df["has_prior_no_show"] = (prev_no_shows > 0).astype(int)

    # 3. Frequent Patient Flag (>= 5 appointments)
    feat_df["frequent_patient"] = (prev_appts >= 5).astype(int)

    # 4. Weekend Indicator
    feat_df["is_weekend"] = weekday.isin(["Saturday", "Sunday"]).astype(int)

    # 5. Lead Time Categorical Buckets
    lead_buckets = []
    for lt in lead_time:
        if lt == 0:
            lead_buckets.append("SameDay")
        elif lt <= 3:
            lead_buckets.append("Short")
        elif lt <= 7:
            lead_buckets.append("Medium")
        else:
            lead_buckets.append("Long")
    feat_df["lead_time_bucket"] = lead_buckets

    # 6. Age Cohorts
    age_cohorts = []
    for a in age:
        if a < 18:
            age_cohorts.append("Pediatric")
        elif a <= 35:
            age_cohorts.append("YoungAdult")
        elif a <= 64:
            age_cohorts.append("Adult")
        else:
            age_cohorts.append("Senior")
    feat_df["age_cohort"] = age_cohorts

    # 7. Unreminded Long Lead Time Interaction
    feat_df["unreminded_long_lead"] = ((lead_time >= 7) & (sms == 0)).astype(int)

    return feat_df
