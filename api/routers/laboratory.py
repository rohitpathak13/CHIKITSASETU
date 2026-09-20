from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from core.database import get_db
from core.models import (
    LabOrder, LabResult, LabTest, LabTestType, Notification,
    User, Doctor, RoleEnum, LabOrderStatusEnum, NotificationTypeEnum
)
from core.services.laboratory_service import (
    order_lab_tests, receive_and_collect_sample, start_processing_order,
    enter_lab_result, doctor_review_lab_result, cancel_lab_order,
    get_lab_order_detail, list_lab_orders as svc_list_lab_orders,
    create_or_update_lab_test, LaboratoryServiceError, InvalidLabDataError,
    LabOrderNotFoundError, LabPermissionError, LabInvalidStateTransitionError
)
from api.dependencies import get_current_user, require_roles
from api.schemas.laboratory import (
    LabOrderCreateRequest, LabResultEntryRequest, LabOrderReviewRequest,
    LabOrderCancelRequest, LabTestFormularyCreateRequest
)

router = APIRouter(prefix="/laboratory", tags=["Laboratory Diagnostics"])


@router.get("/orders")
def list_orders(
    status_filter: Optional[str] = None,
    priority: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Restrict to clinical, lab, admin, or patient roles
    allowed_roles = [RoleEnum.ADMIN, RoleEnum.DOCTOR, RoleEnum.LAB_TECH, RoleEnum.NURSE, RoleEnum.PATIENT]
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Role '{current_user.role.value}' is not authorized to view laboratory orders."
        )

    orders = svc_list_lab_orders(
        db_session=db,
        status_filter=status_filter,
        priority=priority,
        search_query=q
    )
    
    # Scoping: Patients can only inspect their own lab orders
    if current_user.role == RoleEnum.PATIENT:
        orders = [o for o in orders if o.patient_id == current_user.id]

    return [{
        "id": o.id,
        "patient_id": o.patient_id,
        "patient_name": o.patient.user.full_name if o.patient and o.patient.user else "Unknown",
        "doctor_name": o.doctor.user.full_name if o.doctor and o.doctor.user else "Unknown",
        "test_name": o.test.name if o.test else "Unknown",
        "test_code": o.test.test_code if o.test else "",
        "priority": o.priority,
        "status": o.status.value,
        "ordered_at": o.ordered_at.isoformat() if o.ordered_at else None,
        "has_result": o.result is not None,
        "doctor_reviewed": o.doctor_reviewed
    } for o in orders]


@router.post("/orders", status_code=status.HTTP_201_CREATED)
def create_order(
    payload: LabOrderCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.DOCTOR, RoleEnum.ADMIN]))
):
    """Physician orders diagnostic laboratory investigation."""
    try:
        test_id = payload.test_type_id or payload.test_id
        if not test_id:
            raise HTTPException(status_code=400, detail="Either test_type_id or test_id is required")
        doc_id = None
        if current_user.role == RoleEnum.DOCTOR:
            doc_record = db.query(Doctor).filter(Doctor.id == current_user.id).first()
            if doc_record:
                doc_id = doc_record.id

        if not doc_id:
            doc_record = db.query(Doctor).filter(Doctor.id == current_user.id).first()
            if doc_record:
                doc_id = doc_record.id
            else:
                first_doc = db.query(Doctor).first()
                if first_doc:
                    doc_id = first_doc.id
                else:
                    auto_doc = Doctor(
                        id=current_user.id,
                        specialization="General Medicine",
                        license_number=f"DOC-AUTO-{current_user.id}",
                        qualification="MBBS"
                    )
                    db.add(auto_doc)
                    db.flush()
                    doc_id = auto_doc.id

        orders = order_lab_tests(
            db_session=db,
            patient_id=payload.patient_id,
            doctor_id=doc_id,
            test_ids=[test_id],
            medical_record_id=payload.medical_record_id,
            priority=payload.priority or "routine",
            clinical_notes=payload.clinical_notes,
            ordering_user_id=current_user.id,
            user_role=current_user.role.value
        )
        return {
            "message": "Lab order successfully created",
            "id": orders[0].id,
            "order_id": orders[0].id,
            "status": orders[0].status.value
        }
    except (InvalidLabDataError, LabPermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/collect")
@router.post("/orders/{order_id}/collect-sample")
def collect_order_sample(
    order_id: int,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.LAB_TECH, RoleEnum.ADMIN]))
):
    """Transitions lab order to SAMPLE_COLLECTED."""
    try:
        order = receive_and_collect_sample(
            db_session=db,
            order_id=order_id,
            technician_id=current_user.id,
            notes=notes,
            user_role=current_user.role.value
        )
        return {
            "message": "Specimen successfully collected",
            "order_id": order.id,
            "status": order.status.value,
            "sample_collected_at": order.sample_collected_at.isoformat()
        }
    except LabOrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (LabInvalidStateTransitionError, LabPermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/process")
@router.post("/orders/{order_id}/start-processing")
def process_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.LAB_TECH, RoleEnum.ADMIN]))
):
    """Transitions lab order to PROCESSING."""
    try:
        order = start_processing_order(
            db_session=db,
            order_id=order_id,
            technician_id=current_user.id,
            user_role=current_user.role.value
        )
        return {
            "message": "Test analysis started",
            "order_id": order.id,
            "status": order.status.value,
            "processing_started_at": order.processing_started_at.isoformat()
        }
    except LabOrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (LabInvalidStateTransitionError, LabPermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/result")
def enter_order_result(
    order_id: int,
    payload: LabResultEntryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.LAB_TECH, RoleEnum.ADMIN]))
):
    """Enters diagnostic result directly targeting order_id in route."""
    try:
        order = enter_lab_result(
            db_session=db,
            order_id=order_id,
            measured_value=payload.measured_value,
            technician_id=current_user.id,
            technician_notes=payload.technician_notes,
            result_text=payload.result_text,
            user_role=current_user.role.value
        )
        res = order.result
        return {
            "message": "Lab result successfully recorded and physician notified",
            "result_id": res.id if res else None,
            "status": order.status.value,
            "measured_value": res.measured_value if res else payload.measured_value,
            "unit": res.unit if res else payload.unit,
            "is_abnormal": res.is_abnormal if res else (payload.is_abnormal or False),
            "critical_alert": res.critical_alert if res else False
        }
    except LabOrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (InvalidLabDataError, LabInvalidStateTransitionError, LabPermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/results", status_code=status.HTTP_201_CREATED)
def record_lab_result(
    payload: LabResultEntryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.LAB_TECH, RoleEnum.ADMIN]))
):
    """
    Records laboratory quantitative result, evaluates reference range thresholds,
    flags abnormal/critical findings, and dispatches clinical notification.
    """
    try:
        order = enter_lab_result(
            db_session=db,
            order_id=payload.lab_order_id,
            measured_value=payload.measured_value,
            technician_id=current_user.id,
            technician_notes=payload.technician_notes,
            result_text=payload.result_text,
            user_role=current_user.role.value
        )
        res = order.result
        return {
            "message": "Lab result successfully recorded and physician notified",
            "result_id": res.id,
            "measured_value": res.measured_value,
            "unit": res.unit,
            "is_abnormal": res.is_abnormal,
            "critical_alert": res.critical_alert
        }
    except LabOrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (InvalidLabDataError, LabInvalidStateTransitionError, LabPermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/review")
def review_order_result(
    order_id: int,
    payload: LabOrderReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.DOCTOR, RoleEnum.ADMIN]))
):
    """Doctor reviews and signs off on completed lab report."""
    try:
        review_notes = payload.review_notes or payload.doctor_review_notes
        order = doctor_review_lab_result(
            db_session=db,
            order_id=order_id,
            doctor_id=current_user.id,
            review_notes=review_notes,
            user_role=current_user.role.value
        )
        return {
            "message": "Clinical review successfully signed off",
            "order_id": order.id,
            "doctor_reviewed": order.doctor_reviewed,
            "reviewed_at": order.doctor_reviewed_at.isoformat() if order.doctor_reviewed_at else datetime.now(timezone.utc).isoformat()
        }
    except LabOrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (LabInvalidStateTransitionError, LabPermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LabOrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (LabInvalidStateTransitionError, LabPermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/cancel")
def cancel_order(
    order_id: int,
    payload: LabOrderCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([RoleEnum.DOCTOR, RoleEnum.LAB_TECH, RoleEnum.ADMIN]))
):
    """Cancels a pending or in-process laboratory order."""
    try:
        order = cancel_lab_order(
            db_session=db,
            order_id=order_id,
            user_id=current_user.id,
            reason=payload.reason,
            user_role=current_user.role.value
        )
        return {
            "message": "Lab order successfully cancelled",
            "order_id": order.id,
            "status": order.status.value
        }
    except LabOrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (LabInvalidStateTransitionError, InvalidLabDataError, LabPermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/catalog")
def get_catalog(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Returns all active diagnostic laboratory tests."""
    tests = db.query(LabTest).order_by(LabTest.name.asc()).all()
    return [{
        "id": t.id,
        "name": t.name,
        "test_code": t.test_code,
        "sample_type": t.sample_type,
        "unit": t.unit,
        "reference_range_min": t.reference_range_min,
        "reference_range_max": t.reference_range_max,
        "cost": float(t.cost)
    } for t in tests]

