from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Optional

from core.database import db_session
from core.models import (
    Prescription, PrescriptionItem, Medicine, MedicineInventory, MedicineBatch,
    StockTransaction, StockTransactionTypeEnum,
    RoleEnum, PrescriptionStatusEnum, Notification, NotificationTypeEnum, AuditLog
)
from web.decorators import login_required, roles_required

from core.services.prescription_service import (
    dispense_prescription, cancel_prescription, get_prescription_detail,
    list_prescriptions, PrescriptionServiceError, PrescriptionNotFoundError,
    InvalidPrescriptionDataError
)
from core.services.pharmacy_service import (
    create_medicine, update_medicine, get_medicine, list_medicines,
    stock_in, stock_out, get_low_stock_medicines, get_expired_batches,
    get_expiring_soon_batches, get_pharmacy_dashboard_stats, list_stock_transactions,
    PharmacyServiceError, MedicineNotFoundError, BatchNotFoundError,
    InvalidInventoryDataError, InsufficientInventoryError
)

pharmacy_bp = Blueprint("pharmacy", __name__, url_prefix="/pharmacy")


@pharmacy_bp.route("/")
@login_required
@roles_required(RoleEnum.PHARMACIST, RoleEnum.ADMIN)
def dashboard():
    status_filter = request.args.get("status", "all")
    search_query = request.args.get("q", "").strip()

    prescriptions = list_prescriptions(
        db_session=db_session,
        status=status_filter if status_filter != "all" else None,
        search=search_query if search_query else None
    )

    stats = get_pharmacy_dashboard_stats(db_session)

    return render_template(
        "pharmacy/dashboard.html",
        active_page="pharm_dashboard",
        prescriptions=prescriptions,
        stats=stats,
        total_meds=stats["total_medicines"],
        low_stock_count=stats["low_stock_count"],
        low_stock_meds=stats["low_stock_medicines"],
        expired_count=stats["expired_batches_count"],
        expired_batches=stats["expired_batches"],
        expiring_soon_count=stats["expiring_soon_batches_count"],
        expiring_soon_batches=stats["expiring_soon_batches"],
        pending_count=stats["pending_prescriptions_count"],
        dispensed_count=stats["dispensed_prescriptions_count"],
        total_rx_count=stats["total_prescriptions_count"],
        current_status=status_filter,
        search_query=search_query,
        today_date=date.today()
    )


@pharmacy_bp.route("/prescription/<int:rx_id>")
@login_required
@roles_required(RoleEnum.PHARMACIST, RoleEnum.ADMIN)
def prescription_process(rx_id: int):
    """
    Renders detailed pharmacy fulfillment view with real-time FEFO batch stock inspection.
    """
    try:
        rx = get_prescription_detail(
            db_session=db_session,
            prescription_id=rx_id,
            requester_user_id=session.get("user_id"),
            requester_role=session.get("user_role")
        )
    except PrescriptionNotFoundError:
        flash("Prescription not found.", "danger")
        return redirect(url_for("pharmacy.dashboard"))

    # Inspect available unexpired batches for each item
    item_batch_map = {}
    for item in rx.items:
        batches = db_session.query(MedicineInventory).filter(
            MedicineInventory.medicine_id == item.medicine_id,
            MedicineInventory.expiry_date >= date.today(),
            MedicineInventory.quantity_in_stock > 0
        ).order_by(MedicineInventory.expiry_date.asc()).all()
        item_batch_map[item.id] = batches

    return render_template(
        "pharmacy/prescription_process.html",
        active_page="pharm_dashboard",
        rx=rx,
        item_batch_map=item_batch_map,
        today_date=date.today()
    )


@pharmacy_bp.route("/dispense/<int:rx_id>", methods=["POST"])
@login_required
@roles_required(RoleEnum.PHARMACIST, RoleEnum.ADMIN)
def dispense(rx_id: int):
    try:
        result = dispense_prescription(
            db_session=db_session,
            prescription_id=rx_id,
            actor_id=session.get("user_id"),
            ip_address=request.remote_addr
        )
        flash(
            f"Prescription #{rx_id} dispensed successfully. {result['units_dispensed']} unit(s) deducted via FEFO. Status: {result['status']}.",
            "success"
        )
    except (PrescriptionNotFoundError, PrescriptionServiceError) as e:
        flash(str(e), "danger")

    return redirect(url_for("pharmacy.dashboard"))


@pharmacy_bp.route("/cancel/<int:rx_id>", methods=["POST"])
@login_required
@roles_required(RoleEnum.PHARMACIST, RoleEnum.ADMIN)
def cancel(rx_id: int):
    reason = request.form.get("cancellation_reason", "").strip() or "Cancelled by pharmacy staff"
    try:
        rx = cancel_prescription(
            db_session=db_session,
            prescription_id=rx_id,
            actor_id=session.get("user_id"),
            cancellation_reason=reason,
            ip_address=request.remote_addr
        )
        flash(f"Prescription #{rx.id} was cancelled successfully.", "info")
    except (PrescriptionNotFoundError, PrescriptionServiceError, InvalidPrescriptionDataError) as e:
        flash(str(e), "danger")

    return redirect(url_for("pharmacy.dashboard"))


@pharmacy_bp.route("/inventory", methods=["GET", "POST"])
@login_required
@roles_required(RoleEnum.PHARMACIST, RoleEnum.ADMIN)
def inventory():
    if request.method == "POST":
        med_id = int(request.form.get("medicine_id"))
        batch_num = request.form.get("batch_number", "").strip()
        expiry_str = request.form.get("expiry_date")
        qty = int(request.form.get("quantity"))
        cost = Decimal(request.form.get("purchase_cost", "10.00"))
        selling_price_val = request.form.get("selling_price")
        supplier_val = request.form.get("supplier", "").strip() or None
        notes_val = request.form.get("notes", "").strip() or None

        selling_price = Decimal(selling_price_val) if selling_price_val else None

        try:
            res = stock_in(
                db_session=db_session,
                medicine_id=med_id,
                batch_number=batch_num,
                expiry_date=expiry_str,
                quantity=qty,
                purchase_cost=cost,
                selling_price=selling_price,
                supplier=supplier_val,
                performed_by_id=session.get("user_id"),
                notes=notes_val,
                ip_address=request.remote_addr
            )
            flash(f"Stock In successful: Added {qty} units to batch '{batch_num}'. Current batch stock: {res['quantity_in_stock']} units.", "success")
        except (PharmacyServiceError, Exception) as e:
            flash(f"Stock In Error: {str(e)}", "danger")

        return redirect(url_for("pharmacy.inventory", tab="batches"))

    tab = request.args.get("tab", "catalog")
    search_q = request.args.get("q", "").strip()
    category_filter = request.args.get("category", "")
    status_filter = request.args.get("status", "")

    # Medicines
    medicines = list_medicines(
        db_session=db_session,
        search=search_q if (tab == "catalog" and search_q) else None,
        category=category_filter if (tab == "catalog" and category_filter) else None,
        stock_status=status_filter if (tab == "catalog" and status_filter) else None
    )

    # Batches
    batch_query = db_session.query(MedicineInventory).join(MedicineInventory.medicine)
    if tab == "batches" and search_q:
        s_term = f"%{search_q}%"
        batch_query = batch_query.filter(
            (MedicineInventory.batch_number.ilike(s_term)) |
            (Medicine.name.ilike(s_term)) |
            (MedicineInventory.supplier.ilike(s_term))
        )
    if tab == "batches" and status_filter:
        today = date.today()
        if status_filter == "expired":
            batch_query = batch_query.filter(MedicineInventory.expiry_date < today, MedicineInventory.quantity_in_stock > 0)
        elif status_filter == "expiring_soon":
            batch_query = batch_query.filter(
                MedicineInventory.expiry_date >= today,
                MedicineInventory.expiry_date <= today + timedelta(days=30),
                MedicineInventory.quantity_in_stock > 0
            )
        elif status_filter == "active":
            batch_query = batch_query.filter(MedicineInventory.expiry_date >= today, MedicineInventory.quantity_in_stock > 0)
        elif status_filter == "out_of_stock":
            batch_query = batch_query.filter(MedicineInventory.quantity_in_stock <= 0)

    batches = batch_query.order_by(MedicineInventory.expiry_date.asc()).all()

    # Transactions / Movements Ledger
    transactions = list_stock_transactions(
        db_session=db_session,
        transaction_type=status_filter if (tab == "ledger" and status_filter) else None,
        limit=150
    )

    # All categories for filter dropdown
    all_categories = sorted(list({m.category for m in db_session.query(Medicine).all() if m.category}))
    all_meds_for_dropdown = db_session.query(Medicine).order_by(Medicine.name.asc()).all()

    return render_template(
        "pharmacy/inventory.html",
        active_page="pharm_inventory",
        tab=tab,
        medicines=medicines,
        batches=batches,
        transactions=transactions,
        all_categories=all_categories,
        all_meds_for_dropdown=all_meds_for_dropdown,
        search_query=search_q,
        category_filter=category_filter,
        status_filter=status_filter,
        today_date=date.today()
    )


@pharmacy_bp.route("/medicine/add", methods=["POST"])
@login_required
@roles_required(RoleEnum.PHARMACIST, RoleEnum.ADMIN)
def add_medicine():
    try:
        med = create_medicine(
            db_session=db_session,
            name=request.form.get("name"),
            generic_name=request.form.get("generic_name"),
            category=request.form.get("category"),
            unit=request.form.get("unit"),
            unit_price=request.form.get("unit_price"),
            purchase_price=request.form.get("purchase_price") or "0.00",
            reorder_level=int(request.form.get("reorder_level", 20)),
            supplier=request.form.get("supplier"),
            manufacturer=request.form.get("manufacturer"),
            description=request.form.get("description"),
            actor_id=session.get("user_id"),
            ip_address=request.remote_addr
        )
        flash(f"Medication '{med.name}' added to formulary catalog successfully.", "success")
    except (PharmacyServiceError, Exception) as e:
        flash(f"Failed to add medicine: {str(e)}", "danger")

    return redirect(url_for("pharmacy.inventory", tab="catalog"))


@pharmacy_bp.route("/medicine/<int:medicine_id>/edit", methods=["POST"])
@login_required
@roles_required(RoleEnum.PHARMACIST, RoleEnum.ADMIN)
def edit_medicine(medicine_id: int):
    try:
        med = update_medicine(
            db_session=db_session,
            medicine_id=medicine_id,
            name=request.form.get("name"),
            generic_name=request.form.get("generic_name"),
            category=request.form.get("category"),
            unit=request.form.get("unit"),
            unit_price=request.form.get("unit_price"),
            purchase_price=request.form.get("purchase_price"),
            reorder_level=request.form.get("reorder_level"),
            supplier=request.form.get("supplier"),
            manufacturer=request.form.get("manufacturer"),
            description=request.form.get("description"),
            actor_id=session.get("user_id"),
            ip_address=request.remote_addr
        )
        flash(f"Medication '{med.name}' updated successfully.", "success")
    except (PharmacyServiceError, Exception) as e:
        flash(f"Failed to update medicine: {str(e)}", "danger")

    return redirect(url_for("pharmacy.inventory", tab="catalog"))


@pharmacy_bp.route("/stock-in", methods=["POST"])
@login_required
@roles_required(RoleEnum.PHARMACIST, RoleEnum.ADMIN)
def stock_in_route():
    try:
        med_id = int(request.form.get("medicine_id"))
        batch_num = request.form.get("batch_number", "").strip()
        exp_date = request.form.get("expiry_date")
        qty = int(request.form.get("quantity"))
        cost = Decimal(request.form.get("purchase_cost", "0.00"))
        selling_price_val = request.form.get("selling_price")
        selling_price = Decimal(selling_price_val) if selling_price_val else None
        supplier_val = request.form.get("supplier", "").strip() or None
        notes_val = request.form.get("notes", "").strip() or None

        res = stock_in(
            db_session=db_session,
            medicine_id=med_id,
            batch_number=batch_num,
            expiry_date=exp_date,
            quantity=qty,
            purchase_cost=cost,
            selling_price=selling_price,
            supplier=supplier_val,
            performed_by_id=session.get("user_id"),
            notes=notes_val,
            ip_address=request.remote_addr
        )
        flash(f"Stock In recorded: Received {qty} units for Batch #{batch_num}. Total available: {res['total_medicine_stock']} units.", "success")
    except (PharmacyServiceError, Exception) as e:
        flash(f"Stock In Error: {str(e)}", "danger")

    return redirect(url_for("pharmacy.inventory", tab="batches"))


@pharmacy_bp.route("/stock-out", methods=["POST"])
@login_required
@roles_required(RoleEnum.PHARMACIST, RoleEnum.ADMIN)
def stock_out_route():
    try:
        batch_id = int(request.form.get("batch_id"))
        qty = int(request.form.get("quantity"))
        reason = request.form.get("reason", "").strip()
        notes = request.form.get("notes", "").strip() or None

        res = stock_out(
            db_session=db_session,
            batch_id=batch_id,
            quantity=qty,
            reason=reason,
            performed_by_id=session.get("user_id"),
            notes=notes,
            ip_address=request.remote_addr
        )
        flash(f"Stock Out recorded: Deducted {qty} units from Batch #{res['batch_number']}. Reason: {reason}. Remaining: {res['remaining_batch_stock']} units.", "info")
    except (PharmacyServiceError, Exception) as e:
        flash(f"Stock Out Error: {str(e)}", "danger")

    return redirect(url_for("pharmacy.inventory", tab="batches"))


@pharmacy_bp.route("/reorder/<int:medicine_id>", methods=["POST"])
@login_required
@roles_required(RoleEnum.PHARMACIST, RoleEnum.ADMIN)
def reorder_stock(medicine_id: int):
    med = db_session.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not med:
        flash("Medicine not found.", "danger")
        return redirect(url_for("pharmacy.dashboard"))

    batch_num = request.form.get("batch_number", "").strip() or f"BT-{med.id}-{int(datetime.now(timezone.utc).timestamp())}"
    expiry_str = request.form.get("expiry_date")
    qty = int(request.form.get("quantity", 100))
    cost = Decimal(request.form.get("purchase_cost", "12.00"))
    supplier_val = request.form.get("supplier", "").strip() or med.supplier

    try:
        exp_date = datetime.strptime(expiry_str, "%Y-%m-%d").date() if expiry_str else (date.today() + timedelta(days=365))
    except Exception:
        exp_date = date.today() + timedelta(days=365)

    try:
        stock_in(
            db_session=db_session,
            medicine_id=med.id,
            batch_number=batch_num,
            expiry_date=exp_date,
            quantity=qty,
            purchase_cost=cost,
            supplier=supplier_val,
            performed_by_id=session.get("user_id"),
            notes=f"Quick replenishment from Low Stock alert.",
            ip_address=request.remote_addr
        )
        flash(f"Restocked {qty} units of {med.name} (Batch #{batch_num}). Current total: {med.total_stock} units.", "success")
    except (PharmacyServiceError, Exception) as e:
        flash(f"Restock error: {str(e)}", "danger")

    return redirect(url_for("pharmacy.dashboard"))
