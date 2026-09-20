"""
Safe educational and demonstration dataset loader and generator for Patient Risk Prediction.
Generates plausible, clinically grounded synthetic patient profiles for demonstration purposes.

DISCLAIMER: This dataset is entirely synthetic and designed for educational/technical
pipeline evaluation. It does NOT contain real protected health information (PHI) and
must NOT be interpreted as medical evidence or clinical guidance.
"""

import os
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
RAW_DATASET_PATH = CURRENT_DIR / "synthetic_patient_risk.csv"

FEATURE_COLUMNS = [
    "age",
    "gender",
    "blood_pressure",
    "glucose",
    "bmi",
    "heart_rate",
    "smoking_status",
    "family_history_diabetes",
    "family_history_hypertension",
    "family_history_heart_disease"
]

TARGET_COLUMN = "risk_category"


def generate_synthetic_patient_risk_data(
    n_samples: int = 2000,
    random_state: int = 42,
    output_path: Optional[Path] = None,
    inject_missing: bool = True
) -> pd.DataFrame:
    """
    Synthesizes a realistic clinical patient cohort with physiological correlations.

    Parameters:
        n_samples: Number of patient records to generate.
        random_state: Seed for reproducible distribution sampling.
        output_path: Optional path to save CSV.
        inject_missing: Whether to introduce realistic sparse missing values for cleaning testing.

    Returns:
        pd.DataFrame containing demographic, vital, metabolic, and genetic risk features with risk_category target.
    """
    rng = np.random.default_rng(random_state)

    # 1. Demographics
    age = rng.integers(18, 86, size=n_samples)
    gender = rng.choice(["Male", "Female", "Other"], size=n_samples, p=[0.49, 0.49, 0.02])

    # 2. Lifestyle & Family History
    smoking_status = rng.choice(["never", "former", "current"], size=n_samples, p=[0.55, 0.25, 0.20])
    fam_diabetes = rng.choice([0, 1], size=n_samples, p=[0.70, 0.30])
    fam_hypertension = rng.choice([0, 1], size=n_samples, p=[0.65, 0.35])
    fam_heart_disease = rng.choice([0, 1], size=n_samples, p=[0.75, 0.25])

    # 3. Metabolic & Physiological Features (correlated with age and lifestyle)
    # Base BMI with age effect
    bmi_base = 22.0 + (age - 18) * 0.10 + rng.normal(loc=3.0, scale=4.5, size=n_samples)
    bmi = np.clip(bmi_base, 16.0, 48.0).round(1)

    # Glucose fasting (mg/dL): correlated with age, BMI, and family history of diabetes
    glucose_latent = (
        75.0
        + 0.35 * (age - 30)
        + 1.4 * (bmi - 22.0)
        + 25.0 * fam_diabetes
        + rng.normal(loc=10.0, scale=18.0, size=n_samples)
    )
    glucose = np.clip(glucose_latent, 65.0, 290.0).round(1)

    # Blood pressure: Systolic and Diastolic
    # Systolic increases with age, BMI, hypertension family history, and smoking
    sys_latent = (
        105.0
        + 0.55 * (age - 20)
        + 0.85 * (bmi - 22.0)
        + 16.0 * fam_hypertension
        + 8.0 * (smoking_status == "current")
        + rng.normal(loc=5.0, scale=12.0, size=n_samples)
    )
    systolic = np.clip(sys_latent, 85, 210).astype(int)

    # Diastolic follows systolic with physiological gap (pulse pressure 35-55)
    dia_latent = 60.0 + 0.35 * (systolic - 90.0) + rng.normal(loc=5.0, scale=7.0, size=n_samples)
    diastolic = np.clip(dia_latent, 50, 125).astype(int)
    # Ensure systolic > diastolic
    diastolic = np.minimum(diastolic, systolic - 15)

    bp_strings = [f"{s}/{d}" for s, d in zip(systolic, diastolic)]

    # Resting Heart Rate (bpm)
    hr_latent = 65.0 + 0.25 * (bmi - 22.0) + 6.0 * (smoking_status == "current") + rng.normal(loc=5.0, scale=9.0, size=n_samples)
    heart_rate = np.clip(hr_latent, 48, 128).astype(int)

    # 4. Latent Risk Score Calculation (Determines Low, Medium, High Risk Category)
    # Clinically inspired multi-factor risk score
    risk_score = (
        0.035 * (age - 40)
        + 0.045 * (bmi - 25.0)
        + 0.025 * (systolic - 120)
        + 0.020 * (diastolic - 80)
        + 0.022 * (glucose - 100)
        + 0.45 * (smoking_status == "current")
        + 0.15 * (smoking_status == "former")
        + 0.35 * fam_diabetes
        + 0.40 * fam_hypertension
        + 0.50 * fam_heart_disease
        + rng.normal(loc=0.0, scale=0.65, size=n_samples)
    )

    # Tiers: ~45% Low, ~35% Medium, ~20% High
    q_low = np.percentile(risk_score, 45)
    q_med = np.percentile(risk_score, 80)

    risk_categories = []
    for s in risk_score:
        if s <= q_low:
            risk_categories.append("Low")
        elif s <= q_med:
            risk_categories.append("Medium")
        else:
            risk_categories.append("High")

    df = pd.DataFrame({
        "age": age,
        "gender": gender,
        "blood_pressure": bp_strings,
        "glucose": glucose,
        "bmi": bmi,
        "heart_rate": heart_rate,
        "smoking_status": smoking_status,
        "family_history_diabetes": fam_diabetes,
        "family_history_hypertension": fam_hypertension,
        "family_history_heart_disease": fam_heart_disease,
        "risk_category": risk_categories
    })

    # 5. Inject controlled realistic missing values if requested
    if inject_missing:
        # ~2.5% missing in glucose
        mask_glucose = rng.random(n_samples) < 0.025
        df.loc[mask_glucose, "glucose"] = np.nan

        # ~2% missing in bmi
        mask_bmi = rng.random(n_samples) < 0.020
        df.loc[mask_bmi, "bmi"] = np.nan

        # ~1% missing in heart_rate
        mask_hr = rng.random(n_samples) < 0.010
        df.loc[mask_hr, "heart_rate"] = np.nan

        # ~1.5% missing in smoking_status
        mask_smoke = rng.random(n_samples) < 0.015
        df.loc[mask_smoke, "smoking_status"] = np.nan

    target_path = output_path or RAW_DATASET_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target_path, index=False)
    return df


def load_patient_risk_dataset(
    csv_path: Optional[Path] = None,
    auto_generate: bool = True
) -> pd.DataFrame:
    """
    Loads the patient risk dataset from disk, auto-generating it if absent.

    Parameters:
        csv_path: Optional custom path to CSV.
        auto_generate: Whether to generate the demo dataset if not found.

    Returns:
        pd.DataFrame containing patient risk data.
    """
    target_file = Path(csv_path) if csv_path else RAW_DATASET_PATH
    if not target_file.exists():
        if auto_generate:
            return generate_synthetic_patient_risk_data(output_path=target_file)
        raise FileNotFoundError(f"Dataset not found at {target_file}")

    df = pd.read_csv(target_file)
    return df
