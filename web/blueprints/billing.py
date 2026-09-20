from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from datetime import datetime, date, timezone
from decimal import Decimal
import json

from core.database import db_session
from core.models import (
    Bill, BillItem, Invoice, InvoiceItem, Payment, Patient, User,
    RoleEnum, BillStatusEnum, PaymentStatusEnum, ItemTypeEnum, PaymentMethodEnum
)
from core.services import billing_service
from web.decorators import login_required, roles_required

billing_bp = Blueprint("billing", __name__, url_prefix="/billing")


@billing_bp.route("/")
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.RECEPTIONIST, RoleEnum.DOCTOR)
def dashboard():
    """
    Billing operations dashboard with search query, payment status filter,
    component filter, date range, and KPI summary stats.
    """
    search_query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all").strip().lower()
    item_type_filter = request.args.get("item_type", "all").strip().lower()
    start_date_str = request.args.get("start_date", "").strip()
    end_date_str = request.args.get("end_date", "").strip()

    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    invoices, total_count = billing_service.search_and_filter_bills(
        db=db_session,
        query=search_query,
        status=status_filter,
        item_type=item_type_filter if item_type_filter != "all" else None,
        start_date=start_date,
        end_date=end_date,
        limit=150
    )

    stats = billing_service.get_billing_dashboard_stats(db_session)

    # Component list for filter dropdown
    components = [
        {"value": "consultation", "label": "Consultation"},
        {"value": "laboratory", "label": "Laboratory"},
        {"value": "medicines", "label": "Medicines"},
        {"value": "room", "label": "Room"},
        {"value": "bed", "label": "Bed"},
        {"value": "procedures", "label": "Procedures"},
        {"value": "other_services", "label": "Other Services"}
    ]

    return render_template(
        "billing/dashboard.html",
        active_page="billing_dashboard",
        invoices=invoices,
        total_count=total_count,
        stats=stats,
        total_billed=stats["total_billed"],
        total_collected=stats["total_collected"],
        total_due=stats["total_due"],
        total_refunds=stats["total_refunds"],
        search_query=search_query,
        status_filter=status_filter,
        item_type_filter=item_type_filter,
        start_date=start_date_str,
        end_date=end_date_str,
        components=components
    )


@billing_bp.route("/create", methods=["GET", "POST"])
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.RECEPTIONIST)
def create_bill():
    """Generates a new multi-component hospital bill."""
    if request.method == "POST":
        patient_id = request.form.get("patient_id", type=int)
        discount_val = request.form.get("discount", "0.0")
        discount_type = request.form.get("discount_type", "amount")
        tax_rate_val = request.form.get("tax_rate", "0.05")
        insurance_covered_val = request.form.get("insurance_covered", "0.0")
        due_date_str = request.form.get("due_date", "").strip()
        notes = request.form.get("notes", "").strip()

        # Extract items from repeatable fields
        item_types = request.form.getlist("item_type[]")
        descriptions = request.form.getlist("description[]")
        unit_prices = request.form.getlist("unit_price[]")
        quantities = request.form.getlist("quantity[]")

        items_payload = []
        for itype, desc, uprice, qty in zip(item_types, descriptions, unit_prices, quantities):
            if desc.strip() and uprice.strip():
                try:
                    items_payload.append({
                        "item_type": itype.strip().lower(),
                        "description": desc.strip(),
                        "unit_price": Decimal(uprice.strip()),
                        "quantity": int(qty.strip() or 1)
                    })
                except Exception:
                    continue

        if not items_payload:
            flash("Please add at least one bill item with description and price.", "danger")
            return redirect(url_for("billing.create_bill"))

        due_date = None
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        try:
            bill = billing_service.create_bill(
                db=db_session,
                patient_id=patient_id,
                items=items_payload,
                discount=Decimal(discount_val or "0.00"),
                discount_type=discount_type,
                tax_rate=Decimal(tax_rate_val or "0.05"),
                insurance_covered=Decimal(insurance_covered_val or "0.00"),
                due_date=due_date,
                notes=notes,
                actor_id=session.get("user_id")
            )
            db_session.commit()
            flash(f"Hospital bill #{bill.bill_number} generated successfully!", "success")
            return redirect(url_for("billing.invoice_detail", invoice_id=bill.id))
        except billing_service.BillingServiceError as be:
            db_session.rollback()
            flash(str(be), "danger")
        except Exception as e:
            db_session.rollback()
            flash(f"Failed to generate bill: {str(e)}", "danger")

    # GET: Load patients for selection
    patients = db_session.query(Patient).join(User, Patient.user_id == User.id).order_by(User.last_name.asc()).all()
    components = [
        ("consultation", "Consultation"),
        ("laboratory", "Laboratory"),
        ("medicines", "Medicines"),
        ("room", "Room"),
        ("bed", "Bed"),
        ("procedures", "Procedures"),
        ("other_services", "Other Services"),
    ]
    return render_template(
        "billing/create_bill.html",
        active_page="billing_create",
        patients=patients,
        components=components
    )


@billing_bp.route("/invoice/<int:invoice_id>")
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.RECEPTIONIST, RoleEnum.DOCTOR, RoleEnum.PATIENT)
def invoice_detail(invoice_id: int):
    """Renders the executive professional hospital invoice."""
    inv = db_session.query(Bill).filter(Bill.id == invoice_id).first()
    if not inv:
        flash("Invoice not found.", "danger")
        return redirect(url_for("billing.dashboard"))

    # If patient, verify ownership
    user_id = session.get("user_id")
    if session.get("user_role") == RoleEnum.PATIENT.value:
        is_own = (inv.patient_id == user_id) or (inv.patient and inv.patient.user_id == user_id)
        if not is_own:
            abort(403)

    return render_template(
        "billing/invoice_detail.html",
        invoice=inv,
        active_page="billing_dashboard"
    )


@billing_bp.route("/pay/<int:invoice_id>", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.RECEPTIONIST)
def process_payment(invoice_id: int):
    """Processes a partial or full payment against an invoice."""
    amount_str = request.form.get("amount", "0.0")
    method_str = request.form.get("payment_method", "cash")
    ref = request.form.get("transaction_reference", "").strip()
    notes = request.form.get("notes", "").strip()

    try:
        amt = Decimal(amount_str)
        payment, bill = billing_service.record_payment(
            db=db_session,
            bill_id=invoice_id,
            amount=amt,
            payment_method=method_str,
            transaction_reference=ref,
            notes=notes,
            actor_id=session.get("user_id")
        )
        db_session.commit()
        flash(
            f"Payment of ${amt:.2f} recorded successfully via {payment.payment_method.value.upper()}. Invoice status: {bill.status.value.upper()}.",
            "success"
        )
    except billing_service.BillingServiceError as bse:
        db_session.rollback()
        flash(str(bse), "danger")
    except Exception as e:
        db_session.rollback()
        flash(f"Payment failed: {str(e)}", "danger")

    return redirect(url_for("billing.invoice_detail", invoice_id=invoice_id))


@billing_bp.route("/refund/<int:invoice_id>", methods=["POST"])
@login_required
@roles_required(RoleEnum.ADMIN)
def process_refund(invoice_id: int):
    """Processes a partial or full refund for a settled invoice."""
    amount_str = request.form.get("refund_amount", "0.0")
    reason = request.form.get("reason", "").strip()

    try:
        amt = Decimal(amount_str)
        refund, bill = billing_service.process_refund(
            db=db_session,
            bill_id=invoice_id,
            amount=amt,
            reason=reason,
            actor_id=session.get("user_id")
        )
        db_session.commit()
        flash(
            f"Refund of ${amt:.2f} processed successfully. Invoice status: {bill.status.value.upper()}.",
            "success"
        )
    except billing_service.BillingServiceError as bse:
        db_session.rollback()
        flash(str(bse), "danger")
    except Exception as e:
        db_session.rollback()
        flash(f"Refund processing failed: {str(e)}", "danger")

    return redirect(url_for("billing.invoice_detail", invoice_id=invoice_id))

