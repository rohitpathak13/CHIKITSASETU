from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class HospitalAnalyticsSummaryResponse(BaseModel):
    total_patients: int
    total_doctors: int
    bed_occupancy_rate: float
    occupied_beds: int
    total_beds: int
    total_billed_revenue: float
    total_collected_revenue: float
    total_appointments_30d: int
    completed_appointments_30d: int
    pharmacy_low_stock_alerts: int
    pharmacy_expiring_alerts: int
    pharmacy_valuation: float
    no_show_rate: float
    cancellation_rate: float

class PatientGrowthResponse(BaseModel):
    dates: List[str]
    new_patients: List[int]
    cumulative_patients: List[int]
    total_registered: int

class AppointmentTrendsResponse(BaseModel):
    dates: List[str]
    total: List[int]
    completed: List[int]
    scheduled: List[int]
    cancelled: List[int]
    no_show: List[int]
    summary: Dict[str, int]

class BedOccupancyResponse(BaseModel):
    total_beds: int
    occupied_beds: int
    available_beds: int
    reserved_beds: int
    maintenance_beds: int
    occupancy_rate: float
    ward_breakdown: List[Dict[str, Any]]

class RevenueTrendsResponse(BaseModel):
    dates: List[str]
    billed: List[float]
    collected: List[float]
    balance: List[float]
    categories: Dict[str, float]
    summary: Dict[str, float]

class AllChartsResponse(BaseModel):
    chart_patient_growth: str
    chart_appointment_trends: str
    chart_dept_stats: str
    chart_doctor_workload: str
    chart_disease_dist: str
    chart_age_dist: str
    chart_gender_dist: str
    chart_adm_trends: str
    chart_dis_trends: str
    chart_bed_gauge: str
    chart_ward_bar: str
    chart_revenue_trends: str
    chart_revenue_donut: str
    chart_lab_trends: str
    chart_pharmacy_inventory: str
    chart_cancellation: str
    chart_no_show: str
