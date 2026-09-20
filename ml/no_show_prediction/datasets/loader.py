"""
Historical and Demonstration Dataset Loader and Generator for Appointment No-Show Prediction.
Simulates realistic outpatient scheduling patterns, lead times, historical attendance records,
and department behaviors for operational triage evaluation.

DISCLAIMER: This dataset is entirely synthetic and designed for educational/technical
pipeline evaluation. It contains no Protected Health Information (PHI) and makes no
clinical medical claims.
"""

from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
DEMO_NO_SHOW_DATASET_PATH = CURRENT_DIR / "demo_appointment_no_show.csv"

FEATURE_COLUMNS = [
    "patient_age",
    "appointment_weekday",
    "appointment_lead_time",
    "previous_appointment_count",
    "previous_no_show_count",
    "department",
    "sms_reminder_sent"
]

TARGET_COLUMN = "no_show"

DEPARTMENTS = [
    "General Medicine",
    "Cardiology",
    "Pediatrics",
    "Orthopedics",
    "Dermatology",
    "Neurology",
    "ENT",
    "Ophthalmology"
]

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def generate_synthetic_no_show_data(
    n_samples: int = 3000,
    random_state: int = 42,
    output_path: Optional[Path] = None,
    inject_missing: bool = True
) -> pd.DataFrame:
    """
    Generates realistic historical outpatient scheduling data with empirical attendance patterns.

    Parameters:
        n_samples: Number of appointment records to generate.
        random_state: Random seed for reproducibility.
        output_path: Optional file path to persist CSV.
        inject_missing: Whether to introduce sparse missing values to verify imputation.

    Returns:
        pd.DataFrame containing appointment scheduling features and no_show target (0 or 1).
    """
    rng = np.random.default_rng(random_state)

    # 1. Demographics & Departments
    age = rng.integers(1, 92, size=n_samples)
    department = rng.choice(DEPARTMENTS, size=n_samples, p=[0.28, 0.14, 0.14, 0.12, 0.10, 0.08, 0.07, 0.07])
    weekday = rng.choice(WEEKDAYS, size=n_samples, p=[0.22, 0.19, 0.18, 0.18, 0.15, 0.08])

    # 2. Scheduling Parameters
    # Lead time in days: Exponentially distributed (median ~5 days, max ~45 days)
    lead_time = rng.exponential(scale=6.5, size=n_samples).astype(int)
    lead_time = np.clip(lead_time, 0, 45)

    # Historical Visits and Prior No-Shows
    prev_appts = rng.negative_binomial(n=2, p=0.35, size=n_samples)
    prev_appts = np.clip(prev_appts, 0, 25)

    # Prior no-shows: bounded by prev_appts
    prev_no_shows = []
    for appts in prev_appts:
        if appts == 0:
            prev_no_shows.append(0)
        else:
            # Probability of historical no-show typically ~0.15
            ns = rng.binomial(n=appts, p=0.18)
            prev_no_shows.append(min(ns, appts))
    prev_no_shows = np.array(prev_no_shows)

    # SMS reminder sent (more likely for longer lead times)
    sms_prob = np.where(lead_time >= 2, 0.82, 0.35)
    sms_sent = (rng.random(n_samples) < sms_prob).astype(int)

    # 3. True Latent Log-Odds of No-Show
    # Empirical Behavioral Predictors:
    # - Lead time increases no-show risk (+0.04 per day)
    # - Prior no-show ratio strongly increases no-show risk
    # - Young adults (18-32) have elevated no-show risk
    # - SMS reminder reduces no-show risk (-0.65)
    # - Mondays and Saturdays have higher friction (+0.25)
    # - Highly engaged patients with 0 prior no-shows have lower risk
    no_show_ratio = prev_no_shows / np.maximum(1, prev_appts)
    young_adult_flag = ((age >= 18) & (age <= 32)).astype(int)
    monday_or_sat_flag = np.isin(weekday, ["Monday", "Saturday"]).astype(int)

    log_odds = (
        -1.75
        + 0.045 * lead_time
        + 1.85 * no_show_ratio
        + 0.40 * young_adult_flag
        + 0.28 * monday_or_sat_flag
        - 0.65 * sms_sent
        - 0.25 * (prev_appts >= 5).astype(int)
        + rng.normal(loc=0.0, scale=0.45, size=n_samples)
    )

    prob = 1.0 / (1.0 + np.exp(-log_odds))
    no_show = (rng.random(n_samples) < prob).astype(int)

    df = pd.DataFrame({
        "patient_age": age,
        "appointment_weekday": weekday,
        "appointment_lead_time": lead_time,
        "previous_appointment_count": prev_appts,
        "previous_no_show_count": prev_no_shows,
        "department": department,
        "sms_reminder_sent": sms_sent,
        "no_show": no_show
    })

    # 4. Inject sparse realistic missing values if requested
    if inject_missing:
        mask_lead = rng.random(n_samples) < 0.02
        df.loc[mask_lead, "appointment_lead_time"] = np.nan

        mask_prev = rng.random(n_samples) < 0.015
        df.loc[mask_prev, "previous_appointment_count"] = np.nan

        mask_dept = rng.random(n_samples) < 0.010
        df.loc[mask_dept, "department"] = np.nan

    target_path = output_path or DEMO_NO_SHOW_DATASET_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target_path, index=False)
    return df


def load_no_show_dataset(
    csv_path: Optional[Path] = None,
    auto_generate: bool = True
) -> pd.DataFrame:
    """
    Loads appointment no-show dataset from disk, auto-generating it if absent.
    """
    target_file = Path(csv_path) if csv_path else DEMO_NO_SHOW_DATASET_PATH
    if not target_file.exists():
        if auto_generate:
            return generate_synthetic_no_show_data(output_path=target_file)
        raise FileNotFoundError(f"Dataset not found at {target_file}")

    return pd.read_csv(target_file)
