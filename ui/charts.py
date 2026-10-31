"""ui/charts.py - Central Data Colour System & Plotly / Table Styling.

Strict Okabe-Ito colour-blind-safe data palette:
- Scope 1: #E69F00 (Orange)
- Scope 2: #56B4E9 (Sky Blue)
- Scope 3: #009E73 (Bluish Green)
- Extra series: #0072B2 (Blue), #D55E00 (Vermilion), #CC79A7 (Reddish Purple)
- Status On track: #009E73
- Status Off track: #D55E00
- Anomaly marker: #D55E00
"""

from typing import Any, Dict, List, Optional
import pandas as pd
import plotly.graph_objects as go

# 1. Palettes
SCOPE_COLORS: Dict[str, str] = {
    "Scope 1": "#E69F00",
    "Scope 2": "#56B4E9",
    "Scope 3": "#009E73",
    "scope_1": "#E69F00",
    "scope_2": "#56B4E9",
    "scope_3": "#009E73",
}

STATUS_COLORS: Dict[str, str] = {
    "On track": "#009E73",
    "Off track": "#D55E00",
    "on_track": "#009E73",
    "off_track": "#D55E00",
}

ANOMALY_COLOR = "#D55E00"

SERIES_PALETTE: List[str] = [
    "#E69F00",  # Scope 1 / Orange
    "#56B4E9",  # Scope 2 / Sky Blue
    "#009E73",  # Scope 3 / Bluish Green
    "#0072B2",  # Blue
    "#D55E00",  # Vermilion
    "#CC79A7",  # Reddish Purple
]


def get_scope_color(scope: str) -> str:
    """Return the Okabe-Ito hex color for a given scope."""
    key = str(scope).strip()
    return SCOPE_COLORS.get(key, SCOPE_COLORS.get(key.lower(), SERIES_PALETTE[0]))


def get_status_color(status: str) -> str:
    """Return the Okabe-Ito hex color for a given target status."""
    key = str(status).strip()
    return STATUS_COLORS.get(key, STATUS_COLORS.get(key.lower(), "#999999"))


# 2. Plotly Layout
def plotly_layout(
    mode: Optional[str] = None,
    title: Optional[str] = None,
    yaxis_title: str = "Emissions (t CO2e)",
    xaxis_title: Optional[str] = None,
) -> Dict[str, Any]:
    """Returns consistent Plotly layout settings matching light/dark mode.

    - Transparent paper and plot background.
    - Grid and font matched to mode (grey grid, white text on dark, black text on light).
    - SERIES_PALETTE set as colorway.
    - Axis titles always carry the required unit 't CO2e'.
    """
    if mode is None:
        try:
            from ui.theme import current_mode
            mode = current_mode()
        except Exception:
            mode = "light"

    is_dark = str(mode).lower() == "dark"
    font_color = "#FFFFFF" if is_dark else "#111111"
    grid_color = "#333333" if is_dark else "#E5E5E5"
    zero_line_color = "#555555" if is_dark else "#CCCCCC"

    # Enforce unit 't CO2e' on yaxis if not explicitly containing it
    if yaxis_title and "t CO2e" not in yaxis_title:
        yaxis_title = f"{yaxis_title} (t CO2e)"

    layout: Dict[str, Any] = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {
            "family": "Inter, -apple-system, BlinkMacSystemFont, sans-serif",
            "color": font_color,
            "size": 13,
        },
        "colorway": SERIES_PALETTE,
        "xaxis": {
            "showgrid": True,
            "gridcolor": grid_color,
            "zerolinecolor": zero_line_color,
            "color": font_color,
            "tickfont": {"color": font_color, "size": 12},
            "titlefont": {"color": font_color, "size": 13},
        },
        "yaxis": {
            "title": yaxis_title,
            "showgrid": True,
            "gridcolor": grid_color,
            "zerolinecolor": zero_line_color,
            "color": font_color,
            "tickfont": {"color": font_color, "size": 12},
            "titlefont": {"color": font_color, "size": 13},
        },
        "legend": {
            "font": {"color": font_color},
            "bgcolor": "rgba(0,0,0,0)",
        },
        "margin": {"l": 50, "r": 20, "t": 40 if title else 20, "b": 40},
    }

    if title:
        layout["title"] = {"text": title, "font": {"size": 16, "color": font_color}}
    if xaxis_title:
        layout["xaxis"]["title"] = xaxis_title

    return layout


def apply_plotly_theme(
    fig: go.Figure,
    mode: Optional[str] = None,
    yaxis_title: str = "Emissions (t CO2e)",
    title: Optional[str] = None,
    xaxis_title: Optional[str] = None,
    **kwargs: Any,
) -> go.Figure:
    """Convenience helper to apply plotly_layout to an existing Figure."""
    if mode is None:
        try:
            from ui.theme import current_mode
            mode = current_mode()
        except Exception:
            mode = "light"

    is_dark = str(mode).lower() == "dark"
    font_color = "#FFFFFF" if is_dark else "#111111"
    grid_color = "#333333" if is_dark else "#E5E5E5"
    zero_line_color = "#555555" if is_dark else "#CCCCCC"

    if yaxis_title and "t CO2e" not in yaxis_title:
        yaxis_title = f"{yaxis_title} (t CO2e)"

    layout_kwargs: Dict[str, Any] = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {
            "family": "Inter, -apple-system, BlinkMacSystemFont, sans-serif",
            "color": font_color,
            "size": 13,
        },
        "colorway": SERIES_PALETTE,
        "legend": {
            "font": {"color": font_color},
            "bgcolor": "rgba(0,0,0,0)",
        },
        "margin": {"l": 50, "r": 20, "t": 40 if title else 20, "b": 40},
    }

    if title:
        layout_kwargs["title"] = {"text": title, "font": {"size": 16, "color": font_color}}

    if kwargs:
        layout_kwargs.update(kwargs)

    fig.update_layout(**layout_kwargs)

    # Update axes separately so subsequent update_layout(xaxis=...) calls
    # only merge rather than wipe out tickfont/titlefont settings.
    fig.update_xaxes(
        showgrid=True,
        gridcolor=grid_color,
        zerolinecolor=zero_line_color,
        color=font_color,
        tickfont={"color": font_color, "size": 12},
        titlefont={"color": font_color, "size": 13},
        title_text=xaxis_title or "",
    )
    fig.update_yaxes(
        title_text=yaxis_title,
        showgrid=True,
        gridcolor=grid_color,
        zerolinecolor=zero_line_color,
        color=font_color,
        tickfont={"color": font_color, "size": 12},
        titlefont={"color": font_color, "size": 13},
    )

    return fig


# 3. Pandas Styler Table Styling
def _tint_color(hex_color: str, opacity: float = 0.2) -> str:
    """Converts hex '#RRGGBB' to rgba string for light tinting."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {opacity})"


def styled_table(df: pd.DataFrame, mode: Optional[str] = None) -> Any:
    """Returns a pandas Styler that colours DATA cells only without matplotlib.

    - Scope columns use scope color as a light tint background with normal text.
    - Status columns show text + status color.
    - Emission values get explicit bar styling.
    - Flagged anomaly months get anomaly color + warning indicator.
    """
    if mode is None:
        try:
            from ui.theme import current_mode
            mode = current_mode()
        except Exception:
            mode = "light"

    is_dark = str(mode).lower() == "dark"
    fg_text = "#FFFFFF" if is_dark else "#111111"

    def style_cell(val, col_name):
        val_str = str(val).strip()
        # Scope cell tinting: always use white text on the darkened tinted cell
        if col_name.lower() in ("scope", "scope_name"):
            color = get_scope_color(val_str)
            tint = _tint_color(color, 0.40 if is_dark else 0.28)
            return f"background-color: {tint}; color: #FFFFFF; font-weight: 600;"

        # Status cell styling
        if col_name.lower() in ("status", "target_status"):
            color = get_status_color(val_str)
            tint = _tint_color(color, 0.25 if is_dark else 0.18)
            return f"color: {color}; background-color: {tint}; font-weight: 600;"

        # Anomaly marker styling
        if col_name.lower() in ("is_anomaly", "anomaly", "flagged"):
            if val is True or str(val).lower() in ("true", "yes", "⚠️ anomaly", "flagged"):
                tint = _tint_color(ANOMALY_COLOR, 0.25 if is_dark else 0.18)
                return f"color: {ANOMALY_COLOR}; background-color: {tint}; font-weight: bold;"

        return ""

    # Apply cell styling across dataframe
    styler = df.style
    for col in df.columns:
        styler = styler.map(lambda v, c=col: style_cell(v, c), subset=[col])

    return styler
