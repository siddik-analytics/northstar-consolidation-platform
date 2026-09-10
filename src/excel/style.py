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

#: The secondary accent: a muted industrial copper, not an orange.
#:
#: The workbook already had a warm colour -- a saturated amber used, without ever being named
#: as such, for whatever a chart's second series happened to be. Introducing a *separate*
#: copper beside it would have given the pack two warm hues competing at slightly different
#: saturations, which reads as indecision. So the amber is retuned to copper and there is one
#: warm colour in the system, used deliberately.
#:
#: Contrast against white is about 3.7:1 -- enough for a line, a fill, a marker or a short
#: bold label, and NOT enough for body text. It is never used for body text.
COPPER = "B07A45"
COPPER_TINT = "E8D8C8"  # a light wash, for a rule or a band, never for a whole panel

ACTUAL = "1B4965"       # deep teal-blue
BUDGET = "8C9BAB"       # grey-blue
FORECAST = COPPER       # forecast is the warm scenario, and the warm colour is copper
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
    # A quiet group heading over a band of KPI cards: small, letter-spaced by capitals rather
    # than by tracking Excel does not have, and muted so it labels without competing.
    _style("ns_kpi_band", size=8, bold=True, colour=INK_MUTED, align="left"),
    # ---- structure
    _style("ns_title", size=20, bold=True, colour=HEADER_BG, align="left"),
    _style("ns_subtitle", size=11, colour=INK_MUTED, align="left"),
    # A hairline of copper under the page title. It is the only mark on most sheets that is
    # not navy or grey, which is exactly how much identity a management pack needs.
    _style("ns_title_rule", size=1, fill=COPPER),
    # ---- the copper vocabulary
    # A hairline of copper directly beneath a navy section bar. This is the workbook's
    # signature: navy states the section, copper closes it. It is the one treatment that IS
    # repeated, because a section header system is meant to be consistent -- the variety comes
    # from the accents on the pages themselves.
    _style("ns_section_rule", size=1, fill=COPPER),
    # A light copper wash behind a group of analytical columns -- variance, outlook, movement.
    # It tells a reader where the reported figures stop and the analysis begins without a
    # single extra word or line.
    _style("ns_colhead_x", size=10, bold=True, colour=INK, fill=COPPER_TINT, align="right"),
    _style("ns_group_tint", size=10, colour=INK, fill=COPPER_TINT, align="right"),
    _style("ns_group_tint_l", size=10, colour=INK, fill=COPPER_TINT, align="left", indent=1),
    # KPI band two: a copper edge above it and a light wash behind its labels, so the two
    # bands read as two groups rather than ten cards.
    _style("ns_kpi_band_rule", size=1, fill=COPPER),
    _style("ns_kpi_label_x", size=10, colour=INK_MUTED, fill=COPPER_TINT, align="left",
           indent=1, top=Side(style="medium", color=COPPER)),
    _style("ns_kpi_value_x", size=18, bold=True, colour=HEADER_BG, fill=COPPER_TINT,
           align="left", indent=1),
    _style("ns_kpi_value_rx", size=18, bold=True, colour=HEADER_BG, fill=COPPER_TINT,
           align="left", indent=1, fmt=RATIO),
    _style("ns_kpi_value_nx", size=18, bold=True, colour=HEADER_BG, fill=COPPER_TINT,
           align="left", indent=1, fmt=FTE),
    _style("ns_kpi_sub_x", size=8, colour=INK_MUTED, fill=COPPER_TINT, align="left", indent=1),
    # A copper marker cell: a solid square used as a category key beside a layer or a label.
    _style("ns_marker_copper", size=1, fill=COPPER),
    _style("ns_marker_tint", size=1, fill=COPPER_TINT),
    _style("ns_marker_navy", size=1, fill=HEADER_BG),
    _style("ns_marker_rule", size=1, fill=RULE_STRONG),
    # Copper text, reserved for a short bold label -- never body text. Contrast on white is
    # 3.7:1, which is enough for this and not enough for a paragraph.
    _style("ns_label_copper", size=10, bold=True, colour=COPPER, align="left"),
    _style("ns_label_copper_i", size=10, bold=True, colour=COPPER, align="left", indent=1),
    # The covenant limit as a figure: copper, because it is the agreement's term and not a
    # status. The reader's eye finds the threshold on the table the way it finds the dashed
    # line on the chart -- same colour, same meaning.
    _style("ns_ratio_copper", size=10, bold=True, colour=COPPER, fmt=RATIO),
    # The same idea for an amount: a policy floor or a contractual figure, in copper because
    # it is a term the business has set itself and not a result it has reported.
    _style("ns_m1_copper", size=10, bold=True, colour=COPPER, fmt=USD_M1),
    _style("ns_note_copper", size=9, italic=True, colour=COPPER, align="left", indent=1),
    _style("ns_section", size=12, bold=True, colour=HEADER_TX, fill=HEADER_BG, align="left",
           indent=1, bottom=Side(style="medium", color=COPPER)),
    _style("ns_section_r", size=12, bold=True, colour=HEADER_TX, fill=HEADER_BG,
           bottom=Side(style="medium", color=COPPER),
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
