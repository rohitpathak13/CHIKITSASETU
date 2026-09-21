"""
Comprehensive In-App Notification Service for CHIKITSASETU.
Encapsulates role-based visibility, notification creation, unread tracking,
bulk status updates, history retrieval, and operational domain generators:
- Appointment Reminders
- Lab Results Available (with critical/abnormal triage)
- Low Medicine Stock Alerts (with deduplication)
- Medicine Expiry Alerts (<30d warning, <7d critical)
- Pending Payment & Invoice Notices
- Inpatient Admission & Discharge Events
"""

import json
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, desc

from backend.models.user import User, RoleEnum
from backend.models.notification import (
    Notification,
    NotificationTypeEnum,
    NotificationPriorityEnum
)


class NotificationService:
    """
    Pure-service layer for enterprise notification dispatching and role-based lifecycle management.
    """

    # -------------------------------------------------------------------------
    # 1. Base Query Builder with Strict Role-Based Visibility
    # -------------------------------------------------------------------------
    @staticmethod
    def _build_visibility_query(
        db: Session,
        user_id: int,
        role: Optional[RoleEnum] = None
    ):
        """
        Builds a base SQLAlchemy query respecting role boundaries:
        - Specific targeting: notification.user_id == user_id
        - Role broadcast: notification.target_role == role AND notification.user_id is None
        - Admin override: Administrators can observe role broadcasts and administrative events
        - Patient isolation: Patients can strictly access their own personal or patient broadcasts
        """
        query = db.query(Notification)

        if role is None:
            # Fallback: lookup user role from DB
            user = db.query(User).filter(User.id == user_id).first()
            role = user.role if user else None

        conditions = [Notification.user_id == user_id]

        if role:
            # Role broadcast messages (not assigned to a single person)
            conditions.append(
                and_(
                    Notification.target_role == role,
                    Notification.user_id.is_(None)
                )
            )
            # Administrators can also observe system-wide admin notifications
            if role == RoleEnum.ADMIN:
                conditions.append(Notification.target_role == RoleEnum.ADMIN)

        return query.filter(or_(*conditions))

    # -------------------------------------------------------------------------
    # 2. Notification Creation
    # -------------------------------------------------------------------------
    @classmethod
    def create_notification(
        cls,
        db: Session,
        title: str,
        message: str,
        type: NotificationTypeEnum = NotificationTypeEnum.SYSTEM,
        priority: NotificationPriorityEnum = NotificationPriorityEnum.NORMAL,
        user_id: Optional[int] = None,
        target_role: Optional[RoleEnum] = None,
        reference_type: Optional[str] = None,
        reference_id: Optional[int] = None,
        action_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        commit: bool = True
    ) -> Notification:
        """
        Dispatches a notification targeted to an individual, a functional role group, or both.
        """
        meta_str = json.dumps(metadata) if metadata else None

        notification = Notification(
            user_id=user_id,
            target_role=target_role,
            title=title.strip(),
            message=message.strip(),
            type=type,
            priority=priority,
            is_read=False,
            read_at=None,
            reference_type=reference_type,
            reference_id=reference_id,
            action_url=action_url,
            metadata_json=meta_str
        )

        db.add(notification)
        if commit:
            db.commit()
            db.refresh(notification)
        else:
            db.flush()

        return notification

    # -------------------------------------------------------------------------
    # 3. Unread Count
    # -------------------------------------------------------------------------
    @classmethod
    def get_unread_count(
        cls,
        db: Session,
        user_id: int,
        role: Optional[RoleEnum] = None
    ) -> int:
        """
        Computes the total number of unread notifications visible to the user and their role.
        """
        query = cls._build_visibility_query(db, user_id=user_id, role=role)
        return query.filter(Notification.is_read.is_(False)).count()

    # -------------------------------------------------------------------------
    # 4. Mark As Read / Bulk Updates
    # -------------------------------------------------------------------------
    @classmethod
    def mark_as_read(
        cls,
        db: Session,
        notification_id: int,
        user_id: Optional[int] = None,
        role: Optional[RoleEnum] = None,
        commit: bool = True
    ) -> Optional[Notification]:
        """
        Marks a specific notification as read, enforcing authorization.
        """
        query = db.query(Notification).filter(Notification.id == notification_id)
        if user_id is not None:
            # Ensure the caller has visibility to this notification
            vis_query = cls._build_visibility_query(db, user_id=user_id, role=role)
            notification = vis_query.filter(Notification.id == notification_id).first()
        else:
            notification = query.first()

        if not notification:
            return None

        notification.mark_read()
        if commit:
            db.commit()
            db.refresh(notification)
        else:
            db.flush()

        return notification

    @classmethod
    def mark_all_as_read(
        cls,
        db: Session,
        user_id: int,
        role: Optional[RoleEnum] = None,
        commit: bool = True
    ) -> int:
        """
        Marks all unread notifications visible to this user and role as read.
        """
        now = datetime.now(timezone.utc)
        query = cls._build_visibility_query(db, user_id=user_id, role=role)
        unread_notifs = query.filter(Notification.is_read.is_(False)).all()

        count = len(unread_notifs)
        for n in unread_notifs:
            n.is_read = True
            n.read_at = now

        if commit:
            db.commit()
        else:
            db.flush()

        return count

    # -------------------------------------------------------------------------
    # 5. History & Pagination
    # -------------------------------------------------------------------------
    @classmethod
    def get_notification_history(
        cls,
        db: Session,
        user_id: int,
        role: Optional[RoleEnum] = None,
        is_read: Optional[bool] = None,
        type: Optional[NotificationTypeEnum] = None,
        priority: Optional[NotificationPriorityEnum] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Notification], int]:
        """
        Retrieves paginated notification history with optional status and category filters.
        """
        query = cls._build_visibility_query(db, user_id=user_id, role=role)

        if is_read is not None:
            query = query.filter(Notification.is_read == is_read)
        if type is not None:
            query = query.filter(Notification.type == type)
        if priority is not None:
            query = query.filter(Notification.priority == priority)

        total_count = query.count()
        items = (
            query.order_by(desc(Notification.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return items, total_count

    # -------------------------------------------------------------------------
    # 6. Domain-Specific Notification Generators
    # -------------------------------------------------------------------------

    # (A) Appointment Reminders
    @classmethod
    def notify_appointment_reminder(
        cls,
        db: Session,
        appointment_id: int,
        patient_user_id: int,
        doctor_user_id: int,
        appointment_time: datetime,
        doctor_name: str,
        patient_name: str,
        department_name: Optional[str] = None
    ) -> List[Notification]:
        """
        Generates bidirectional appointment reminder notifications for both patient and doctor.
        """
        time_str = appointment_time.strftime("%A, %b %d at %I:%M %p")
        dept_str = f" ({department_name})" if department_name else ""
        notifs = []

        # 1. Patient Reminder
        n_patient = cls.create_notification(
            db=db,
            user_id=patient_user_id,
            title="Upcoming Appointment Reminder",
            message=f"You have an upcoming consultation with Dr. {doctor_name}{dept_str} scheduled for {time_str}.",
            type=NotificationTypeEnum.APPOINTMENT_REMINDER,
            priority=NotificationPriorityEnum.NORMAL,
            reference_type="Appointment",
            reference_id=appointment_id,
            action_url=f"/appointments/{appointment_id}",
            commit=False
        )
        notifs.append(n_patient)

        # 2. Doctor Reminder
        n_doctor = cls.create_notification(
            db=db,
            user_id=doctor_user_id,
            title="Scheduled Patient Consultation",
            message=f"Upcoming appointment with patient {patient_name} scheduled for {time_str}.",
            type=NotificationTypeEnum.APPOINTMENT_REMINDER,
            priority=NotificationPriorityEnum.NORMAL,
            reference_type="Appointment",
            reference_id=appointment_id,
            action_url=f"/appointments/{appointment_id}",
            commit=False
        )
        notifs.append(n_doctor)

        db.commit()
        for n in notifs:
            db.refresh(n)
        return notifs

    # (B) Lab Result Available
    @classmethod
    def notify_lab_result_available(
        cls,
        db: Session,
        lab_order_id: int,
        test_name: str,
        patient_user_id: Optional[int],
        doctor_user_id: Optional[int],
        is_abnormal: bool = False,
        is_critical: bool = False
    ) -> List[Notification]:
        """
        Dispatches lab completion notices with automatic clinical triage priority escalations.
        """
        if is_critical:
            priority = NotificationPriorityEnum.CRITICAL
            tag = "CRITICAL ALERT: "
        elif is_abnormal:
            priority = NotificationPriorityEnum.HIGH
            tag = "Attention Required: "
        else:
            priority = NotificationPriorityEnum.NORMAL
            tag = ""

        notifs = []

        # Doctor Notification
        if doctor_user_id:
            n_doc = cls.create_notification(
                db=db,
                user_id=doctor_user_id,
                title=f"{tag}Diagnostic Report Available - {test_name}",
                message=f"Laboratory analysis for {test_name} (Order #{lab_order_id}) has been completed and verified.",
                type=NotificationTypeEnum.LAB_RESULT,
                priority=priority,
                reference_type="LabOrder",
                reference_id=lab_order_id,
                action_url=f"/laboratory/orders/{lab_order_id}",
                commit=False
            )
            notifs.append(n_doc)

        # Patient Notification
        if patient_user_id:
            n_pat = cls.create_notification(
                db=db,
                user_id=patient_user_id,
                title=f"Lab Results Ready - {test_name}",
                message=f"Your diagnostic laboratory results for {test_name} are now available for review with your physician.",
                type=NotificationTypeEnum.LAB_RESULT,
                priority=NotificationPriorityEnum.NORMAL,
                reference_type="LabOrder",
                reference_id=lab_order_id,
                action_url=f"/laboratory/orders/{lab_order_id}",
                commit=False
            )
            notifs.append(n_pat)

        db.commit()
        for n in notifs:
            db.refresh(n)
        return notifs

    # (C) Low Medicine Stock
    @classmethod
    def notify_low_stock(
        cls,
        db: Session,
        medicine_id: int,
        medicine_name: str,
        current_stock: int,
        reorder_level: int
    ) -> Optional[Notification]:
        """
        Alerts pharmacy staff when medication inventory drops to or below the reorder point.
        Includes 24-hour deduplication to prevent repetitive alert spam.
        """
        # Deduplication check: Has a low stock notification been issued recently for this drug?
        one_day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
        existing = db.query(Notification).filter(
            Notification.reference_type == "Medicine",
            Notification.reference_id == medicine_id,
            Notification.type == NotificationTypeEnum.LOW_STOCK,
            Notification.is_read.is_(False),
            Notification.created_at >= one_day_ago
        ).first()

        if existing:
            return None

        priority = NotificationPriorityEnum.CRITICAL if current_stock == 0 else NotificationPriorityEnum.HIGH
        status_msg = "COMPLETELY OUT OF STOCK" if current_stock == 0 else f"Current stock: {current_stock} units (Reorder threshold: {reorder_level})"

        return cls.create_notification(
            db=db,
            target_role=RoleEnum.PHARMACIST,
            title=f"Low Stock Alert: {medicine_name}",
            message=f"Medication '{medicine_name}' requires immediate replenishment. {status_msg}.",
            type=NotificationTypeEnum.LOW_STOCK,
            priority=priority,
            reference_type="Medicine",
            reference_id=medicine_id,
            action_url="/pharmacy/inventory",
            metadata={"medicine_id": medicine_id, "current_stock": current_stock, "reorder_level": reorder_level},
            commit=True
        )

    # (D) Medicine Expiry
    @classmethod
    def notify_medicine_expiry(
        cls,
        db: Session,
        batch_id: int,
        medicine_name: str,
        batch_number: str,
        expiry_date: date,
        days_until_expiry: int
    ) -> Optional[Notification]:
        """
        Alerts pharmacy team regarding expiring medication batches (e.g. <30 days, <7 days).
        """
        # Deduplication check
        one_day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
        existing = db.query(Notification).filter(
            Notification.reference_type == "MedicineBatch",
            Notification.reference_id == batch_id,
            Notification.type == NotificationTypeEnum.MEDICINE_EXPIRY,
            Notification.is_read.is_(False),
            Notification.created_at >= one_day_ago
        ).first()

        if existing:
            return None

        if days_until_expiry <= 0:
            priority = NotificationPriorityEnum.CRITICAL
            timing = "HAS EXPIRED"
        elif days_until_expiry <= 7:
            priority = NotificationPriorityEnum.CRITICAL
            timing = f"expires in {days_until_expiry} days"
        else:
            priority = NotificationPriorityEnum.HIGH
            timing = f"expires in {days_until_expiry} days"

        return cls.create_notification(
            db=db,
            target_role=RoleEnum.PHARMACIST,
            title=f"Medicine Expiry Warning: {medicine_name}",
            message=f"Batch '{batch_number}' of '{medicine_name}' {timing} on {expiry_date.strftime('%Y-%m-%d')}. Ensure FEFO disposal or transfer.",
            type=NotificationTypeEnum.MEDICINE_EXPIRY,
            priority=priority,
            reference_type="MedicineBatch",
            reference_id=batch_id,
            action_url="/pharmacy/inventory",
            metadata={"batch_id": batch_id, "batch_number": batch_number, "days_left": days_until_expiry},
            commit=True
        )

    # (E) Pending Payment
    @classmethod
    def notify_pending_payment(
        cls,
        db: Session,
        bill_id: int,
        invoice_number: str,
        patient_user_id: Optional[int],
        outstanding_amount: float,
        due_date: Optional[date] = None
    ) -> List[Notification]:
        """
        Generates invoice settlement reminder for patient and cashier/receptionist roster.
        """
        due_str = f" due by {due_date.strftime('%b %d, %Y')}" if due_date else ""
        notifs = []

        # 1. Patient Notification
        if patient_user_id:
            n_pat = cls.create_notification(
                db=db,
                user_id=patient_user_id,
                title="Pending Hospital Invoice",
                message=f"Invoice #{invoice_number} has an outstanding balance of ₹{outstanding_amount:,.2f}{due_str}.",
                type=NotificationTypeEnum.PENDING_PAYMENT,
                priority=NotificationPriorityEnum.NORMAL,
                reference_type="Bill",
                reference_id=bill_id,
                action_url=f"/billing/invoices/{bill_id}",
                commit=False
            )
            notifs.append(n_pat)

        # 2. Receptionist / Billing Desk Broadcast
        n_desk = cls.create_notification(
            db=db,
            target_role=RoleEnum.RECEPTIONIST,
            title=f"Outstanding Balance: #{invoice_number}",
            message=f"Invoice #{invoice_number} requires settlement: ₹{outstanding_amount:,.2f} pending{due_str}.",
            type=NotificationTypeEnum.PENDING_PAYMENT,
            priority=NotificationPriorityEnum.NORMAL,
            reference_type="Bill",
            reference_id=bill_id,
            action_url=f"/billing/invoices/{bill_id}",
            commit=False
        )
        notifs.append(n_desk)

        db.commit()
        for n in notifs:
            db.refresh(n)
        return notifs

    # (F) Admission and Discharge Events
    @classmethod
    def notify_admission_discharge_event(
        cls,
        db: Session,
        admission_id: int,
        event_type: str,  # "ADMISSION" or "DISCHARGE"
        patient_name: str,
        patient_user_id: Optional[int],
        doctor_user_id: Optional[int],
        ward_name: str,
        bed_number: str
    ) -> List[Notification]:
        """
        Notifies clinical team (nurses, attending doctor) and patient regarding inpatient admission or discharge.
        """
        is_admission = event_type.upper() == "ADMISSION"
        notifs = []

        if is_admission:
            title = f"New Patient Admission: {patient_name}"
            msg_nurse = f"Patient {patient_name} admitted to {ward_name}, Bed {bed_number}. Please initiate clinical intake."
            msg_doc = f"Your patient {patient_name} has been admitted to {ward_name}, Bed {bed_number}."
            msg_pat = f"You have been admitted to {ward_name}, Bed {bed_number}. Healthcare staff will assist you shortly."
        else:
            title = f"Patient Discharged: {patient_name}"
            msg_nurse = f"Patient {patient_name} discharged from {ward_name}, Bed {bed_number}. Bed marked ready for sanitization."
            msg_doc = f"Your inpatient {patient_name} has completed discharge procedures from {ward_name}."
            msg_pat = f"Your discharge from {ward_name} has been completed. Take care and follow your discharge medications."

        # 1. Nurse Station Broadcast
        n_nurse = cls.create_notification(
            db=db,
            target_role=RoleEnum.NURSE,
            title=title,
            message=msg_nurse,
            type=NotificationTypeEnum.ADMISSION_DISCHARGE,
            priority=NotificationPriorityEnum.NORMAL,
            reference_type="Admission",
            reference_id=admission_id,
            action_url=f"/ipd/admissions/{admission_id}",
            commit=False
        )
        notifs.append(n_nurse)

        # 2. Attending Physician
        if doctor_user_id:
            n_doc = cls.create_notification(
                db=db,
                user_id=doctor_user_id,
                title=title,
                message=msg_doc,
                type=NotificationTypeEnum.ADMISSION_DISCHARGE,
                priority=NotificationPriorityEnum.NORMAL,
                reference_type="Admission",
                reference_id=admission_id,
                action_url=f"/ipd/admissions/{admission_id}",
                commit=False
            )
            notifs.append(n_doc)

        # 3. Patient
        if patient_user_id:
            n_pat = cls.create_notification(
                db=db,
                user_id=patient_user_id,
                title=title,
                message=msg_pat,
                type=NotificationTypeEnum.ADMISSION_DISCHARGE,
                priority=NotificationPriorityEnum.NORMAL,
                reference_type="Admission",
                reference_id=admission_id,
                action_url=f"/ipd/admissions/{admission_id}",
                commit=False
            )
            notifs.append(n_pat)

        # 4. Discharge event also alerts billing desk for receipt finalization
        if not is_admission:
            n_rec = cls.create_notification(
                db=db,
                target_role=RoleEnum.RECEPTIONIST,
                title=f"Discharge Complete: {patient_name}",
                message=f"Discharge clearance recorded for {patient_name}. Finalize settlement receipt.",
                type=NotificationTypeEnum.ADMISSION_DISCHARGE,
                priority=NotificationPriorityEnum.NORMAL,
                reference_type="Admission",
                reference_id=admission_id,
                action_url=f"/ipd/admissions/{admission_id}",
                commit=False
            )
            notifs.append(n_rec)

        db.commit()
        for n in notifs:
            db.refresh(n)
        return notifs

    # -------------------------------------------------------------------------
    # 7. Automated Operational Scanners
    # -------------------------------------------------------------------------
    @classmethod
    def scan_and_generate_operational_notifications(cls, db: Session) -> Dict[str, int]:
        """
        Runs periodic checks across hospital operational tables:
        1. Low Stock: MedicineInventory items at or below reorder level.
        2. Medicine Expiry: MedicineBatch items expiring within 30 days.
        3. Appointment Reminders: Outpatient appointments scheduled in next 24 hours.
        4. Pending Payments: Unpaid or partially paid bills.
        """
        stats = {
            "low_stock_generated": 0,
            "expiry_generated": 0,
            "appointment_reminders_generated": 0,
            "pending_payments_generated": 0
        }

        # 1. Low Stock Scan
        try:
            from backend.models.pharmacy import Medicine
            medicines = db.query(Medicine).all()
            for med in medicines:
                if med.total_stock <= med.reorder_level:
                    res = cls.notify_low_stock(
                        db=db,
                        medicine_id=med.id,
                        medicine_name=med.name,
                        current_stock=med.total_stock,
                        reorder_level=med.reorder_level
                    )
                    if res:
                        stats["low_stock_generated"] += 1
        except Exception:
            pass

        # 2. Medicine Expiry Scan
        try:
            from backend.models.pharmacy import MedicineInventory, Medicine
            cutoff_date = date.today() + timedelta(days=30)
            batches = (
                db.query(MedicineInventory, Medicine)
                .join(Medicine, MedicineInventory.medicine_id == Medicine.id)
                .filter(
                    MedicineInventory.expiry_date <= cutoff_date,
                    MedicineInventory.quantity_in_stock > 0
                )
                .all()
            )
            for batch, med in batches:
                days_left = (batch.expiry_date - date.today()).days
                res = cls.notify_medicine_expiry(
                    db=db,
                    batch_id=batch.id,
                    medicine_name=med.name,
                    batch_number=batch.batch_number,
                    expiry_date=batch.expiry_date,
                    days_until_expiry=days_left
                )
                if res:
                    stats["expiry_generated"] += 1
        except Exception:
            pass

        # 3. Upcoming Appointment Reminders Scan (<24 hours)
        try:
            from backend.models.clinical import Appointment, AppointmentStatusEnum
            from backend.models.user import DoctorProfile, PatientProfile
            now_utc = datetime.now(timezone.utc)
            window_end = now_utc + timedelta(hours=24)

            appts = (
                db.query(Appointment)
                .filter(
                    Appointment.appointment_datetime >= now_utc,
                    Appointment.appointment_datetime <= window_end,
                    Appointment.status == AppointmentStatusEnum.SCHEDULED
                )
                .all()
            )

            for appt in appts:
                # Deduplicate: check if reminder already sent for this appointment
                existing = db.query(Notification).filter(
                    Notification.reference_type == "Appointment",
                    Notification.reference_id == appt.id,
                    Notification.type == NotificationTypeEnum.APPOINTMENT_REMINDER
                ).first()

                if not existing:
                    # Resolve patient and doctor users
                    doc_user = db.query(User).filter(User.id == appt.doctor_id).first()
                    pat_user = db.query(User).filter(User.id == appt.patient_id).first()
                    doc_name = f"{doc_user.first_name} {doc_user.last_name}" if doc_user else "Doctor"
                    pat_name = f"{pat_user.first_name} {pat_user.last_name}" if pat_user else "Patient"

                    cls.notify_appointment_reminder(
                        db=db,
                        appointment_id=appt.id,
                        patient_user_id=appt.patient_id,
                        doctor_user_id=appt.doctor_id,
                        appointment_time=appt.appointment_datetime,
                        doctor_name=doc_name,
                        patient_name=pat_name
                    )
                    stats["appointment_reminders_generated"] += 1
        except Exception:
            pass

        # 4. Pending Payment Scan
        try:
            from backend.models.billing import Bill, BillStatusEnum
            pending_bills = (
                db.query(Bill)
                .filter(Bill.status.in_([BillStatusEnum.UNPAID, BillStatusEnum.PARTIALLY_PAID]))
                .limit(20)
                .all()
            )
            for bill in pending_bills:
                existing = db.query(Notification).filter(
                    Notification.reference_type == "Bill",
                    Notification.reference_id == bill.id,
                    Notification.type == NotificationTypeEnum.PENDING_PAYMENT,
                    Notification.is_read.is_(False)
                ).first()

                if not existing:
                    outstanding = float(bill.total_amount - (bill.paid_amount or 0.0))
                    if outstanding > 0:
                        cls.notify_pending_payment(
                            db=db,
                            bill_id=bill.id,
                            invoice_number=bill.invoice_number,
                            patient_user_id=bill.patient_id,
                            outstanding_amount=outstanding,
                            due_date=bill.due_date
                        )
                        stats["pending_payments_generated"] += 1
        except Exception:
            pass

        return stats
