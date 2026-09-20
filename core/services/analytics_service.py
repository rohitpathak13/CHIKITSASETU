"""
Hospital Analytics & Business Intelligence Service.

Extracts, aggregates, and transforms clinical, operational, and financial hospital data
using SQLAlchemy and Pandas. Designed to handle empty datasets safely with zero hardcoding.
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_, and_

from core.models import (
    User, Patient, Doctor, Staff, Department,
    Appointment, AppointmentStatusEnum,
    MedicalRecord, Diagnosis,
    Admission, Bed, Room, BedStatusEnum, AdmissionStatusEnum,
    Bill, BillItem, Payment, BillStatusEnum, ItemTypeEnum,
    LabTest, LabOrder, LabResult, LabOrderStatusEnum,
    Medicine, MedicineInventory, StockTransaction,
    GenderEnum
)


# ---------------------------------------------------------------------------
# Helper Utilities
# ---------------------------------------------------------------------------

def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or pd.isna(val):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# 1. Patient Growth
# ---------------------------------------------------------------------------

def get_patient_growth_data(db: Session, days: Optional[int] = 30) -> Dict[str, Any]:
    """
    Computes daily new patient registrations and cumulative patient census over time.
    """
    patients = db.query(Patient).all()
    if not patients:
        return {
            "dates": [],
            "new_patients": [],
            "cumulative_patients": [],
            "total_registered": 0
        }

    records = []
    for p in patients:
        created = p.created_at or datetime.now(timezone.utc)
        if hasattr(created, "date"):
            d = created.date()
        else:
            d = date.today()
        records.append({"date": d})

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    # Filter by days if specified
    if days is not None and days > 0:
        cutoff = date.today() - timedelta(days=days)
        df_window = df[df["date"] >= cutoff]
    else:
        df_window = df

    if df_window.empty:
        return {
            "dates": [str(date.today())],
            "new_patients": [0],
            "cumulative_patients": [len(patients)],
            "total_registered": len(patients)
        }

    daily = df_window.groupby("date").size().reset_index(name="new_patients")
    daily = daily.sort_values("date")

    # Reindex to ensure continuous date sequence
    min_date = daily["date"].min()
    max_date = daily["date"].max()
    all_dates = pd.date_range(start=min_date, end=max_date).date
    daily = daily.set_index("date").reindex(all_dates, fill_value=0).rename_axis("date").reset_index()

    # Prior patients before cutoff
    prior_count = len(df[df["date"] < min_date]) if (days is not None and days > 0) else 0
    daily["cumulative_patients"] = daily["new_patients"].cumsum() + prior_count

    return {
        "dates": [str(d) for d in daily["date"]],
        "new_patients": daily["new_patients"].tolist(),
        "cumulative_patients": daily["cumulative_patients"].tolist(),
        "total_registered": len(patients)
    }


# ---------------------------------------------------------------------------
# 2. Appointment Trends
# ---------------------------------------------------------------------------

def get_appointment_trends_data(db: Session, days: Optional[int] = 30) -> Dict[str, Any]:
    """
    Computes outpatient appointment volume, scheduled, completed, cancelled, and no-shows.
    """
    query = db.query(Appointment)
    appointments = query.all()

    empty_result = {
        "dates": [],
        "total": [],
        "completed": [],
        "scheduled": [],
        "cancelled": [],
        "no_show": [],
        "summary": {
            "total": 0, "completed": 0, "scheduled": 0, "cancelled": 0, "no_show": 0
        }
    }
    if not appointments:
        return empty_result

    records = []
    for a in appointments:
        dt = a.appointment_datetime
        d = dt.date() if hasattr(dt, "date") else date.today()
        status_str = a.status.value if hasattr(a.status, "value") else str(a.status).lower()
        records.append({"date": d, "status": status_str})

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    if days is not None and days > 0:
        cutoff = date.today() - timedelta(days=days)
        df_window = df[df["date"] >= cutoff]
    else:
        df_window = df

    summary = {
        "total": len(df_window),
        "completed": int((df_window["status"] == "completed").sum()) if not df_window.empty else 0,
        "scheduled": int(df_window["status"].isin(["scheduled", "confirmed"]).sum()) if not df_window.empty else 0,
        "cancelled": int((df_window["status"] == "cancelled").sum()) if not df_window.empty else 0,
        "no_show": int((df_window["status"] == "no_show").sum()) if not df_window.empty else 0
    }

    if df_window.empty:
        return {**empty_result, "summary": summary}

    min_date = df_window["date"].min()
    max_date = df_window["date"].max()
    all_dates = pd.date_range(start=min_date, end=max_date).date

    grouped = df_window.groupby(["date", "status"]).size().unstack(fill_value=0)
    grouped = grouped.reindex(all_dates, fill_value=0)

    dates_str = [str(d) for d in grouped.index]
    total_series = grouped.sum(axis=1).tolist()
    completed_series = grouped["completed"].tolist() if "completed" in grouped.columns else [0] * len(dates_str)
    scheduled_series = (
        (grouped.get("scheduled", 0) + grouped.get("confirmed", 0)).tolist()
        if any(c in grouped.columns for c in ["scheduled", "confirmed"])
        else [0] * len(dates_str)
    )
    cancelled_series = grouped["cancelled"].tolist() if "cancelled" in grouped.columns else [0] * len(dates_str)
    no_show_series = grouped["no_show"].tolist() if "no_show" in grouped.columns else [0] * len(dates_str)

    return {
        "dates": dates_str,
        "total": total_series,
        "completed": completed_series,
        "scheduled": scheduled_series,
        "cancelled": cancelled_series,
        "no_show": no_show_series,
        "summary": summary
    }


# ---------------------------------------------------------------------------
# 3. Department Statistics
# ---------------------------------------------------------------------------

def get_department_statistics_data(db: Session) -> Dict[str, Any]:
    """
    Computes doctor headcount, appointments, inpatient admissions, and bed capacity per department.
    """
    departments = db.query(Department).all()
    if not departments:
        return {
            "departments": [],
            "doctor_counts": [],
            "appointment_counts": [],
            "admission_counts": [],
            "bed_counts": []
        }

    records = []
    for dept in departments:
        # Doctors in department
        doc_count = len(dept.doctors)
        doc_ids = [d.id for d in dept.doctors]

        # Appointments for doctors in this dept
        app_count = 0
        if doc_ids:
            app_count = db.query(Appointment).filter(Appointment.doctor_id.in_(doc_ids)).count()

        # Admissions in this dept
        adm_count = db.query(Admission).filter(Admission.department_id == dept.id).count()

        # Beds in rooms belonging to this dept
        bed_count = 0
        for r in dept.rooms:
            bed_count += len(r.beds)

        records.append({
            "name": dept.name,
            "doctors": doc_count,
            "appointments": app_count,
            "admissions": adm_count,
            "beds": bed_count
        })

    df = pd.DataFrame(records)
    df = df.sort_values(by=["appointments", "doctors"], ascending=False)

    return {
        "departments": df["name"].tolist(),
        "doctor_counts": df["doctors"].tolist(),
        "appointment_counts": df["appointments"].tolist(),
        "admission_counts": df["admissions"].tolist(),
        "bed_counts": df["beds"].tolist()
    }


# ---------------------------------------------------------------------------
# 4. Doctor Workload
# ---------------------------------------------------------------------------

def get_doctor_workload_data(db: Session, limit: int = 10) -> Dict[str, Any]:
    """
    Computes workload per doctor: assigned appointments, completed consultations, and admissions.
    """
    doctors = db.query(Doctor).all()
    if not doctors:
        return {
            "doctors": [],
            "specializations": [],
            "total_appointments": [],
            "completed_consultations": [],
            "admissions": []
        }

    records = []
    for doc in doctors:
        name = doc.user.full_name if doc.user else f"Dr. ID {doc.id}"
        total_app = len(doc.appointments)
        completed_app = sum(
            1 for a in doc.appointments
            if (a.status.value if hasattr(a.status, "value") else str(a.status)) == "completed"
        )
        adm_count = len(doc.admissions)

        records.append({
            "name": f"Dr. {name}",
            "specialization": doc.specialization,
            "total_appointments": total_app,
            "completed_consultations": completed_app,
            "admissions": adm_count,
            "score": total_app + adm_count
        })

    df = pd.DataFrame(records)
    df = df.sort_values(by="score", ascending=False).head(limit)

    return {
        "doctors": df["name"].tolist(),
        "specializations": df["specialization"].tolist(),
        "total_appointments": df["total_appointments"].tolist(),
        "completed_consultations": df["completed_consultations"].tolist(),
        "admissions": df["admissions"].tolist()
    }


# ---------------------------------------------------------------------------
# 5. Disease Distribution
# ---------------------------------------------------------------------------

def get_disease_distribution_data(db: Session, top_n: int = 8) -> Dict[str, Any]:
    """
    Aggregates clinical diagnosis frequency and disease distribution from diagnoses and medical records.
    """
    diagnoses = db.query(Diagnosis).all()
    records = []

    for d in diagnoses:
        if d.diagnosis_name and d.diagnosis_name.strip():
            records.append({"condition": d.diagnosis_name.strip()})

    # Supplement from MedicalRecord.diagnosis if few diagnoses
    if not records:
        med_records = db.query(MedicalRecord).all()
        for mr in med_records:
            if mr.diagnosis and mr.diagnosis.strip():
                records.append({"condition": mr.diagnosis.strip()})

    if not records:
        return {
            "labels": [],
            "counts": [],
            "percentages": [],
            "total_diagnoses": 0
        }

    df = pd.DataFrame(records)
    counts = df["condition"].value_counts()
    total = len(df)

    top = counts.head(top_n)
    other_sum = counts.iloc[top_n:].sum() if len(counts) > top_n else 0

    labels = top.index.tolist()
    val_counts = top.values.tolist()

    if other_sum > 0:
        labels.append("Other Conditions")
        val_counts.append(int(other_sum))

    percentages = [round((c / total) * 100, 1) for c in val_counts] if total > 0 else []

    return {
        "labels": labels,
        "counts": val_counts,
        "percentages": percentages,
        "total_diagnoses": total
    }


# ---------------------------------------------------------------------------
# 6. Age Distribution
# ---------------------------------------------------------------------------

def get_age_distribution_data(db: Session) -> Dict[str, Any]:
    """
    Computes patient age demographic breakdown into standard clinical cohorts.
    """
    cohort_labels = [
        "0-12 (Pediatric)",
        "13-19 (Adolescent)",
        "20-39 (Young Adult)",
        "40-59 (Middle Age)",
        "60+ (Senior)"
    ]
    patients = db.query(Patient).all()

    empty_result = {
        "cohorts": cohort_labels,
        "counts": [0, 0, 0, 0, 0],
        "percentages": [0.0, 0.0, 0.0, 0.0, 0.0],
        "avg_age": 0.0,
        "total": 0
    }
    if not patients:
        return empty_result

    today = date.today()
    ages = []
    for p in patients:
        if p.dob:
            age = today.year - p.dob.year - ((today.month, today.day) < (p.dob.month, p.dob.day))
            ages.append(max(0, age))

    if not ages:
        return empty_result

    df = pd.DataFrame({"age": ages})
    bins = [-1, 12, 19, 39, 59, 150]
    df["cohort"] = pd.cut(df["age"], bins=bins, labels=cohort_labels)

    cohort_counts = df["cohort"].value_counts().reindex(cohort_labels, fill_value=0)
    total = len(ages)
    percentages = [round((int(c) / total) * 100, 1) for c in cohort_counts]
    avg_age = round(float(df["age"].mean()), 1)

    return {
        "cohorts": cohort_labels,
        "counts": cohort_counts.astype(int).tolist(),
        "percentages": percentages,
        "avg_age": avg_age,
        "total": total
    }


# ---------------------------------------------------------------------------
# 7. Gender Distribution
# ---------------------------------------------------------------------------

def get_gender_distribution_data(db: Session) -> Dict[str, Any]:
    """
    Aggregates patient gender breakdown across Male, Female, and Other.
    """
    patients = db.query(Patient).all()
    if not patients:
        return {
            "labels": ["Male", "Female", "Other"],
            "counts": [0, 0, 0],
            "percentages": [0.0, 0.0, 0.0],
            "total": 0
        }

    records = []
    for p in patients:
        g = p.gender.value if hasattr(p.gender, "value") else str(p.gender).lower()
        records.append({"gender": g})

    df = pd.DataFrame(records)
    total = len(df)

    canonical_order = ["male", "female", "other"]
    counts_map = df["gender"].value_counts().to_dict()

    counts = [int(counts_map.get(k, 0)) for k in canonical_order]
    percentages = [round((c / total) * 100, 1) for c in counts] if total > 0 else [0.0, 0.0, 0.0]

    return {
        "labels": ["Male", "Female", "Other"],
        "counts": counts,
        "percentages": percentages,
        "total": total
    }


# ---------------------------------------------------------------------------
# 8. Admission Trends
# ---------------------------------------------------------------------------

def get_admission_trends_data(db: Session, days: Optional[int] = 30) -> Dict[str, Any]:
    """
    Computes daily/weekly inpatient admission volume over time.
    """
    admissions = db.query(Admission).all()
    if not admissions:
        return {
            "dates": [],
            "counts": [],
            "total_admissions": 0
        }

    records = []
    for a in admissions:
        dt = a.admission_date
        d = dt.date() if hasattr(dt, "date") else date.today()
        records.append({"date": d})

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    if days is not None and days > 0:
        cutoff = date.today() - timedelta(days=days)
        df_window = df[df["date"] >= cutoff]
    else:
        df_window = df

    if df_window.empty:
        return {
            "dates": [str(date.today())],
            "counts": [0],
            "total_admissions": len(admissions)
        }

    daily = df_window.groupby("date").size().reset_index(name="counts")
    daily = daily.sort_values("date")

    min_date = daily["date"].min()
    max_date = daily["date"].max()
    all_dates = pd.date_range(start=min_date, end=max_date).date
    daily = daily.set_index("date").reindex(all_dates, fill_value=0).rename_axis("date").reset_index()

    return {
        "dates": [str(d) for d in daily["date"]],
        "counts": daily["counts"].tolist(),
        "total_admissions": len(df_window)
    }


# ---------------------------------------------------------------------------
# 9. Discharge Trends
# ---------------------------------------------------------------------------

def get_discharge_trends_data(db: Session, days: Optional[int] = 30) -> Dict[str, Any]:
    """
    Computes daily discharges, cumulative discharges, and average length of stay (LOS).
    """
    admissions = db.query(Admission).all()
    discharged = [
        a for a in admissions
        if a.discharge_date is not None
        or (a.status.value if hasattr(a.status, "value") else str(a.status)).lower() == "discharged"
    ]

    empty_result = {
        "dates": [],
        "counts": [],
        "avg_los_days": 0.0,
        "total_discharges": 0
    }
    if not discharged:
        return empty_result

    records = []
    for a in discharged:
        dt = a.discharge_date or a.admission_date
        d = dt.date() if hasattr(dt, "date") else date.today()
        los = a.length_of_stay_days
        records.append({"date": d, "los": los})

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    if days is not None and days > 0:
        cutoff = date.today() - timedelta(days=days)
        df_window = df[df["date"] >= cutoff]
    else:
        df_window = df

    if df_window.empty:
        return {
            "dates": [str(date.today())],
            "counts": [0],
            "avg_los_days": round(float(df["los"].mean()), 1) if not df.empty else 0.0,
            "total_discharges": len(discharged)
        }

    daily = df_window.groupby("date").size().reset_index(name="counts")
    daily = daily.sort_values("date")

    min_date = daily["date"].min()
    max_date = daily["date"].max()
    all_dates = pd.date_range(start=min_date, end=max_date).date
    daily = daily.set_index("date").reindex(all_dates, fill_value=0).rename_axis("date").reset_index()

    avg_los = round(float(df_window["los"].mean()), 1)

    return {
        "dates": [str(d) for d in daily["date"]],
        "counts": daily["counts"].tolist(),
        "avg_los_days": avg_los,
        "total_discharges": len(df_window)
    }


# ---------------------------------------------------------------------------
# 10. Bed Occupancy
# ---------------------------------------------------------------------------

def get_bed_occupancy_data(db: Session) -> Dict[str, Any]:
    """
    Computes hospital-wide and ward-by-ward bed availability, occupancy rate, and status breakdown.
    """
    beds = db.query(Bed).all()
    rooms = db.query(Room).all()

    empty_result = {
        "total_beds": 0,
        "occupied_beds": 0,
        "available_beds": 0,
        "reserved_beds": 0,
        "maintenance_beds": 0,
        "occupancy_rate": 0.0,
        "ward_breakdown": []
    }
    if not beds:
        return empty_result

    total = len(beds)
    occupied = sum(1 for b in beds if b.status == BedStatusEnum.OCCUPIED)
    available = sum(1 for b in beds if b.status == BedStatusEnum.AVAILABLE)
    reserved = sum(1 for b in beds if b.status == BedStatusEnum.RESERVED)
    maintenance = sum(1 for b in beds if b.status == BedStatusEnum.MAINTENANCE)
    occupancy_rate = round((occupied / total) * 100, 1) if total > 0 else 0.0

    ward_breakdown = []
    for r in rooms:
        w_total = len(r.beds)
        w_occ = sum(1 for b in r.beds if b.status == BedStatusEnum.OCCUPIED)
        w_avail = sum(1 for b in r.beds if b.status == BedStatusEnum.AVAILABLE)
        w_maint = sum(1 for b in r.beds if b.status == BedStatusEnum.MAINTENANCE)
        w_rate = round((w_occ / w_total) * 100, 1) if w_total > 0 else 0.0
        ward_breakdown.append({
            "room_id": r.id,
            "room_number": r.room_number,
            "room_type": r.room_type.value if hasattr(r.room_type, "value") else str(r.room_type),
            "ward_name": f"Room {r.room_number} ({r.room_type.value if hasattr(r.room_type, 'value') else str(r.room_type)})",
            "total": w_total,
            "occupied": w_occ,
            "available": w_avail,
            "maintenance": w_maint,
            "occupancy_rate": w_rate
        })

    return {
        "total_beds": total,
        "occupied_beds": occupied,
        "available_beds": available,
        "reserved_beds": reserved,
        "maintenance_beds": maintenance,
        "occupancy_rate": occupancy_rate,
        "ward_breakdown": ward_breakdown
    }


# ---------------------------------------------------------------------------
# 11. Revenue Trends
# ---------------------------------------------------------------------------

def get_revenue_trends_data(db: Session, days: Optional[int] = 30) -> Dict[str, Any]:
    """
    Computes billed revenue, collected cash payments, outstanding receivables, and cost center distribution.
    """
    bills = db.query(Bill).all()
    payments = db.query(Payment).all()
    items = db.query(BillItem).all()

    empty_result = {
        "dates": [],
        "billed": [],
        "collected": [],
        "balance": [],
        "categories": {},
        "summary": {
            "total_billed": 0.0,
            "total_collected": 0.0,
            "total_balance": 0.0,
            "collection_rate": 0.0
        }
    }
    if not bills and not payments:
        return empty_result

    # 1. Total summary
    total_billed = float(sum((b.final_amount or Decimal("0.00")) for b in bills))
    total_collected = float(sum((p.amount if not p.is_refund else -p.amount) for p in payments))
    total_balance = max(0.0, total_billed - total_collected)
    collection_rate = round((total_collected / total_billed) * 100, 1) if total_billed > 0 else 0.0

    # 2. Time-series aggregation
    bill_records = []
    for b in bills:
        dt = b.created_at or datetime.now(timezone.utc)
        d = dt.date() if hasattr(dt, "date") else date.today()
        bill_records.append({"date": d, "billed": float(b.final_amount or 0.00)})

    pay_records = []
    for p in payments:
        dt = p.payment_date or p.created_at or datetime.now(timezone.utc)
        d = dt.date() if hasattr(dt, "date") else date.today()
        amt = float(p.amount if not p.is_refund else -p.amount)
        pay_records.append({"date": d, "collected": amt})

    df_b = pd.DataFrame(bill_records) if bill_records else pd.DataFrame(columns=["date", "billed"])
    df_p = pd.DataFrame(pay_records) if pay_records else pd.DataFrame(columns=["date", "collected"])

    if not df_b.empty:
        df_b["date"] = pd.to_datetime(df_b["date"]).dt.date
    if not df_p.empty:
        df_p["date"] = pd.to_datetime(df_p["date"]).dt.date

    # Filter window
    if days is not None and days > 0:
        cutoff = date.today() - timedelta(days=days)
        if not df_b.empty:
            df_b = df_b[df_b["date"] >= cutoff]
        if not df_p.empty:
            df_p = df_p[df_p["date"] >= cutoff]

    # Combine timeline
    dates_b = set(df_b["date"]) if not df_b.empty else set()
    dates_p = set(df_p["date"]) if not df_p.empty else set()
    combined_dates = sorted(list(dates_b.union(dates_p)))

    if not combined_dates:
        combined_dates = [date.today()]

    min_date = min(combined_dates)
    max_date = max(combined_dates)
    all_dates = pd.date_range(start=min_date, end=max_date).date

    grouped_b = df_b.groupby("date")["billed"].sum().reindex(all_dates, fill_value=0.0) if not df_b.empty else pd.Series(0.0, index=all_dates)
    grouped_p = df_p.groupby("date")["collected"].sum().reindex(all_dates, fill_value=0.0) if not df_p.empty else pd.Series(0.0, index=all_dates)

    dates_str = [str(d) for d in all_dates]
    billed_series = [round(float(v), 2) for v in grouped_b.values]
    collected_series = [round(float(v), 2) for v in grouped_p.values]
    balance_series = [round(max(0.0, float(b - c)), 2) for b, c in zip(billed_series, collected_series)]

    # 3. Category distribution
    categories = {}
    for item in items:
        cat = item.item_type.value if hasattr(item.item_type, "value") else str(item.item_type)
        cat_clean = cat.replace("_", " ").title()
        categories[cat_clean] = round(categories.get(cat_clean, 0.0) + float(item.subtotal), 2)

    return {
        "dates": dates_str,
        "billed": billed_series,
        "collected": collected_series,
        "balance": balance_series,
        "categories": categories,
        "summary": {
            "total_billed": round(total_billed, 2),
            "total_collected": round(total_collected, 2),
            "total_balance": round(total_balance, 2),
            "collection_rate": collection_rate
        }
    }


# ---------------------------------------------------------------------------
# 12. Laboratory Test Trends
# ---------------------------------------------------------------------------

def get_lab_test_trends_data(db: Session, days: Optional[int] = 30) -> Dict[str, Any]:
    """
    Computes laboratory order volume, top ordered tests, status distribution, and abnormality rates.
    """
    orders = db.query(LabOrder).all()
    results = db.query(LabResult).all()

    empty_result = {
        "top_tests": [],
        "top_counts": [],
        "status_distribution": {},
        "abnormal_count": 0,
        "normal_count": 0,
        "abnormal_rate": 0.0,
        "total_orders": 0
    }
    if not orders:
        return empty_result

    records = []
    for o in orders:
        test_name = o.test.name if o.test else f"Test #{o.test_id}"
        status_val = o.status.value if hasattr(o.status, "value") else str(o.status).lower()
        records.append({
            "test_name": test_name,
            "status": status_val
        })

    df = pd.DataFrame(records)
    total_orders = len(df)

    top_tests_series = df["test_name"].value_counts().head(8)
    status_dist = df["status"].value_counts().to_dict()

    abnormal_count = sum(1 for r in results if r.is_abnormal)
    normal_count = sum(1 for r in results if not r.is_abnormal)
    total_results = abnormal_count + normal_count
    abnormal_rate = round((abnormal_count / total_results) * 100, 1) if total_results > 0 else 0.0

    return {
        "top_tests": top_tests_series.index.tolist(),
        "top_counts": top_tests_series.values.tolist(),
        "status_distribution": {k.replace("_", " ").title(): int(v) for k, v in status_dist.items()},
        "abnormal_count": abnormal_count,
        "normal_count": normal_count,
        "abnormal_rate": abnormal_rate,
        "total_orders": total_orders
    }


# ---------------------------------------------------------------------------
# 13. Pharmacy Inventory
# ---------------------------------------------------------------------------

def get_pharmacy_inventory_data(db: Session) -> Dict[str, Any]:
    """
    Computes stock units by therapeutic category, total inventory valuation, and stock health alerts.
    """
    medicines = db.query(Medicine).all()
    batches = db.query(MedicineInventory).all()

    empty_result = {
        "categories": [],
        "category_units": [],
        "category_skus": [],
        "total_skus": 0,
        "total_stock_units": 0,
        "total_valuation": 0.0,
        "low_stock_count": 0,
        "expiring_soon_count": 0,
        "expired_count": 0
    }
    if not medicines and not batches:
        return empty_result

    today = date.today()
    cutoff_expiring = today + timedelta(days=30)

    # Valuation & Expirations from batches
    total_stock_units = sum(b.quantity_in_stock for b in batches if b.quantity_in_stock > 0 and b.expiry_date >= today)
    total_valuation = float(sum((b.quantity_in_stock * (b.purchase_cost or Decimal("0.00"))) for b in batches if b.quantity_in_stock > 0))
    expiring_soon = sum(1 for b in batches if (today <= b.expiry_date <= cutoff_expiring) and b.quantity_in_stock > 0)
    expired = sum(1 for b in batches if b.expiry_date < today and b.quantity_in_stock > 0)

    # Category aggregation from medicines
    records = []
    low_stock = 0
    for m in medicines:
        if m.is_low_stock:
            low_stock += 1
        cat = m.category or "General"
        units = m.total_stock
        records.append({"category": cat, "units": units, "sku": 1})

    df = pd.DataFrame(records)
    if not df.empty:
        cat_group = df.groupby("category").agg({"units": "sum", "sku": "count"}).reset_index()
        cat_group = cat_group.sort_values(by="units", ascending=False).head(8)
        categories = cat_group["category"].tolist()
        cat_units = cat_group["units"].astype(int).tolist()
        cat_skus = cat_group["sku"].astype(int).tolist()
    else:
        categories, cat_units, cat_skus = [], [], []

    return {
        "categories": categories,
        "category_units": cat_units,
        "category_skus": cat_skus,
        "total_skus": len(medicines),
        "total_stock_units": total_stock_units,
        "total_valuation": round(total_valuation, 2),
        "low_stock_count": low_stock,
        "expiring_soon_count": expiring_soon,
        "expired_count": expired
    }


# ---------------------------------------------------------------------------
# 14. Appointment Cancellation
# ---------------------------------------------------------------------------

def get_appointment_cancellation_data(db: Session, days: Optional[int] = 30) -> Dict[str, Any]:
    """
    Computes appointment cancellation count, cancellation rate %, and cancellation timeline.
    """
    appointments = db.query(Appointment).all()
    empty_result = {
        "total_appointments": 0,
        "cancelled_count": 0,
        "cancellation_rate": 0.0,
        "dates": [],
        "cancelled_timeline": []
    }
    if not appointments:
        return empty_result

    total = len(appointments)
    cancelled_app = [
        a for a in appointments
        if (a.status.value if hasattr(a.status, "value") else str(a.status)).lower() == "cancelled"
    ]
    cancelled_count = len(cancelled_app)
    cancellation_rate = round((cancelled_count / total) * 100, 1) if total > 0 else 0.0

    records = []
    for a in cancelled_app:
        dt = a.appointment_datetime
        d = dt.date() if hasattr(dt, "date") else date.today()
        records.append({"date": d})

    df = pd.DataFrame(records)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
        if days is not None and days > 0:
            cutoff = date.today() - timedelta(days=days)
            df = df[df["date"] >= cutoff]

    if df.empty:
        dates_str = [str(date.today())]
        cancelled_series = [0]
    else:
        daily = df.groupby("date").size().reset_index(name="cancelled")
        daily = daily.sort_values("date")
        min_date = daily["date"].min()
        max_date = daily["date"].max()
        all_dates = pd.date_range(start=min_date, end=max_date).date
        daily = daily.set_index("date").reindex(all_dates, fill_value=0).rename_axis("date").reset_index()
        dates_str = [str(d) for d in daily["date"]]
        cancelled_series = daily["cancelled"].tolist()

    return {
        "total_appointments": total,
        "cancelled_count": cancelled_count,
        "cancellation_rate": cancellation_rate,
        "dates": dates_str,
        "cancelled_timeline": cancelled_series
    }


# ---------------------------------------------------------------------------
# 15. Appointment No-Show
# ---------------------------------------------------------------------------

def get_appointment_no_show_data(db: Session, days: Optional[int] = 30) -> Dict[str, Any]:
    """
    Computes no-show count, no-show rate %, average ML no-show risk, and risk cohort distribution.
    """
    appointments = db.query(Appointment).all()
    empty_result = {
        "total_appointments": 0,
        "no_show_count": 0,
        "no_show_rate": 0.0,
        "avg_no_show_prob": 0.0,
        "risk_buckets": {
            "Low Risk (<20%)": 0,
            "Medium Risk (20-50%)": 0,
            "High Risk (>50%)": 0
        }
    }
    if not appointments:
        return empty_result

    total = len(appointments)
    no_shows = [
        a for a in appointments
        if (a.status.value if hasattr(a.status, "value") else str(a.status)).lower() == "no_show"
    ]
    no_show_count = len(no_shows)
    no_show_rate = round((no_show_count / total) * 100, 1) if total > 0 else 0.0

    probs = [a.no_show_probability for a in appointments if a.no_show_probability is not None]
    avg_prob = round(float(np.mean(probs)) * 100, 1) if probs else 0.0

    low_risk = sum(1 for p in probs if p < 0.20)
    med_risk = sum(1 for p in probs if 0.20 <= p <= 0.50)
    high_risk = sum(1 for p in probs if p > 0.50)

    return {
        "total_appointments": total,
        "no_show_count": no_show_count,
        "no_show_rate": no_show_rate,
        "avg_no_show_prob": avg_prob,
        "risk_buckets": {
            "Low Risk (<20%)": low_risk,
            "Medium Risk (20-50%)": med_risk,
            "High Risk (>50%)": high_risk
        }
    }


# ---------------------------------------------------------------------------
# Master Hospital Analytics Summary
# ---------------------------------------------------------------------------

def get_hospital_analytics_summary(db: Session) -> Dict[str, Any]:
    """
    Computes consolidated executive KPIs for top-level hospital dashboards.
    """
    patients_count = db.query(Patient).count()
    doctors_count = db.query(Doctor).count()
    beds_data = get_bed_occupancy_data(db)
    rev_data = get_revenue_trends_data(db, days=30)
    app_data = get_appointment_trends_data(db, days=30)
    pharmacy_data = get_pharmacy_inventory_data(db)
    no_show_data = get_appointment_no_show_data(db, days=30)
    cancel_data = get_appointment_cancellation_data(db, days=30)

    return {
        "total_patients": patients_count,
        "total_doctors": doctors_count,
        "bed_occupancy_rate": beds_data["occupancy_rate"],
        "occupied_beds": beds_data["occupied_beds"],
        "total_beds": beds_data["total_beds"],
        "total_billed_revenue": rev_data["summary"]["total_billed"],
        "total_collected_revenue": rev_data["summary"]["total_collected"],
        "total_appointments_30d": app_data["summary"]["total"],
        "completed_appointments_30d": app_data["summary"]["completed"],
        "pharmacy_low_stock_alerts": pharmacy_data["low_stock_count"],
        "pharmacy_expiring_alerts": pharmacy_data["expiring_soon_count"],
        "pharmacy_valuation": pharmacy_data["total_valuation"],
        "no_show_rate": no_show_data["no_show_rate"],
        "cancellation_rate": cancel_data["cancellation_rate"]
    }
