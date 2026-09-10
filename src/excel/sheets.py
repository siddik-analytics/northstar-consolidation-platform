"""
The report sheets.

Layout rules applied to every sheet, because consistency is what makes a pack readable rather
than a collection of pages:

* column A is a 2-character gutter, so nothing touches the left edge;
* column B carries the row label at a fixed width, so labels line up across sheets;
* data starts at column C and every data column is the same width;
* the title block is rows 1-3, the section header sits on row 5, and content starts at row 7;
* freeze panes always lock the labels and the column headings;
* no merged cells except the title, because merged cells break sorting, filtering and copying.

Every figure is a `SUMIFS` against a hidden governed data sheet. There is no pivot on a
presentation sheet: a pivot resizes when a filter changes and takes conditional formatting and
chart ranges with it, and these sheets have to survive being exported to PDF.
"""

from __future__ import annotations

from openpyxl.chart import BarChart, LineChart, Reference, Series
from openpyxl.chart.axis import ChartLines
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.text import RichText
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.colors import ColorChoice
from openpyxl.drawing.text import (CharacterProperties, Font, Paragraph,
                                   ParagraphProperties)
from openpyxl.chart.marker import DataPoint, Marker
from openpyxl.drawing.line import LineProperties
from openpyxl.formatting.rule import CellIsRule
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.pagebreak import Break
from openpyxl.worksheet.datavalidation import DataValidation

from . import style as S
from .data import ACT_VERSION, BUD_VERSION, FC_VERSION, PY_VERSION, REPORT_FY, REPORT_PERIOD

MONTHS = [REPORT_FY * 100 + m for m in range(1, 13)]
ACTUAL_MONTHS = [p for p in MONTHS if p <= REPORT_PERIOD]
LABEL_COL = "B"
FIRST_DATA_COL = 3  # C


# ------------------------------------------------------------------ small helpers
def col(i: int) -> str:
    return get_column_letter(i)


def put(ws, cell, value, style=None):
    c = ws[cell]
    c.value = value
    if style:
        c.style = style
    return c


def title(ws, text, subtitle, width_cols=14):
    ws.merge_cells(start_row=1, start_column=2, end_row=1, end_column=width_cols)
    put(ws, "B1", text, "ns_title")
    ws.row_dimensions[1].height = 30
    put(ws, "B2", subtitle, "ns_subtitle")
    ws.row_dimensions[2].height = 16
    # A copper mark in the gutter beside the title, not a rule beneath it.
    #
    # A horizontal hairline under the title block rendered as an underline running through the
    # subtitle -- it read as an accident rather than as an accent. The gutter column is empty
    # on every sheet by design, so a short vertical mark there is unmistakably deliberate, and
    # it is the workbook's only non-navy structural element.
    for row in (1, 2):
        ws.cell(row=row, column=1).style = "ns_title_rule"


def section(ws, row, text, last_col=14, right_text=None, rule=True):
    """
    A navy section bar closed by a copper hairline.

    The rule is a **border on the bar**, not a row beneath it. Written as its own row it
    consumed the row the sheets use for their column headers, and half of "Actual YTD /
    Budget YTD / Var $" disappeared behind a copper strip on every table in the pack.

    This is the workbook's signature and the one copper treatment that repeats, because a
    section system is meant to be consistent. Everything else copper does -- the column-group
    washes, the KPI band, the chart series, the covenant threshold, the layer markers -- is
    specific to the page it appears on.
    """
    for i in range(2, last_col + 1):
        ws.cell(row=row, column=i).style = "ns_section"
    put(ws, f"B{row}", text, "ns_section")
    if right_text:
        c = ws.cell(row=row, column=last_col)
        c.value = right_text
        c.style = "ns_section_r"
    ws.row_dimensions[row].height = 20


def column_group(ws, row, first_col, last_col, label=None):
    """
    A light copper wash behind a group of analytical columns.

    Used where a reader crosses from reported figures into analysis -- the variance block, the
    full-year outlook, the movement columns on the balance sheet. It marks the boundary with a
    tint rather than another rule, because the sheets already carry enough lines.
    """
    for i in range(first_col, last_col + 1):
        ws.cell(row=row, column=i).style = "ns_colhead_x"
    if label:
        ws.cell(row=row - 1, column=first_col).value = label
        ws.cell(row=row - 1, column=first_col).style = "ns_label_copper"


def marker(ws, cell_ref, kind="copper"):
    """A small solid key square, for a category legend beside a label."""
    ws[cell_ref].style = f"ns_marker_{kind}"


def note(ws, row, text, last_col=14):
    """
    A wrapped explanatory note, with the row height computed from the text.

    Excel does not auto-fit a merged cell, so a fixed height silently clips a long note or --
    worse -- lets it overflow onto whatever is drawn below it. The covenant note ran straight
    through the section band beneath it before this measured the text.
    """
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=last_col)
    put(ws, f"B{row}", text, "ns_note")
    width = sum(ws.column_dimensions[col(i)].width or 8.43
                for i in range(2, last_col + 1))
    lines = max(1, -(-len(text) // max(int(width * 1.05), 20)))
    ws.row_dimensions[row].height = 12 + 11 * lines


def headers(ws, row, labels, first=FIRST_DATA_COL, label_text=""):
    put(ws, f"{LABEL_COL}{row}", label_text, "ns_colhead_l")
    for i, lab in enumerate(labels):
        c = ws.cell(row=row, column=first + i)
        c.value = lab
        c.style = "ns_colhead"


def measure_style(is_subtotal, is_total, indent, kind="m1"):
    if is_total:
        return f"ns_{kind}_tot"
    if is_subtotal:
        return f"ns_{kind}_sub"
    return f"ns_{kind}_i" if indent else f"ns_{kind}"


def label_style(is_subtotal, is_total, indent):
    if is_total:
        return "ns_label_tot"
    if is_subtotal:
        return "ns_label_sub"
    return "ns_label_i" if indent else "ns_label"


#: Chart text. One size for a title, one for everything else, both muted -- a chart is read
#: for its shape first and its numbers second, and 11pt black axis labels fight the shape.
CHART_TITLE_PT = 950
CHART_AXIS_PT = 800


def _text_properties(size: int, colour: str, bold: bool = False):
    """Rich text for a chart element, in the workbook's own font and palette."""
    return RichText(
        p=[Paragraph(pPr=ParagraphProperties(
            defRPr=CharacterProperties(sz=size, b=bold, latin=Font(typeface=S.FONT),
                                       solidFill=ColorChoice(srgbClr=colour))),
            endParaRPr=CharacterProperties(sz=size, b=bold))])


def _style_axis(axis, number_format=None, gridlines=False):
    """
    Make an axis visible and quiet.

    openpyxl builds an axis with `delete` unset, which Excel reads as **deleted**. Every chart
    in this workbook rendered with no value scale and no category labels because of it: bare
    lines floating over gridlines that implied a scale nobody could read. `delete = False` is
    the whole fix, and it is the reason this helper exists rather than three lines at each
    call site where the next chart would forget it again.
    """
    axis.delete = False
    if number_format:
        axis.numFmt = number_format
    axis.majorTickMark = "none"
    axis.minorTickMark = "none"
    axis.txPr = _text_properties(CHART_AXIS_PT, S.INK_MUTED)
    axis.spPr = GraphicalProperties(ln=LineProperties(solidFill=S.RULE, w=6350))
    if gridlines:
        # Present, but a hairline in the table-rule colour: enough to read a value against,
        # not enough to compete with the data.
        axis.majorGridlines = ChartLines(
            spPr=GraphicalProperties(ln=LineProperties(solidFill=S.RULE, w=6350)))
    else:
        axis.majorGridlines = None


def _frame(ch):
    """No border and no fill. The section header already frames the chart."""
    ch.graphical_properties = GraphicalProperties(noFill=True)
    ch.graphical_properties.ln = LineProperties(noFill=True)


def _keep_chart_whole(ws, anchor: str):
    """
    Start the chart band on a fresh page, unless the sheet is designed as one page.

    The Executive Summary opts out: it is meant to be taken in at a glance, and pushing its
    two trend charts onto a second page to keep them whole trades the thing that matters for
    the thing that does not.

    Sheets print as one page wide and as many pages tall as they need, so a chart placed
    under a long table lands wherever the table happens to end -- and on the cash flow sheet
    that put the page break through the middle of both charts, cutting the top off one page
    and the bottom off the next. Neither half was readable and the legend appeared without
    the plot it belonged to.

    The break goes three rows above the chart so the section header travels with it.
    """
    row = int("".join(ch for ch in anchor if ch.isdigit()) or 0)
    if row <= 4:
        return
    # Break after the last row that has content, not a fixed three rows above the chart.
    # A fixed offset lands wherever the preceding table happens to end -- on the EBITDA bridge
    # it fell inside the final table, orphaning two rows onto a page of their own and pushing
    # the chart to a third page.
    target = min(row - 1, max(ws.max_row + 1, 2))
    if target >= row or target <= 1:
        return
    if target not in {b.id for b in ws.row_breaks.brk}:
        ws.row_breaks.append(Break(id=target))


def line_chart(ws, anchor, title_text, cats_ref, series, width=17.5, height=7.2,
               number_format=S.USD_M1, y_title=None, y_min=None, y_max=None,
               page_break=False):
    ch = LineChart()
    ch.title = title_text
    ch.style = None
    ch.width, ch.height = width, height
    # A month with no actual yet is a GAP, not a zero. Excel's default plots an empty cell as
    # zero, and the first draft of the revenue chart showed the group falling off a cliff in
    # September because the actual series simply had not been posted yet.
    ch.dispBlanksAs = "gap"
    _style_axis(ch.y_axis, number_format, gridlines=True)
    _style_axis(ch.x_axis)
    # Month labels at the foot of the plot, not on the zero line -- the translation movement
    # crosses zero every other month and was drawn straight through its own labels.
    ch.x_axis.tickLblPos = "low"
    if y_min is not None:
        ch.y_axis.scaling.min = y_min
    if y_max is not None:
        ch.y_axis.scaling.max = y_max
    if y_title:
        ch.y_axis.title = y_title
    for ref, name, colour, dash in series:
        s = Series(ref, title=name)
        s.graphicalProperties.line = LineProperties(solidFill=colour, w=22000,
                                                    prstDash=dash or "solid")
        s.marker = Marker(symbol="none")
        s.smooth = False
        ch.series.append(s)
    ch.set_categories(cats_ref)
    _legend(ch, len(series))
    _title(ch, title_text)
    _frame(ch)
    if page_break:
        _keep_chart_whole(ws, anchor)
    ws.add_chart(ch, anchor)
    return ch


def _title(ch, title_text):
    """A chart title in the workbook's own voice: small, muted, not shouting."""
    if title_text is None:
        ch.title = None
        return
    ch.title = title_text
    try:
        ch.title.tx.rich.p[0].pPr = ParagraphProperties(
            defRPr=CharacterProperties(sz=CHART_TITLE_PT, b=True,
                                       latin=Font(typeface=S.FONT),
                                       solidFill=ColorChoice(srgbClr=S.INK)))
    except (AttributeError, IndexError):          # pragma: no cover - openpyxl shape
        pass


def _legend(ch, series_count):
    """
    A legend for one series names the series once and then lists every CATEGORY, which on a
    twelve-month chart is twelve entries of noise under a single line. One series needs no
    legend: the title already says what it is.
    """
    if series_count < 2:
        ch.legend = None
        return
    ch.legend.position = "b"
    ch.legend.overlay = False
    ch.legend.txPr = _text_properties(CHART_AXIS_PT, S.INK_MUTED)


def bar_chart(ws, anchor, title_text, cats_ref, series, width=17.5, height=7.2,
              number_format=S.USD_M1, overlap=-10, gap=60, horizontal=False,
              data_labels=False, page_break=False, point_colours=None):
    ch = BarChart()
    ch.type = "bar" if horizontal else "col"
    ch.style = None
    ch.dispBlanksAs = "gap"
    ch.width, ch.height = width, height
    ch.overlap = overlap
    ch.gapWidth = gap
    # Gridlines run across the value axis only, and on a horizontal bar chart that is the
    # x axis rather than the y.
    value_axis, category_axis = (ch.x_axis, ch.y_axis) if horizontal else (ch.y_axis,
                                                                          ch.x_axis)
    _style_axis(value_axis, number_format, gridlines=True)
    _style_axis(category_axis)
    # Category labels sit at the bottom of the plot, not on the zero line: on a chart with
    # negative bars Excel otherwise draws "Operating" and "Investing" inside the bars.
    category_axis.tickLblPos = "low"
    for series_idx, (ref, name, colour) in enumerate(series):
        s = Series(ref, title=name)
        s.graphicalProperties.solidFill = colour
        s.graphicalProperties.line.noFill = True
        # Excel's default inverts a negative bar to a hollow outline, which reads as missing
        # data rather than as a negative number -- the cash flow chart had three empty
        # rectangles where investing, financing and FX should have been.
        s.invertIfNegative = False
        # Individual bars may carry their own colour. Used for the EBITDA bridge, where the
        # two definitions either side and the adjustment between them are different kinds of
        # thing and should not look identical. Point colours belong to the first series
        # only: on a two-series comparison the highlight marks the unit's Actual bar, and the
        # Budget bar beside it keeps its own colour so the pair still reads as a comparison.
        if point_colours and series_idx == 0:
            s.data_points = [
                # invertIfNegative defaults ON at the point level too, and a negative bar
                # with an inverted copper fill renders as a hollow outline -- which is how
                # the investing bar came to look like missing data.
                DataPoint(idx=idx, invertIfNegative=False,
                          spPr=GraphicalProperties(
                              solidFill=colour_at,
                              ln=LineProperties(noFill=True)))
                for idx, colour_at in sorted(point_colours.items())]
        ch.series.append(s)
    ch.set_categories(cats_ref)
    if data_labels:
        # Kept for a caller that genuinely needs labels, with one caveat recorded here rather
        # than rediscovered: this openpyxl version does not serialise `numFmt` on a label
        # list, so labels render at the source value's full precision -- "29.2024", not
        # "29.2". Nothing in the pack uses them for that reason; every chart carries a visible
        # value axis instead, which is what an axis is for.
        ch.dataLabels = DataLabelList(showVal=True, showSerName=False, showCatName=False,
                                      showLegendKey=False, showPercent=False,
                                      showBubbleSize=False, showLeaderLines=False)
        ch.dataLabels.txPr = _text_properties(CHART_AXIS_PT, S.INK_MUTED)
    _legend(ch, len(series))
    _title(ch, title_text)
    _frame(ch)
    if page_break:
        _keep_chart_whole(ws, anchor)
    ws.add_chart(ch, anchor)
    return ch


def std_widths(ws, label_width=40, data_width=12, n_data=12, gutter=2.2):
    spec = {"A": gutter, LABEL_COL: label_width}
    for i in range(n_data):
        spec[col(FIRST_DATA_COL + i)] = data_width
    S.widths(ws, spec)


#: Excel column width is measured in characters of the default font; a character is very close
#: to 0.19 cm at 11pt Calibri. Charts are sized in centimetres, so the two have to be reconciled
#: somewhere, and doing it once here is better than guessing a width on fifteen sheets.
CM_PER_CHAR = 0.19


def sheet_width_cm(ws, last_col: int) -> float:
    return sum((ws.column_dimensions[col(i)].width or 8.43)
               for i in range(2, last_col + 1)) * CM_PER_CHAR


def chart_slots(ws, last_col: int, count: int = 2, gap_cm: float = 0.4):
    """
    Anchor cells and a width for `count` charts laid side by side across the sheet.

    Charts were previously given a fixed 16.5 cm and anchored at fixed columns, and on every
    sheet narrower than 33 cm the right-hand one ran off the page. Deriving both from the
    sheet's own column widths means a chart cannot be wider than the report it sits under.

    An anchor can only sit on a column edge, so each chart is anchored at the edge nearest
    its ideal position, and the shared width is trimmed only as far as is needed for the
    charts not to overlap each other or run past the last printed column.
    """
    total = sheet_width_cm(ws, last_col)
    width = (total - gap_cm * (count - 1)) / count
    # left edge of every column from B to one past the last, in cm from the left of B
    edges = [0.0]
    for column in range(2, last_col + 1):
        edges.append(edges[-1] + (ws.column_dimensions[col(column)].width or 8.43) * CM_PER_CHAR)
    anchors = []
    for k in range(count):
        target = k * (width + gap_cm)
        nearest = min(range(len(edges) - 1), key=lambda n: abs(edges[n] - target))
        anchors.append(nearest)
    slots = [col(2 + n) for n in anchors]
    for k in range(count - 1):
        width = min(width, edges[anchors[k + 1]] - edges[anchors[k]] - gap_cm)
    width = min(width, total - edges[anchors[-1]])
    return slots, round(width, 2)


# ------------------------------------------------------------------ 00 Cover
def cover(wb, meta):
    ws = wb.create_sheet("00 Cover")
    S.sheet_setup(ws, freeze="A1", zoom=100, landscape=False)
    # C and D are narrow because the control table uses them for counts; every prose
    # cell merges C:E, so descriptions still have 80 characters to run in.
    S.widths(ws, {"A": 2.2, "B": 34, "C": 16, "D": 16, "E": 48})

    title(ws, "Northstar Industrial Group", "Management reporting pack", width_cols=5)
    put(ws, "B3", f"Reporting date  ·  {meta['report_label']}   |   "
                  f"Basis  ·  Statutory   |   Currency  ·  USD", "ns_subtitle")

    section(ws, 5, "Purpose", last_col=5)
    note(ws, 6, "A monthly management reporting pack for the Board and the executive team, "
                "built directly on the governed consolidation. Every figure in this workbook "
                "is a lookup into a reporting mart that reconciles to the consolidated "
                "financial statements; the workbook adds presentation and analysis and "
                "contains no accounting policy of its own.", last_col=5)

    rows = [
        ("Model architecture", ""),
        ("  Source systems", "Three ERPs — Aurora (SAP-style), Sable (NetSuite-style), "
                             "Kestrel (Dynamics-style)"),
        ("  Consolidation", "Five layers: reported, intercompany elimination, consolidation "
                            "adjustments, management adjustments, translation"),
        ("  Reporting basis", "Statutory = layers 1+2+3+5.  Management = statutory + layer 4"),
        ("  This workbook", "Reads the Phase 5 reporting marts only. No accounting logic is "
                            "restated here"),
        ("", ""),
        ("Scenario definitions", ""),
        ("  Actual", "Reported results from the three ERP systems, consolidated and "
                     "translated at actual rates"),
        ("  Budget", f"{meta['bud_name']} — board approved {meta['bud_approved']}, locked, "
                     f"translated at locked budget rates"),
        ("  Forecast", f"{meta['fc_name']} — the current live forecast. "
                       f"{meta['fc_actual_months']} actual months plus "
                       f"{meta['fc_forecast_months']} forecast"),
        ("  Prior year", "Derived from Actual by a twelve-month offset. Never stored, so it "
                         "cannot drift from the actual it is a view of"),
        ("  Downside", "Reserved. Not populated, and deliberately not offered as a reporting "
                       "option"),
        ("", ""),
        ("Refresh", ""),
        ("  To rebuild", "python -m src.marts.run   then   python -m src.excel.build"),
        ("  Determinism", "The same inputs produce a byte-identical workbook. The build "
                          "identifiers below are digests of the inputs, not of the run"),
        ("  Source layer digest", meta["source_digest"][:32] + "…"),
        ("  Consolidation build", meta["consol_build"]),
        ("  Reporting build", meta["mart_build"]),
    ]
    r = 8
    for label, value in rows:
        if label and not value:
            section(ws, r, label, last_col=5)
        elif label:
            put(ws, f"B{r}", label, "ns_text")
            ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
            put(ws, f"C{r}", value, "ns_text_mut")
        r += 1

    section(ws, r + 1, "Control status", last_col=5)
    headers(ws, r + 2, ["Controls", "Passed", "Status"], label_text="Phase")
    r += 3
    for phase, total, passed in meta["control_summary"]:
        put(ws, f"B{r}", phase, "ns_label")
        put(ws, f"C{r}", total, "ns_fte")
        put(ws, f"D{r}", passed, "ns_fte")
        put(ws, f"E{r}", "PASS" if total == passed else "FAIL",
            "ns_status_ok" if total == passed else "ns_status_bad")
        r += 1

    section(ws, r + 1, "Navigation", last_col=5)
    r += 2
    for name, purpose in meta["navigation"]:
        put(ws, f"B{r}", name, "ns_label")
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
        put(ws, f"C{r}", purpose, "ns_text_mut")
        ws[f"B{r}"].hyperlink = f"#'{name}'!A1"
        link_colour = S.HEADER_BG
        if name == "01 Executive Summary":
            # The page to open first, for a reader who has just opened the file: a copper
            # key in the gutter and the link itself in copper. Every other entry stays navy,
            # and every description stays as written -- the pointer is colour, not words.
            marker(ws, f"A{r}", "copper")
            link_colour = S.COPPER
        ws[f"B{r}"].font = ws[f"B{r}"].font.copy(color=link_colour, underline="single",
                                                 bold=(link_colour == S.COPPER))
        r += 1

    ws.print_area = f"A1:E{r}"
    return ws


# ------------------------------------------------------------------ 01 Executive summary
KPI = [
    ("Revenue", "REVENUE", "ns_kpi_value", S.USD_M1, "USD m, year to date"),
    ("Gross margin", "GROSS_MARGIN", "ns_kpi_value_p", S.PCT1, "year to date"),
    ("EBITDA", "EBITDA", "ns_kpi_value", S.USD_M1, "USD m, year to date"),
    ("Adjusted EBITDA", "ADJ_EBITDA", "ns_kpi_value", S.USD_M1, "USD m, year to date"),
    ("EBITDA margin", "EBITDA_MARGIN", "ns_kpi_value_p", S.PCT1, "year to date"),
    ("Operating cash flow", "OCF", "ns_kpi_value", S.USD_M1, "USD m, year to date"),
    ("Net debt", "NET_DEBT", "ns_kpi_value", S.USD_M1, "USD m, at the reporting date"),
    ("Net leverage", "LEVERAGE", "ns_kpi_value_r", S.RATIO, "covenant basis"),
    ("Covenant headroom", "HEADROOM", "ns_kpi_value_r", S.RATIO, "turns against the limit"),
    ("Headcount", "FTE", "ns_kpi_value_n", S.FTE, "full-time equivalents"),
]


#: The two KPI bands, named. Ten metrics in an undifferentiated grid is ten things to read;
#: two named groups of five is a page a reader can take in at a glance, which is what an
#: executive summary is for.
KPI_BANDS = ("Performance", "Cash, leverage and capacity")

EXEC_COLS = 16


def executive(wb, meta):
    ws = wb.create_sheet("01 Executive Summary")
    S.sheet_setup(ws, freeze="C7", zoom=100)
    std_widths(ws, label_width=34, data_width=13.2, n_data=EXEC_COLS - 2)

    title(ws, "Executive summary", f"Group performance to {meta['report_label']} · "
                                   f"USD millions unless stated · statutory basis",
          width_cols=EXEC_COLS)

    # ---------------- KPI strip: five across, two rows deep
    section(ws, 5, "Key performance indicators", last_col=EXEC_COLS,
            right_text="Year to date against budget")
    r = 7
    for block in range(2):
        put(ws, f"B{r}", KPI_BANDS[block], "ns_kpi_band")
        r += 1
        for i in range(5):
            k = block * 5 + i
            if k >= len(KPI):
                break
            name, code, vstyle, fmt, sub = KPI[k]
            c1 = FIRST_DATA_COL - 1 + i * 2 if False else 2 + i * 2
            a, b = col(c1), col(c1 + 1)
            # Band one -- the trading performance -- sits on the cool neutral panel. Band two --
            # cash, leverage and capacity -- sits on the light copper wash with a copper top
            # edge, so the two groups read as two different kinds of question and not as ten
            # cards. The headline figures stay navy on both; only the ground changes.
            tinted = block == 1
            label_style = "ns_kpi_label_x" if tinted else "ns_kpi_label"
            sub_style = "ns_kpi_sub_x" if tinted else "ns_kpi_sub"
            value_style = vstyle
            if tinted:
                value_style = {"ns_kpi_value": "ns_kpi_value_x",
                               "ns_kpi_value_r": "ns_kpi_value_rx",
                               "ns_kpi_value_n": "ns_kpi_value_nx",
                               "ns_kpi_value_p": "ns_kpi_value_x"}.get(vstyle, vstyle)
            put(ws, f"{a}{r}", name, label_style)
            ws.cell(row=r, column=c1 + 1).style = label_style
            ws.merge_cells(start_row=r + 1, start_column=c1, end_row=r + 1, end_column=c1 + 1)
            cell = put(ws, f"{a}{r+1}", meta["kpi"][code]["value"], value_style)
            cell.number_format = fmt
            ws.merge_cells(start_row=r + 2, start_column=c1, end_row=r + 2, end_column=c1 + 1)
            fav = meta["kpi"][code]["fav"]
            put(ws, f"{a}{r+2}", meta["kpi"][code]["delta"],
                "ns_kpi_sub_fav" if fav == "FAVOURABLE"
                else "ns_kpi_sub_unf" if fav == "UNFAVOURABLE"
                else sub_style)
            if tinted and fav in ("FAVOURABLE", "UNFAVOURABLE"):
                # keep the status colour, but on the band's own ground
                ws[f"{a}{r+2}"].fill = ws[f"{a}{r}"].fill.copy()
            ws.merge_cells(start_row=r + 3, start_column=c1, end_row=r + 3, end_column=c1 + 1)
            put(ws, f"{a}{r+3}", sub, sub_style)
        ws.row_dimensions[r].height = 15
        ws.row_dimensions[r + 1].height = 26
        ws.row_dimensions[r + 2].height = 13
        ws.row_dimensions[r + 3].height = 13
        r += 5

    # ---------------- performance summary
    section(ws, r, "Group performance", last_col=EXEC_COLS, right_text="USD m")
    r += 1
    header_row = r
    headers(ws, r, ["Actual YTD", "Budget YTD", "Var $", "Var %", "Prior year YTD",
                    "Var $", "FY outlook", "FY budget", "Var $"], label_text="")
    # The last three columns look forward. A light copper wash on their headers marks where
    # the reported year to date ends and the outlook begins, which is the one boundary on this
    # table a reader must not cross without noticing.
    column_group(ws, r, FIRST_DATA_COL + 6, FIRST_DATA_COL + 8)
    hdr = r
    r += 1
    body_start = r
    for code, name, sub in meta["summary_rows"]:
        put(ws, f"B{r}", name, "ns_label_sub" if sub else "ns_label")
        st = "ns_m1_sub" if sub else "ns_m1"
        ws[f"C{r}"] = (f'=SUMIFS(pl_ytd,pl_measure,"{code}",pl_scen,"ACT",'
                       f'pl_period,{REPORT_PERIOD})')
        ws[f"D{r}"] = (f'=SUMIFS(pl_ytd,pl_measure,"{code}",pl_ver,"{BUD_VERSION}",'
                       f'pl_period,{REPORT_PERIOD})')
        ws[f"E{r}"] = f"=C{r}-D{r}"
        ws[f"F{r}"] = f'=IF(D{r}=0,"",E{r}/ABS(D{r}))'
        ws[f"G{r}"] = (f'=SUMIFS(pl_ytd,pl_measure,"{code}",pl_ver,"{PY_VERSION}",'
                       f'pl_period,{REPORT_PERIOD})')
        ws[f"H{r}"] = f"=C{r}-G{r}"
        ws[f"I{r}"] = (f'=SUMIFS(pl_fy,pl_measure,"{code}",pl_ver,"{FC_VERSION}",'
                       f'pl_period,{REPORT_FY}12)')
        ws[f"J{r}"] = (f'=SUMIFS(pl_fy,pl_measure,"{code}",pl_ver,"{BUD_VERSION}",'
                       f'pl_period,{REPORT_FY}12)')
        ws[f"K{r}"] = f"=I{r}-J{r}"
        for c in "CDEGHIJK":
            ws[f"{c}{r}"].style = st
        ws[f"F{r}"].style = "ns_pct_sub" if sub else "ns_pct"
        r += 1
    body_end = r - 1

    for column in ("E", "H", "K"):
        rng = f"{column}{body_start}:{column}{body_end}"
        ws.conditional_formatting.add(rng, CellIsRule(
            operator="greaterThan", formula=["0"],
            font=__import__("openpyxl").styles.Font(name=S.FONT, color=S.FAVOURABLE)))
        ws.conditional_formatting.add(rng, CellIsRule(
            operator="lessThan", formula=["0"],
            font=__import__("openpyxl").styles.Font(name=S.FONT, color=S.UNFAVOURABLE)))

    note(ws, r, "Variances are shown against the measure's own favourable direction: revenue "
                "above plan is favourable, cost above plan is not. Cost lines are presented "
                "as positive amounts, so a positive variance on a cost line is an overspend.",
         last_col=EXEC_COLS)
    r += 2

    # ---------------- charts
    section(ws, r, "Trend and business unit performance", last_col=EXEC_COLS)
    chart_row = r + 2
    ws.row_dimensions[r + 1].height = 6

    # Revenue and EBITDA on one axis makes EBITDA a flat line along the bottom -- it is a
    # tenth the size. Two charts, each with its own scale, say more than one with two scales.
    slots, chart_w = chart_slots(ws, EXEC_COLS)
    cats = Reference(wb["_chart"], min_col=2, min_row=2, max_row=13)
    line_chart(ws, f"{slots[0]}{chart_row}", "Revenue — actual against budget, FY2026",
               cats,
               [(Reference(wb["_chart"], min_col=3, min_row=2, max_row=13), "Actual",
                 S.ACTUAL, None),
                (Reference(wb["_chart"], min_col=4, min_row=2, max_row=13), "Budget",
                 S.BUDGET, "dash")],
               width=chart_w, height=7.4, page_break=False)

    line_chart(ws, f"{slots[1]}{chart_row}", "Adjusted EBITDA — actual against budget, FY2026",
               cats,
               # Actual is navy on every chart in the pack. This one was warm, sitting beside
               # a revenue chart whose Actual was navy, so two charts on the flagship page
               # disagreed about what the same scenario looks like. Scenario meaning outranks
               # variety (Phase 5.2A).
               [(Reference(wb["_chart"], min_col=5, min_row=2, max_row=13), "Actual",
                 S.ACTUAL, None),
                (Reference(wb["_chart"], min_col=7, min_row=2, max_row=13), "Budget",
                 S.BUDGET, "dash")],
               width=chart_w, height=7.4, page_break=False)
    # Two charts, not three. The business unit comparison has a whole sheet of its own and the
    # brief for this page is not to overcrowd it.
    r = chart_row + 16

    # ---------------- attention
    section(ws, r, "Requires management attention", last_col=EXEC_COLS)
    r += 1
    headers(ws, r, ["Measure", "Amount", "Comment"], label_text="Item")
    r += 1
    for item, measure, amount, comment in meta["attention"]:
        # A copper flag in the gutter. The amounts keep their status colour; the flag says
        # only "this needs a manager's eye", which is neither favourable nor unfavourable.
        marker(ws, f"A{r}", "copper")
        put(ws, f"B{r}", item, "ns_label")
        put(ws, f"C{r}", measure, "ns_label_copper")
        c = put(ws, f"D{r}", amount, "ns_m1")
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=EXEC_COLS)
        put(ws, f"E{r}", comment, "ns_text_mut")
        r += 1
    note(ws, r + 1, "Each line is generated from the variance mart by a deterministic rule — "
                    "the largest unfavourable year-to-date variances and any covenant "
                    "headroom below one turn. The comment states the calculation, not an "
                    "interpretation of it.", last_col=EXEC_COLS)
    ws.print_area = f"A1:P{r + 2}"
    return ws


# ------------------------------------------------------------------ 02 P&L
def profit_and_loss(wb, meta):
    ws = wb.create_sheet("02 P&L")
    S.sheet_setup(ws, freeze="C8", zoom=100)
    std_widths(ws, label_width=36, data_width=10.5, n_data=13)

    title(ws, "Consolidated income statement",
          f"FY{REPORT_FY} · USD millions · statutory basis · "
          f"actual to {meta['report_label']}, forecast thereafter", width_cols=15)

    section(ws, 5, "Monthly", last_col=15, right_text=f"FY{REPORT_FY}")
    labels = [meta["period_labels"][p] for p in MONTHS] + ["FY outlook"]
    headers(ws, 7, labels)
    # Where Actual stops and Forecast begins. The subtitle says "actual to Aug 2026, forecast
    # thereafter"; the wash says it in the place a reader is actually looking, across the four
    # forecast months and the outlook they roll into. Copper is the forecast colour on the
    # charts as well, so the two agree.
    column_group(ws, 7, FIRST_DATA_COL + len(ACTUAL_MONTHS), FIRST_DATA_COL + len(MONTHS))
    r = 8
    for code, name, indent, sub, total in meta["pl_rows"]:
        put(ws, f"B{r}", name, label_style(sub, total, indent))
        for i, p in enumerate(MONTHS):
            c = col(FIRST_DATA_COL + i)
            scen = f'"{ACT_VERSION}"' if p <= REPORT_PERIOD else f'"{FC_VERSION}"'
            ws[f"{c}{r}"] = (f'=SUMIFS(pl_mtd,pl_measure,"{code}",pl_ver,{scen},'
                             f'pl_period,{p})')
            ws[f"{c}{r}"].style = measure_style(sub, total, indent)
        c = col(FIRST_DATA_COL + 12)
        ws[f"{c}{r}"] = (f'=SUMIFS(pl_fy,pl_measure,"{code}",pl_ver,"{FC_VERSION}",'
                         f'pl_period,{REPORT_FY}12)')
        ws[f"{c}{r}"].style = measure_style(sub, total, indent)
        r += 1

    # margins under the statement
    for code, name, num, den in (("GM", "Gross margin %", "GROSS_PROFIT", "REVENUE"),
                                 ("EM", "EBITDA margin %", "EBITDA", "REVENUE")):
        put(ws, f"B{r}", name, "ns_label_i")
        for i, p in enumerate(MONTHS):
            c = col(FIRST_DATA_COL + i)
            scen = f'"{ACT_VERSION}"' if p <= REPORT_PERIOD else f'"{FC_VERSION}"'
            ws[f"{c}{r}"] = (
                f'=IFERROR(SUMIFS(pl_mtd,pl_measure,"{num}",pl_ver,{scen},pl_period,{p})'
                f'/SUMIFS(pl_mtd,pl_measure,"{den}",pl_ver,{scen},pl_period,{p}),"")')
            ws[f"{c}{r}"].style = "ns_pct"
        c = col(FIRST_DATA_COL + 12)
        ws[f"{c}{r}"] = (
            f'=IFERROR(SUMIFS(pl_fy,pl_measure,"{num}",pl_ver,"{FC_VERSION}",'
            f'pl_period,{REPORT_FY}12)/SUMIFS(pl_fy,pl_measure,"{den}",pl_ver,'
            f'"{FC_VERSION}",pl_period,{REPORT_FY}12),"")')
        ws[f"{c}{r}"].style = "ns_pct"
        r += 1

    r += 1
    section(ws, r, "Year to date and full year", last_col=15,
            right_text=f"to {meta['report_label']}")
    r += 1
    ytd_hdr = r
    headers(ws, r, ["Actual", "Budget", "Var $", "Var %", "Prior year", "Var $", "Var %",
                    "FY outlook", "FY budget", "Var $", "Var %"], label_text="")
    # Two analytical groups on this table: the year-to-date variance (Var $, Var %) and
    # the full-year outlook. Both are washed so a reader crossing from a reported figure
    # into an analysis of it sees the boundary without a rule.
    column_group(ws, ytd_hdr, FIRST_DATA_COL + 2, FIRST_DATA_COL + 3)
    column_group(ws, ytd_hdr, FIRST_DATA_COL + 7, FIRST_DATA_COL + 10)
    r += 1
    start = r
    for code, name, indent, sub, total in meta["pl_rows"]:
        put(ws, f"B{r}", name, label_style(sub, total, indent))
        ws[f"C{r}"] = (f'=SUMIFS(pl_ytd,pl_measure,"{code}",pl_ver,"{ACT_VERSION}",'
                       f'pl_period,{REPORT_PERIOD})')
        ws[f"D{r}"] = (f'=SUMIFS(pl_ytd,pl_measure,"{code}",pl_ver,"{BUD_VERSION}",'
                       f'pl_period,{REPORT_PERIOD})')
        ws[f"E{r}"] = f"=C{r}-D{r}"
        ws[f"F{r}"] = f'=IF(D{r}=0,"",E{r}/ABS(D{r}))'
        ws[f"G{r}"] = (f'=SUMIFS(pl_ytd,pl_measure,"{code}",pl_ver,"{PY_VERSION}",'
                       f'pl_period,{REPORT_PERIOD})')
        ws[f"H{r}"] = f"=C{r}-G{r}"
        ws[f"I{r}"] = f'=IF(G{r}=0,"",H{r}/ABS(G{r}))'
        ws[f"J{r}"] = (f'=SUMIFS(pl_fy,pl_measure,"{code}",pl_ver,"{FC_VERSION}",'
                       f'pl_period,{REPORT_FY}12)')
        ws[f"K{r}"] = (f'=SUMIFS(pl_fy,pl_measure,"{code}",pl_ver,"{BUD_VERSION}",'
                       f'pl_period,{REPORT_FY}12)')
        ws[f"L{r}"] = f"=J{r}-K{r}"
        ws[f"M{r}"] = f'=IF(K{r}=0,"",L{r}/ABS(K{r}))'
        for c in "CDEGHJKL":
            ws[f"{c}{r}"].style = measure_style(sub, total, indent)
        for c in "FIM":
            ws[f"{c}{r}"].style = "ns_pct_sub" if sub or total else "ns_pct"
        r += 1
    _colour_variance(ws, ["E", "H", "L"], start, r - 1)
    note(ws, r, "Budget and forecast are built at entity level and carry no consolidation "
                "adjustments, so plan comparisons are like for like down to EBIT and are not "
                "below it. Intercompany trade is removed from both sides of every comparison.",
         last_col=15)
    r += 2

    # The lower half of this sheet was empty canvas. A management P&L is read for its margins
    # as much as its absolutes, and the two questions the tables above cannot answer at a
    # glance -- is the margin holding, and where is the gap to plan -- are the two charts here.
    # One chart, not two. A bar of six year-to-date variances says exactly what the Var $
    # column beside it already says, and a chart that repeats the table it sits under is
    # decoration. What the tables cannot show at a glance is the shape of the margin over the
    # year, so that is the chart that stays -- and it gets the full width rather than half.
    section(ws, r, "Margin trend", last_col=EXEC_COLS)
    # One chart, the full width of the sheet, anchored at the first printed column. Anchored at
    # C with a two-slot width it began 36 characters in and ran off the right of the page,
    # which is how the last three months of the year came to be missing from the trend.
    (slot,), chart_w = chart_slots(ws, EXEC_COLS, count=1)
    line_chart(ws, f"{slot}{r + 2}", "Gross and EBITDA margin — FY2026 by month",
               Reference(wb["_chart"], min_col=2, min_row=2, max_row=13),
               [(Reference(wb["_chart"], min_col=6, min_row=2, max_row=13), "Gross margin",
                 S.ACTUAL, None),
                (Reference(wb["_chart"], min_col=46, min_row=2, max_row=13), "EBITDA margin",
                 S.FORECAST, None)],
               width=chart_w, height=7.6, number_format=S.PCT1, page_break=True)
    ws.print_area = f"A1:O{r + 18}"
    return ws


def _colour_variance(ws, columns, first, last):
    from openpyxl.styles import Font
    for column in columns:
        rng = f"{column}{first}:{column}{last}"
        ws.conditional_formatting.add(rng, CellIsRule(
            operator="greaterThan", formula=["0"],
            font=Font(name=S.FONT, color=S.FAVOURABLE)))
        ws.conditional_formatting.add(rng, CellIsRule(
            operator="lessThan", formula=["0"],
            font=Font(name=S.FONT, color=S.UNFAVOURABLE)))
