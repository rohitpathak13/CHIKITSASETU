import os
from datetime import timedelta
from flask import Flask, redirect, url_for, session, render_template
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from backend.config import settings
from backend.database import db_session, init_db, Base
from backend.models import User, Notification

migrate = Migrate()
csrf = CSRFProtect()

def create_app() -> Flask:
    """Flask Application Factory configured for decoupled Frontend/Backend layout."""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    frontend_dir = os.path.join(project_root, "frontend")
    template_dir = os.path.join(frontend_dir, "templates")
    static_dir = os.path.join(frontend_dir, "static")

    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir,
        static_url_path="/static"
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

    # Register Blueprints from backend.routes
    from backend.routes.auth import auth_bp
    from backend.routes.admin import admin_bp
    from backend.routes.doctor import doctor_bp
    from backend.routes.patient import patient_bp
    from backend.routes.receptionist import receptionist_bp
    from backend.routes.nurse import nurse_bp
    from backend.routes.pharmacy import pharmacy_bp
    from backend.routes.laboratory import laboratory_bp
    from backend.routes.billing import billing_bp
    from backend.routes.analytics import analytics_bp
    from backend.routes.notifications import notifications_bp
    from backend.routes.appointment import appointment_bp
    from backend.routes.ipd import ipd_bp
    from backend.chatbot import chatbot_bp

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
    app.register_blueprint(chatbot_bp)

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

    @app.route("/health")
    def health():
        return {"status": "ok", "service": "CHIKITSASETU Web Portal"}, 200

    return app
