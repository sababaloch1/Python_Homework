"""ui/Home.py - Main entry point with st.navigation & access control.

Header bar (top, before every page):
  Logged-out:  🌍 CarbonLens  ·  🌙/☀️  ·  Log In  ·  Sign Up
  Logged-in:   🌍 CarbonLens  ·  🌙/☀️  ·  👤 email · Role  ·  Log Out

Sidebar: navigation links only.
"""

import streamlit as st

from ui.theme import apply_theme, toggle_theme, current_mode
from ui.auth_state import is_logged_in, current_email, current_role, logout

st.set_page_config(page_title="CarbonLens", page_icon="🌍", layout="wide")
apply_theme()

logged_in = is_logged_in()


def navigate_to_page(page_name: str):
    st.session_state["target_page"] = page_name
    st.rerun()


# ── Shared header bar (all pages) ─────────────────────────────────────────────
mode = current_mode()
toggle_icon = "🌙" if mode == "light" else "☀️"

if logged_in:
    email = current_email() or "User"
    role  = (current_role() or "contributor").capitalize()
    hc = st.columns([5, 3, 1.2, 0.5])
    hc[0].markdown(
        "<div style='font-size: 1.45rem; font-weight: 800; letter-spacing: -0.02em; display: flex; align-items: center; gap: 0.4rem;'>"
        "<span>🌍</span><span>CarbonLens</span></div>",
        unsafe_allow_html=True,
    )
    hc[1].markdown(
        f"<div style='text-align: right; font-size: 0.88rem; color: var(--muted); padding-top: 0.35rem;'>"
        f"👤 {email} · {role}</div>",
        unsafe_allow_html=True,
    )
    if hc[2].button("Log Out", key="hdr_logout_btn", use_container_width=True):
        logout()
        st.rerun()
    if hc[3].button(toggle_icon, key="hdr_theme_btn", help="Toggle theme", use_container_width=True):
        toggle_theme()
        st.rerun()
else:
    hc = st.columns([7.5, 1, 1, 0.5])
    hc[0].markdown(
        "<div style='font-size: 1.45rem; font-weight: 800; letter-spacing: -0.02em; display: flex; align-items: center; gap: 0.4rem;'>"
        "<span>🌍</span><span>CarbonLens</span></div>",
        unsafe_allow_html=True,
    )
    if hc[1].button("Log In", key="hdr_login_btn", use_container_width=True):
        navigate_to_page("Login")
    if hc[2].button("Sign Up", key="hdr_signup_btn", use_container_width=True):
        navigate_to_page("Sign Up")
    if hc[3].button(toggle_icon, key="hdr_theme_btn", help="Toggle theme", use_container_width=True):
        toggle_theme()
        st.rerun()

st.divider()

# ── Horizontal nav bar for logged-in users (replaces sidebar) ─────────────────
# (page_obj_* are defined below; this block runs at render time via pg.run())

# ── Page definitions ──────────────────────────────────────────────────────────
from ui.pages_public.landing import render_landing_page
from ui.pages_public.login import render_login_page
from ui.pages_public.signup import render_signup_page


def page_home():
    render_landing_page(navigate_to=navigate_to_page)


def page_login():
    render_login_page(navigate_to=navigate_to_page)


def page_signup():
    render_signup_page(navigate_to=navigate_to_page)


def page_about():
    apply_theme()
    render_landing_page()


page_obj_home      = st.Page(page_home,   title="Home",          icon="🏠", default=True)
page_obj_login     = st.Page(page_login,  title="Login",         icon="🔑")
page_obj_signup    = st.Page(page_signup, title="Sign Up",        icon="📝")

page_obj_dashboard = st.Page("pages_private/dashboard.py",              title="Dashboard",          icon="📊")
page_obj_targets   = st.Page("pages_private/targets.py",                title="Targets",            icon="🎯")
page_obj_score     = st.Page("pages_private/score.py",                  title="Score",              icon="🏅")
page_obj_reports   = st.Page("pages_private/reports.py",                title="Reports",            icon="📄")
page_obj_live      = st.Page("pages_private/live_monitor.py",           title="Live Monitor",       icon="📡")
page_obj_factors   = st.Page("pages/2_Factors_and_Tariffs.py",          title="Factors & Tariffs",  icon="⚡")
page_obj_data_entry= st.Page("pages_private/placeholder_data_entry.py", title="Data Entry",         icon="📋")
page_obj_coach     = st.Page("pages_private/placeholder_coach.py",      title="Coach (S4)",         icon="🤖")
page_obj_about     = st.Page(page_about,  title="About CarbonLens",     icon="ℹ️")

# ── Horizontal nav bar for logged-in users (replaces sidebar) ─────────────────
if logged_in:
    nav_items = [
        (page_obj_dashboard, "📊 Dashboard"),
        (page_obj_targets,   "🎯 Targets"),
        (page_obj_score,     "🏅 Score"),
        (page_obj_reports,   "📄 Reports"),
        (page_obj_live,      "📡 Live"),
        (page_obj_factors,   "⚡ Factors"),
        (page_obj_data_entry,"📋 Data Entry"),
        (page_obj_coach,     "🤖 Coach"),
    ]
    nav_cols = st.columns(len(nav_items))
    for col, (page_obj, label) in zip(nav_cols, nav_items):
        col.page_link(page_obj, label=label, use_container_width=True)
    st.divider()

# ── Navigation (hidden — we use inline header + nav bar instead) ───────────────
if not logged_in:
    pg = st.navigation(
        [page_obj_home, page_obj_login, page_obj_signup],
        position="hidden",
    )
else:
    pg = st.navigation(
        {
            "Analytics & Reporting (S3)": [
                page_obj_dashboard,
                page_obj_targets,
                page_obj_score,
                page_obj_reports,
                page_obj_live,
            ],
            "Platform Modules": [
                page_obj_factors,
                page_obj_data_entry,
                page_obj_coach,
            ],
            "Overview": [page_obj_about],
        },
        position="hidden",
    )

# ── Programmatic navigation ───────────────────────────────────────────────────
# Header buttons set st.session_state["target_page"]; here we turn that into a
# real page switch. Only pages in the CURRENT navigation list may be targeted.
if "target_page" in st.session_state:
    target = st.session_state.pop("target_page")

    if logged_in:
        allowed = [
            page_obj_dashboard, page_obj_targets, page_obj_score, page_obj_reports,
            page_obj_live, page_obj_factors, page_obj_data_entry, page_obj_coach,
            page_obj_about,
        ]
    else:
        allowed = [page_obj_home, page_obj_login, page_obj_signup]

    for p in allowed:
        if p.title == target:
            st.switch_page(p)        # switches page and reruns; code below is skipped

    if not logged_in:
        # Asked for a private page while logged out: send them to Login instead.
        st.switch_page(page_obj_login)

pg.run()
