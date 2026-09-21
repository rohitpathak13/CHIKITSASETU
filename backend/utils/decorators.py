from functools import wraps
from flask import session, redirect, url_for, flash, request, abort, jsonify
from backend.models import RoleEnum, User, AuditLog
from backend.database import db_session


def normalize_role(role) -> str:
    """Normalize a role enum or string into its canonical value."""
    if isinstance(role, RoleEnum):
        return role.value
    role_str = str(role).lower().strip()
    if role_str == "lab_technician":
        return RoleEnum.LAB_TECH.value
    return role_str


def get_current_user():
    """Retrieve the currently authenticated User instance from db_session, or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db_session.query(User).filter(User.id == user_id).first()


def get_current_role() -> str:
    """Retrieve the current user's role string from session, or empty string."""
    return session.get("user_role", "")


def is_authenticated() -> bool:
    """Return True if an active user session exists."""
    return "user_id" in session


def has_role(*roles) -> bool:
    """Return True if the current user possesses any of the specified roles."""
    if not is_authenticated():
        return False
    user_role = get_current_role()
    allowed = {normalize_role(r) for r in roles}
    return user_role in allowed


def login_required(f):
    """Ensures the client has an active, authenticated session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized", "message": "Authentication required."}), 401
            return redirect(url_for("auth.login", next=request.url))

        # Check that user is still active in database
        user = get_current_user()
        if not user or not user.is_active:
            session.clear()
            flash("Your account has been deactivated or does not exist. Please sign in again.", "danger")
            return redirect(url_for("auth.login"))

        return f(*args, **kwargs)
    return decorated_function


def roles_required(*roles):
    """
    Ensures the logged-in user possesses at least one of the specified roles.
    Accepts RoleEnum instances or strings.
    If unauthenticated, redirects to login.
    If authenticated but role does not match, logs audit and raises 403 Forbidden.
    """
    allowed_roles = {normalize_role(r) for r in roles}

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to access this page.", "warning")
                if request.is_json or request.path.startswith("/api/"):
                    return jsonify({"error": "Unauthorized", "message": "Authentication required."}), 401
                return redirect(url_for("auth.login", next=request.url))

            user_role = normalize_role(session.get("user_role", ""))
            if user_role not in allowed_roles:
                # Log unauthorized access attempt for security auditing
                user_id = session.get("user_id")
                try:
                    audit = AuditLog(
                        user_id=user_id,
                        action="UNAUTHORIZED_ACCESS_ATTEMPT",
                        resource_type="Route",
                        resource_id=None,
                        ip_address=request.remote_addr,
                        details_json=f'{{"attempted_path": "{request.path}", "user_role": "{user_role}", "allowed_roles": {list(allowed_roles)}}}'
                    )
                    db_session.add(audit)
                    db_session.commit()
                except Exception:
                    db_session.rollback()

                if request.is_json or request.path.startswith("/api/"):
                    return jsonify({
                        "error": "Forbidden",
                        "message": f"Access denied. Role '{user_role}' is not authorized for this resource."
                    }), 403

                # Abort with HTTP 403 Forbidden
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Convenient role-specific shortcuts
def admin_required(f):
    return roles_required(RoleEnum.ADMIN)(f)


def doctor_required(f):
    return roles_required(RoleEnum.DOCTOR)(f)


def patient_required(f):
    return roles_required(RoleEnum.PATIENT)(f)


def receptionist_required(f):
    return roles_required(RoleEnum.RECEPTIONIST, RoleEnum.ADMIN)(f)


def nurse_required(f):
    return roles_required(RoleEnum.NURSE, RoleEnum.ADMIN)(f)


def pharmacist_required(f):
    return roles_required(RoleEnum.PHARMACIST, RoleEnum.ADMIN)(f)


def lab_technician_required(f):
    return roles_required(RoleEnum.LAB_TECH, RoleEnum.LAB_TECHNICIAN, RoleEnum.ADMIN)(f)


# Backward compatibility alias
lab_tech_required = lab_technician_required
