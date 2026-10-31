"""ui/pages_public/landing.py - Public landing page.

Strict monochrome aesthetic, fully responsive at 1280 px.
Displays in exact specified order:
1. Header: Project name, tagline, theme toggle, Login / Sign up buttons.
2. Hero: Overview of enterprise decarbonization platform.
3. What we offer: 8 feature cards with status badges.
4. How we calculate CO2e: Formula, Scope 1/2/3 breakdown, location vs market, worked example, versioned audit traces.
5. How it works: 4 sequential steps.
6. Footer: "FH Dortmund Capstone Project" and verified member names from ui/site_content.py only.
"""

import streamlit as st

from ui.theme import apply_theme, current_mode
from ui import site_content


def render_landing_page(navigate_to=None):
    apply_theme()
    mode = current_mode()
    is_dark = mode == "dark"

    card_bg = "#141414" if is_dark else "#fcfcfc"
    card_border = "#262626" if is_dark else "#e5e5e5"
    subtext_color = "#999999" if is_dark else "#555555"

    # Custom card CSS helper
    st.markdown(
        f"""
        <style>
        .landing-card {{
            background-color: {card_bg};
            border: 1px solid {card_border};
            border-radius: 6px;
            padding: 1.25rem;
            margin-bottom: 1rem;
            height: 100%;
        }}
        .landing-card h4 {{
            margin-top: 0;
            margin-bottom: 0.5rem;
        }}
        .landing-card p {{
            color: {subtext_color};
            font-size: 0.92rem;
            line-height: 1.45;
            margin: 0;
        }}
        .badge-soon {{
            display: inline-block;
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            border: 1px solid {subtext_color};
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 6px;
        }}
        .step-box {{
            background-color: {card_bg};
            border: 1px solid {card_border};
            border-radius: 6px;
            padding: 1.2rem;
            text-align: left;
        }}
        .step-num {{
            font-size: 1.5rem;
            font-weight: 700;
            margin-bottom: 0.4rem;
        }}
        .footer-container {{
            text-align: center;
            padding: 2.5rem 0 1rem 0;
            border-top: 1px solid {card_border};
            margin-top: 3rem;
            color: {subtext_color};
            font-size: 0.88rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # 2. Hero Section
    st.markdown(f"## {site_content.HERO_TITLE}")
    st.markdown(f"<p style='font-size: 1.12rem; line-height: 1.6; color: {subtext_color};'>{site_content.HERO_DESCRIPTION}</p>", unsafe_allow_html=True)
    st.write("")

    # 3. What We Offer
    st.markdown("### What We Offer")
    offerings = site_content.WHAT_WE_OFFER

    # Render in 4 columns x 2 rows
    row1 = offerings[:4]
    row2 = offerings[4:]

    cols1 = st.columns(4)
    for idx, item in enumerate(row1):
        with cols1[idx]:
            badge = f"<span class='badge-soon'>{item['status']}</span>" if "status" in item else ""
            st.markdown(
                f"""
                <div class="landing-card">
                    <h4>{item['icon']} {item['title']}{badge}</h4>
                    <p>{item['description']}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    cols2 = st.columns(4)
    for idx, item in enumerate(row2):
        with cols2[idx]:
            badge = f"<span class='badge-soon'>{item['status']}</span>" if "status" in item else ""
            st.markdown(
                f"""
                <div class="landing-card">
                    <h4>{item['icon']} {item['title']}{badge}</h4>
                    <p>{item['description']}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.divider()

    # 4. How We Calculate CO2e
    st.markdown("### How We Calculate CO2e")
    calc = site_content.CALCULATION_EXPLANATION

    st.markdown(
        f"""
        <div style="background-color: {card_bg}; border: 1px solid {card_border}; border-radius: 6px; padding: 1.25rem; margin-bottom: 1.5rem;">
            <p style="font-size: 1.15rem; font-weight: 600; margin-bottom: 0.75rem;">Formula: <code>{calc['formula']}</code></p>
            <p style="color: {subtext_color}; line-height: 1.5; margin-bottom: 1rem;">{calc['electricity_methods']}</p>
            <p style="margin-bottom: 0.3rem;"><strong>Worked Example:</strong></p>
            <ul style="color: {subtext_color}; margin-top: 0; line-height: 1.5;">
                <li>Activity: {calc['example']['activity']}</li>
                <li>Factor: {calc['example']['factor']}</li>
                <li><strong>Result:</strong> <code>{calc['example']['calculation']}</code></li>
            </ul>
            <p style="font-size: 0.88rem; color: {subtext_color}; margin-top: 0.75rem; border-top: 1px dashed {card_border}; padding-top: 0.75rem;">
                ℹ️ <em>{calc['trace_note']}</em>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    s_cols = st.columns(3)
    for idx, sc in enumerate(calc["scopes"]):
        with s_cols[idx]:
            st.markdown(
                f"""
                <div class="landing-card">
                    <h4>{sc['scope']}</h4>
                    <p>{sc['desc']}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.divider()

    # 5. How It Works
    st.markdown("### How It Works")
    step_cols = st.columns(4)
    for idx, step in enumerate(site_content.HOW_IT_WORKS_STEPS):
        with step_cols[idx]:
            st.markdown(
                f"""
                <div class="step-box">
                    <div class="step-num">0{step['step']}</div>
                    <div style="font-weight: 600; font-size: 1.05rem; margin-bottom: 0.35rem;">{step['title']}</div>
                    <p style="color: {subtext_color}; font-size: 0.88rem; line-height: 1.4; margin: 0;">{step['desc']}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # 6. Footer (Strictly FH Dortmund Capstone Project and Member names only)
    members_str = " • ".join(site_content.MEMBERS)
    st.markdown(
        f"""
        <div class="footer-container">
            <div style="font-weight: 600; margin-bottom: 0.4rem;">{site_content.FOOTER_PROJECT}</div>
            <div>{members_str}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    st.set_page_config(page_title="CarbonLens", page_icon="🌍", layout="wide")
    render_landing_page()
