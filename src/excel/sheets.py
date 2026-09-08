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
from openpyxl.chart.marker import Marker
from openpyxl.drawing.line import LineProperties
from openpyxl.formatting.rule import CellIsRule
from openpyxl.utils import get_column_letter
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


def section(ws, row, text, last_col=14, right_text=None):
    for i in range(2, last_col + 1):
        ws.cell(row=row, column=i).style = "ns_section"
    put(ws, f"B{row}", text, "ns_section")
    if right_text:
        c = ws.cell(row=row, column=last_col)
        c.value = right_text
        c.style = "ns_section_r"
    ws.row_dimensions[row].height = 20


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


def line_chart(ws, anchor, title_text, cats_ref, series, width=17.5, height=7.2,
               number_format=S.USD_M1, y_title=None):
    ch = LineChart()
    ch.title = title_text
    ch.style = None
    ch.width, ch.height = width, height
    ch.y_axis.numFmt = number_format
    ch.y_axis.majorGridlines.spPr = None
    # A month with no actual yet is a GAP, not a zero. Excel's default plots an empty cell as
    # zero, and the first draft of the revenue chart showed the group falling off a cliff in
    # September because the actual series simply had not been posted yet.
    ch.dispBlanksAs = "gap"
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
    ws.add_chart(ch, anchor)
    return ch


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


def bar_chart(ws, anchor, title_text, cats_ref, series, width=17.5, height=7.2,
              number_format=S.USD_M1, overlap=-10, gap=60):
    ch = BarChart()
    ch.type = "col"
    ch.title = title_text
    ch.style = None
    ch.dispBlanksAs = "gap"
    ch.width, ch.height = width, height
    ch.y_axis.numFmt = number_format
    ch.overlap = overlap
    ch.gapWidth = gap
    for ref, name, colour in series:
        s = Series(ref, title=name)
        s.graphicalProperties.solidFill = colour
        s.graphicalProperties.line.noFill = True
        ch.series.append(s)
    ch.set_categories(cats_ref)
    _legend(ch, len(series))
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
    """
    total = sheet_width_cm(ws, last_col)
    width = (total - gap_cm * (count - 1)) / count
    slots = []
    cumulative = 0.0
    target = 0.0
    column = 2
    for _ in range(count):
        while column <= last_col and cumulative < target - 0.01:
            cumulative += (ws.column_dimensions[col(column)].width or 8.43) * CM_PER_CHAR
            column += 1
        slots.append(col(column))
        target += width + gap_cm
        while column <= last_col and cumulative < target - 0.01:
            cumulative += (ws.column_dimensions[col(column)].width or 8.43) * CM_PER_CHAR
            column += 1
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
        ws[f"B{r}"].font = ws[f"B{r}"].font.copy(color=S.HEADER_BG, underline="single")
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


EXEC_COLS = 16


def executive(wb, meta):
    ws = wb.create_sheet("01 Executive Summary")
    S.sheet_setup(ws, freeze="C7", zoom=100)
    std_widths(ws, label_width=32, data_width=12.4, n_data=EXEC_COLS - 2)

    title(ws, "Executive summary", f"Group performance to {meta['report_label']} · "
                                   f"USD millions unless stated · statutory basis",
          width_cols=EXEC_COLS)

    # ---------------- KPI strip: five across, two rows deep
    section(ws, 5, "Key performance indicators", last_col=EXEC_COLS,
            right_text="Year to date against budget")
    r = 7
    for block in range(2):
        for i in range(5):
            k = block * 5 + i
            if k >= len(KPI):
                break
            name, code, vstyle, fmt, sub = KPI[k]
            c1 = FIRST_DATA_COL - 1 + i * 2 if False else 2 + i * 2
            a, b = col(c1), col(c1 + 1)
            put(ws, f"{a}{r}", name, "ns_kpi_label")
            ws.cell(row=r, column=c1 + 1).style = "ns_kpi_label"
            ws.merge_cells(start_row=r + 1, start_column=c1, end_row=r + 1, end_column=c1 + 1)
            cell = put(ws, f"{a}{r+1}", meta["kpi"][code]["value"], vstyle)
            cell.number_format = fmt
            ws.merge_cells(start_row=r + 2, start_column=c1, end_row=r + 2, end_column=c1 + 1)
            put(ws, f"{a}{r+2}", meta["kpi"][code]["delta"],
                "ns_kpi_sub_fav" if meta["kpi"][code]["fav"] == "FAVOURABLE"
                else "ns_kpi_sub_unf" if meta["kpi"][code]["fav"] == "UNFAVOURABLE"
                else "ns_kpi_sub")
            ws.merge_cells(start_row=r + 3, start_column=c1, end_row=r + 3, end_column=c1 + 1)
            put(ws, f"{a}{r+3}", sub, "ns_kpi_sub")
        ws.row_dimensions[r].height = 15
        ws.row_dimensions[r + 1].height = 26
        ws.row_dimensions[r + 2].height = 13
        ws.row_dimensions[r + 3].height = 13
        r += 5

    # ---------------- performance summary
    section(ws, r, "Group performance", last_col=EXEC_COLS, right_text="USD m")
    r += 1
    headers(ws, r, ["Actual YTD", "Budget YTD", "Var $", "Var %", "Prior year YTD",
                    "Var $", "FY outlook", "FY budget", "Var $"], label_text="")
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
               [(Reference(wb["_chart"], min_col=3, min_row=1, max_row=13), "Actual",
                 S.ACTUAL, None),
                (Reference(wb["_chart"], min_col=4, min_row=1, max_row=13), "Budget",
                 S.BUDGET, "dash")],
               width=chart_w, height=7.4)

    line_chart(ws, f"{slots[1]}{chart_row}", "Adjusted EBITDA — actual against budget, FY2026",
               cats,
               [(Reference(wb["_chart"], min_col=5, min_row=1, max_row=13), "Actual",
                 S.FORECAST, None),
                (Reference(wb["_chart"], min_col=7, min_row=1, max_row=13), "Budget",
                 S.BUDGET, "dash")],
               width=chart_w, height=7.4)
    # Two charts, not three. The business unit comparison has a whole sheet of its own and the
    # brief for this page is not to overcrowd it.
    r = chart_row + 16

    # ---------------- attention
    section(ws, r, "Requires management attention", last_col=EXEC_COLS)
    r += 1
    headers(ws, r, ["Measure", "Amount", "Comment"], label_text="Item")
    r += 1
    for item, measure, amount, comment in meta["attention"]:
        put(ws, f"B{r}", item, "ns_label")
        put(ws, f"C{r}", measure, "ns_text_mut")
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
    headers(ws, r, ["Actual", "Budget", "Var $", "Var %", "Prior year", "Var $", "Var %",
                    "FY outlook", "FY budget", "Var $", "Var %"], label_text="")
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
    ws.print_area = f"A1:O{r + 1}"
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
