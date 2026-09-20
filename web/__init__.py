import os
from datetime import timedelta
from flask import Flask, redirect, url_for, session, render_template
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from core.config import settings
from core.database import db_session, init_db, Base
from core.models import User, Notification

migrate = Migrate()
csrf = CSRFProtect()

def create_app() -> Flask:
    """Flask Application Factory."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )

    app.config["SECRET_KEY"] = settings.SECRET_KEY
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = settings.DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = settings.SESSION_COOKIE_SECURE
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)

    # Initialize CSRF Protection
    csrf.init_app(app)

    # Initialize Flask-Migrate
    migrate.init_app(app, db=Base.metadata)

    # Defensive HTTP Security Headers
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Custom HTTP Error Handlers
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template("errors/403.html", error=error), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html", error=error), 404

    @app.errorhandler(500)
    def internal_server_error(error):
        db_session.rollback()
        return render_template("errors/500.html", error=error), 500

    # Ensure database tables exist
    init_db()

    # Teardown database session per request
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db_session.remove()

    # Context processor to inject active session user and notifications into templates
    @app.context_processor
    def inject_user():
        user_id = session.get("user_id")
        current_user = None
        recent_notifications = []
        unread_notifications_count = 0
        if user_id:
            current_user = db_session.query(User).filter(User.id == user_id).first()
            if current_user:
                recent_notifications = (
                    db_session.query(Notification)
                    .filter(Notification.user_id == user_id)
                    .order_by(Notification.created_at.desc())
                    .limit(6)
                    .all()
                )
                unread_notifications_count = (
                    db_session.query(Notification)
                    .filter(Notification.user_id == user_id, Notification.is_read == False)
                    .count()
                )
        return dict(
            current_user=current_user,
            recent_notifications=recent_notifications,
            unread_notifications_count=unread_notifications_count
        )

    # Register Blueprints
    from web.blueprints.auth import auth_bp
    from web.blueprints.admin import admin_bp
    from web.blueprints.doctor import doctor_bp
    from web.blueprints.patient import patient_bp
    from web.blueprints.receptionist import receptionist_bp
    from web.blueprints.nurse import nurse_bp
    from web.blueprints.pharmacy import pharmacy_bp
    from web.blueprints.laboratory import laboratory_bp
    from web.blueprints.billing import billing_bp
    from web.blueprints.analytics import analytics_bp
    from web.blueprints.notifications import notifications_bp
    from web.blueprints.appointment import appointment_bp
    from web.blueprints.ipd import ipd_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(receptionist_bp)
    app.register_blueprint(nurse_bp)
    app.register_blueprint(pharmacy_bp)
    app.register_blueprint(laboratory_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(appointment_bp)
    app.register_blueprint(ipd_bp)

    @app.route("/")
    def index():
        if "user_id" in session:
            role = session.get("user_role")
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
        return redirect(url_for("auth.login"))

    return app
