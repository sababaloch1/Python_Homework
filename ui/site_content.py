"""All public website copy and project metadata in one central place.
"""

PROJECT_NAME = "CarbonLens"
TAGLINE = "Corporate Carbon Accounting & Sustainability Intelligence"

HERO_TITLE = "Empowering organizations to measure, report, and reduce their carbon footprint."
HERO_DESCRIPTION = (
    "CarbonLens provides audit-ready greenhouse gas accounting across Scope 1, 2, and 3. "
    "Automate activity data ingestion, apply transparent versioned emission factors with complete "
    "calculation traces, monitor progress against decarbonization targets, and generate compliant "
    "ESG reports effortlessly."
)

WHAT_WE_OFFER = [
    {
        "title": "Activity Data Collection",
        "description": "Seamlessly collect data from utility meters, invoices, fuel logs, and travel records with multi-tenant isolation.",
        "icon": "📋",
    },
    {
        "title": "Automatic CO2e Calculation",
        "description": "Deterministic calculations with dual-reporting (location-based & market-based) and full trace transparency.",
        "icon": "⚡",
    },
    {
        "title": "Dashboards & Trends",
        "description": "Interactive time-series analysis, 12-month trailing trends, and granular breakdowns by facility or department.",
        "icon": "📈",
    },
    {
        "title": "Decarbonization Targets",
        "description": "Set science-based reduction milestones and track real-time progress along trajectory paths.",
        "icon": "🎯",
    },
    {
        "title": "Sustainability Score",
        "description": "A balanced 0-100 score reflecting YoY reduction, target adherence, data quality, and emissions per employee.",
        "icon": "🏅",
    },
    {
        "title": "Compliance Reports",
        "description": "Instant generation of audit-ready CSV exports and executive PDF summaries for stakeholder disclosures.",
        "icon": "📄",
    },
    {
        "title": "Live Facility Monitor",
        "description": "Continuous real-time tracking of facility smart meter emissions with automated anomaly alerts.",
        "icon": "📡",
    },
    {
        "title": "AI Sustainability Coach",
        "description": "Prescriptive, data-backed decarbonization recommendations tailored to your industry profile (coming soon).",
        "icon": "🤖",
        "status": "coming soon",
    },
]

CALCULATION_EXPLANATION = {
    "formula": "CO2e (kg) = Activity Amount × Emission Factor",
    "scopes": [
        {"scope": "Scope 1 (Direct)", "desc": "Direct greenhouse gas emissions from company-owned or controlled sources, such as natural gas boilers and fleet vehicles."},
        {"scope": "Scope 2 (Indirect - Energy)", "desc": "Indirect emissions from the generation of purchased electricity, steam, heating, and cooling consumed by the organization."},
        {"scope": "Scope 3 (Indirect - Value Chain)", "desc": "All other indirect emissions that occur across the upstream and downstream value chain, including business travel and waste."},
    ],
    "electricity_methods": (
        "We support both location-based (reflecting average grid intensity) and market-based "
        "(reflecting contractual supplier instruments and green tariffs) accounting standards."
    ),
    "example": {
        "activity": "Electricity consumption of 12,000 kWh",
        "factor": "German Grid Emission Factor: 0.363 kg CO2e / kWh",
        "calculation": "12,000 kWh × 0.363 kg CO2e/kWh = 4,356 kg CO2e (4.356 t CO2e)",
    },
    "trace_note": "Every single emission result preserves an immutable audit trace detailing the factor version, source authority, and calculation timestamp.",
}

HOW_IT_WORKS_STEPS = [
    {"step": 1, "title": "Enter Data", "desc": "Log activities directly or bulk import CSV files categorized across your facilities."},
    {"step": 2, "title": "Calculate", "desc": "Our calculation engine applies regional, versioned factors with automated currency and unit conversions."},
    {"step": 3, "title": "Analyse", "desc": "Evaluate Scope 1-3 contributions, seasonal patterns, anomalies, and department performance."},
    {"step": 4, "title": "Act", "desc": "Benchmark against targets, improve your sustainability score, and generate verified ESG disclosures."},
]

FOOTER_PROJECT = "FH Dortmund Capstone Project"
MEMBERS = [
    "Saba",
    "Tuba Jabeen",
    "Sameer Ghaffar",
    "Mustafa",
]
