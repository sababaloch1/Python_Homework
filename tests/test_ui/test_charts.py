import pandas as pd
import pytest
from ui.charts import (
    SCOPE_COLORS,
    STATUS_COLORS,
    SERIES_PALETTE,
    ANOMALY_COLOR,
    get_scope_color,
    get_status_color,
    plotly_layout,
    styled_table,
)


def test_palette_definitions():
    # Verify strict Okabe-Ito colors from specification
    assert SCOPE_COLORS["Scope 1"] == "#E69F00"
    assert SCOPE_COLORS["Scope 2"] == "#56B4E9"
    assert SCOPE_COLORS["Scope 3"] == "#009E73"

    assert STATUS_COLORS["On track"] == "#009E73"
    assert STATUS_COLORS["Off track"] == "#D55E00"
    assert ANOMALY_COLOR == "#D55E00"

    assert len(SERIES_PALETTE) >= 6
    assert SERIES_PALETTE[0] == "#E69F00"
    assert SERIES_PALETTE[1] == "#56B4E9"
    assert SERIES_PALETTE[2] == "#009E73"


def test_status_and_scope_color_helpers():
    assert get_scope_color("Scope 1") == "#E69F00"
    assert get_scope_color("scope_2") == "#56B4E9"
    assert get_status_color("On track") == "#009E73"
    assert get_status_color("Off track") == "#D55E00"


def test_plotly_layout_light_and_dark():
    layout_light = plotly_layout(mode="light", title="Emissions Overview")
    assert layout_light["paper_bgcolor"] == "rgba(0,0,0,0)"
    assert layout_light["font"]["color"] == "#111111"
    assert "t CO2e" in layout_light["yaxis"]["title"]

    layout_dark = plotly_layout(mode="dark", title="Emissions Overview")
    assert layout_dark["paper_bgcolor"] == "rgba(0,0,0,0)"
    assert layout_dark["font"]["color"] == "#FFFFFF"
    assert "t CO2e" in layout_dark["yaxis"]["title"]


def test_styled_table_without_matplotlib():
    df = pd.DataFrame({
        "scope": ["Scope 1", "Scope 2", "Scope 3"],
        "emissions_t": [12.4, 45.2, 89.1],
        "status": ["On track", "Off track", "On track"],
        "anomaly": [False, True, False],
    })
    # Must succeed without throwing AttributeError or missing matplotlib error
    styler_light = styled_table(df, mode="light")
    styler_dark = styled_table(df, mode="dark")
    html_light = styler_light.to_html()
    html_dark = styler_dark.to_html()

    assert "rgba(" in html_light
    assert "#D55E00" in html_light
    assert "rgba(" in html_dark
