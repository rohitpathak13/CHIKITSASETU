from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import RoleEnum
from backend.fastapi_service.dependencies import get_current_user, require_roles
from backend.fastapi_service.schemas.analytics import (
    HospitalAnalyticsSummaryResponse,
    PatientGrowthResponse,
    BedOccupancyResponse,
    RevenueTrendsResponse,
    AppointmentTrendsResponse,
    AllChartsResponse
)
from backend.services.analytics_service import (
    get_hospital_analytics_summary,
    get_patient_growth_data,
    get_bed_occupancy_data,
    get_revenue_trends_data,
    get_appointment_trends_data,
    get_department_statistics_data,
    get_doctor_workload_data,
    get_disease_distribution_data,
    get_age_distribution_data,
    get_gender_distribution_data,
    get_admission_trends_data,
    get_discharge_trends_data,
    get_lab_test_trends_data,
    get_pharmacy_inventory_data,
    get_appointment_cancellation_data,
    get_appointment_no_show_data
)
from ml.analytics.plotly_charts import (
    build_patient_growth_chart,
    build_appointment_trends_chart,
    build_department_stats_chart,
    build_doctor_workload_chart,
    build_disease_distribution_chart,
    build_age_distribution_chart,
    build_gender_distribution_chart,
    build_admission_trends_chart,
    build_discharge_trends_chart,
    build_bed_occupancy_gauge,
    build_ward_breakdown_bar,
    build_revenue_trends_chart,
    build_revenue_donut_chart,
    build_lab_trends_chart,
    build_pharmacy_inventory_chart,
    build_cancellation_chart,
    build_no_show_chart
)

router = APIRouter(
    prefix="/analytics",
    tags=["Hospital Analytics & BI"],
    dependencies=[Depends(require_roles([RoleEnum.ADMIN, RoleEnum.DOCTOR]))]
)


@router.get("/summary", response_model=HospitalAnalyticsSummaryResponse)
def get_analytics_summary(db: Session = Depends(get_db)):
    """Returns top-level hospital operational and financial KPI summary metrics."""
    return get_hospital_analytics_summary(db)


@router.get("/patient-growth", response_model=PatientGrowthResponse)
def get_patient_growth(
    days: Optional[int] = Query(30, description="Timeframe window in days (or None for all)"),
    db: Session = Depends(get_db)
):
    """Returns daily patient registrations and cumulative growth timeline."""
    return get_patient_growth_data(db, days=days)


@router.get("/bed-occupancy", response_model=BedOccupancyResponse)
def get_bed_occupancy(db: Session = Depends(get_db)):
    """Returns hospital-wide bed occupancy rate and ward-level capacity allocation."""
    return get_bed_occupancy_data(db)


@router.get("/revenue-trends", response_model=RevenueTrendsResponse)
def get_revenue_trends(
    days: Optional[int] = Query(30, description="Timeframe window in days"),
    db: Session = Depends(get_db)
):
    """Returns billed revenue, collected cash payments, balance, and cost center breakdown."""
    return get_revenue_trends_data(db, days=days)


@router.get("/appointment-trends", response_model=AppointmentTrendsResponse)
def get_appointment_trends(
    days: Optional[int] = Query(30, description="Timeframe window in days"),
    db: Session = Depends(get_db)
):
    """Returns outpatient appointment volume and status timeline."""
    return get_appointment_trends_data(db, days=days)


@router.get("/charts", response_model=AllChartsResponse)
def get_all_plotly_charts(
    days: Optional[int] = Query(30, description="Timeframe window in days"),
    db: Session = Depends(get_db)
):
    """Returns serialized interactive Plotly JSON specs for all hospital analytics domains."""
    patient_growth = get_patient_growth_data(db, days=days)
    app_trends = get_appointment_trends_data(db, days=days)
    dept_stats = get_department_statistics_data(db)
    doc_workload = get_doctor_workload_data(db)
    disease_dist = get_disease_distribution_data(db)
    age_dist = get_age_distribution_data(db)
    gender_dist = get_gender_distribution_data(db)
    adm_trends = get_admission_trends_data(db, days=days)
    dis_trends = get_discharge_trends_data(db, days=days)
    bed_stats = get_bed_occupancy_data(db)
    rev_trends = get_revenue_trends_data(db, days=days)
    lab_trends = get_lab_test_trends_data(db, days=days)
    pharm_stats = get_pharmacy_inventory_data(db)
    cancel_data = get_appointment_cancellation_data(db, days=days)
    no_show_data = get_appointment_no_show_data(db, days=days)

    return AllChartsResponse(
        chart_patient_growth=build_patient_growth_chart(patient_growth),
        chart_appointment_trends=build_appointment_trends_chart(app_trends),
        chart_dept_stats=build_department_stats_chart(dept_stats),
        chart_doctor_workload=build_doctor_workload_chart(doc_workload),
        chart_disease_dist=build_disease_distribution_chart(disease_dist),
        chart_age_dist=build_age_distribution_chart(age_dist),
        chart_gender_dist=build_gender_distribution_chart(gender_dist),
        chart_adm_trends=build_admission_trends_chart(adm_trends),
        chart_dis_trends=build_discharge_trends_chart(dis_trends),
        chart_bed_gauge=build_bed_occupancy_gauge(bed_stats["occupancy_rate"]),
        chart_ward_bar=build_ward_breakdown_bar(bed_stats["ward_breakdown"]),
        chart_revenue_trends=build_revenue_trends_chart(rev_trends),
        chart_revenue_donut=build_revenue_donut_chart(rev_trends["categories"]),
        chart_lab_trends=build_lab_trends_chart(lab_trends),
        chart_pharmacy_inventory=build_pharmacy_inventory_chart(pharm_stats),
        chart_cancellation=build_cancellation_chart(cancel_data),
        chart_no_show=build_no_show_chart(no_show_data)
    )
