import numpy as np
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "raw"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def generate_readmission_dataset(n_samples: int = 5000, random_state: int = 42) -> pd.DataFrame:
    """
    Generates a clinically realistic synthetic dataset for 30-day Inpatient Readmission Risk.
    Features mimic Electronic Health Record (EHR) demographics, comorbidities, vitals, and lab results.
    """
    np.random.seed(random_state)

    age = np.random.normal(loc=62, scale=16, size=n_samples).clip(18, 95).astype(int)
    gender = np.random.choice(["male", "female"], size=n_samples, p=[0.51, 0.49])
    
    admission_type = np.random.choice(["elective", "emergency", "urgent"], size=n_samples, p=[0.35, 0.50, 0.15])
    ward_type = np.random.choice(["general", "icu", "emergency", "pediatric", "surgical"], size=n_samples, p=[0.45, 0.20, 0.15, 0.05, 0.15])
    
    length_of_stay_days = np.random.exponential(scale=4.5, size=n_samples).clip(1, 45).round(1)
    previous_admissions_12m = np.random.poisson(lam=1.2, size=n_samples).clip(0, 12)
    chronic_conditions_count = np.random.poisson(lam=2.1, size=n_samples).clip(0, 8)
    
    # Lab & physiological markers
    abnormal_lab_count = np.random.poisson(lam=2.8, size=n_samples).clip(0, 15)
    vital_instability_index = np.random.beta(a=2, b=5, size=n_samples).round(2)  # [0.0 - 1.0]
    medication_count = np.random.normal(loc=7, scale=3, size=n_samples).clip(1, 25).astype(int)
    high_risk_medication_flag = np.random.choice([0, 1], size=n_samples, p=[0.72, 0.28])

    # True probability of readmission based on clinical weights
    logit = (
        -3.2
        + 0.025 * (age - 50)
        + 0.12 * length_of_stay_days
        + 0.45 * previous_admissions_12m
        + 0.30 * chronic_conditions_count
        + 0.18 * abnormal_lab_count
        + 1.8 * vital_instability_index
        + 0.08 * medication_count
        + 0.65 * high_risk_medication_flag
        + 0.70 * (admission_type == "emergency")
        + 0.85 * (ward_type == "icu")
    )
    prob = 1.0 / (1.0 + np.exp(-logit))
    readmitted_30d = (np.random.rand(n_samples) < prob).astype(int)

    df = pd.DataFrame({
        "age": age,
        "gender": gender,
        "admission_type": admission_type,
        "ward_type": ward_type,
        "length_of_stay_days": length_of_stay_days,
        "previous_admissions_12m": previous_admissions_12m,
        "chronic_conditions_count": chronic_conditions_count,
        "abnormal_lab_count": abnormal_lab_count,
        "vital_instability_index": vital_instability_index,
        "medication_count": medication_count,
        "high_risk_medication_flag": high_risk_medication_flag,
        "readmitted_30d": readmitted_30d
    })

    output_path = DATA_DIR / "readmission_training_data.csv"
    df.to_csv(output_path, index=False)
    print(f"[+] Generated Readmission dataset: {n_samples} rows, {df['readmitted_30d'].mean():.1%} positive class rate -> {output_path}")
    return df


def generate_no_show_dataset(n_samples: int = 6000, random_state: int = 42) -> pd.DataFrame:
    """
    Generates a realistic synthetic dataset for Outpatient Appointment No-Show Prediction.
    Factors include booking lead time, age, historical patient reliability, day of week, and SMS reminder.
    """
    np.random.seed(random_state)

    age = np.random.normal(loc=44, scale=18, size=n_samples).clip(1, 95).astype(int)
    gender = np.random.choice(["male", "female"], size=n_samples, p=[0.48, 0.52])
    
    # Days between booking date and scheduled appointment date
    lead_time_days = np.random.exponential(scale=9.0, size=n_samples).clip(0, 90).astype(int)
    day_of_week = np.random.choice(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], size=n_samples, p=[0.22, 0.21, 0.20, 0.18, 0.14, 0.05])
    appointment_hour = np.random.choice([8, 9, 10, 11, 12, 14, 15, 16, 17], size=n_samples)
    
    department = np.random.choice(
        ["Cardiology", "Neurology", "Pediatrics", "Orthopedics", "General Medicine"],
        size=n_samples,
        p=[0.20, 0.15, 0.20, 0.20, 0.25]
    )
    
    # Historical no-show behavior
    historical_appointments = np.random.poisson(lam=3.5, size=n_samples).clip(0, 20)
    historical_no_shows = np.random.binomial(n=np.maximum(historical_appointments, 1), p=0.20)
    historical_no_show_ratio = np.where(
        historical_appointments > 0,
        historical_no_shows / historical_appointments,
        0.15 # Default prior for first-time attendees
    ).round(2)
    
    sms_reminder_sent = np.random.choice([0, 1], size=n_samples, p=[0.30, 0.70])

    # True probability of no-show
    logit = (
        -2.0
        + 0.045 * lead_time_days
        + 2.2 * historical_no_show_ratio
        - 0.015 * (age - 40)
        - 0.85 * sms_reminder_sent
        + 0.40 * (day_of_week == "Mon")
        + 0.35 * (day_of_week == "Sat")
        + 0.25 * (appointment_hour >= 16)
        + 0.30 * (department == "General Medicine")
    )
    prob = 1.0 / (1.0 + np.exp(-logit))
    no_show = (np.random.rand(n_samples) < prob).astype(int)

    df = pd.DataFrame({
        "age": age,
        "gender": gender,
        "lead_time_days": lead_time_days,
        "day_of_week": day_of_week,
        "appointment_hour": appointment_hour,
        "department": department,
        "historical_appointments": historical_appointments,
        "historical_no_show_ratio": historical_no_show_ratio,
        "sms_reminder_sent": sms_reminder_sent,
        "no_show": no_show
    })

    output_path = DATA_DIR / "no_show_training_data.csv"
    df.to_csv(output_path, index=False)
    print(f"[+] Generated No-Show dataset: {n_samples} rows, {df['no_show'].mean():.1%} positive class rate -> {output_path}")
    return df

if __name__ == "__main__":
    generate_readmission_dataset()
    generate_no_show_dataset()
