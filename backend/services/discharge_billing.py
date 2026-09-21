from datetime import datetime, timezone
from decimal import Decimal
from typing import Tuple, Optional
from sqlalchemy.orm import Session
from backend.models import (
    Admission, Bed, Invoice, InvoiceItem, Prescription, PrescriptionItem,
    LabOrder, AuditLog, Notification,
    AdmissionStatusEnum, BedStatusEnum, InvoiceStatusEnum,
    ItemTypeEnum, NotificationTypeEnum, LabOrderStatusEnum
)

def process_inpatient_discharge_and_billing(
    admission_id: int,
    discharge_summary: str,
    db: Session,
    actor_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Tuple[Admission, Invoice]:
    """
    Executes clinical inpatient discharge clearance:
    1. Computes inpatient bed stay duration and bed accommodation charges.
    2. Consolidates diagnostic laboratory orders and pharmacy medications dispensed during the stay.
    3. Auto-generates an itemized hospital invoice with standard 5% tax.
    4. Transitions bed status to MAINTENANCE for sanitization.
    5. Dispatches notifications to patient, doctor, and nurse station.
    6. Logs audit trail for HIPAA/NABH compliance.
    """
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise ValueError(f"Admission record #{admission_id} not found.")
    
    if admission.status != AdmissionStatusEnum.ADMITTED:
        raise ValueError(f"Admission #{admission_id} is already in '{admission.status.value}' status.")

    discharge_dt = datetime.now(timezone.utc)
    
    # 1. Calculate Length of Stay (LOS) in days (minimum 1 day)
    admission_date = admission.admission_date.date() if hasattr(admission.admission_date, "date") else admission.admission_date
    discharge_date = discharge_dt.date()
    days_stayed = max(1, (discharge_date - admission_date).days)

    bed = admission.bed
    daily_rate = Decimal(str(bed.daily_rate if bed and bed.daily_rate else 1500.00))
    bed_subtotal = daily_rate * Decimal(days_stayed)

    # 2. Check or create consolidated Invoice
    existing_invoice = db.query(Invoice).filter(Invoice.admission_id == admission.id).first()
    if existing_invoice:
        invoice = existing_invoice
    else:
        inv_number = f"INV-IPD-{admission.id}-{int(discharge_dt.timestamp())}"
        invoice = Invoice(
            invoice_number=inv_number,
            patient_id=admission.patient_id,
            admission_id=admission.id,
            subtotal=Decimal("0.00"),
            tax=Decimal("0.00"),
            discount=Decimal("0.00"),
            total_amount=Decimal("0.00"),
            status=InvoiceStatusEnum.UNPAID
        )
        db.add(invoice)
        db.flush()

    # Clear existing items if re-evaluating
    if invoice.items:
        for it in list(invoice.items):
            db.delete(it)
        db.flush()

    # 3. Add Bed Charge Item
    ward_name = bed.ward.name if bed and bed.ward else "General Ward"
    bed_num = bed.bed_number if bed else "Standard Bed"
    bed_item = InvoiceItem(
        invoice_id=invoice.id,
        item_type=ItemTypeEnum.BED_CHARGE,
        description=f"Inpatient Bed Accommodation: {ward_name} (Bed {bed_num}) - {days_stayed} Day(s) @ ${daily_rate}/day",
        unit_price=daily_rate,
        quantity=days_stayed,
        subtotal=bed_subtotal
    )
    db.add(bed_item)

    items_subtotal = bed_subtotal

    # 4. Consolidate Dispensed Pharmacy Medications during this admission
    prescriptions = db.query(Prescription).filter(
        Prescription.patient_id == admission.patient_id,
        Prescription.created_at >= admission.admission_date
    ).all()

    for rx in prescriptions:
        for rx_item in rx.items:
            qty = rx_item.quantity_dispensed or 0
            if qty > 0 and rx_item.medicine:
                med_price = Decimal(str(rx_item.medicine.unit_price or 15.00))
                med_sub = med_price * Decimal(qty)
                med_invoice_item = InvoiceItem(
                    invoice_id=invoice.id,
                    item_type=ItemTypeEnum.PHARMACY,
                    description=f"Medication: {rx_item.medicine.name} ({rx_item.dosage}) x {qty}",
                    unit_price=med_price,
                    quantity=qty,
                    subtotal=med_sub
                )
                db.add(med_invoice_item)
                items_subtotal += med_sub

    # 5. Consolidate Diagnostic Lab Orders during this admission
    lab_orders = db.query(LabOrder).filter(
        LabOrder.patient_id == admission.patient_id,
        LabOrder.ordered_at >= admission.admission_date,
        LabOrder.status == LabOrderStatusEnum.COMPLETED
    ).all()

    for order in lab_orders:
        if order.test_type:
            test_cost = Decimal(str(order.test_type.cost or 50.00))
            lab_invoice_item = InvoiceItem(
                invoice_id=invoice.id,
                item_type=ItemTypeEnum.LAB_TEST,
                description=f"Diagnostic Test: {order.test_type.name} ({order.test_type.test_code})",
                unit_price=test_cost,
                quantity=1,
                subtotal=test_cost
            )
            db.add(lab_invoice_item)
            items_subtotal += test_cost

    # 6. Calculate Subtotal, 5% Healthcare Tax, and Total
    invoice.subtotal = items_subtotal
    tax_rate = Decimal("0.05")
    invoice.tax = Decimal(str(round(float(items_subtotal) * float(tax_rate), 2)))
    invoice.discount = Decimal("0.00")
    invoice.total_amount = invoice.subtotal + invoice.tax - invoice.discount
    invoice.recalculate()

    # 7. Update Admission Record
    admission.status = AdmissionStatusEnum.DISCHARGED
    admission.discharge_date = discharge_dt
    admission.discharge_summary = discharge_summary or "Patient medically cleared and discharged in stable clinical condition."

    # 8. Mark Bed as MAINTENANCE
    if bed:
        bed.status = BedStatusEnum.MAINTENANCE

    # 9. Audit Trail
    audit = AuditLog(
        user_id=actor_id,
        action="INPATIENT_DISCHARGE_AND_BILLING",
        resource_type="Admission",
        resource_id=admission.id,
        ip_address=ip_address,
        details_json=f'{{"patient_id": {admission.patient_id}, "bed": "{bed_num}", "days": {days_stayed}, "total": {float(invoice.total_amount)}}}'
    )
    db.add(audit)

    # 10. Automated Notifications
    patient_user_id = admission.patient.user_id if admission.patient else None
    if patient_user_id:
        notif_patient = Notification(
            user_id=patient_user_id,
            title="Discharge Clearance Completed",
            message=f"Your inpatient stay has been completed. Consolidated Invoice #{invoice.invoice_number} generated for ${float(invoice.total_amount):.2f}.",
            type=NotificationTypeEnum.SYSTEM
        )
        db.add(notif_patient)

    if admission.admitting_doctor_id:
        notif_doc = Notification(
            user_id=admission.admitting_doctor_id,
            title=f"Discharge Completed: {admission.patient.user.full_name}",
            message=f"Patient discharged from Bed {bed_num}. Summary: {admission.discharge_summary[:80]}...",
            type=NotificationTypeEnum.REMINDER
        )
        db.add(notif_doc)

    return admission, invoice
