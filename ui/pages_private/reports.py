"""ui/pages_private/reports.py - FR-3.08: Export Emissions Reports (CSV & PDF).

Features:
- Period picker (start and end date)
- Download buttons for CSV and PDF using st.download_button
- Calls GET /analytics/report.csv and GET /analytics/report.pdf
- Loading spinner while generating report bytes
- Graceful error handling for slow/failed responses
- Strict adherence to monochrome theme
"""

from datetime import date
import streamlit as st

from ui.api_client import api_get
from ui.auth_state import current_org_name
from ui.theme import apply_theme

apply_theme()

st.title("📄 Audit & Compliance Reports")
st.caption(f"Organization: **{current_org_name()}** | Official GHGP & CSRD Alignment Exports")

st.markdown(
    "Export comprehensive emissions summaries, scope breakdowns, facility aggregations, "
    "and identified anomalies in standard audit-ready formats."
)

st.divider()

# 1. Period Filter
col_p1, col_p2 = st.columns(2)
with col_p1:
    start_date = st.date_input("Start date", value=date(2025, 1, 1), help="Leave as earliest for full history")
with col_p2:
    end_date = st.date_input("End date", value=date.today(), help="Report through this date")

if start_date > end_date:
    st.error("Start date must be before or equal to End date.")
    st.stop()

params = {
    "start": start_date.isoformat(),
    "end": end_date.isoformat(),
}

st.markdown("### Choose Export Format")

col_csv, col_pdf = st.columns(2)

# 2. CSV Report Section
with col_csv:
    st.markdown(
        """
        <div style="border: 1px solid #CCCCCC; border-radius: 8px; padding: 20px; background-color: rgba(245, 245, 245, 0.4); height: 100%;">
            <h4>📊 Raw Data & Summary (CSV)</h4>
            <p style="font-size: 13px; color: #555;">
                Includes structured sections for overall emissions KPIs, Scope 1/2/3 breakdown,
                and facility-level aggregations suitable for spreadsheet modeling and external audit tools.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    if st.button("Generate CSV Export", key="btn_gen_csv", use_container_width=True):
        with st.spinner("Compiling CSV report..."):
            ok_csv, res_csv = api_get("analytics/report.csv", params=params, timeout=12)
            if ok_csv:
                csv_bytes = res_csv if isinstance(res_csv, (bytes, str)) else str(res_csv)
                st.download_button(
                    label="⬇️ Download CSV File",
                    data=csv_bytes,
                    file_name=f"carbonlens_report_{start_date}_{end_date}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            else:
                err_msg = res_csv.get("detail", "Error generating CSV report.") if isinstance(res_csv, dict) else str(res_csv)
                st.error(f"Failed to generate CSV: {err_msg}")

# 3. PDF Report Section
with col_pdf:
    st.markdown(
        """
        <div style="border: 1px solid #CCCCCC; border-radius: 8px; padding: 20px; background-color: rgba(245, 245, 245, 0.4); height: 100%;">
            <h4>📑 Official Executive Report (PDF)</h4>
            <p style="font-size: 13px; color: #555;">
                Monochrome, publication-ready PDF summary containing organizational overview,
                KPIs, scope split table, top 5 emission drivers, flagged anomalies, and demo factor notices.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    if st.button("Generate PDF Export", key="btn_gen_pdf", use_container_width=True):
        with st.spinner("Rendering PDF document..."):
            ok_pdf, res_pdf = api_get("analytics/report.pdf", params=params, timeout=15)
            if ok_pdf:
                pdf_bytes = res_pdf if isinstance(res_pdf, bytes) else str(res_pdf).encode("utf-8")
                st.download_button(
                    label="⬇️ Download PDF Document",
                    data=pdf_bytes,
                    file_name=f"carbonlens_report_{start_date}_{end_date}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            else:
                err_msg = res_pdf.get("detail", "Error generating PDF report.") if isinstance(res_pdf, dict) else str(res_pdf)
                st.error(f"Failed to generate PDF: {err_msg}")

st.divider()
st.caption(
    "Note: Emission factors and tariffs used in these reports are demo-quality and provided for demonstration "
    "and educational purposes under the CarbonLens FH Dortmund project."
)
