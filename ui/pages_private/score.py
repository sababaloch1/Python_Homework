"""ui/pages_private/score.py - FR-3.05, NFR-3.07: Sustainability Score Page.

Features:
- Displays overall 0-100 sustainability score in a prominent monochrome KPI gauge/metric
- 4 Component Breakdown (25 pts each):
  1. YoY Trend Progress (0-25)
  2. Target Alignment & Pathway (0-25)
  3. Data Completeness & Engine Reliability (0-25)
  4. Carbon Intensity per Employee (0-25)
- Explanations for each component
- Link/expander describing the full mathematical formula from docs/S3_Score_Formula.md
- Empty state when score is null (e.g. organization has no data)
- Adheres to monochrome theme + Okabe-Ito chart palette
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.api_client import api_get
from ui.auth_state import current_org_name
from ui.charts import apply_plotly_theme
from ui.theme import apply_theme

apply_theme()

st.title("🏅 Sustainability Score")
st.caption(f"Organization: **{current_org_name()}** | Holistic ESG & Carbon Performance Index")

with st.spinner("Calculating sustainability score..."):
    ok, score_data = api_get("analytics/score")

if not ok or not score_data or score_data.get("score") is None:
    message = score_data.get("message") if isinstance(score_data, dict) else "No emissions data available."
    st.info(
        f"📊 **Score Pending Data**\n\n"
        f"{message}\n\n"
        "Your sustainability score is evaluated across four dimensions (Trend, Targets, Data Completeness, "
        "and Employee Intensity). Once activity data is recorded, your score will be automatically computed."
    )
    st.stop()

score = float(score_data.get("score", 0.0))
components = score_data.get("components", {})

# 1. Overall Score Metric Block
col_score1, col_score2 = st.columns([1, 2])

with col_score1:
    st.markdown("### Overall Score")
    # Score classification badge
    if score >= 75:
        tier = "Leader"
        tier_color = "#009E73"
    elif score >= 50:
        tier = "Advancing"
        tier_color = "#56B4E9"
    elif score >= 25:
        tier = "Developing"
        tier_color = "#E69F00"
    else:
        tier = "Needs Attention"
        tier_color = "#D55E00"

    st.markdown(
        f"""
        <div style="border: 1px solid var(--border); border-radius: 8px; padding: 24px 20px; text-align: center; background-color: var(--card);">
            <div style="font-size: 54px; font-weight: 800; line-height: 1.1; color: var(--fg);">{score:.1f}<span style="font-size: 24px; color: var(--muted); font-weight: normal;"> / 100</span></div>
            <div style="margin-top: 14px;">
                <span style="background-color: {tier_color}33; color: {tier_color}; border: 1px solid {tier_color}; padding: 4px 14px; border-radius: 12px; font-weight: 700; font-size: 13px; letter-spacing: 0.04em;">
                    {tier.upper()}
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_score2:
    st.markdown("### Dimension Breakdown")
    def get_comp_points(key: str, alt_key: str = "") -> float:
        val = components.get(key)
        if val is None and alt_key:
            val = components.get(alt_key)
        if isinstance(val, dict):
            return float(val.get("points", 0.0))
        try:
            return float(val) if val is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    c1 = get_comp_points("yoy_trend")
    c2 = get_comp_points("target_progress")
    c3 = get_comp_points("data_completeness")
    c4 = get_comp_points("carbon_intensity", "emissions_per_employee")

    comp_df = pd.DataFrame([
        {"Dimension": "1. YoY Trend", "Score": c1, "Max": 25.0},
        {"Dimension": "2. Target Progress", "Score": c2, "Max": 25.0},
        {"Dimension": "3. Data Completeness", "Score": c3, "Max": 25.0},
        {"Dimension": "4. Emissions / Employee", "Score": c4, "Max": 25.0},
    ])

    fig_bar = go.Figure(go.Bar(
        x=comp_df["Score"],
        y=comp_df["Dimension"],
        orientation="h",
        marker=dict(color=["#E69F00", "#56B4E9", "#009E73", "#0072B2"]),
        text=[f"{s:.1f} / 25" for s in comp_df["Score"]],
        textposition="auto",
    ))
    apply_plotly_theme(fig_bar, xaxis_title="Points (out of 25)", yaxis_title="")
    fig_bar.update_layout(
        height=220,
        margin=dict(l=20, r=20, t=10, b=30),
    )
    fig_bar.update_xaxes(range=[0, 25.5])
    st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# 2. Detailed Dimension Cards
st.subheader("Component Details & Scoring Criteria")
c_col1, c_col2 = st.columns(2)

desc1 = components.get("yoy_trend", {}).get("description") if isinstance(components.get("yoy_trend"), dict) else "Rewards sustained reduction in absolute gross emissions compared to the prior 12-month period."
desc2 = components.get("target_progress", {}).get("description") if isinstance(components.get("target_progress"), dict) else "Measures alignment with decarbonization targets along linear milestones."
desc3 = components.get("data_completeness", {}).get("description") if isinstance(components.get("data_completeness"), dict) else "Evaluates reporting continuity across months and error-free calculation traces in the engine."
desc4_comp = components.get("carbon_intensity") or components.get("emissions_per_employee")
desc4 = desc4_comp.get("description") if isinstance(desc4_comp, dict) else "Normalizes corporate carbon footprint per full-time employee against regional manufacturing benchmarks."

with c_col1:
    with st.container():
        st.markdown(f"#### 1. Year-over-Year Trend: **{c1:.1f} / 25 pts**")
        st.caption(desc1)
        st.progress(c1 / 25.0)

    st.markdown("<br>", unsafe_allow_html=True)
    with st.container():
        st.markdown(f"#### 2. Target Trajectory Progress: **{c2:.1f} / 25 pts**")
        st.caption(desc2)
        st.progress(c2 / 25.0)

with c_col2:
    with st.container():
        st.markdown(f"#### 3. Data Completeness & Quality: **{c3:.1f} / 25 pts**")
        st.caption(desc3)
        st.progress(c3 / 25.0)

    st.markdown("<br>", unsafe_allow_html=True)
    with st.container():
        st.markdown(f"#### 4. Carbon Intensity per Employee: **{c4:.1f} / 25 pts**")
        st.caption(desc4)
        st.progress(c4 / 25.0)

st.divider()

# 3. Transparent Formula Documentation Expander
with st.expander("📖 Transparency & Scoring Methodology (docs/S3_Score_Formula.md)"):
    st.markdown(
        """
        The **CarbonLens Sustainability Score** is an objective, deterministic 0–100 index evaluated across four equally weighted pillars (25 points each):

        ### 1. YoY Emissions Trend (0–25 pts)
        - Compares current 12-month total location-based emissions against prior 12-month total.
        - **Full 25 pts**: Reduction $\\ge 10\\%$ YoY.
        - **Pro-rated 10–25 pts**: Linear scaling for reductions between $0\\%$ and $10\\%$.
        - **5 pts**: Minor increase up to $5\\%$.
        - **0 pts**: Emissions increased by $> 5\\%$ or no historical data.

        ### 2. Target Progress (0–25 pts)
        - Compares current YTD emissions against expected linear trajectory milestones.
        - **25 pts**: All targets strictly on track ($Actual \\le Expected$).
        - **15 pts**: Average target gap is within $+10\\%$ of expected pace.
        - **5 pts**: Active targets defined but falling behind expectation.
        - **0 pts**: No decarbonization targets configured.

        ### 3. Data Completeness & Integrity (0–25 pts)
        - Combines reporting frequency (months with data out of 12) and engine calculation success rate.
        - Formula: $25 \\times \\left( 0.6 \\times \\frac{ActiveMonths}{12} + 0.4 \\times \\text{CalculationSuccessRate} \\right)$.

        ### 4. Emissions per Employee (0–25 pts)
        - Benchmarks annual emissions divided by `Organization.employee_count`.
        - **25 pts**: $< 2.0$ tonnes CO2e / employee / year.
        - **15 pts**: $2.0 - 5.0$ tonnes CO2e / employee / year.
        - **8 pts**: $5.0 - 10.0$ tonnes CO2e / employee / year.
        - **0 pts**: $\\ge 10.0$ tonnes CO2e / employee / year.
        """
    )
