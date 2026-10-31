"""ui/theme.py - Monochrome theme system (light / dark).

Colour rules:
- Background / text / borders: black, white, greys only.
- Data colours: Okabe-Ito palette only, defined in ui/charts.py.

Public API used by every page:
  apply_theme()           - inject CSS (call once near top of each page)
  current_mode()          - 'light' | 'dark'
  toggle_theme()          - flip mode
  render_theme_toggle()   - small inline ☀️/🌙 button (for header bar)
"""

import streamlit as st

# ---------------------------------------------------------------------------
# CSS variables & rules – two modes
# ---------------------------------------------------------------------------

_SHARED_CSS = """
/* Hide Streamlit chrome: toolbar, footer, hamburger */
header[data-testid="stHeader"] { display: none !important; }
footer { display: none !important; }
#MainMenu { display: none !important; }

/* Hide sidebar and its collapse toggle entirely */
section[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }

/* Compensate for removed header — keep default top padding */
.block-container { padding-top: 1.5rem !important; }

/* ---- App body ---- */
.stApp {
    background-color: var(--bg) !important;
    color: var(--fg) !important;
}

/* Sidebar – nav links only */
section[data-testid="stSidebar"] {
    border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * { color: var(--fg) !important; }

/* Typography */
h1, h2, h3, h4, h5, h6, p, span, label { color: var(--fg); }
.stMarkdown { color: var(--fg) !important; }

/* Metric cards */
div[data-testid="stMetric"], .metric-card, .theme-card {
    background-color: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    padding: 16px !important;
}

/* Inputs */
div[data-baseweb="input"] {
    background-color: var(--input-bg) !important;
}
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div,
div[data-baseweb="select"] > div {
    background-color: var(--input-bg) !important;
    border: 1px solid var(--border) !important;
    color: var(--fg) !important;
}
input, textarea {
    color: var(--fg) !important;
    background-color: transparent !important;
}

/* Fix Streamlit / BaseWeb password reveal/hide icon */
div[data-baseweb="input"] button,
div[data-baseweb="input"] [role="button"] {
    background: transparent !important;
    border: none !important;
    color: var(--fg) !important;
    box-shadow: none !important;
    padding: 0 8px !important;
}
div[data-baseweb="input"] svg {
    fill: var(--fg) !important;
    color: var(--fg) !important;
}

/* Default buttons: outlined, not filled (applies to st.button, st.download_button, and st.link_button) */
.stButton > button,
.stDownloadButton > button,
.stLinkButton > a,
div[data-testid="stDownloadButton"] > button,
div[data-testid="stLinkButton"] > a,
div[data-testid="stDownloadButton"] > button:focus,
div[data-testid="stDownloadButton"] > button:active {
    background-color: transparent !important;
    color: var(--fg) !important;
    border: 1px solid var(--border) !important;
    border-radius: 4px !important;
    transition: background-color 0.15s, border-color 0.15s;
    font-size: 0.85rem;
    padding: 4px 14px;
    text-decoration: none !important;
    box-shadow: none !important;
    outline: none !important;
}
.stButton > button *,
.stDownloadButton > button *,
.stLinkButton > a *,
div[data-testid="stDownloadButton"] > button *,
div[data-testid="stLinkButton"] > a * {
    color: var(--fg) !important;
}
.stButton > button:hover,
.stDownloadButton > button:hover,
.stLinkButton > a:hover,
div[data-testid="stDownloadButton"] > button:hover,
div[data-testid="stLinkButton"] > a:hover {
    background-color: var(--card) !important;
    border-color: var(--fg) !important;
    color: var(--fg) !important;
}
/* Override Streamlit's red focus ring on download buttons */
div[data-testid="stDownloadButton"] > button:focus:not(:active),
div[data-testid="stDownloadButton"] > button:focus-visible {
    border-color: var(--border) !important;
    box-shadow: none !important;
    outline: none !important;
}

/* Theme-toggle icon button: small, borderless, compact */
button[data-testid="baseButton-secondary"][title="Toggle theme"],
button[aria-label="Toggle theme"],
.stButton > button[title="Toggle theme"],
.stButton > button[aria-label="Toggle theme"] {
    background: transparent !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    box-shadow: none !important;
    padding: 2px 6px !important;
    font-size: 0.95rem !important;
    line-height: 1 !important;
    min-height: 32px !important;
    height: 32px !important;
    color: var(--fg) !important;
}
.stButton > button[title="Toggle theme"]:hover,
.stButton > button[aria-label="Toggle theme"]:hover {
    background: var(--card) !important;
    border-color: var(--fg) !important;
}

/* Form submit / primary action buttons stay filled */
.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"],
div[data-testid="stDownloadButton"] > button[kind="primary"] {
    background-color: var(--btn-bg) !important;
    color: var(--btn-fg) !important;
    border-color: var(--btn-bg) !important;
}
.stButton > button[kind="primary"] *,
.stDownloadButton > button[kind="primary"] *,
div[data-testid="stDownloadButton"] > button[kind="primary"] * {
    color: var(--btn-fg) !important;
}
.stButton > button[kind="primary"]:hover,
.stDownloadButton > button[kind="primary"]:hover,
div[data-testid="stDownloadButton"] > button[kind="primary"]:hover {
    background-color: var(--btn-hover) !important;
    border-color: var(--btn-hover) !important;
}

/* Expanders */
div[data-testid="stExpander"] {
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    background-color: var(--card) !important;
}

/* Dataframe */
div[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
}

/* Alerts */
div[data-testid="stAlert"] {
    background-color: var(--card) !important;
    border: 1px solid var(--border) !important;
    color: var(--fg) !important;
}

/* File Uploader styling */
div[data-testid="stFileUploader"] section,
div[data-testid="stFileUploaderDropzone"],
div[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
    background-color: var(--card) !important;
    border: 1px dashed var(--border) !important;
    color: var(--fg) !important;
}
div[data-testid="stFileUploader"] section *,
div[data-testid="stFileUploaderDropzone"] * {
    color: var(--fg) !important;
}
div[data-testid="stFileUploader"] section svg,
div[data-testid="stFileUploaderDropzone"] svg {
    fill: var(--fg) !important;
    stroke: var(--fg) !important;
}
"""

LIGHT_THEME_CSS = f"""
<style>
:root {{
    --bg: #ffffff;
    --fg: #111111;
    --muted: #666666;
    --border: #e0e0e0;
    --card: #f5f5f5;
    --input-bg: #ffffff;
    --btn-bg: #111111;
    --btn-fg: #ffffff;
    --btn-hover: #333333;
}}
section[data-testid="stSidebar"] {{ background-color: #fafafa !important; }}
{_SHARED_CSS}
</style>
"""

DARK_THEME_CSS = f"""
<style>
:root {{
    --bg: #0d0d0d;
    --fg: #f0f0f0;
    --muted: #999999;
    --border: #2a2a2a;
    --card: #161616;
    --input-bg: #1a1a1a;
    --btn-bg: #f0f0f0;
    --btn-fg: #0d0d0d;
    --btn-hover: #cccccc;
}}
section[data-testid="stSidebar"] {{ background-color: #080808 !important; }}
{_SHARED_CSS}
</style>
"""


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def current_mode() -> str:
    """Return 'light' or 'dark'. Defaults to 'light'."""
    return st.session_state.get("mode", "light")


def toggle_theme() -> None:
    st.session_state["mode"] = "dark" if current_mode() == "light" else "light"


def apply_theme() -> None:
    """Inject CSS for the current mode. Call once near the top of every page."""
    if "mode" not in st.session_state:
        st.session_state["mode"] = "light"
    css = DARK_THEME_CSS if st.session_state["mode"] == "dark" else LIGHT_THEME_CSS
    st.markdown(css, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Header bar helpers
# ---------------------------------------------------------------------------

def render_theme_toggle() -> None:
    """Render a compact ☀️/🌙 toggle button (works anywhere: header col or sidebar)."""
    mode = current_mode()
    icon = "🌙" if mode == "light" else "☀️"
    label = f"{icon} {'Dark' if mode == 'light' else 'Light'}"
    if st.button(label, key="theme_toggle_btn", help="Switch theme"):
        toggle_theme()
        st.rerun()


def render_header_bar(logged_in: bool, navigate_to=None) -> None:
    """Render the top header bar (brand · theme toggle · auth actions).

    Layout logged-out:  🌍 CarbonLens  ··  🌙  ·  Log In  ·  Sign Up
    Layout logged-in:   🌍 CarbonLens  ··  🌙  ·  👤 email · role  ·  Log Out
    """
    from ui.auth_state import current_email, current_role, logout  # avoid circular at module level

    mode = current_mode()
    toggle_label = "🌙" if mode == "light" else "☀️"

    if logged_in:
        cols = st.columns([5, 1, 2, 1])
        cols[0].markdown("**🌍 CarbonLens**")
        if cols[1].button(toggle_label, key="hdr_theme_btn", help="Toggle light/dark"):
            toggle_theme()
            st.rerun()
        email = current_email() or "User"
        role  = current_role()  or "contributor"
        cols[2].caption(f"👤 {email} · {role.capitalize()}")
        if cols[3].button("Log Out", key="hdr_logout_btn"):
            logout()
            st.rerun()
    else:
        cols = st.columns([5, 1, 1, 1])
        cols[0].markdown("**🌍 CarbonLens**")
        if cols[1].button(toggle_label, key="hdr_theme_btn", help="Toggle light/dark"):
            toggle_theme()
            st.rerun()
        if navigate_to:
            if cols[2].button("Log In", key="hdr_login_btn"):
                navigate_to("Login")
            if cols[3].button("Sign Up", key="hdr_signup_btn"):
                navigate_to("Sign Up")
