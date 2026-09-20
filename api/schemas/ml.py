from pydantic import BaseModel, Field
from typing import Optional, List, Dict

class ReadmissionPredictRequest(BaseModel):
    age: int
    gender: str = "male"
    admission_type: str = "emergency"
    ward_type: str = "general"
    length_of_stay_days: float = 3.0
    previous_admissions_12m: int = 0
    chronic_conditions_count: int = 1
    abnormal_lab_count: int = 0
    vital_instability_index: float = 0.15
    medication_count: int = 4
    high_risk_medication_flag: int = 0

class ReadmissionPredictResponse(BaseModel):
    risk_score: float
    risk_percentage: float
    risk_level: str
    is_high_risk: bool
    top_drivers: List[str]

class NoShowPredictRequest(BaseModel):
    patient_age: Optional[int] = Field(default=None, ge=0, le=125, description="Patient age in years")
    age: Optional[int] = Field(default=None, ge=0, le=125, description="Alias for patient age")
    appointment_weekday: Optional[str] = Field(default=None, description="Day of appointment (e.g. 'Monday', 'Tue')")
    day_of_week: Optional[str] = Field(default=None, description="Alias for weekday")
    appointment_lead_time: Optional[int] = Field(default=None, ge=0, le=180, description="Days between booking and appointment")
    lead_time_days: Optional[int] = Field(default=None, ge=0, le=180, description="Alias for lead time")
    previous_appointment_count: Optional[int] = Field(default=None, ge=0, description="Total historical appointments")
    historical_appointments: Optional[int] = Field(default=None, ge=0, description="Alias for previous appointments")
    previous_no_show_count: Optional[int] = Field(default=None, ge=0, description="Total prior missed appointments")
    historical_no_shows: Optional[int] = Field(default=None, ge=0, description="Alias for previous no-shows")
    department: str = Field(default="General Medicine", description="Clinical department")
    sms_reminder_sent: int = Field(default=1, ge=0, le=1, description="Whether an SMS reminder was sent (1 or 0)")
    appointment_history: Optional[str] = Field(default=None, description="Notes on patient appointment history")

    def get_canonical_age(self) -> int:
        if self.patient_age is not None:
            return self.patient_age
        if self.age is not None:
            return self.age
        return 40

    def get_canonical_weekday(self) -> str:
        return self.appointment_weekday or self.day_of_week or "Monday"

    def get_canonical_lead_time(self) -> int:
        if self.appointment_lead_time is not None:
            return self.appointment_lead_time
        if self.lead_time_days is not None:
            return self.lead_time_days
        return 3

    def get_canonical_previous_appointments(self) -> int:
        if self.previous_appointment_count is not None:
            return self.previous_appointment_count
        if self.historical_appointments is not None:
            return self.historical_appointments
        return 2

    def get_canonical_previous_no_shows(self) -> int:
        if self.previous_no_show_count is not None:
            return self.previous_no_show_count
        if self.historical_no_shows is not None:
            return self.historical_no_shows
        return 0


class NoShowPredictResponse(BaseModel):
    no_show_probability: float
    no_show_percentage: float
    no_show_prediction: bool = False
    risk_tier: str
    confidence: float = 0.85
    recommendation: str
    risk_factors: List[str] = []
    model_version: str = "1.0.0"
    algorithm: str = "CalibratedClassifier"
    is_medical_diagnosis: bool = False
    disclaimer: str = (
        "DISCLAIMER: This system is an operational scheduling decision-support tool. "
        "It DOES NOT make clinical diagnoses or medical health claims."
    )


class PatientRiskPredictRequest(BaseModel):
    age: int = Field(..., ge=1, le=125, description="Patient age in years")
    gender: str = Field(default="Male", description="Gender ('Male', 'Female', 'Other')")
    blood_pressure: Optional[str] = Field(default="120/80", description="Blood pressure string e.g. '120/80'")
    bp_systolic: Optional[float] = Field(default=None, ge=50, le=300, description="Systolic blood pressure (mmHg)")
    bp_diastolic: Optional[float] = Field(default=None, ge=30, le=200, description="Diastolic blood pressure (mmHg)")
    glucose: float = Field(..., ge=20.0, le=600.0, description="Fasting plasma glucose (mg/dL)")
    bmi: float = Field(..., ge=10.0, le=80.0, description="Body Mass Index (kg/m²)")
    heart_rate: Optional[int] = Field(default=72, ge=30, le=240, description="Resting heart rate (bpm)")
    smoking_status: Optional[str] = Field(default="never", description="Smoking status ('never', 'former', 'current')")
    family_history_diabetes: Optional[int] = Field(default=0, ge=0, le=1, description="Family history of diabetes (0 or 1)")
    family_history_hypertension: Optional[int] = Field(default=0, ge=0, le=1, description="Family history of hypertension (0 or 1)")
    family_history_heart_disease: Optional[int] = Field(default=0, ge=0, le=1, description="Family history of cardiovascular disease (0 or 1)")


class PatientRiskPredictResponse(BaseModel):
    risk_category: str = Field(..., description="Predicted risk tier ('Low', 'Medium', 'High')")
    confidence: float = Field(..., description="Model confidence score (0.0 - 1.0)")
    probabilities: Dict[str, float] = Field(..., description="Calibrated class probability distribution")
    model_version: str = Field(..., description="Trained model version")
    algorithm: str = Field(..., description="Underlying ML algorithm")
    risk_factors: List[str] = Field(default_factory=list, description="Primary clinical/physiological risk drivers detected")
    is_medical_diagnosis: bool = Field(default=False, description="Confirmation that this is NOT a medical diagnosis")
    disclaimer: str = Field(..., description="Mandatory educational decision-support disclaimer")
