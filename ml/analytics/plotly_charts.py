"""
Plotly Chart Generator for Hospital Analytics & Business Intelligence.

Renders responsive, interactive, clinical-grade charts for all 15 operational,
clinical, and financial domains. Generates serialized JSON compatible with Plotly.js.
Handles empty datasets safely with zero hardcoded statistics.
"""

import json
import plotly.graph_objects as go
import plotly.express as px
from typing import List, Dict, Any, Optional

# Clinical Modern Palette matching the design system
COLOR_PRIMARY = "#0D9488"    # Clinical Teal
COLOR_SECONDARY = "#0284C7"  # Medical Azure
COLOR_ACCENT = "#F59E0B"     # Amber Warning
COLOR_DANGER = "#EF4444"     # Rose Red / Alert
COLOR_PURPLE = "#8B5CF6"     # Indigo / Diagnostic
COLOR_EMERALD = "#10B981"    # Success Emerald
COLOR_MUTED = "#64748B"      # Slate Gray
COLOR_BG = "rgba(0, 0, 0, 0)"# Transparent for glassmorphic cards
FONT_FAMILY = "Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif"

def _empty_figure(message: str = "No data available in selected period", height: int = 260) -> str:
    """Returns a clean empty figure placeholder when data is absent."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=13, color="#94A3B8", family=FONT_FAMILY)
    )
    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=height,
        margin=dict(l=20, r=20, t=30, b=30),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False)
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 1. Patient Growth Chart
# ---------------------------------------------------------------------------

def build_patient_growth_chart(data: Dict[str, Any]) -> str:
    """Area + Line chart displaying daily registrations and cumulative patient census."""
    dates = data.get("dates", [])
    new_pts = data.get("new_patients", [])
    cum_pts = data.get("cumulative_patients", [])

    if not dates or not cum_pts:
        return _empty_figure("No patient registration records found")

    fig = go.Figure()
    # Cumulative Growth Area
    fig.add_trace(go.Scatter(
        x=dates, y=cum_pts,
        name="Cumulative Census",
        mode="lines+markers",
        line=dict(color=COLOR_PRIMARY, width=3),
        fill="tozeroy",
        fillcolor="rgba(13, 148, 136, 0.12)",
        marker=dict(size=5)
    ))
    # Daily Registrations Bar
    fig.add_trace(go.Bar(
        x=dates, y=new_pts,
        name="New Registrations",
        marker_color="rgba(2, 132, 199, 0.65)",
        yaxis="y2"
    ))

    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=280,
        margin=dict(l=35, r=35, t=30, b=40),
        font=dict(family=FONT_FAMILY, color="#94A3B8", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(gridcolor="#1E293B", showgrid=True),
        yaxis=dict(title="Total Patients", gridcolor="#1E293B", showgrid=True),
        yaxis2=dict(title="Daily Intake", overlaying="y", side="right", showgrid=False)
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 2. Appointment Trends Chart
# ---------------------------------------------------------------------------

def build_appointment_trends_chart(data: Dict[str, Any]) -> str:
    """Multi-bar / line trend chart for outpatient appointment volume & completion."""
    dates = data.get("dates", [])
    if not dates:
        return _empty_figure("No appointment schedule data available")

    completed = data.get("completed", [])
    scheduled = data.get("scheduled", [])
    cancelled = data.get("cancelled", [])
    no_show = data.get("no_show", [])

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Completed", x=dates, y=completed, marker_color=COLOR_EMERALD))
    fig.add_trace(go.Bar(name="Scheduled", x=dates, y=scheduled, marker_color=COLOR_SECONDARY))
    fig.add_trace(go.Bar(name="Cancelled", x=dates, y=cancelled, marker_color=COLOR_DANGER))
    fig.add_trace(go.Bar(name="No-Show", x=dates, y=no_show, marker_color=COLOR_ACCENT))

    fig.update_layout(
        barmode="stack",
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=280,
        margin=dict(l=35, r=25, t=30, b=40),
        font=dict(family=FONT_FAMILY, color="#94A3B8", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(gridcolor="#1E293B", title="Appointments")
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 3. Department Statistics Chart
# ---------------------------------------------------------------------------

def build_department_stats_chart(data: Dict[str, Any]) -> str:
    """Grouped horizontal bar chart comparing department clinical activity."""
    depts = data.get("departments", [])
    if not depts:
        return _empty_figure("No active departments registered")

    app_counts = data.get("appointment_counts", [])
    doc_counts = data.get("doctor_counts", [])
    adm_counts = data.get("admission_counts", [])

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Consultations", y=depts, x=app_counts, orientation="h", marker_color=COLOR_PRIMARY))
    fig.add_trace(go.Bar(name="Admissions", y=depts, x=adm_counts, orientation="h", marker_color=COLOR_SECONDARY))
    fig.add_trace(go.Bar(name="Physicians", y=depts, x=doc_counts, orientation="h", marker_color=COLOR_PURPLE))

    fig.update_layout(
        barmode="group",
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=280,
        margin=dict(l=80, r=25, t=30, b=40),
        font=dict(family=FONT_FAMILY, color="#94A3B8", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(gridcolor="#1E293B", title="Volume"),
        yaxis=dict(autorange="reversed")
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 4. Doctor Workload Chart
# ---------------------------------------------------------------------------

def build_doctor_workload_chart(data: Dict[str, Any]) -> str:
    """Horizontal bar chart ranking provider appointment and consultation loads."""
    doctors = data.get("doctors", [])
    if not doctors:
        return _empty_figure("No medical staff data recorded")

    total_app = data.get("total_appointments", [])
    completed = data.get("completed_consultations", [])

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Completed Consultations",
        y=doctors, x=completed,
        orientation="h",
        marker_color=COLOR_EMERALD
    ))
    fig.add_trace(go.Bar(
        name="Total Assigned",
        y=doctors, x=total_app,
        orientation="h",
        marker_color="rgba(14, 165, 233, 0.45)"
    ))

    fig.update_layout(
        barmode="overlay",
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=280,
        margin=dict(l=100, r=25, t=30, b=40),
        font=dict(family=FONT_FAMILY, color="#94A3B8", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(gridcolor="#1E293B", title="Encounter Count"),
        yaxis=dict(autorange="reversed")
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 5. Disease Distribution Chart
# ---------------------------------------------------------------------------

def build_disease_distribution_chart(data: Dict[str, Any]) -> str:
    """Donut chart illustrating prevalence of diagnosed clinical conditions."""
    labels = data.get("labels", [])
    counts = data.get("counts", [])

    if not labels or not counts:
        return _empty_figure("No diagnostic encounter records found")

    colors = [COLOR_PRIMARY, COLOR_SECONDARY, COLOR_ACCENT, COLOR_PURPLE, COLOR_EMERALD, "#F43F5E", "#EAB308", "#64748B"]

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=counts,
        hole=0.55,
        marker=dict(colors=colors),
        textinfo="label+percent",
        hoverinfo="label+value+percent",
        insidetextorientation="horizontal"
    )])

    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=280,
        margin=dict(l=20, r=20, t=25, b=25),
        showlegend=False,
        font=dict(family=FONT_FAMILY, color="#E2E8F0", size=11)
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 6. Age Distribution Chart
# ---------------------------------------------------------------------------

def build_age_distribution_chart(data: Dict[str, Any]) -> str:
    """Cohort bar chart showing patient demographic distribution across age brackets."""
    cohorts = data.get("cohorts", [])
    counts = data.get("counts", [])

    if not any(counts):
        return _empty_figure("No patient age records available")

    colors = ["#38BDF8", "#0D9488", "#2DD4BF", "#F59E0B", "#F43F5E"]

    fig = go.Figure(data=[go.Bar(
        x=cohorts,
        y=counts,
        marker_color=colors[:len(cohorts)],
        text=counts,
        textposition="auto"
    )])

    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=260,
        margin=dict(l=35, r=20, t=30, b=40),
        font=dict(family=FONT_FAMILY, color="#94A3B8", size=11),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(gridcolor="#1E293B", title="Patients")
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 7. Gender Distribution Chart
# ---------------------------------------------------------------------------

def build_gender_distribution_chart(data: Dict[str, Any]) -> str:
    """Donut chart illustrating gender demographic ratio."""
    labels = data.get("labels", [])
    counts = data.get("counts", [])

    if not any(counts):
        return _empty_figure("No patient gender data recorded")

    colors = [COLOR_SECONDARY, "#EC4899", COLOR_ACCENT]

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=counts,
        hole=0.55,
        marker=dict(colors=colors),
        textinfo="label+percent",
        hoverinfo="label+value+percent"
    )])

    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=260,
        margin=dict(l=20, r=20, t=25, b=25),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
        font=dict(family=FONT_FAMILY, color="#E2E8F0", size=11)
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 8. Admission Trends Chart
# ---------------------------------------------------------------------------

def build_admission_trends_chart(data: Dict[str, Any]) -> str:
    """Timeline line chart for IPD inpatient admissions."""
    dates = data.get("dates", [])
    counts = data.get("counts", [])

    if not dates or not any(counts):
        return _empty_figure("No inpatient admissions in this window")

    fig = go.Figure(data=[go.Scatter(
        x=dates, y=counts,
        mode="lines+markers",
        name="Daily Admissions",
        line=dict(color=COLOR_PRIMARY, width=3),
        marker=dict(size=6, color=COLOR_PRIMARY),
        fill="tozeroy",
        fillcolor="rgba(13, 148, 136, 0.15)"
    )])

    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=260,
        margin=dict(l=35, r=20, t=30, b=40),
        font=dict(family=FONT_FAMILY, color="#94A3B8", size=11),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(gridcolor="#1E293B", title="Admissions")
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 9. Discharge Trends Chart
# ---------------------------------------------------------------------------

def build_discharge_trends_chart(data: Dict[str, Any]) -> str:
    """Timeline chart for inpatient discharges and average length of stay."""
    dates = data.get("dates", [])
    counts = data.get("counts", [])
    avg_los = data.get("avg_los_days", 0.0)

    if not dates or not any(counts):
        return _empty_figure("No patient discharges recorded in this period")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=dates, y=counts,
        name="Discharges",
        marker_color=COLOR_SECONDARY
    ))

    fig.add_annotation(
        text=f"Avg Stay: {avg_los} Days",
        xref="paper", yref="paper",
        x=0.03, y=0.92,
        showarrow=False,
        bgcolor="rgba(15, 23, 42, 0.8)",
        bordercolor="#334155",
        borderwidth=1,
        font=dict(color="#38BDF8", size=11, family=FONT_FAMILY)
    )

    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=260,
        margin=dict(l=35, r=20, t=30, b=40),
        font=dict(family=FONT_FAMILY, color="#94A3B8", size=11),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(gridcolor="#1E293B", title="Discharges")
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 10. Bed Occupancy Charts
# ---------------------------------------------------------------------------

def build_bed_occupancy_gauge(occupancy_rate: float) -> str:
    """Gauge chart for real-time hospital bed occupancy percentage."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=occupancy_rate,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': "Hospital Bed Occupancy", 'font': {'size': 16, 'color': '#F8FAFC', 'family': FONT_FAMILY}},
        number={'suffix': "%", 'font': {'size': 36, 'color': '#38BDF8', 'family': FONT_FAMILY}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#94A3B8"},
            'bar': {'color': COLOR_PRIMARY},
            'bgcolor': "rgba(30, 41, 59, 0.6)",
            'borderwidth': 1,
            'bordercolor': "#334155",
            'steps': [
                {'range': [0, 60], 'color': "rgba(13, 148, 136, 0.25)"},
                {'range': [60, 85], 'color': "rgba(245, 158, 11, 0.25)"},
                {'range': [85, 100], 'color': "rgba(239, 68, 68, 0.35)"}
            ],
            'threshold': {
                'line': {'color': COLOR_DANGER, 'width': 3},
                'thickness': 0.75,
                'value': 90
            }
        }
    ))
    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        margin=dict(l=25, r=25, t=40, b=20),
        height=240,
        font=dict(family=FONT_FAMILY, color='#E2E8F0')
    )
    return fig.to_json()


def build_ward_breakdown_bar(ward_data: List[Dict[str, Any]]) -> str:
    """Stacked bar chart showing occupied, available, and maintenance beds per ward."""
    if not ward_data:
        return _empty_figure("No ward or room inventory registered")

    ward_names = [w.get("ward_name", f"Ward {w.get('room_number', '')}") for w in ward_data]
    occupied = [w.get("occupied", 0) for w in ward_data]
    available = [w.get("available", 0) for w in ward_data]
    maintenance = [w.get("maintenance", 0) for w in ward_data]

    fig = go.Figure(data=[
        go.Bar(name='Occupied Beds', x=ward_names, y=occupied, marker_color=COLOR_PRIMARY),
        go.Bar(name='Available Beds', x=ward_names, y=available, marker_color='#334155'),
        go.Bar(name='Maintenance', x=ward_names, y=maintenance, marker_color=COLOR_ACCENT)
    ])
    fig.update_layout(
        barmode='stack',
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        margin=dict(l=30, r=20, t=30, b=40),
        height=260,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        font=dict(family=FONT_FAMILY, color='#94A3B8', size=11),
        yaxis=dict(gridcolor="#1E293B"),
        xaxis=dict(gridcolor="#1E293B")
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 11. Revenue Trends & Donut Charts
# ---------------------------------------------------------------------------

def build_revenue_trends_chart(data: Dict[str, Any]) -> str:
    """Multi-line/area chart showing gross billing vs collections over time."""
    dates = data.get("dates", [])
    billed = data.get("billed", [])
    collected = data.get("collected", [])

    if not dates or (not any(billed) and not any(collected)):
        return _empty_figure("No invoice or payment transactions recorded")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=billed,
        name="Billed Gross",
        mode="lines+markers",
        line=dict(color=COLOR_SECONDARY, width=3),
        marker=dict(size=5)
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=collected,
        name="Cash Collected",
        mode="lines+markers",
        line=dict(color=COLOR_EMERALD, width=3),
        fill="tozeroy",
        fillcolor="rgba(16, 185, 129, 0.12)",
        marker=dict(size=5)
    ))

    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=280,
        margin=dict(l=45, r=25, t=30, b=40),
        font=dict(family=FONT_FAMILY, color="#94A3B8", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(gridcolor="#1E293B", title="Amount ($)")
    )
    return fig.to_json()


def build_revenue_donut_chart(category_dist: Dict[str, float]) -> str:
    """Donut chart illustrating income distribution across 7 hospital cost centers."""
    labels = list(category_dist.keys()) if category_dist else []
    values = list(category_dist.values()) if category_dist else []

    if not labels or not values:
        return _empty_figure("No billed items recorded yet")

    formatted_labels = [l.replace("_", " ").title() for l in labels]
    colors = [COLOR_PRIMARY, COLOR_SECONDARY, COLOR_ACCENT, COLOR_PURPLE, COLOR_EMERALD, "#F43F5E", "#64748B"]

    fig = go.Figure(data=[go.Pie(
        labels=formatted_labels,
        values=values,
        hole=.55,
        marker=dict(colors=colors),
        textinfo='label+percent',
        hoverinfo='label+value+percent'
    )])
    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        margin=dict(l=20, r=20, t=25, b=25),
        height=260,
        showlegend=False,
        font=dict(family=FONT_FAMILY, color='#E2E8F0', size=11)
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 12. Laboratory Test Trends Chart
# ---------------------------------------------------------------------------

def build_lab_trends_chart(data: Dict[str, Any]) -> str:
    """Bar chart for top ordered laboratory tests and abnormality rate."""
    top_tests = data.get("top_tests", [])
    top_counts = data.get("top_counts", [])
    abnormal_rate = data.get("abnormal_rate", 0.0)

    if not top_tests:
        return _empty_figure("No diagnostic lab orders placed")

    fig = go.Figure(data=[go.Bar(
        x=top_tests,
        y=top_counts,
        marker_color=COLOR_PURPLE,
        text=top_counts,
        textposition="auto"
    )])

    fig.add_annotation(
        text=f"Abnormal Rate: {abnormal_rate}%",
        xref="paper", yref="paper",
        x=0.97, y=0.92,
        showarrow=False,
        bgcolor="rgba(15, 23, 42, 0.8)",
        bordercolor="#334155",
        borderwidth=1,
        font=dict(color="#F43F5E" if abnormal_rate > 20 else "#38BDF8", size=11, family=FONT_FAMILY)
    )

    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=260,
        margin=dict(l=35, r=20, t=30, b=45),
        font=dict(family=FONT_FAMILY, color="#94A3B8", size=11),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(gridcolor="#1E293B", title="Orders")
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 13. Pharmacy Inventory Chart
# ---------------------------------------------------------------------------

def build_pharmacy_inventory_chart(data: Dict[str, Any]) -> str:
    """Category stock count & inventory health indicators."""
    categories = data.get("categories", [])
    units = data.get("category_units", [])
    val = data.get("total_valuation", 0.0)

    if not categories:
        return _empty_figure("No pharmacy medicines catalogued")

    fig = go.Figure(data=[go.Bar(
        x=categories,
        y=units,
        marker_color=COLOR_PRIMARY,
        text=units,
        textposition="auto"
    )])

    fig.add_annotation(
        text=f"Valuation: ${val:,.2f}",
        xref="paper", yref="paper",
        x=0.97, y=0.92,
        showarrow=False,
        bgcolor="rgba(15, 23, 42, 0.8)",
        bordercolor="#334155",
        borderwidth=1,
        font=dict(color="#34D399", size=11, family=FONT_FAMILY)
    )

    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=260,
        margin=dict(l=35, r=20, t=30, b=45),
        font=dict(family=FONT_FAMILY, color="#94A3B8", size=11),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(gridcolor="#1E293B", title="Stock Units")
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 14. Appointment Cancellation Chart
# ---------------------------------------------------------------------------

def build_cancellation_chart(data: Dict[str, Any]) -> str:
    """Cancellation rate indicator and trend line."""
    dates = data.get("dates", [])
    timeline = data.get("cancelled_timeline", [])
    rate = data.get("cancellation_rate", 0.0)

    if not dates or not any(timeline):
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=rate,
            title={'text': "Cancellation Rate", 'font': {'size': 16, 'color': '#F8FAFC', 'family': FONT_FAMILY}},
            number={'suffix': "%", 'font': {'size': 32, 'color': '#38BDF8', 'family': FONT_FAMILY}},
            gauge={'axis': {'range': [0, 50]}, 'bar': {'color': COLOR_SECONDARY}}
        ))
        fig.update_layout(paper_bgcolor=COLOR_BG, plot_bgcolor=COLOR_BG, height=240, margin=dict(l=20, r=20, t=35, b=20))
        return fig.to_json()

    fig = go.Figure(data=[go.Bar(
        x=dates, y=timeline,
        marker_color=COLOR_DANGER,
        name="Cancelled"
    )])

    fig.add_annotation(
        text=f"Rate: {rate}%",
        xref="paper", yref="paper",
        x=0.03, y=0.92,
        showarrow=False,
        bgcolor="rgba(15, 23, 42, 0.8)",
        bordercolor="#334155",
        borderwidth=1,
        font=dict(color="#F87171", size=11, family=FONT_FAMILY)
    )

    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=240,
        margin=dict(l=35, r=20, t=30, b=40),
        font=dict(family=FONT_FAMILY, color="#94A3B8", size=11),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(gridcolor="#1E293B", title="Cancellations")
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# 15. Appointment No-Show Chart
# ---------------------------------------------------------------------------

def build_no_show_chart(data: Dict[str, Any]) -> str:
    """No-show rate gauge and ML risk cohort distribution."""
    rate = data.get("no_show_rate", 0.0)
    buckets = data.get("risk_buckets", {})

    b_labels = list(buckets.keys())
    b_values = list(buckets.values())

    if not any(b_values):
        # Fallback to single gauge indicator
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=rate,
            title={'text': "Outpatient No-Show Rate", 'font': {'size': 16, 'color': '#F8FAFC', 'family': FONT_FAMILY}},
            number={'suffix': "%", 'font': {'size': 32, 'color': '#FBBF24', 'family': FONT_FAMILY}},
            gauge={'axis': {'range': [0, 50]}, 'bar': {'color': COLOR_ACCENT}}
        ))
        fig.update_layout(paper_bgcolor=COLOR_BG, plot_bgcolor=COLOR_BG, height=240, margin=dict(l=20, r=20, t=35, b=20))
        return fig.to_json()

    colors = [COLOR_EMERALD, COLOR_ACCENT, COLOR_DANGER]

    fig = go.Figure(data=[go.Bar(
        x=b_labels,
        y=b_values,
        marker_color=colors[:len(b_labels)],
        text=b_values,
        textposition="auto"
    )])

    fig.add_annotation(
        text=f"Actual No-Show: {rate}%",
        xref="paper", yref="paper",
        x=0.97, y=0.92,
        showarrow=False,
        bgcolor="rgba(15, 23, 42, 0.8)",
        bordercolor="#334155",
        borderwidth=1,
        font=dict(color="#FBBF24", size=11, family=FONT_FAMILY)
    )

    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        height=240,
        margin=dict(l=35, r=20, t=30, b=40),
        font=dict(family=FONT_FAMILY, color="#94A3B8", size=11),
        xaxis=dict(gridcolor="#1E293B"),
        yaxis=dict(gridcolor="#1E293B", title="Appointments")
    )
    return fig.to_json()


# ---------------------------------------------------------------------------
# Inpatient Census Trend (Legacy & Dynamic Integration)
# ---------------------------------------------------------------------------

def build_patient_census_trend(adm_data: Optional[Dict[str, Any]] = None, dis_data: Optional[Dict[str, Any]] = None) -> str:
    """Generates dual admission vs discharge timeline chart from real database queries."""
    if not adm_data or not dis_data or not adm_data.get("dates"):
        return _empty_figure("No admission/discharge timeline data available")

    dates = adm_data.get("dates", [])
    admissions = adm_data.get("counts", [])
    discharges = dis_data.get("counts", [0] * len(dates))

    # Match lengths
    if len(discharges) < len(dates):
        discharges = discharges + [0] * (len(dates) - len(discharges))
    elif len(discharges) > len(dates):
        discharges = discharges[:len(dates)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=admissions, mode='lines+markers', name='Admissions',
        line=dict(color=COLOR_PRIMARY, width=3),
        marker=dict(size=6)
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=discharges, mode='lines+markers', name='Discharges',
        line=dict(color=COLOR_SECONDARY, width=3, dash='dot'),
        marker=dict(size=6)
    ))
    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        margin=dict(l=30, r=20, t=30, b=40),
        height=260,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        font=dict(family=FONT_FAMILY, color='#94A3B8', size=11),
        yaxis=dict(gridcolor="#1E293B"),
        xaxis=dict(gridcolor="#1E293B")
    )
    return fig.to_json()
