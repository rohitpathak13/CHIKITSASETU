"""
CHIKITSASETU AI Health Assistant - Retrieval Engine
Connects queries to the internal CHIKITSASETU database (Doctors, Departments, Prescriptions, Labs)
while strictly adhering to role-based access control (RBAC).
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.database import db_session
from backend.models import (
    User, Doctor, Department, Appointment, Prescription,
    PrescriptionItem, Medicine, LabOrder, LabResult, RoleEnum
)
from backend.chatbot.schemas import DoctorRecommendation
from backend.chatbot.retrieval.knowledge_base import (
    MEDICINE_KNOWLEDGE_BASE,
    LAB_TEST_REFERENCE_RANGES,
    RADIOLOGY_GLOSSARY,
    SYMPTOM_SPECIALTY_MAP
)


def find_medicine_knowledge(query_text: str) -> Optional[Dict[str, Any]]:
    """Searches the educational medicine knowledge base for matching generic or brand names."""
    q = query_text.lower()
    for med_key, data in MEDICINE_KNOWLEDGE_BASE.items():
        if med_key in q or data["generic"].lower() in q:
            return data
    return None


def find_lab_param_knowledge(param_name: str) -> Optional[Dict[str, Any]]:
    """Searches standard reference ranges for a lab test parameter."""
    p = param_name.lower()
    for key, data in LAB_TEST_REFERENCE_RANGES.items():
        if key in p or data["test_name"].lower() in p:
            return data
    return None


def find_radiology_term_explanation(term: str) -> Optional[str]:
    """Finds simple-language explanation for radiological terminology."""
    t = term.lower()
    for key, explanation in RADIOLOGY_GLOSSARY.items():
        if key in t:
            return explanation
    return None


def triage_symptoms_to_department(text: str) -> Dict[str, str]:
    """Matches symptom descriptions to the most relevant hospital department."""
    t = text.lower()
    best_match = {
        "specialty": "General Medicine",
        "department": "General Medicine",
        "rationale": "General medical evaluation is appropriate for comprehensive primary triage."
    }

    for item in SYMPTOM_SPECIALTY_MAP:
        for kw in item["keywords"]:
            if kw in t:
                return {
                    "specialty": item["specialty"],
                    "department": item["department"],
                    "rationale": f"Reported symptoms commonly fall under the clinical scope of {item['specialty']}."
                }

    return best_match


def get_available_hospital_doctors(department_name: str, limit: int = 3) -> List[DoctorRecommendation]:
    """
    Queries actual Doctors registered in CHIKITSASETU matching the requested department or specialty.
    """
    recs: List[DoctorRecommendation] = []
    try:
        query = (
            db_session.query(Doctor)
            .join(User, Doctor.id == User.id)
            .outerjoin(Department, Doctor.department_id == Department.id)
            .filter(User.is_active == True)
        )

        if department_name and department_name != "General Medicine":
            query = query.filter(
                or_(
                    Department.name.ilike(f"%{department_name}%"),
                    Doctor.specialization.ilike(f"%{department_name}%")
                )
            )

        doctors = query.limit(limit).all()

        # Fallback to general doctors if no specific department match found
        if not doctors:
            doctors = (
                db_session.query(Doctor)
                .join(User, Doctor.id == User.id)
                .filter(User.is_active == True)
                .limit(limit)
                .all()
            )

        for doc in doctors:
            dept_name = doc.department.name if doc.department else "Outpatient Clinic"
            recs.append(
                DoctorRecommendation(
                    department=dept_name,
                    specialization=doc.specialization,
                    doctor_name=f"Dr. {doc.user.full_name}" if doc.user else "Staff Doctor",
                    doctor_id=doc.id,
                    available_days=doc.available_days,
                    consultation_fee=float(doc.consultation_fee) if doc.consultation_fee else 500.0,
                    appointment_url=f"/appointments/book?doctor_id={doc.id}"
                )
            )

        # Resilient fallback if no doctor records exist in test/empty database
        if not recs:
            dept = department_name or "General Medicine"
            recs.append(
                DoctorRecommendation(
                    department=dept,
                    specialization=f"{dept} Specialist",
                    doctor_name=f"On-Duty Consultant ({dept})",
                    doctor_id=None,
                    available_days="Mon-Sat",
                    consultation_fee=500.0,
                    appointment_url="/appointments/book"
                )
            )
    except Exception:
        db_session.rollback()
        dept = department_name or "General Medicine"
        recs.append(
            DoctorRecommendation(
                department=dept,
                specialization=f"{dept} Specialist",
                doctor_name=f"On-Duty Consultant ({dept})",
                doctor_id=None,
                available_days="Mon-Sat",
                consultation_fee=500.0,
                appointment_url="/appointments/book"
            )
        )

    return recs


def get_patient_authorized_context(user_id: Optional[int], user_role: Optional[str]) -> Dict[str, Any]:
    """
    Retrieves authorized clinical context exclusively for the authenticated user.
    Strictly isolated: Patients can ONLY access their own records.
    """
    if not user_id or user_role != RoleEnum.PATIENT.value:
        return {"authorized": False, "prescriptions": [], "recent_labs": [], "appointments": []}

    context: Dict[str, Any] = {
        "authorized": True,
        "prescriptions": [],
        "recent_labs": [],
        "appointments": []
    }

    try:
        # 1. Patient's active prescriptions
        prescriptions = (
            db_session.query(Prescription)
            .filter(Prescription.patient_id == user_id)
            .order_by(Prescription.created_at.desc())
            .limit(3)
            .all()
        )
        for rx in prescriptions:
            items = []
            for item in rx.items:
                med_name = item.medicine.name if item.medicine else "Prescribed Medicine"
                items.append({
                    "medicine": med_name,
                    "dosage": item.dosage,
                    "frequency": item.frequency,
                    "instructions": item.instructions or "As directed"
                })
            context["prescriptions"].append({
                "prescription_id": rx.id,
                "doctor": f"Dr. {rx.doctor.user.full_name}" if (rx.doctor and rx.doctor.user) else "Doctor",
                "date": rx.created_at.strftime("%d %b %Y") if rx.created_at else "",
                "items": items
            })

        # 2. Patient's recent lab orders
        labs = (
            db_session.query(LabOrder)
            .filter(LabOrder.patient_id == user_id)
            .order_by(LabOrder.created_at.desc())
            .limit(3)
            .all()
        )
        for lo in labs:
            results = []
            for res in lo.results:
                results.append({
                    "parameter": res.parameter_name or (res.test.name if res.test else "Test"),
                    "value": res.result_value,
                    "unit": res.unit or "",
                    "reference": res.reference_range or "",
                    "is_abnormal": res.is_abnormal
                })
            context["recent_labs"].append({
                "order_id": lo.id,
                "status": lo.status.value if lo.status else "completed",
                "date": lo.created_at.strftime("%d %b %Y") if lo.created_at else "",
                "results": results
            })

        # 3. Patient's upcoming appointments
        appts = (
            db_session.query(Appointment)
            .filter(Appointment.patient_id == user_id)
            .order_by(Appointment.appointment_date.desc())
            .limit(2)
            .all()
        )
        for ap in appts:
            doc_name = f"Dr. {ap.doctor.user.full_name}" if (ap.doctor and ap.doctor.user) else "Specialist"
            context["appointments"].append({
                "appointment_id": ap.id,
                "doctor": doc_name,
                "date": ap.appointment_date.strftime("%d %b %Y %H:%M") if ap.appointment_date else "",
                "status": ap.status.value if ap.status else "scheduled"
            })

    except Exception:
        db_session.rollback()

    return context
