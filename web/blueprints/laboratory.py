from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from datetime import datetime, timezone
from decimal import Decimal

from core.database import db_session
from core.models import (
    LabOrder, LabResult, LabTest, LabTestType, Notification,
    RoleEnum, LabOrderStatusEnum, NotificationTypeEnum, Department
)
from core.services.laboratory_service import (
    receive_and_collect_sample, start_processing_order, enter_lab_result,
    cancel_lab_order, list_lab_orders, get_lab_order_detail,
    create_or_update_lab_test, LaboratoryServiceError,
    InvalidLabDataError, LabOrderNotFoundError, LabInvalidStateTransitionError,
    LabPermissionError
)
from web.decorators import login_required, roles_required, normalize_role

laboratory_bp = Blueprint("laboratory", __name__, url_prefix="/laboratory")


@laboratory_bp.route("/")
@login_required
@roles_required(RoleEnum.LAB_TECH, RoleEnum.ADMIN)
def dashboard():
    status_filter = request.args.get("status", "all").strip().lower()
    search_q = request.args.get("q", "").strip()
    priority_filter = request.args.get("priority", "all").strip().lower()

    # Retrieve all orders to calculate queue metrics
    all_orders = db_session.query(LabOrder).order_by(LabOrder.ordered_at.desc()).all()

    counts = {
        "all": len(all_orders),
        "ordered": sum(1 for o in all_orders if o.status == LabOrderStatusEnum.ORDERED),
        "sample_collected": sum(1 for o in all_orders if o.status == LabOrderStatusEnum.SAMPLE_COLLECTED),
        "processing": sum(1 for o in all_orders if o.status == LabOrderStatusEnum.PROCESSING),
        "completed": sum(1 for o in all_orders if o.status == LabOrderStatusEnum.COMPLETED),
        "cancelled": sum(1 for o in all_orders if o.status == LabOrderStatusEnum.CANCELLED),
    }

    # Filtered list using laboratory service
    orders = list_lab_orders(
        db_session=db_session,
        status_filter=status_filter if status_filter != "all" else None,
        search_query=search_q if search_q else None,
        priority=priority_filter if priority_filter != "all" else None
    )

    return render_template(
        "laboratory/dashboard.html",
        active_page="lab_dashboard",
        orders=orders,
        status_filter=status_filter,
        priority_filter=priority_filter,
        search_q=search_q,
        counts=counts,
        pending_count=counts["ordered"] + counts["sample_collected"] + counts["processing"],
        completed_count=counts["completed"]
    )


@laboratory_bp.route("/collect/<int:order_id>", methods=["POST"])
@login_required
@roles_required(RoleEnum.LAB_TECH, RoleEnum.ADMIN)
def collect_sample(order_id: int):
    user_id = session.get("user_id")
    user_role = session.get("user_role")
    notes = request.form.get("notes", "").strip()

    try:
        order = receive_and_collect_sample(
            db_session=db_session,
            order_id=order_id,
            technician_id=user_id,
            notes=notes if notes else None,
            user_role=user_role
        )
        flash(f"Specimen collected for Order #{order.id} ({order.test.name}). Ready for processing.", "info")
    except (LabOrderNotFoundError, LabInvalidStateTransitionError, LabPermissionError) as e:
        flash(str(e), "danger")
    return redirect(url_for("laboratory.dashboard"))


@laboratory_bp.route("/process/<int:order_id>", methods=["POST"])
@login_required
@roles_required(RoleEnum.LAB_TECH, RoleEnum.ADMIN)
def process_order(order_id: int):
    user_id = session.get("user_id")
    user_role = session.get("user_role")

    try:
        order = start_processing_order(
            db_session=db_session,
            order_id=order_id,
            technician_id=user_id,
            user_role=user_role
        )
        flash(f"Order #{order.id} ({order.test.name}) is now in PROCESSING.", "primary")
    except (LabOrderNotFoundError, LabInvalidStateTransitionError, LabPermissionError) as e:
        flash(str(e), "danger")
    return redirect(url_for("laboratory.dashboard"))


@laboratory_bp.route("/result/<int:order_id>", methods=["POST"])
@login_required
@roles_required(RoleEnum.LAB_TECH, RoleEnum.ADMIN)
def submit_result(order_id: int):
    user_id = session.get("user_id")
    user_role = session.get("user_role")

    val_str = request.form.get("measured_value", "").strip()
    notes = request.form.get("notes", "").strip()
    result_text = request.form.get("result_text", "").strip()

    try:
        order = enter_lab_result(
            db_session=db_session,
            order_id=order_id,
            measured_value=val_str,
            technician_id=user_id,
            technician_notes=notes if notes else None,
            result_text=result_text if result_text else None,
            user_role=user_role
        )
        res = order.result
        finding_msg = "CRITICAL" if res.critical_alert else ("ABNORMAL" if res.is_abnormal else "NORMAL")
        flash(f"Results for Order #{order.id} verified. Finding: [{finding_msg}] ({res.measured_value} {res.unit}).", "success")
    except (InvalidLabDataError, LabOrderNotFoundError, LabInvalidStateTransitionError, LabPermissionError) as e:
        flash(str(e), "danger")

    return redirect(url_for("laboratory.dashboard"))


@laboratory_bp.route("/cancel/<int:order_id>", methods=["POST"])
@login_required
@roles_required(RoleEnum.LAB_TECH, RoleEnum.ADMIN, RoleEnum.DOCTOR)
def cancel_order(order_id: int):
    user_id = session.get("user_id")
    user_role = session.get("user_role")
    reason = request.form.get("reason", "").strip()

    if not reason:
        flash("A cancellation reason is required.", "warning")
        return redirect(url_for("laboratory.dashboard"))

    try:
        order = cancel_lab_order(
            db_session=db_session,
            order_id=order_id,
            user_id=user_id,
            reason=reason,
            user_role=user_role
        )
        flash(f"Lab Order #{order.id} has been cancelled.", "warning")
    except (LabOrderNotFoundError, LabInvalidStateTransitionError, LabPermissionError, InvalidLabDataError) as e:
        flash(str(e), "danger")

    return redirect(url_for("laboratory.dashboard"))


@laboratory_bp.route("/catalog")
@login_required
@roles_required(RoleEnum.LAB_TECH, RoleEnum.ADMIN, RoleEnum.DOCTOR)
def test_catalog():
    tests = db_session.query(LabTest).order_by(LabTest.name.asc()).all()
    departments = db_session.query(Department).order_by(Department.name.asc()).all()
    return render_template(
        "laboratory/catalog.html",
        active_page="lab_catalog",
        tests=tests,
        departments=departments
    )


@laboratory_bp.route("/catalog/new", methods=["POST"])
@login_required
@roles_required(RoleEnum.LAB_TECH, RoleEnum.ADMIN)
def new_catalog_test():
    name = request.form.get("name", "").strip()
    test_code = request.form.get("test_code", "").strip()
    sample_type = request.form.get("sample_type", "").strip()
    unit = request.form.get("unit", "").strip()
    min_val = request.form.get("reference_range_min")
    max_val = request.form.get("reference_range_max")
    cost = request.form.get("cost", "100.00")
    dept_id = request.form.get("department_id")
    description = request.form.get("description", "").strip()

    try:
        test = create_or_update_lab_test(
            db_session=db_session,
            name=name,
            test_code=test_code,
            sample_type=sample_type,
            cost=cost,
            unit=unit if unit else None,
            reference_range_min=float(min_val) if min_val and min_val.strip() else None,
            reference_range_max=float(max_val) if max_val and max_val.strip() else None,
            description=description if description else None,
            department_id=int(dept_id) if dept_id and dept_id.isdigit() else None,
            user_role=session.get("user_role")
        )
        flash(f"Diagnostic Test '{test.name}' ({test.test_code}) added to formulary.", "success")
    except (InvalidLabDataError, LabPermissionError) as e:
        flash(str(e), "danger")

    return redirect(url_for("laboratory.test_catalog"))


@laboratory_bp.route("/catalog/<int:test_id>/edit", methods=["POST"])
@login_required
@roles_required(RoleEnum.LAB_TECH, RoleEnum.ADMIN)
def edit_catalog_test(test_id: int):
    name = request.form.get("name", "").strip()
    test_code = request.form.get("test_code", "").strip()
    sample_type = request.form.get("sample_type", "").strip()
    unit = request.form.get("unit", "").strip()
    min_val = request.form.get("reference_range_min")
    max_val = request.form.get("reference_range_max")
    cost = request.form.get("cost", "100.00")
    dept_id = request.form.get("department_id")
    description = request.form.get("description", "").strip()

    try:
        test = create_or_update_lab_test(
            db_session=db_session,
            name=name,
            test_code=test_code,
            sample_type=sample_type,
            cost=cost,
            unit=unit if unit else None,
            reference_range_min=float(min_val) if min_val and min_val.strip() else None,
            reference_range_max=float(max_val) if max_val and max_val.strip() else None,
            description=description if description else None,
            department_id=int(dept_id) if dept_id and dept_id.isdigit() else None,
            test_id=test_id,
            user_role=session.get("user_role")
        )
        flash(f"Test '{test.name}' formulary entry updated successfully.", "success")
    except (InvalidLabDataError, LabPermissionError) as e:
        flash(str(e), "danger")

    return redirect(url_for("laboratory.test_catalog"))

