"""
Integration tests for Hospital Analytics Module.
Tests web views, timeframe filters, RBAC access control, and RESTful API endpoints.
"""

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest

from core.models import User, RoleEnum, Patient, GenderEnum


def test_flask_analytics_dashboard_admin_access(flask_client, admin_user):
    """
    Verifies that an administrator can load the analytics dashboard and that
    all 15 interactive Plotly chart containers and KPI elements are rendered.
    """
    with flask_client.session_transaction() as sess:
        sess["user_id"] = admin_user.id
        sess["user_role"] = "admin"

    response = flask_client.get("/analytics/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    # Verify header and title
    assert "Hospital Analytics &amp; BI" in html or "Hospital Analytics" in html
    assert "Executive Business Intelligence" in html

    # Verify all 15 chart container DOM IDs exist in HTML
    chart_ids = [
        "chart-patient-growth",
        "chart-appointment-trends",
        "chart-dept-stats",
        "chart-doctor-workload",
        "chart-disease-dist",
        "chart-age-dist",
        "chart-gender-dist",
        "chart-adm-trends",
        "chart-dis-trends",
        "chart-bed-gauge",
        "chart-ward-bar",
        "chart-revenue-trends",
        "chart-revenue-donut",
        "chart-lab-trends",
        "chart-pharmacy-inventory",
        "chart-cancellation",
        "chart-no-show"
    ]
    for cid in chart_ids:
        assert f'id="{cid}"' in html, f"Missing chart container: {cid}"

    # Verify timeframe filter tabs
    assert "7 Days" in html
    assert "30 Days" in html
    assert "90 Days" in html
    assert "All Time" in html


def test_flask_analytics_timeframe_filters(flask_client, admin_user):
    """
    Tests timeframe filtering parameters on the web dashboard.
    """
    with flask_client.session_transaction() as sess:
        sess["user_id"] = admin_user.id
        sess["user_role"] = "admin"

    # 7-day view
    resp_7 = flask_client.get("/analytics/?timeframe=7")
    assert resp_7.status_code == 200

    # 90-day view
    resp_90 = flask_client.get("/analytics/?timeframe=90")
    assert resp_90.status_code == 200

    # All-time view
    resp_all = flask_client.get("/analytics/?timeframe=all")
    assert resp_all.status_code == 200


def test_flask_analytics_api_summary(flask_client, admin_user):
    """
    Tests the JSON summary endpoint used for dynamic UI widgets.
    """
    with flask_client.session_transaction() as sess:
        sess["user_id"] = admin_user.id
        sess["user_role"] = "admin"

    response = flask_client.get("/analytics/api/summary")
    assert response.status_code == 200
    data = response.get_json()
    assert "total_patients" in data
    assert "bed_occupancy_rate" in data
    assert "total_billed_revenue" in data
    assert "total_appointments_30d" in data
    assert "pharmacy_low_stock_alerts" in data


def test_flask_analytics_rbac_unauthorized_role(flask_client, db_session):
    """
    Verifies that non-authorized roles (such as patients) receive 403 Forbidden.
    """
    u_pat = User(email="patient_unauth@medicare.ai", password_hash="hash", role=RoleEnum.PATIENT, first_name="Unauth", last_name="Patient")
    db_session.add(u_pat)
    db_session.commit()

    with flask_client.session_transaction() as sess:
        sess["user_id"] = u_pat.id
        sess["user_role"] = "patient"

    response = flask_client.get("/analytics/")
    assert response.status_code == 403


def test_fastapi_analytics_rest_endpoints(fastapi_client, admin_auth_headers):
    """
    Tests the FastAPI REST endpoints under /api/v1/analytics/*
    """
    # 1. Summary KPIs
    resp_sum = fastapi_client.get("/api/v1/analytics/summary", headers=admin_auth_headers)
    assert resp_sum.status_code == 200
    sum_json = resp_sum.json()
    assert "total_patients" in sum_json
    assert "bed_occupancy_rate" in sum_json
    assert "total_billed_revenue" in sum_json

    # 2. All Plotly Chart JSON specs
    resp_charts = fastapi_client.get("/api/v1/analytics/charts?days=30", headers=admin_auth_headers)
    assert resp_charts.status_code == 200
    charts_json = resp_charts.json()
    assert "chart_patient_growth" in charts_json
    assert "chart_bed_gauge" in charts_json
    assert "chart_revenue_trends" in charts_json
    assert "chart_lab_trends" in charts_json
    assert "chart_pharmacy_inventory" in charts_json

    # 3. Patient Growth
    resp_pg = fastapi_client.get("/api/v1/analytics/patient-growth?days=30", headers=admin_auth_headers)
    assert resp_pg.status_code == 200
    pg_json = resp_pg.json()
    assert "cumulative_patients" in pg_json
    assert "new_patients" in pg_json

    # 4. Bed Occupancy
    resp_bo = fastapi_client.get("/api/v1/analytics/bed-occupancy", headers=admin_auth_headers)
    assert resp_bo.status_code == 200
    bo_json = resp_bo.json()
    assert "occupancy_rate" in bo_json
    assert "ward_breakdown" in bo_json

    # 5. Revenue Trends
    resp_rev = fastapi_client.get("/api/v1/analytics/revenue-trends?days=30", headers=admin_auth_headers)
    assert resp_rev.status_code == 200
    rev_json = resp_rev.json()
    assert "billed" in rev_json
    assert "collected" in rev_json
    assert "summary" in rev_json

    # 6. Appointment Trends
    resp_app = fastapi_client.get("/api/v1/analytics/appointment-trends?days=30", headers=admin_auth_headers)
    assert resp_app.status_code == 200
    app_json = resp_app.json()
    assert "completed" in app_json
    assert "summary" in app_json
