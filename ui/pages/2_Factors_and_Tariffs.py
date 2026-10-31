"""S2 - Factors & tariffs page (FR-2.01, FR-2.02, FR-2.10).

Tabs: Factors | Tariffs | Simulate.
Login: reuses the token if Member 3's shell already stored one in st.session_state
(keys tried below); otherwise shows its own small login box.
"""
import os

import pandas as pd
import requests
import streamlit as st

from ui.auth_state import current_email, current_org_name, current_role
from ui.charts import styled_table
from ui.theme import apply_theme, current_mode

apply_theme()

API_URL = os.getenv("API_URL", "http://localhost:8000")
TOKEN_KEYS = ("token", "access_token", "jwt")   # if Member 3 uses another key, add it here

CATEGORIES = ["electricity", "natural_gas", "diesel", "petrol", "fleet_km", "refrigerant",
              "flight_short_haul", "flight_long_haul", "rail", "hotel_night",
              "employee_commute", "waste_landfill", "waste_recycled", "water"]
UNITS = ["kWh", "MWh", "m3", "litre", "km", "miles", "passenger_km", "night", "kg", "tonne"]

st.title("⚡ Factors & Tariffs")
st.caption(f"Organization: **{current_org_name()}** | Emission Factors, Tariffs & Scenario Engine")


# ------------------------------------------------------------------ auth
def get_token():
    for key in TOKEN_KEYS:
        if st.session_state.get(key):
            return st.session_state[key]
    return None


def login_box():
    st.info("Please log in to continue.")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Log in"):
            try:
                r = requests.post(f"{API_URL}/auth/login", data={"username": email, "password": password}, timeout=10)
            except requests.RequestException as exc:
                st.error(f"API not reachable: {exc}")
                return
            if r.status_code == 200:
                st.session_state["token"] = r.json()["access_token"]
                st.rerun()
            else:
                st.error(r.json().get("detail", "Login failed"))


token = get_token()
if not token:
    login_box()
    st.stop()

HEADERS = {"Authorization": f"Bearer {token}"}


def api(method, path, **kwargs):
    """Calls the API. Returns (ok, data). Expired token -> asks to log in again."""
    try:
        r = requests.request(method, f"{API_URL}{path}", headers=HEADERS, timeout=30, **kwargs)
    except requests.RequestException as exc:
        return False, f"API not reachable: {exc}"
    if r.status_code == 401:
        for key in TOKEN_KEYS:
            st.session_state.pop(key, None)
        st.warning("Session expired. Please log in again.")
        st.rerun()
    try:
        data = r.json() if r.content else None
    except ValueError:
        data = r.text
    return r.status_code < 400, data


def show_error(data):
    detail = data.get("detail") if isinstance(data, dict) else data
    if isinstance(detail, dict):
        st.error(detail.get("message", "Request failed"))
        errs = detail.get("errors") or []
        if errs:
            st.dataframe(pd.DataFrame(errs), use_container_width=True)
    elif isinstance(detail, list):       # FastAPI validation errors
        st.error("; ".join(f"{'.'.join(map(str, e.get('loc', [])[1:]))}: {e.get('msg')}" for e in detail))
    else:
        st.error(str(detail))


def show_import_result(result):
    st.success(f"Import {result.get('status', 'done')}: "
               f"{result.get('created', 0)} created, {result.get('versioned', 0)} new versions, "
               f"{result.get('updated', 0)} updated, {result.get('unchanged', 0)} unchanged.")


# Role check: the JWT carries the role; a non-admin gets 403 on write calls, which show_error displays.
tab_factors, tab_tariffs, tab_green, tab_sim = st.tabs(["Emission factors", "Tariffs", "Green electricity", "Simulate"])

# ------------------------------------------------------------------ factors
with tab_factors:
    f1, f2, f3, f4 = st.columns(4)
    cat = f1.selectbox("Activity type", ["(all)"] + CATEGORIES, key="f_cat")
    reg = f2.text_input("Region (e.g. DE, GLOBAL)", key="f_reg")
    yr = f3.number_input("Year (0 = all)", min_value=0, max_value=2100, value=0, key="f_yr")
    inactive = f4.checkbox("Include old versions", key="f_inactive")

    params = {"include_inactive": inactive}
    if cat != "(all)":
        params["activity_type"] = cat
    if reg.strip():
        params["region"] = reg.strip()
    if yr:
        params["year"] = int(yr)
    ok, data = api("GET", "/engine/factors", params=params)
    if ok:
        df = pd.DataFrame(data)
        if df.empty:
            st.info("No factors found.")
        else:
            cols = ["activity_type", "region", "year", "unit", "kg_co2e_per_unit", "scope",
                    "ghg_category", "version", "is_active", "source"]
            st.dataframe(styled_table(df[cols], mode=current_mode()), use_container_width=True, hide_index=True)
            st.caption(f"{len(df)} factor(s). Changing a factor creates a new version; old ones are kept (NFR-2.08).")
    else:
        show_error(data)

    st.subheader("Import factors from CSV (admin)")
    st.caption("Columns: activity_type, region, year, unit, kg_co2e_per_unit, scope, ghg_category, source. "
               "The whole file is rejected if any row is wrong.")
    up = st.file_uploader("CSV file", type="csv", key="f_up")
    if up and st.button("Import factors"):
        ok, res = api("POST", "/engine/factors/import", files={"file": (up.name, up.getvalue(), "text/csv")})
        show_import_result(res) if ok else show_error(res)

    st.subheader("Add or update one factor (admin)")
    with st.form("one_factor"):
        c1, c2, c3 = st.columns(3)
        a_cat = c1.selectbox("Activity type", CATEGORIES, key="a_cat")
        a_reg = c2.text_input("Region", value="DE")
        a_yr = c3.number_input("Year", 1990, 2100, 2026)
        c4, c5, c6 = st.columns(3)
        a_unit = c4.selectbox("Unit", UNITS)
        a_val = c5.text_input("kg CO2e per unit", value="")
        a_scope = c6.selectbox("Scope", ["scope_1", "scope_2", "scope_3"])
        a_ghg = st.text_input("GHG category (optional)")
        a_src = st.text_input("Source (required)")
        if st.form_submit_button("Save factor"):
            body = {"activity_type": a_cat, "region": a_reg, "year": int(a_yr), "unit": a_unit,
                    "kg_co2e_per_unit": a_val.replace(",", "."), "scope": a_scope,
                    "ghg_category": a_ghg or None, "source": a_src}
            ok, res = api("POST", "/engine/factors", json=body)
            if ok:
                st.success(f"Saved: version {res['version']}. Affected results were recalculated.")
            else:
                show_error(res)

# ------------------------------------------------------------------ tariffs
with tab_tariffs:
    ok, data = api("GET", "/engine/tariffs")
    if ok:
        df = pd.DataFrame(data)
        if df.empty:
            st.info("No tariffs yet.")
        else:
            t_cols = ["activity_type", "region", "year", "unit", "eur_per_unit", "source"]
            st.dataframe(styled_table(df[t_cols], mode=current_mode()), use_container_width=True, hide_index=True)
    else:
        show_error(data)

    st.subheader("Import tariffs from CSV (admin)")
    st.caption("Columns: activity_type, region, year, unit, eur_per_unit, source.")
    up = st.file_uploader("CSV file", type="csv", key="t_up")
    if up and st.button("Import tariffs"):
        ok, res = api("POST", "/engine/tariffs/import", files={"file": (up.name, up.getvalue(), "text/csv")})
        show_import_result(res) if ok else show_error(res)

    st.subheader("Add or update one tariff (admin)")
    with st.form("one_tariff"):
        c1, c2, c3 = st.columns(3)
        t_cat = c1.selectbox("Activity type", CATEGORIES, key="t_cat")
        t_reg = c2.text_input("Region", value="DE", key="t_reg")
        t_yr = c3.number_input("Year", 1990, 2100, 2026, key="t_yr")
        c4, c5 = st.columns(2)
        t_unit = c4.selectbox("Unit", UNITS, key="t_unit")
        t_val = c5.text_input("EUR per unit", key="t_val")
        t_src = st.text_input("Source (required)", key="t_src")
        if st.form_submit_button("Save tariff"):
            body = {"activity_type": t_cat, "region": t_reg, "year": int(t_yr), "unit": t_unit,
                    "eur_per_unit": t_val.replace(",", "."), "source": t_src}
            ok, res = api("POST", "/engine/tariffs", json=body)
            st.success("Saved. Affected results were recalculated.") if ok else show_error(res)

# ------------------------------------------------------------------ green tariff (FR-2.07)
with tab_green:
    st.caption("A facility with a green-tariff factor gets a second, market-based Scope 2 result "
               "for its electricity. The normal result stays location-based.")
    ok, facilities = api("GET", "/facilities")
    if not ok or not facilities:
        st.info("No facilities found. Create a facility first.")
    else:
        names = {f"{f['name']} ({f.get('city') or '-'})": f["id"] for f in facilities}
        choice = st.selectbox("Facility", list(names))
        fid = names[choice]
        ok, rows = api("GET", f"/engine/facilities/{fid}/green-tariff")
        if ok and rows:
            g_cols = ["year", "kg_co2e_per_kwh", "supplier", "source", "version"]
            st.dataframe(styled_table(pd.DataFrame(rows)[g_cols], mode=current_mode()),
                         use_container_width=True, hide_index=True)
        elif ok:
            st.info("This facility has no green tariff (only location-based results).")
        else:
            show_error(rows)
        with st.form("green_form"):
            c1, c2 = st.columns(2)
            g_year = c1.number_input("Year", 1990, 2100, 2026, key="g_year")
            g_val = c2.text_input("kg CO2e per kWh (supplier-specific)", key="g_val")
            g_sup = st.text_input("Supplier (optional)", key="g_sup")
            g_src = st.text_input("Source, e.g. supplier certificate (required)", key="g_src")
            if st.form_submit_button("Save green tariff (admin)"):
                body = {"year": int(g_year), "kg_co2e_per_kwh": g_val.replace(",", "."),
                        "supplier": g_sup or None, "source": g_src}
                ok, res = api("PUT", f"/engine/facilities/{fid}/green-tariff", json=body)
                st.success("Saved. Electricity results for this facility were recalculated.") if ok else show_error(res)
        if st.button("Remove green tariff (admin)"):
            ok, res = api("DELETE", f"/engine/facilities/{fid}/green-tariff")
            st.success("Removed.") if ok else show_error(res)

# ------------------------------------------------------------------ simulate (FR-2.10: nothing is saved)
with tab_sim:
    st.caption("What-if calculator. Nothing is saved to your data.")

    def sim_editor(title, key, default):
        st.markdown(f"**{title}**")
        return st.data_editor(
            pd.DataFrame(default), key=key, num_rows="dynamic", use_container_width=True,
            column_config={
                "category": st.column_config.SelectboxColumn("category", options=CATEGORIES, required=True),
                "unit": st.column_config.SelectboxColumn("unit", options=UNITS, required=True),
                "amount": st.column_config.NumberColumn("amount", min_value=0.0, required=True),
                "year": st.column_config.NumberColumn("year", min_value=1990, max_value=2100, step=1, required=True),
                "region": st.column_config.TextColumn("region", required=True),
            })

    def to_items(df):
        items = []
        for _, r in df.dropna(subset=["category", "unit", "amount", "year", "region"]).iterrows():
            items.append({"category": r["category"], "amount": str(r["amount"]), "unit": r["unit"],
                          "year": int(r["year"]), "region": str(r["region"]),
                          "label": r.get("label") or None})
        return items

    mode = st.radio("Mode", ["Calculate", "Compare before / after"], horizontal=True)
    base = [{"label": "Office electricity", "category": "electricity", "amount": 12000.0,
             "unit": "kWh", "year": 2024, "region": "DE"}]
    alt = [{"label": "Office electricity (-20%)", "category": "electricity", "amount": 9600.0,
            "unit": "kWh", "year": 2024, "region": "DE"}]

    def result_table(out):
        t = pd.DataFrame(out["items"])
        res_cols = ["label", "category", "amount", "unit", "kg_co2e", "cost_eur", "scope", "error"]
        st.dataframe(styled_table(t[res_cols], mode=current_mode()),
                     use_container_width=True, hide_index=True)
        if out["errors"]:
            st.warning(f"{out['errors']} item(s) could not be calculated (missing factor or unit mismatch). "
                       "They are NOT counted as zero.")

    if mode == "Calculate":
        df = sim_editor("Items", "sim_items", base)
        if st.button("Calculate"):
            items = to_items(df)
            if not items:
                st.warning("Add at least one complete row.")
            else:
                ok, out = api("POST", "/engine/simulate", json={"items": items})
                if ok:
                    result_table(out)
                    m1, m2 = st.columns(2)
                    m1.metric("Total kg CO2e", f"{float(out['total_kg_co2e']):,.2f}")
                    m2.metric("Total cost EUR", f"{float(out['total_cost_eur']):,.2f}")
                else:
                    show_error(out)
    else:
        before = sim_editor("Before", "sim_before", base)
        after = sim_editor("After", "sim_after", alt)
        if st.button("Compare"):
            b, a = to_items(before), to_items(after)
            if not b or not a:
                st.warning("Both tables need at least one complete row.")
            else:
                ok, out = api("POST", "/engine/simulate/compare", json={"before": b, "after": a})
                if ok:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Before kg CO2e", f"{float(out['before']['total_kg_co2e']):,.2f}")
                    c2.metric("After kg CO2e", f"{float(out['after']['total_kg_co2e']):,.2f}")
                    pct = out.get("saving_pct")
                    c3.metric("Saving kg CO2e", f"{float(out['saving_kg_co2e']):,.2f}",
                              f"{float(pct):.1f}%" if pct is not None else None)
                    st.metric("Cost saving EUR", f"{float(out['saving_cost_eur']):,.2f}")
                    result_table(out["before"])
                    result_table(out["after"])
                else:
                    show_error(out)
