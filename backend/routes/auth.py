from datetime import datetime, date, timezone
from urllib.parse import urlparse
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from backend.database import db_session
from backend.models import User, Patient, Role, RoleEnum, GenderEnum, AuditLog
from backend.security import get_password_hash


auth_bp = Blueprint("auth", __name__)


def is_safe_redirect_url(target: str) -> bool:
    """Validate that the redirect target is a safe, relative URL to prevent open-redirect vulnerabilities."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(target)
    # Target must be relative (no scheme/netloc) and must not start with //
    return (test_url.scheme == "" and test_url.netloc == "" and not target.startswith("//") and target.startswith("/"))


def redirect_to_role_dashboard(role: str):
    """Map user role to its designated operational dashboard."""
    role_map = {
        "admin": "admin.dashboard",
        "doctor": "doctor.dashboard",
        "patient": "patient.dashboard",
        "receptionist": "receptionist.dashboard",
        "nurse": "nurse.dashboard",
        "pharmacist": "pharmacy.dashboard",
        "lab_tech": "laboratory.dashboard"
    }
    return redirect(url_for(role_map.get(role, "auth.login")))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session and request.method == "GET":
        return redirect_to_role_dashboard(session.get("user_role"))

    next_url = request.args.get("next") or request.form.get("next")

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        user = db_session.query(User).filter(User.email == email.lower()).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash("Your account has been deactivated. Please contact the hospital administrator.", "danger")
                return render_template("auth/login.html", next_url=next_url), 403

            # Prevent session fixation: clear previous session completely
            session.clear()
            session.permanent = True
            session["user_id"] = user.id
            session["user_email"] = user.email
            session["user_role"] = user.role.value
            session["user_name"] = user.full_name
            session["login_time"] = datetime.now(timezone.utc).isoformat()

            # Record security audit entry
            try:
                audit = AuditLog(
                    user_id=user.id,
                    action="USER_LOGIN",
                    resource_type="User",
                    resource_id=user.id,
                    ip_address=request.remote_addr,
                    details_json='{"status": "Login Successful", "auth_method": "Bcrypt"}'
                )
                db_session.add(audit)
                db_session.commit()
            except Exception:
                db_session.rollback()

            flash(f"Welcome back, {user.full_name}!", "success")

            # Redirect to safe next_url if present
            if next_url and is_safe_redirect_url(next_url):
                return redirect(next_url)

            return redirect_to_role_dashboard(user.role.value)
        else:
            # Audit failed login attempt
            try:
                audit = AuditLog(
                    user_id=user.id if user else None,
                    action="USER_LOGIN_FAILED",
                    resource_type="User",
                    resource_id=None,
                    ip_address=request.remote_addr,
                    details_json=f'{{"attempted_email": "{email}", "status": "Invalid credentials"}}'
                )
                db_session.add(audit)
                db_session.commit()
            except Exception:
                db_session.rollback()

            flash("Invalid email or password. Please verify your credentials and try again.", "danger")
            return render_template("auth/login.html", next_url=next_url, email=email), 401

    return render_template("auth/login.html", next_url=next_url)


@auth_bp.route("/logout")
def logout():
    user_id = session.get("user_id")
    if user_id:
        try:
            audit = AuditLog(
                user_id=user_id,
                action="USER_LOGOUT",
                resource_type="User",
                resource_id=user_id,
                ip_address=request.remote_addr,
                details_json='{"status": "Logged out securely"}'
            )
            db_session.add(audit)
            db_session.commit()
        except Exception:
            db_session.rollback()

    session.clear()
    flash("You have been logged out securely.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Public self-service patient registration."""
    if "user_id" in session:
        return redirect_to_role_dashboard(session.get("user_role"))

    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        phone = request.form.get("phone", "").strip()
        dob_str = request.form.get("dob", "").strip()
        gender_str = request.form.get("gender", "").strip().lower()
        blood_group = request.form.get("blood_group", "").strip()
        emergency_name = request.form.get("emergency_contact_name", "").strip()
        emergency_phone = request.form.get("emergency_contact_phone", "").strip()
        address = request.form.get("address", "").strip()
        allergies = request.form.get("allergies", "").strip()
        chronic = request.form.get("chronic_conditions", "").strip()

        # Validations
        errors = []
        if not first_name or not last_name:
            errors.append("First and last names are required.")
        if not email or "@" not in email:
            errors.append("A valid email address is required.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if not dob_str:
            errors.append("Date of birth is required.")

        # Check existing user
        existing = db_session.query(User).filter(User.email == email).first()
        if existing:
            errors.append("An account with this email address is already registered.")

        # Parse DOB
        dob = None
        if dob_str:
            try:
                dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
                if dob > date.today():
                    errors.append("Date of birth cannot be in the future.")
            except ValueError:
                errors.append("Invalid date format for date of birth (expected YYYY-MM-DD).")

        # Validate Gender
        try:
            gender_enum = GenderEnum(gender_str)
        except ValueError:
            gender_enum = GenderEnum.OTHER

        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template(
                "auth/register.html",
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                dob=dob_str,
                gender=gender_str,
                blood_group=blood_group,
                emergency_contact_name=emergency_name,
                emergency_contact_phone=emergency_phone,
                address=address,
                allergies=allergies,
                chronic_conditions=chronic
            ), 400

        # Get patient role
        patient_role = db_session.query(Role).filter(Role.name == RoleEnum.PATIENT.value).first()

        try:
            new_user = User(
                email=email,
                role=RoleEnum.PATIENT,
                role_id=patient_role.id if patient_role else None,
                first_name=first_name,
                last_name=last_name,
                phone=phone or None,
                is_active=True
            )
            new_user.set_password(password)
            db_session.add(new_user)
            db_session.flush()

            new_patient = Patient(
                id=new_user.id,
                dob=dob,
                gender=gender_enum,
                blood_group=blood_group or None,
                emergency_contact_name=emergency_name or None,
                emergency_contact_phone=emergency_phone or None,
                address=address or None,
                allergies=allergies or None,
                chronic_conditions=chronic or None
            )
            db_session.add(new_patient)

            # Audit log
            audit = AuditLog(
                user_id=new_user.id,
                action="PATIENT_REGISTRATION",
                resource_type="Patient",
                resource_id=new_user.id,
                ip_address=request.remote_addr,
                details_json=f'{{"email": "{email}", "full_name": "{new_user.full_name}"}}'
            )
            db_session.add(audit)
            db_session.commit()

            flash("Registration successful! You may now sign in with your credentials.", "success")
            return redirect(url_for("auth.login"))

        except Exception as ex:
            db_session.rollback()
            flash(f"An unexpected error occurred during registration: {str(ex)}", "danger")
            return render_template("auth/register.html")

    return render_template("auth/register.html")
