"""
Hospital Analytics Aggregators.

Exposes domain-specific and cross-departmental aggregators powered by Pandas and SQLAlchemy.
Integrates with core.services.analytics_service.
"""

from core.services.analytics_service import (
    get_patient_growth_data,
    get_appointment_trends_data,
    get_department_statistics_data,
    get_doctor_workload_data,
    get_disease_distribution_data,
    get_age_distribution_data,
    get_gender_distribution_data,
    get_admission_trends_data,
    get_discharge_trends_data,
    get_bed_occupancy_data,
    get_revenue_trends_data,
    get_lab_test_trends_data,
    get_pharmacy_inventory_data,
    get_appointment_cancellation_data,
    get_appointment_no_show_data,
    get_hospital_analytics_summary
)

# Backwards compatibility wrappers for legacy endpoints/tests
from sqlalchemy.orm import Session

def get_bed_occupancy_stats(db: Session) -> dict:
    """Computes overall and ward-specific bed occupancy metrics."""
    return get_bed_occupancy_data(db)

def get_revenue_summary(db: Session) -> dict:
    """Computes revenue totals and itemized income distribution using Pandas."""
    data = get_revenue_trends_data(db)
    return {
        "total_invoiced": data["summary"]["total_billed"],
        "total_collected": data["summary"]["total_collected"],
        "total_outstanding": data["summary"]["total_balance"],
        "category_distribution": data["categories"]
    }

def get_appointment_kpis(db: Session) -> dict:
    """Extracts outpatient appointment metrics and no-show statistics."""
    data = get_appointment_no_show_data(db)
    app_data = get_appointment_trends_data(db)
    return {
        "total": data["total_appointments"],
        "completed": app_data["summary"]["completed"],
        "scheduled": app_data["summary"]["scheduled"],
        "no_shows": data["no_show_count"],
        "no_show_rate": data["no_show_rate"],
        "avg_no_show_prob": data["avg_no_show_prob"]
    }

def get_pharmacy_kpis(db: Session) -> dict:
    """Computes drug inventory stock health, low stock, and expiring batches."""
    data = get_pharmacy_inventory_data(db)
    return {
        "total_medicines": data["total_skus"],
        "low_stock_count": data["low_stock_count"],
        "expiring_soon_count": data["expiring_soon_count"],
        "expired_count": data["expired_count"]
    }

__all__ = [
    "get_patient_growth_data",
    "get_appointment_trends_data",
    "get_department_statistics_data",
    "get_doctor_workload_data",
    "get_disease_distribution_data",
    "get_age_distribution_data",
    "get_gender_distribution_data",
    "get_admission_trends_data",
    "get_discharge_trends_data",
    "get_bed_occupancy_data",
    "get_revenue_trends_data",
    "get_lab_test_trends_data",
    "get_pharmacy_inventory_data",
    "get_appointment_cancellation_data",
    "get_appointment_no_show_data",
    "get_hospital_analytics_summary",
    "get_bed_occupancy_stats",
    "get_revenue_summary",
    "get_appointment_kpis",
    "get_pharmacy_kpis"
]
