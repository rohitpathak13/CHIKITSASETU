from flask import Blueprint, render_template, request, session, jsonify
from core.database import db_session
from web.decorators import login_required, roles_required
from core.models import RoleEnum
from core.services.analytics_service import (
    get_patient_growth_data,
    get_appointment_trends_data,
    get_department_statistics_data,
    get_doctor_workload_data,
    get_disease_distribution_data,
    get_age_distribution_data,
    get_gender_distribution_data,
    get_admission_trends_data,
    get_discharge_trends_data,
    get_bed_occupancy_data,
    get_revenue_trends_data,
    get_lab_test_trends_data,
    get_pharmacy_inventory_data,
    get_appointment_cancellation_data,
    get_appointment_no_show_data,
    get_hospital_analytics_summary
)
from ml.analytics.plotly_charts import (
    build_patient_growth_chart,
    build_appointment_trends_chart,
    build_department_stats_chart,
    build_doctor_workload_chart,
    build_disease_distribution_chart,
    build_age_distribution_chart,
    build_gender_distribution_chart,
    build_admission_trends_chart,
    build_discharge_trends_chart,
    build_bed_occupancy_gauge,
    build_ward_breakdown_bar,
    build_revenue_trends_chart,
    build_revenue_donut_chart,
    build_lab_trends_chart,
    build_pharmacy_inventory_chart,
    build_cancellation_chart,
    build_no_show_chart,
    build_patient_census_trend
)

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@analytics_bp.route("/")
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.DOCTOR)
def dashboard():
    # 1. Parse timeframe filter
    timeframe = request.args.get("timeframe", "30")
    if timeframe == "all":
        days = None
    else:
        try:
            days = int(timeframe)
        except (ValueError, TypeError):
            days = 30
            timeframe = "30"

    # 2. Extract tabular analytics via Pandas & SQLAlchemy pipelines
    patient_growth = get_patient_growth_data(db_session, days=days)
    appointment_trends = get_appointment_trends_data(db_session, days=days)
    dept_stats = get_department_statistics_data(db_session)
    doctor_workload = get_doctor_workload_data(db_session)
    disease_dist = get_disease_distribution_data(db_session)
    age_dist = get_age_distribution_data(db_session)
    gender_dist = get_gender_distribution_data(db_session)
    adm_trends = get_admission_trends_data(db_session, days=days)
    dis_trends = get_discharge_trends_data(db_session, days=days)
    bed_stats = get_bed_occupancy_data(db_session)
    revenue_trends = get_revenue_trends_data(db_session, days=days)
    lab_trends = get_lab_test_trends_data(db_session, days=days)
    pharmacy_stats = get_pharmacy_inventory_data(db_session)
    cancellation_data = get_appointment_cancellation_data(db_session, days=days)
    no_show_data = get_appointment_no_show_data(db_session, days=days)
    summary_kpis = get_hospital_analytics_summary(db_session)

    # 3. Build responsive, interactive Plotly JSON charts for all 15 domains
    chart_patient_growth = build_patient_growth_chart(patient_growth)
    chart_appointment_trends = build_appointment_trends_chart(appointment_trends)
    chart_dept_stats = build_department_stats_chart(dept_stats)
    chart_doctor_workload = build_doctor_workload_chart(doctor_workload)
    chart_disease_dist = build_disease_distribution_chart(disease_dist)
    chart_age_dist = build_age_distribution_chart(age_dist)
    chart_gender_dist = build_gender_distribution_chart(gender_dist)
    chart_adm_trends = build_admission_trends_chart(adm_trends)
    chart_dis_trends = build_discharge_trends_chart(dis_trends)
    chart_bed_gauge = build_bed_occupancy_gauge(bed_stats["occupancy_rate"])
    chart_ward_bar = build_ward_breakdown_bar(bed_stats["ward_breakdown"])
    chart_revenue_trends = build_revenue_trends_chart(revenue_trends)
    chart_revenue_donut = build_revenue_donut_chart(revenue_trends["categories"])
    chart_lab_trends = build_lab_trends_chart(lab_trends)
    chart_pharmacy_inventory = build_pharmacy_inventory_chart(pharmacy_stats)
    chart_cancellation = build_cancellation_chart(cancellation_data)
    chart_no_show = build_no_show_chart(no_show_data)
    chart_census_flow = build_patient_census_trend(adm_trends, dis_trends)

    return render_template(
        "analytics/dashboard.html",
        active_page="analytics",
        timeframe=timeframe,
        summary_kpis=summary_kpis,
        bed_stats=bed_stats,
        revenue_stats=revenue_trends["summary"],
        appointment_stats=appointment_trends["summary"],
        pharmacy_stats=pharmacy_stats,
        no_show_stats=no_show_data,
        cancellation_stats=cancellation_data,
        chart_patient_growth=chart_patient_growth,
        chart_appointment_trends=chart_appointment_trends,
        chart_dept_stats=chart_dept_stats,
        chart_doctor_workload=chart_doctor_workload,
        chart_disease_dist=chart_disease_dist,
        chart_age_dist=chart_age_dist,
        chart_gender_dist=chart_gender_dist,
        chart_adm_trends=chart_adm_trends,
        chart_dis_trends=chart_dis_trends,
        chart_bed_gauge=chart_bed_gauge,
        chart_ward_bar=chart_ward_bar,
        chart_revenue_trends=chart_revenue_trends,
        chart_revenue_donut=chart_revenue_donut,
        chart_lab_trends=chart_lab_trends,
        chart_pharmacy_inventory=chart_pharmacy_inventory,
        chart_cancellation=chart_cancellation,
        chart_no_show=chart_no_show,
        chart_census_flow=chart_census_flow
    )


@analytics_bp.route("/api/summary")
@login_required
@roles_required(RoleEnum.ADMIN, RoleEnum.DOCTOR)
def api_summary():
    """Returns JSON payload of executive summary KPIs."""
    summary = get_hospital_analytics_summary(db_session)
    return jsonify(summary)
