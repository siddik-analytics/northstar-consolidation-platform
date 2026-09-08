"""
One style system for the whole workbook.

Every sheet draws from this and no sheet formats a cell by hand. That is the difference
between a workbook that looks designed and one that looks assembled: consistency is not a
matter of care applied fifteen times, it is a matter of the decision being made once.

## The palette

Restrained on purpose. Six colours carry meaning and everything else is greyscale, so that
when something IS coloured the reader knows it matters. Scenario colours are identical on
every chart and in every table in the workbook — Budget is the same grey-blue on page 1 and
page 12 — because a reader should not have to re-learn the legend on each sheet.

## Number formats

Financial statements are read at a glance and the eye needs the shape of the number, not its
last digit. So: thousands separated, negatives in parentheses rather than with a minus sign
(the accounting convention, and much easier to spot in a column), and **zero shown as a dash**
rather than `0.0`, because a nil line and a rounding-to-nil line look identical otherwise and
neither is worth the reader's attention.

Precision follows the metric: money in USD millions to one decimal, ratios to two, percentages
to one, headcount and days to none. A leverage ratio quoted to four decimals is not more
precise, it is less readable.
"""

from __future__ import annotations

from openpyxl.styles import Alignment, Border, Font, NamedStyle, PatternFill, Side

FONT = "Calibri"

# --------------------------------------------------------------------------- palette
INK = "1F2A37"          # near-black, blue-grey: body text
INK_MUTED = "5B6B7B"    # secondary text, footnotes, units
RULE = "D5DBE1"         # hairlines
RULE_STRONG = "9AA7B4"  # subtotal and total rules
BAND = "F5F8FA"         # zebra banding, very light
HEADER_BG = "1B4965"    # section headers: deep teal-blue
HEADER_TX = "FFFFFF"
PANEL_BG = "EEF3F7"     # KPI panels and input areas
INPUT_BG = "FFF6E5"     # anything a user may change

ACTUAL = "1B4965"       # deep teal-blue
BUDGET = "8C9BAB"       # grey-blue
FORECAST = "C9772E"     # amber
PRIOR = "B7BFC7"        # light grey
FAVOURABLE = "1E7A46"   # green
UNFAVOURABLE = "B3261E" # red
NEUTRAL = INK_MUTED

SCENARIO_COLOUR = {"ACT": ACTUAL, "BUD": BUDGET, "FC": FORECAST, "PY": PRIOR}

# --------------------------------------------------------------------------- formats
USD_M1 = '#,##0.0;(#,##0.0);"–"'
USD_M2 = '#,##0.00;(#,##0.00);"–"'
USD_M0 = '#,##0;(#,##0);"–"'
PCT1 = '0.0%;(0.0%);"–"'
PCT0 = '0%;(0%);"–"'
PCT_PT = '0.0" pp";(0.0" pp");"–"'   # a margin movement is points, not percent
RATIO = '0.00"x";(0.00"x");"–"'
TURNS = '+0.00"x";(0.00"x");"–"'
FTE = '#,##0;(#,##0);"–"'
FTE1 = '#,##0.0;(#,##0.0);"–"'
DAYS = '#,##0;(#,##0);"–"'
RATE = '0.0000'
DATE = 'dd mmm yyyy'
MONTH = 'mmm yy'
TEXT = '@'

thin = Side(style="thin", color=RULE)
medium = Side(style="thin", color=RULE_STRONG)
heavy = Side(style="medium", color=HEADER_BG)


def _style(name, *, size=11, bold=False, italic=False, colour=INK, fill=None,
           fmt=None, align="right", indent=0, top=None, bottom=None, wrap=False):
    st = NamedStyle(name=name)
    st.font = Font(name=FONT, size=size, bold=bold, italic=italic, color=colour)
    if fill:
        st.fill = PatternFill("solid", fgColor=fill)
    if fmt:
        st.number_format = fmt
    st.alignment = Alignment(horizontal=align, vertical="center", indent=indent,
                             wrap_text=wrap)
    st.border = Border(top=top, bottom=bottom)
    return st


def register(wb) -> None:
    """Add every named style once. openpyxl raises if a name is added twice."""
    existing = set(wb.named_styles)
    for st in STYLES:
        if st.name not in existing:
            wb.add_named_style(st)


STYLES = [
    # ---- structure
    _style("ns_title", size=20, bold=True, colour=HEADER_BG, align="left"),
    _style("ns_subtitle", size=11, colour=INK_MUTED, align="left"),
    _style("ns_section", size=12, bold=True, colour=HEADER_TX, fill=HEADER_BG, align="left",
           indent=1),
    _style("ns_section_r", size=12, bold=True, colour=HEADER_TX, fill=HEADER_BG,
           align="right"),
    _style("ns_colhead", size=10, bold=True, colour=INK, align="right", bottom=medium),
    _style("ns_colhead_l", size=10, bold=True, colour=INK, align="left", bottom=medium),
    _style("ns_note", size=9, italic=True, colour=INK_MUTED, align="left", wrap=True),
    _style("ns_footnote", size=9, colour=INK_MUTED, align="left", wrap=True),

    # ---- row labels, by indent level
    _style("ns_label", size=11, colour=INK, align="left", indent=1),
    _style("ns_label_i", size=11, colour=INK_MUTED, align="left", indent=3),
    _style("ns_label_sub", size=11, bold=True, colour=INK, align="left", indent=1, top=medium),
    _style("ns_label_tot", size=11, bold=True, colour=HEADER_BG, align="left", indent=1,
           top=medium, bottom=heavy),

    # ---- money
    _style("ns_m1", fmt=USD_M1),
    _style("ns_m1_i", fmt=USD_M1, colour=INK_MUTED),
    _style("ns_m1_sub", fmt=USD_M1, bold=True, top=medium),
    _style("ns_m1_tot", fmt=USD_M1, bold=True, colour=HEADER_BG, top=medium, bottom=heavy),
    _style("ns_m0", fmt=USD_M0),
    _style("ns_m2", fmt=USD_M2),

    # ---- ratios and percentages
    _style("ns_pct", fmt=PCT1),
    _style("ns_pct_sub", fmt=PCT1, bold=True, top=medium),
    _style("ns_pp", fmt=PCT_PT),
    _style("ns_ratio", fmt=RATIO),
    _style("ns_ratio_sub", fmt=RATIO, bold=True, top=medium),
    _style("ns_turns", fmt=TURNS),
    _style("ns_fte", fmt=FTE),
    _style("ns_fte1", fmt=FTE1),
    _style("ns_days", fmt=DAYS),
    _style("ns_rate", fmt=RATE),
    _style("ns_date", fmt=DATE, align="left"),
    _style("ns_month", fmt=MONTH),

    # ---- variance, coloured by meaning rather than by sign
    _style("ns_var_fav", fmt=USD_M1, colour=FAVOURABLE),
    _style("ns_var_unf", fmt=USD_M1, colour=UNFAVOURABLE),
    _style("ns_var_pct_fav", fmt=PCT1, colour=FAVOURABLE),
    _style("ns_var_pct_unf", fmt=PCT1, colour=UNFAVOURABLE),

    # ---- KPI panels
    _style("ns_kpi_label", size=10, colour=INK_MUTED, fill=PANEL_BG, align="left", indent=1),
    _style("ns_kpi_value", size=18, bold=True, colour=HEADER_BG, fill=PANEL_BG, align="left",
           indent=1, fmt=USD_M1),
    _style("ns_kpi_value_r", size=18, bold=True, colour=HEADER_BG, fill=PANEL_BG, align="left",
           indent=1, fmt=RATIO),
    _style("ns_kpi_value_p", size=18, bold=True, colour=HEADER_BG, fill=PANEL_BG, align="left",
           indent=1, fmt=PCT1),
    _style("ns_kpi_value_n", size=18, bold=True, colour=HEADER_BG, fill=PANEL_BG, align="left",
           indent=1, fmt=FTE),
    _style("ns_kpi_sub", size=9, colour=INK_MUTED, fill=PANEL_BG, align="left", indent=1),
    _style("ns_kpi_sub_fav", size=9, bold=True, colour=FAVOURABLE, fill=PANEL_BG,
           align="left", indent=1),
    _style("ns_kpi_sub_unf", size=9, bold=True, colour=UNFAVOURABLE, fill=PANEL_BG,
           align="left", indent=1),

    # ---- controls and status
    _style("ns_status_ok", size=10, bold=True, colour=FAVOURABLE, align="center"),
    _style("ns_status_bad", size=10, bold=True, colour=UNFAVOURABLE, align="center"),
    _style("ns_status_info", size=10, colour=INK_MUTED, align="center"),

    # ---- user input
    _style("ns_input", size=11, bold=True, colour=INK, fill=INPUT_BG, align="left", indent=1),
    _style("ns_input_label", size=10, colour=INK_MUTED, align="right"),

    # ---- plain text in tables
    _style("ns_text", size=11, colour=INK, align="left", indent=1),
    _style("ns_text_c", size=11, colour=INK, align="center"),
    _style("ns_text_mut", size=10, colour=INK_MUTED, align="left", indent=1),
]


def widths(ws, spec: dict[str, float]) -> None:
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


def sheet_setup(ws, *, tab_colour=HEADER_BG, freeze=None, zoom=100, gridlines=False,
                landscape=True, fit_width=1) -> None:
    """
    House rules for every sheet: no gridlines (a financial report is not a spreadsheet grid),
    a consistent zoom, sensible freeze panes, and a print setup that produces one page wide.
    """
    ws.sheet_properties.tabColor = tab_colour
    ws.sheet_view.showGridLines = gridlines
    ws.sheet_view.zoomScale = zoom
    if freeze:
        ws.freeze_panes = freeze
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = fit_width
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5
