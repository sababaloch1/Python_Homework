"""api/app/analytics/reports.py - FR-3.08 & NFR-3.06: Reporting export endpoints (CSV and PDF).

Endpoints:
- GET /analytics/report.csv: Structured CSV export with SUMMARY, SCOPE_SPLIT, and FACILITY_BREAKDOWN sections.
- GET /analytics/report.pdf: Formatted PDF report with title, period, totals, scope table, top 5 sources,
  flagged anomaly months, and demo-quality disclaimer note.

PDF library used: reportlab==5.1.0 (added to requirements.txt).
"""

from datetime import date
import io
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from api.app.analytics.anomaly import calculate_anomalies
from api.app.analytics.breakdown import calculate_breakdown
from api.app.analytics.sources import calculate_top_sources
from api.app.analytics.summary import calculate_summary
from api.app.core.database import get_db
from api.app.core.deps import get_current_user
from api.app.core.models import User

router = APIRouter(tags=["S3 Analytics"])

DEMO_DISCLAIMER = (
    "Note: Emission factors and tariffs used in this report are demo-quality "
    "and provided for demonstration and educational purposes under the CarbonLens FH Dortmund project."
)


def generate_csv_report(
    summary_data: dict,
    facility_breakdown: list,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> str:
    """Builds a multi-section CSV report using pandas.

    Sections:
    1. SUMMARY (Period, Total t CO2e, Scope 1, Scope 2, Scope 3, Failed Records, Total Cost EUR, Cost Complete)
    2. SCOPE_SPLIT (Scope, t_co2e, share_pct)
    3. FACILITY_BREAKDOWN (Facility, t_co2e, share_pct)
    """
    total_t = float(summary_data.get("total_t_co2e") or 0.0)
    by_scope = summary_data.get("by_scope") or {}
    s1 = float(by_scope.get("scope_1") or 0.0)
    s2 = float(by_scope.get("scope_2") or 0.0)
    s3 = float(by_scope.get("scope_3") or 0.0)

    # 1. Summary DataFrame
    summary_rows = [
        {"Metric": "Report Start", "Value": str(start) if start else "All Available"},
        {"Metric": "Report End", "Value": str(end) if end else "All Available"},
        {"Metric": "Total Emissions (t CO2e)", "Value": f"{total_t:.4f}"},
        {"Metric": "Scope 1 (t CO2e)", "Value": f"{s1:.4f}"},
        {"Metric": "Scope 2 (t CO2e)", "Value": f"{s2:.4f}"},
        {"Metric": "Scope 3 (t CO2e)", "Value": f"{s3:.4f}"},
        {"Metric": "Failed Records", "Value": str(summary_data.get("failed_records", 0))},
        {"Metric": "Total Cost (EUR)", "Value": f"{float(summary_data.get('total_cost_eur') or 0.0):.2f}"},
        {"Metric": "Cost Complete", "Value": "Yes" if summary_data.get("cost_complete") else "No"},
    ]
    df_summary = pd.DataFrame(summary_rows)

    # 2. Scope Split DataFrame
    scope_rows = [
        {"Scope": "Scope 1", "t_co2e": round(s1, 4), "share_pct": round((s1 / total_t * 100), 2) if total_t > 0 else 0.0},
        {"Scope": "Scope 2", "t_co2e": round(s2, 4), "share_pct": round((s2 / total_t * 100), 2) if total_t > 0 else 0.0},
        {"Scope": "Scope 3", "t_co2e": round(s3, 4), "share_pct": round((s3 / total_t * 100), 2) if total_t > 0 else 0.0},
    ]
    df_scope = pd.DataFrame(scope_rows)

    # 3. Facility Breakdown DataFrame
    facility_rows = []
    for item in facility_breakdown:
        fac_t = float(item.get("t_co2e") or 0.0)
        share = round((fac_t / total_t * 100), 2) if total_t > 0 else 0.0
        facility_rows.append({
            "Facility": item.get("label", "Unassigned"),
            "t_co2e": round(fac_t, 4),
            "share_pct": share,
        })
    df_facility = pd.DataFrame(facility_rows if facility_rows else [{"Facility": "No data", "t_co2e": 0.0, "share_pct": 0.0}])

    # Combine into CSV string with section headers
    output = io.StringIO()
    output.write("# SECTION: SUMMARY\n")
    df_summary.to_csv(output, index=False)
    output.write("\n# SECTION: SCOPE_SPLIT\n")
    df_scope.to_csv(output, index=False)
    output.write("\n# SECTION: FACILITY_BREAKDOWN\n")
    df_facility.to_csv(output, index=False)

    return output.getvalue()


def generate_pdf_report(
    org_name: str,
    summary_data: dict,
    facility_breakdown: list,
    top_sources: list,
    anomalies: list,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> bytes:
    """Builds a monochrome, professional PDF report using ReportLab.

    Contents:
    - Title & Organization
    - Period & Total Emissions KPI
    - Scope Table
    - Facility Breakdown Table
    - Top 5 Sources Table
    - Flagged Anomaly Months
    - Demo factor disclaimer note
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    
    # Custom Monochrome Styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#000000"),
        fontName="Helvetica-Bold",
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#555555"),
        fontName="Helvetica",
        spaceAfter=14,
    )
    h2_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#111111"),
        fontName="Helvetica-Bold",
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "DocBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#222222"),
        fontName="Helvetica",
    )
    disclaimer_style = ParagraphStyle(
        "Disclaimer",
        parent=styles["Italic"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#666666"),
        fontName="Helvetica-Oblique",
        spaceBefore=16,
    )

    story = []

    # Title & Subtitle
    story.append(Paragraph("CarbonLens — Sustainability & Emissions Report", title_style))
    period_str = f"Period: {start if start else 'Earliest'} to {end if end else 'Latest'}"
    story.append(Paragraph(f"Organization: <b>{org_name}</b> | {period_str}", subtitle_style))

    # Summary KPI Block
    total_t = float(summary_data.get("total_t_co2e") or 0.0)
    by_scope = summary_data.get("by_scope") or {}
    s1 = float(by_scope.get("scope_1") or 0.0)
    s2 = float(by_scope.get("scope_2") or 0.0)
    s3 = float(by_scope.get("scope_3") or 0.0)
    total_cost = float(summary_data.get("total_cost_eur") or 0.0)

    summary_table_data = [
        ["Total Emissions", "Scope 1 (Direct)", "Scope 2 (Indirect)", "Scope 3 (Value Chain)", "Total Cost"],
        [
            f"{total_t:.2f} t CO2e",
            f"{s1:.2f} t",
            f"{s2:.2f} t",
            f"{s3:.2f} t",
            f"€{total_cost:,.2f}",
        ],
    ]
    t_summary = Table(summary_table_data, colWidths=[110, 105, 105, 110, 100])
    t_summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F5F5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111111")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 12))

    # Scope Table
    story.append(Paragraph("1. Emissions by Scope", h2_style))
    scope_table_data = [
        ["Scope", "Emissions (t CO2e)", "Share (%)"],
        ["Scope 1 — Direct Combustion & Fleet", f"{s1:.4f}", f"{(s1 / total_t * 100):.1f}%" if total_t > 0 else "0.0%"],
        ["Scope 2 — Purchased Electricity (Location-based)", f"{s2:.4f}", f"{(s2 / total_t * 100):.1f}%" if total_t > 0 else "0.0%"],
        ["Scope 3 — Value Chain & Travel", f"{s3:.4f}", f"{(s3 / total_t * 100):.1f}%" if total_t > 0 else "0.0%"],
        ["Total", f"{total_t:.4f}", "100.0%"],
    ]
    t_scope = Table(scope_table_data, colWidths=[270, 140, 120])
    t_scope.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
        ("LINEBELOW", (0, -1), (-1, -1), 1.0, colors.HexColor("#333333")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_scope)
    story.append(Spacer(1, 10))

    # Top 5 Sources Table
    story.append(Paragraph("2. Top Emission Sources", h2_style))
    sources_rows = [["Rank", "Category", "Facility", "Emissions (t CO2e)", "Share (%)"]]
    if top_sources:
        for idx, src in enumerate(top_sources[:5], 1):
            src_t = float(src.get("t_co2e") or 0.0)
            share_str = f"{(src_t / total_t * 100):.1f}%" if total_t > 0 else "0.0%"
            sources_rows.append([
                str(idx),
                str(src.get("category", "")).replace("_", " ").title(),
                str(src.get("facility", "Unassigned")),
                f"{src_t:.4f}",
                share_str,
            ])
    else:
        sources_rows.append(["-", "No sources found", "-", "0.0000", "0.0%"])

    t_sources = Table(sources_rows, colWidths=[40, 170, 160, 95, 65])
    t_sources.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_sources)
    story.append(Spacer(1, 10))

    # Flagged Months / Anomalies
    story.append(Paragraph("3. Flagged Anomaly Months (>20% Above 3-Month Trailing Avg)", h2_style))
    if anomalies:
        anomaly_rows = [["Month", "Emissions (t CO2e)", "Trailing 3M Avg (t)", "Spike (%)"]]
        for anom in anomalies:
            anomaly_rows.append([
                str(anom.get("month")),
                f"{float(anom.get('value', 0.0)):.4f}",
                f"{float(anom.get('average_3m', 0.0)):.4f}",
                f"+{float(anom.get('pct_above', 0.0)):.1f}%",
            ])
        t_anom = Table(anomaly_rows, colWidths=[120, 140, 140, 130])
        t_anom.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t_anom)
    else:
        story.append(Paragraph("No anomalous months detected in this reporting period.", body_style))

    story.append(Spacer(1, 14))

    # Demo Disclaimer
    story.append(Paragraph(DEMO_DISCLAIMER, disclaimer_style))

    doc.build(story)
    return buffer.getvalue()


@router.get("/report.csv")
def get_report_csv(
    start: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """GET /analytics/report.csv - FR-3.08: Export emissions report in CSV format."""
    summary_data = calculate_summary(db, current_user.org_id, start=start, end=end)
    facility_breakdown = calculate_breakdown(db, current_user.org_id, by="facility", start=start, end=end)

    csv_content = generate_csv_report(
        summary_data=summary_data,
        facility_breakdown=facility_breakdown,
        start=start,
        end=end,
    )

    filename = f"carbonlens_report_{current_user.org_id}_{date.today().isoformat()}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/report.pdf")
def get_report_pdf(
    start: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """GET /analytics/report.pdf - FR-3.08: Export emissions report in PDF format."""
    summary_data = calculate_summary(db, current_user.org_id, start=start, end=end)
    facility_breakdown = calculate_breakdown(db, current_user.org_id, by="facility", start=start, end=end)
    top_sources = calculate_top_sources(db, current_user.org_id, limit=5, start=start, end=end)
    anomalies = calculate_anomalies(db, current_user.org_id)

    org_name = current_user.organization.name if current_user.organization else "Organization"

    pdf_bytes = generate_pdf_report(
        org_name=org_name,
        summary_data=summary_data,
        facility_breakdown=facility_breakdown,
        top_sources=top_sources,
        anomalies=anomalies,
        start=start,
        end=end,
    )

    filename = f"carbonlens_report_{current_user.org_id}_{date.today().isoformat()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
