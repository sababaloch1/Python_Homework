"""ui/pages_private/placeholder_data_entry.py - S1 Data Entry & Activity Management.

Supports:
1. Activity History & Table View (filtering by category, deleting entries)
2. Manual Single Activity Entry (category, amount, unit, period, facility, note)
3. Bulk CSV Ingestion & CSV Template Download
"""

from datetime import date
from decimal import Decimal
import pandas as pd
import streamlit as st

from ui.api_client import api_delete, api_get, api_post
from ui.auth_state import current_org_name
from ui.charts import styled_table
from ui.theme import apply_theme, current_mode

apply_theme()

st.title("📋 Activity Data Collection")
st.caption(f"Organization: **{current_org_name()}** | Subsystem 1: Data Ingestion & Activity Logs")

CATEGORIES = [
    "electricity", "natural_gas", "diesel", "petrol", "fleet_km", "refrigerant",
    "flight_short_haul", "flight_long_haul", "rail", "hotel_night",
    "employee_commute", "waste_landfill", "waste_recycled", "water"
]

UNITS = ["kWh", "MWh", "m3", "litre", "km", "miles", "passenger_km", "night", "kg", "tonne"]

tab_list, tab_create, tab_csv = st.tabs(["Activity Records", "Log Single Activity", "Bulk CSV Import"])

# ------------------------------------------------------------------ 1. View / List Activities
with tab_list:
    f_col1, f_col2 = st.columns([3, 1])
    with f_col1:
        cat_filter = st.selectbox("Filter by Category", ["(All Categories)"] + CATEGORIES, key="de_filter_cat")
    with f_col2:
        st.write("")
        st.write("")
        refresh_btn = st.button("🔄 Refresh Data", key="de_refresh_btn", use_container_width=True)

    params = {}
    if cat_filter != "(All Categories)":
        params["category"] = cat_filter

    with st.spinner("Loading activities..."):
        ok, activities = api_get("activities", params=params)

    if not ok:
        st.error(f"Failed to load activities: {activities.get('detail', 'Unknown error') if isinstance(activities, dict) else activities}")
    elif not activities:
        st.info("No activity records found for your organization yet. Use the tabs above to log data or import a CSV.")
    else:
        df = pd.DataFrame(activities)
        display_cols = [
            col for col in ["category", "amount", "unit", "period_start", "period_end", "facility_id", "department_id", "note"]
            if col in df.columns
        ]
        st.dataframe(
            styled_table(df[display_cols], mode=current_mode()),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"Total entries: {len(df)}")

        # Delete activity action
        with st.expander("🗑️ Delete Activity Record"):
            act_ids = {f"{r.get('category')} - {r.get('amount')} {r.get('unit')} ({r.get('period_start')} to {r.get('period_end')}) [ID: {r.get('id')}]": r.get("id") for r in activities}
            selected_label = st.selectbox("Select record to delete", list(act_ids.keys()), key="del_act_sel")
            if st.button("Delete Selected Activity", type="secondary"):
                del_id = act_ids[selected_label]
                del_ok, del_res = api_delete(f"activities/{del_id}")
                if del_ok:
                    st.success("Activity deleted successfully. Associated emissions recalculated.")
                    st.rerun()
                else:
                    st.error(f"Delete failed: {del_res.get('detail', 'Unknown error') if isinstance(del_res, dict) else del_res}")


# ------------------------------------------------------------------ 2. Manual Data Entry Form
with tab_create:
    st.subheader("Record New Activity")
    st.caption("Submit utility meter readings, fuel receipts, or business travel logs.")

    # Fetch facilities and departments for dropdown
    fac_ok, facilities = api_get("facilities")
    facility_map = {"(None)": None}
    if fac_ok and isinstance(facilities, list):
        for f in facilities:
            facility_map[f"{f.get('name')} ({f.get('city') or '-'})"] = f.get("id")

    dept_ok, departments = api_get("departments")
    department_map = {"(None)": None}
    if dept_ok and isinstance(departments, list):
        for d in departments:
            department_map[d.get("name")] = d.get("id")

    with st.form("manual_activity_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            cat = st.selectbox("Activity Category *", CATEGORIES)
            amount = st.number_input("Amount / Quantity *", min_value=0.0, step=1.0, format="%.2f")
            unit = st.selectbox("Measurement Unit *", UNITS)
        with col2:
            p_start = st.date_input("Period Start Date *", value=date.today().replace(day=1))
            p_end = st.date_input("Period End Date *", value=date.today())
            fac_choice = st.selectbox("Facility (Optional)", list(facility_map.keys()))
            dept_choice = st.selectbox("Department (Optional)", list(department_map.keys()))

        note = st.text_input("Notes / Reference (e.g. Utility invoice #4829)", placeholder="Invoice / Meter Reference")
        submitted = st.form_submit_button("Record Activity & Compute CO2e", use_container_width=True)

        if submitted:
            if amount <= 0:
                st.error("Please enter an amount greater than 0.")
            elif p_start > p_end:
                st.error("Period Start date cannot be after Period End date.")
            else:
                payload = {
                    "category": cat,
                    "amount": float(amount),
                    "unit": unit,
                    "period_start": p_start.isoformat(),
                    "period_end": p_end.isoformat(),
                    "facility_id": facility_map[fac_choice],
                    "department_id": department_map[dept_choice],
                    "note": note.strip() or None,
                }
                with st.spinner("Submitting and calculating deterministic emission results..."):
                    ok, res = api_post("activities/", json_data=payload)

                if ok:
                    st.success("Activity logged successfully! The calculation trace has been computed.")
                else:
                    detail = res.get("detail") if isinstance(res, dict) else res
                    st.error(f"Failed to record activity: {detail}")


# ------------------------------------------------------------------ 3. CSV Ingestion
with tab_csv:
    st.subheader("Bulk Activity Import via CSV")
    st.caption("Upload multi-period activity logs in bulk. Automatic validation checks unit and category compatibility.")

    # Download Template Button
    t_ok, template_data = api_get("activities/template")
    if t_ok and template_data:
        csv_bytes = template_data if isinstance(template_data, (bytes, str)) else str(template_data)
        st.download_button(
            label="📥 Download CSV Template (activity_template.csv)",
            data=csv_bytes,
            file_name="activity_template.csv",
            mime="text/csv",
        )

    st.write("")
    uploaded_file = st.file_uploader("Upload Activities CSV", type=["csv"], key="activity_csv_file")

    if uploaded_file is not None:
        if st.button("Upload and Process File", type="primary", use_container_width=True):
            with st.spinner("Validating and importing activity rows..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "text/csv")}
                ok, res = api_post("activities/import", files=files)

            if ok:
                st.success(f"✓ {res.get('message', 'CSV imported successfully!')} ({res.get('rows_saved', 0)} rows processed)")
            else:
                detail = res.get("detail") if isinstance(res, dict) else res
                if isinstance(detail, dict):
                    st.error(f"Import error: {detail.get('message', 'CSV Import Failed')}")
                    errs = detail.get("errors") or []
                    if errs:
                        st.dataframe(pd.DataFrame(errs), use_container_width=True)
                else:
                    st.error(f"Import error: {detail}")
