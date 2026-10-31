"""ui/pages_private/dashboard.py - FR-3.01 to FR-3.04, FR-3.10: Emissions Dashboard.

Features:
- Period filter (start and end dates)
- KPI row (Total t CO2e, Scope 1, Scope 2, Scope 3, % vs last year)
- Warnings when failed_records > 0 or cost_complete is false
- 12-month trend chart with anomaly months marked with red/vermilion markers
- Breakdown chart with interactive selector (Scope, Category, Department, Facility)
- Top 5 emission sources table (Okabe-Ito styled)
- Expander "Show records" using /analytics/records with pagination
- Empty state for organisations with no data
"""

from datetime import date, datetime
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.api_client import api_get
from ui.auth_state import current_email, current_org_name, current_role
from ui.charts import (
    ANOMALY_COLOR,
    SERIES_PALETTE,
    apply_plotly_theme,
    get_scope_color,
    styled_table,
)
from ui.theme import apply_theme

# Apply monochrome layout and theme
apply_theme()

st.title("📊 Emissions Dashboard")
st.caption(f"Organization: **{current_org_name()}** | Logged in as: {current_email()} ({current_role()})")

# 1. Period Filter
with st.sidebar:
    st.header("Date Range Filter")
    use_date_filter = st.checkbox("Filter by custom date range", value=False)
    start_date = None
    end_date = None
    if use_date_filter:
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_date = st.date_input("Start date", value=date(2025, 1, 1))
        with col_d2:
            end_date = st.date_input("End date", value=date.today())

# Prepare query params
params = {}
if start_date:
    params["start"] = start_date.isoformat()
if end_date:
    params["end"] = end_date.isoformat()

# Fetch Summary and Trend
with st.spinner("Loading emissions summary..."):
    ok_sum, summary_data = api_get("analytics/summary", params=params)
    ok_trend, trend_data = api_get("analytics/trend")
    ok_anom, anomaly_data = api_get("analytics/anomalies")

if not ok_sum or not summary_data:
    st.error("Unable to load summary data from backend.")
    st.stop()

total_t = float(summary_data.get("total_t_co2e") or 0.0)
failed_records = summary_data.get("failed_records", 0)
cost_complete = summary_data.get("cost_complete", True)
total_cost = float(summary_data.get("total_cost_eur") or 0.0)

# Check Empty State
if total_t == 0.0 and (not trend_data or not trend_data.get("months") or all(m["t_co2e"] == 0 for m in trend_data.get("months", []))):
    st.info(
        "👋 Welcome! Your organization currently has no activity or emissions records.\n\n"
        "To get started, enter your organization's energy usage or fuel consumption under **Data Entry**, "
        "or connect real-time meter readings to see your carbon footprint appear here automatically."
    )
    st.stop()

# 2. Warnings
if failed_records > 0:
    st.warning(f"⚠️ **{failed_records} calculation(s) failed** during this period due to missing emission factor data. Check the audit records below.")

if not cost_complete:
    st.info("ℹ️ Some activity records do not have regional tariffs defined, so the total cost figure may be partial.")

# 3. KPI Metric Row
by_scope = summary_data.get("by_scope") or {}
s1 = float(by_scope.get("scope_1") or 0.0)
s2 = float(by_scope.get("scope_2") or 0.0)
s3 = float(by_scope.get("scope_3") or 0.0)

pct_change = trend_data.get("pct_change") if ok_trend and trend_data else None
pct_str = f"{pct_change:+.1f}% vs last year" if pct_change is not None else "No prior year data"

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Emissions", f"{total_t:,.2f} t", delta=pct_str, delta_color="inverse")
col2.metric("Scope 1 (Direct)", f"{s1:,.2f} t", f"{(s1 / total_t * 100):.1f}%" if total_t > 0 else "0%")
col3.metric("Scope 2 (Indirect)", f"{s2:,.2f} t", f"{(s2 / total_t * 100):.1f}%" if total_t > 0 else "0%")
col4.metric("Scope 3 (Value Chain)", f"{s3:,.2f} t", f"{(s3 / total_t * 100):.1f}%" if total_t > 0 else "0%")
col5.metric("Total Cost", f"€{total_cost:,.2f}")

st.divider()

# 4. Charts: 12-Month Trend and Breakdown
chart_col1, chart_col2 = st.columns([3, 2])

# Left: 12-month trend chart with anomalies marked
with chart_col1:
    st.subheader("12-Month Emissions Trend")
    months_list = trend_data.get("months", []) if ok_trend and trend_data else []
    
    if months_list:
        df_trend = pd.DataFrame(months_list)
        # Identify anomalies
        flagged_months = {a["month"]: a for a in (anomaly_data if ok_anom and isinstance(anomaly_data, list) else [])}
        
        df_trend["is_anomaly"] = df_trend["month"].apply(lambda m: m in flagged_months)
        
        fig_trend = go.Figure()
        
        # Main trend line
        fig_trend.add_trace(go.Scatter(
            x=df_trend["month"],
            y=df_trend["t_co2e"],
            mode="lines+markers",
            name="Monthly Emissions",
            line=dict(color="#0072B2", width=2.5),
            marker=dict(size=6),
            hovertemplate="<b>%{x}</b><br>Emissions: %{y:.2f} t CO2e<extra></extra>",
        ))
        
        # Anomaly markers
        anom_df = df_trend[df_trend["is_anomaly"]]
        if not anom_df.empty:
            fig_trend.add_trace(go.Scatter(
                x=anom_df["month"],
                y=anom_df["t_co2e"],
                mode="markers",
                name="Flagged Anomaly (>20% Spike)",
                marker=dict(color=ANOMALY_COLOR, size=11, symbol="triangle-up"),
                hovertemplate="<b>⚠️ %{x}</b><br>Spike: %{y:.2f} t CO2e<extra></extra>",
            ))
            
        apply_plotly_theme(fig_trend, yaxis_title="Emissions (t CO2e)")
        fig_trend.update_layout(height=340, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No trend data available.")

# Right: Breakdown by dimension
with chart_col2:
    st.subheader("Emissions Breakdown")
    dim_choice = st.selectbox(
        "Group breakdown by:",
        options=["Scope", "Category", "Department", "Facility"],
        index=3,
        key="breakdown_dim_select",
    )
    dim_key = dim_choice.lower()
    
    breakdown_params = dict(params)
    breakdown_params["by"] = dim_key
    ok_brk, brk_data = api_get("analytics/breakdown", params=breakdown_params)
    
    if ok_brk and brk_data:
        df_brk = pd.DataFrame(brk_data)
        
        # Donut chart
        colors = [SERIES_PALETTE[i % len(SERIES_PALETTE)] for i in range(len(df_brk))]
        if dim_key == "scope":
            colors = [get_scope_color(lbl) for lbl in df_brk["label"]]
            
        fig_brk = go.Figure(data=[go.Pie(
            labels=df_brk["label"],
            values=df_brk["t_co2e"],
            hole=0.45,
            marker=dict(colors=colors),
            textinfo="label+percent",
            hoverinfo="label+value+percent",
        )])
        apply_plotly_theme(fig_brk)
        fig_brk.update_layout(height=340, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_brk, use_container_width=True)
    else:
        st.info("No breakdown data available for this selection.")

st.divider()

# 5. Top 5 Sources Table
st.subheader("Top 5 Emission Sources")
top_params = dict(params)
top_params["limit"] = 5
ok_top, top_data = api_get("analytics/top-sources", params=top_params)

if ok_top and top_data:
    df_top = pd.DataFrame(top_data)
    df_top["category"] = df_top["category"].apply(lambda c: str(c).replace("_", " ").title())
    df_top.rename(columns={"category": "Activity Category", "facility": "Facility", "t_co2e": "Emissions (t CO2e)"}, inplace=True)
    st.dataframe(styled_table(df_top), use_container_width=True, hide_index=True)
else:
    st.info("No source activity recorded.")

# 6. Audit Records Expander
with st.expander("🔍 Show Underlying Activity Records (/analytics/records)"):
    st.markdown("Detailed audit log of activity records and emission engine calculation traces.")
    rec_params = dict(params)
    rec_params["limit"] = 25
    ok_rec, rec_data = api_get("analytics/records", params=rec_params)
    
    if ok_rec and rec_data:
        df_rec = pd.DataFrame(rec_data)
        if "category" in df_rec.columns:
            df_rec["category"] = df_rec["category"].apply(lambda c: str(c).replace("_", " ").title())
        st.dataframe(styled_table(df_rec), use_container_width=True, hide_index=True)
    else:
        st.info("No records found for the selected period.")
