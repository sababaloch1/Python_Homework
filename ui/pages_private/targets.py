"""ui/pages_private/targets.py - FR-3.06, FR-3.07: Decarbonization Targets & Progress Tracking.

Features:
- Form to create a target (shown only to admin/manager role)
- List of targets with status badges (On track / Off track)
- Target metrics: baseline_t, target_t, expected_now, actual_t, saved_t
- Visual line chart showing baseline, straight-line path, target, and actual progress
- Friendly message when there are no targets
- Strict adherence to monochrome theme + Okabe-Ito chart palette
"""

from datetime import date
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.api_client import api_get, api_post
from ui.auth_state import current_role
from ui.charts import (
    apply_plotly_theme,
    get_status_color,
    styled_table,
)
from ui.theme import apply_theme

apply_theme()

st.title("🎯 Decarbonization Targets")
st.caption("Set reduction commitments, track linear trajectory milestones, and monitor real-world progress.")

role = current_role()
can_manage = role in ("admin", "manager")

# 1. Target Creation Form (Admin / Manager only)
if can_manage:
    with st.expander("➕ Define New Reduction Target", expanded=False):
        with st.form("create_target_form"):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                scope_choice = st.selectbox(
                    "Scope",
                    options=["All Scopes", "Scope 1", "Scope 2", "Scope 3"],
                    help="Target can apply to all emissions or be specific to one scope.",
                )
                scope_val = None if scope_choice == "All Scopes" else scope_choice.lower().replace(" ", "_")
                baseline_year = st.number_input("Baseline Year", min_value=2015, max_value=2050, value=2025, step=1)
            
            with col_f2:
                target_year = st.number_input("Target Year", min_value=2016, max_value=2060, value=2030, step=1)
                reduction_pct = st.number_input("Reduction Target (%)", min_value=1.0, max_value=100.0, value=30.0, step=1.0)

            submitted = st.form_submit_button("Save Target", use_container_width=True)
            if submitted:
                if target_year <= baseline_year:
                    st.error("Target year must be strictly greater than baseline year.")
                else:
                    payload = {
                        "scope": scope_val,
                        "baseline_year": int(baseline_year),
                        "target_year": int(target_year),
                        "reduction_pct": float(reduction_pct),
                    }
                    ok, res = api_post("analytics/targets", json_data=payload)
                    if ok:
                        st.success("Target saved successfully!")
                        st.rerun()
                    else:
                        st.error(f"Failed to save target: {res.get('detail', 'Unknown error')}")
else:
    st.info("ℹ️ You are viewing targets with Contributor access (view-only mode). Managers and Admins can create new targets.")

st.divider()

# 2. Fetch Target Status
with st.spinner("Loading targets and tracking status..."):
    ok_status, targets_status = api_get("analytics/targets/status")

if not ok_status or not targets_status:
    st.info(
        "🎯 No reduction targets defined yet.\n\n"
        "Setting emission reduction targets helps you plan science-based decarbonization pathways "
        "and track actual progress year over year."
    )
    st.stop()

# 3. Targets Summary Table
st.subheader("Active Targets Summary")
summary_rows = []
for t in targets_status:
    status_label = "On track" if t.get("status") == "on_track" else "Off track"
    scope_str = t.get("scope").replace("_", " ").title() if t.get("scope") else "All Scopes"
    summary_rows.append({
        "Scope": scope_str,
        "Baseline Year": t.get("baseline_year"),
        "Target Year": t.get("target_year"),
        "Reduction (%)": f"{t.get('reduction_pct', 0.0):.1f}%",
        "Baseline (t)": f"{t.get('baseline_t', 0.0):,.2f}",
        "Target (t)": f"{t.get('target_t', 0.0):,.2f}",
        "Expected Now (t)": f"{t.get('expected_now', 0.0):,.2f}",
        "Actual YTD (t)": f"{t.get('actual_t', 0.0):,.2f}",
        "Saved (t)": f"{t.get('saved_t', 0.0):,.2f}",
        "Status": status_label,
    })

df_targets = pd.DataFrame(summary_rows)
st.dataframe(styled_table(df_targets), use_container_width=True, hide_index=True)

st.divider()

# 4. Individual Target Trajectory Charts
st.subheader("Target Decarbonization Pathways")

for idx, t in enumerate(targets_status, 1):
    scope_str = t.get("scope").replace("_", " ").title() if t.get("scope") else "All Scopes"
    base_yr = t["baseline_year"]
    tgt_yr = t["target_year"]
    current_yr = date.today().year
    
    base_t = float(t.get("baseline_t") or 0.0)
    tgt_t = float(t.get("target_t") or 0.0)
    expected_now = float(t.get("expected_now") or 0.0)
    actual_t = float(t.get("actual_t") or 0.0)
    is_on_track = t.get("status") == "on_track"
    status_str = "On track" if is_on_track else "Off track"
    status_col = get_status_color(status_str)

    with st.container():
        st.markdown(f"#### Target #{idx}: {scope_str} (-{t.get('reduction_pct')}%) &nbsp; <span style='background-color:{status_col}22; color:{status_col}; padding:3px 10px; border-radius:4px; font-weight:600; font-size:14px;'>{status_str.upper()}</span>", unsafe_allow_html=True)
        
        # Plot straight-line path vs actual
        fig = go.Figure()

        # 1. Straight-line pathway (baseline to target)
        fig.add_trace(go.Scatter(
            x=[base_yr, tgt_yr],
            y=[base_t, tgt_t],
            mode="lines+markers",
            name="Target Pathway (Linear)",
            line=dict(color="#111111", dash="dash", width=2.5),
            marker=dict(symbol="circle", size=8, color="#111111"),
            hovertemplate="Year %{x}: %{y:.2f} t CO2e<extra></extra>",
        ))

        # 2. Expected Now milestone marker
        fig.add_trace(go.Scatter(
            x=[current_yr],
            y=[expected_now],
            mode="markers",
            name="Expected Now (Milestone)",
            marker=dict(symbol="diamond", size=10, color="#0072B2"),
            hovertemplate="Expected Now (%{x}): %{y:.2f} t CO2e<extra></extra>",
        ))

        # 3. Actual Current Year Emissions
        fig.add_trace(go.Scatter(
            x=[current_yr],
            y=[actual_t],
            mode="markers",
            name="Actual Emissions (Current Year)",
            marker=dict(symbol="circle", size=12, color=status_col),
            hovertemplate=f"Actual (%{{x}}): %{{y:.2f}} t CO2e ({status_str})<extra></extra>",
        ))

        apply_plotly_theme(fig, yaxis_title="Emissions (t CO2e)", xaxis_title="Year")
        fig.update_layout(
            height=300,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=20, t=30, b=30),
        )
        fig.update_xaxes(tickmode="linear", dtick=1)
        st.plotly_chart(fig, use_container_width=True)
        st.plotly_chart(fig, use_container_width=True)
