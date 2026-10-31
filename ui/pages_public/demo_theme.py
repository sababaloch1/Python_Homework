"""Demo page to test and preview the monochrome theme, Plotly charts, and styled tables in both Light and Dark modes.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from ui.theme import apply_theme, current_mode
from ui.charts import (
    SCOPE_COLORS,
    SERIES_PALETTE,
    plotly_layout,
    styled_table,
)

st.set_page_config(page_title="CarbonLens - Style Demo", page_icon="🌍", layout="wide")
apply_theme()

# Top bar
col_title, col_toggle = st.columns([8, 2])
with col_title:
    st.title("CarbonLens Style & Theme System Demo")
    st.caption("Testing strict monochrome layout with Okabe-Ito data colours.")

with col_toggle:
    st.write("")

mode = current_mode()
st.write(f"**Active Theme Mode:** `{mode.upper()}`")

# 1. Metric Cards
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Emissions", "142.8 t CO2e", "-12.4%")
m2.metric("Scope 1", "34.5 t CO2e", "-4.1%")
m3.metric("Scope 2", "58.2 t CO2e", "-18.2%")
m4.metric("Scope 3", "50.1 t CO2e", "+1.5%")

st.divider()

# 2. Plotly Chart Demo
st.subheader("1. Plotly Emissions Trend (Data Colours Only)")
fig = go.Figure()
months = ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04"]
fig.add_trace(go.Bar(name="Scope 1", x=months, y=[10, 11, 14, 12, 11, 12], marker_color=SCOPE_COLORS["Scope 1"]))
fig.add_trace(go.Bar(name="Scope 2", x=months, y=[18, 19, 21, 20, 18, 17], marker_color=SCOPE_COLORS["Scope 2"]))
fig.add_trace(go.Bar(name="Scope 3", x=months, y=[15, 14, 16, 17, 16, 15], marker_color=SCOPE_COLORS["Scope 3"]))

fig.update_layout(
    barmode="stack",
    **plotly_layout(mode=mode, title="Monthly Emissions by Scope (t CO2e)", yaxis_title="t CO2e")
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# 3. Styled Table Demo
st.subheader("2. Styled Data Table (Explicit Colouring, No Matplotlib)")
demo_df = pd.DataFrame({
    "Month": ["2026-01", "2026-02", "2026-03", "2026-04"],
    "Scope": ["Scope 1", "Scope 2", "Scope 3", "Scope 2"],
    "Emissions (t CO2e)": [14.0, 20.0, 16.0, 35.5],
    "Status": ["On track", "On track", "On track", "Off track"],
    "Anomaly": ["Normal", "Normal", "Normal", "⚠️ Anomaly"],
})

# Display using styled_table
st.dataframe(styled_table(demo_df, mode=mode), use_container_width=True)

st.divider()

# 4. Standard Column Config Demo
st.subheader("3. Native Column Config Progress / Bar")
st.dataframe(
    demo_df[["Month", "Scope", "Emissions (t CO2e)"]],
    column_config={
        "Emissions (t CO2e)": st.column_config.ProgressColumn(
            "Emissions (t CO2e)",
            help="Total emissions in t CO2e",
            format="%.1f t",
            min_value=0,
            max_value=50,
        ),
    },
    use_container_width=True,
    hide_index=True,
)
