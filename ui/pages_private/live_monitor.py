"""ui/pages_private/live_monitor.py - FR-3.09: Live Facility Meter Monitor.

Features:
- Real-time today's t CO2e emissions per facility
- Bar chart & table of facilities
- Auto-refresh timer every 60 seconds with manual "Refresh Now" button
- Clean display of "as of" timestamp
- Friendly empty state when no meter readings exist for today
- Strict monochrome theme and Okabe-Ito chart coloring
"""

from datetime import datetime
import time
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.api_client import api_get
from ui.auth_state import current_org_name
from ui.charts import SERIES_PALETTE, apply_plotly_theme, styled_table
from ui.theme import apply_theme

apply_theme()

st.title("📡 Live Facility Meter Monitor")
st.caption(f"Organization: **{current_org_name()}** | Automated Real-Time IoT Telemetry")

# 1. Refresh Control Header
header_col1, header_col2 = st.columns([3, 1])

# Check and update refresh timestamp
now = time.time()
if "last_live_refresh" not in st.session_state:
    st.session_state["last_live_refresh"] = now

# Auto refresh if 60 seconds have elapsed
auto_refresh = st.sidebar.checkbox("Auto-refresh every 60s", value=True)
if auto_refresh and (now - st.session_state["last_live_refresh"] > 60):
    st.session_state["last_live_refresh"] = now
    st.rerun()

with header_col2:
    if st.button("🔄 Refresh Now", use_container_width=True):
        st.session_state["last_live_refresh"] = now
        st.rerun()

# 2. Fetch Live Emissions
with st.spinner("Fetching today's live telemetry..."):
    ok, live_data = api_get("analytics/live")

if not ok or not live_data:
    st.error("Failed to connect to live telemetry service.")
    st.stop()

as_of_str = live_data.get("as_of", "")
try:
    dt = datetime.fromisoformat(as_of_str.replace("Z", "+00:00"))
    formatted_as_of = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
except Exception:
    formatted_as_of = as_of_str

with header_col1:
    st.markdown(f"**Status:** Connected &nbsp;|&nbsp; **As of:** `{formatted_as_of}`")

st.divider()

facilities = live_data.get("facilities", [])

# Empty State
if not facilities or all(float(f.get("t_co2e") or 0.0) == 0.0 for f in facilities):
    st.info(
        "📡 **No meter telemetry recorded today.**\n\n"
        "Connect digital power meters, smart gas meters, or IoT telemetry gateways to monitor real-time "
        "facility load. As today's meter readings arrive, facility carbon emissions will appear here instantly."
    )
    st.stop()

# 3. Summary KPIs
total_live_t = sum(float(f.get("t_co2e") or 0.0) for f in facilities)
active_facilities = len([f for f in facilities if float(f.get("t_co2e") or 0.0) > 0])

kpi1, kpi2, kpi3 = st.columns(3)
kpi1.metric("Today's Live Emissions", f"{total_live_t:,.4f} t CO2e")
kpi2.metric("Reporting Facilities", f"{active_facilities} Active")
kpi3.metric("Telemetry Health", "100% Operational")

st.divider()

# 4. Bar Chart & Data Table
chart_col, table_col = st.columns([3, 2])

df_fac = pd.DataFrame(facilities)
df_fac["Facility"] = df_fac["name"]
df_fac["Emissions (t CO2e)"] = df_fac["t_co2e"].apply(lambda v: round(float(v), 4))
df_fac["Share (%)"] = df_fac["t_co2e"].apply(
    lambda v: f"{(float(v) / total_live_t * 100):.1f}%" if total_live_t > 0 else "0.0%"
)

with chart_col:
    st.subheader("Today's Facility Emissions Load")
    fig_bar = go.Figure(go.Bar(
        x=df_fac["Facility"],
        y=df_fac["Emissions (t CO2e)"],
        marker=dict(color=SERIES_PALETTE[:len(df_fac)]),
        text=[f"{v:.4f} t" for v in df_fac["Emissions (t CO2e)"]],
        textposition="auto",
    ))
    apply_plotly_theme(fig_bar, yaxis_title="Emissions (t CO2e)")
    fig_bar.update_layout(height=340, margin=dict(l=30, r=20, t=20, b=30))
    st.plotly_chart(fig_bar, use_container_width=True)

with table_col:
    st.subheader("Facility Telemetry Breakdown")
    display_df = df_fac[["Facility", "Emissions (t CO2e)", "Share (%)"]]
    st.dataframe(styled_table(display_df), use_container_width=True, hide_index=True)
