from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from core.database import db_session
from core.models import Notification, NotificationTypeEnum, RoleEnum
from core.services.notification_service import NotificationService
from web.decorators import login_required

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")

@notifications_bp.route("/")
@login_required
def index():
    user_id = session.get("user_id")
    role_str = session.get("user_role")
    role = None
    if role_str:
        try:
            role = RoleEnum(role_str)
        except ValueError:
            role = None

    filter_type_str = request.args.get("type", "all")
    filter_unread = request.args.get("unread", "0") == "1"

    filter_type = None
    if filter_type_str != "all":
        try:
            filter_type = NotificationTypeEnum(filter_type_str)
        except ValueError:
            pass

    notifications, total = NotificationService.get_notification_history(
        db=db_session,
        user_id=user_id,
        role=role,
        is_read=False if filter_unread else None,
        type=filter_type,
        limit=100
    )

    unread_count = NotificationService.get_unread_count(
        db=db_session,
        user_id=user_id,
        role=role
    )

    return render_template(
        "notifications/index.html",
        active_page="notifications",
        notifications=notifications,
        unread_count=unread_count,
        filter_type=filter_type_str,
        filter_unread=filter_unread
    )

@notifications_bp.route("/mark-read/<int:notif_id>", methods=["POST"])
@login_required
def mark_read(notif_id: int):
    user_id = session.get("user_id")
    role_str = session.get("user_role")
    role = None
    if role_str:
        try:
            role = RoleEnum(role_str)
        except ValueError:
            role = None

    NotificationService.mark_as_read(
        db=db_session,
        notification_id=notif_id,
        user_id=user_id,
        role=role
    )

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({"success": True, "notification_id": notif_id})

    referrer = request.referrer or url_for("notifications.index")
    return redirect(referrer)

@notifications_bp.route("/mark-all-read", methods=["POST"])
@login_required
def mark_all_read():
    user_id = session.get("user_id")
    role_str = session.get("user_role")
    role = None
    if role_str:
        try:
            role = RoleEnum(role_str)
        except ValueError:
            role = None

    count = NotificationService.mark_all_as_read(
        db=db_session,
        user_id=user_id,
        role=role
    )

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({"success": True, "marked_count": count})

    flash(f"{count} notifications marked as read.", "info")
    referrer = request.referrer or url_for("notifications.index")
    return redirect(referrer)
