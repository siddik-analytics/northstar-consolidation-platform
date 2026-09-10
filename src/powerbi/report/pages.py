"""
The report pages, declared.

Each function builds one page on the shared grid (`layout.py`) from the governed measures
(`measures.py`) and nothing else. There is no report-level DAX: a number on a page is a
governed measure, filtered by what the visual is about. Where the brief asks for something the
model has no measure for -- account-level amounts, the consolidation layer bridge, the
working-capital day counts, revolver drawn and available, principal by instrument -- the page
leaves the space to what the model governs and `docs/powerbi-report.md` says so, rather than
inventing a measure here.

Copper means one thing on every page: **the thing to look at** -- the highlighted unit, the
reference line, the bridge step, the forecast, the page you are on. Green and red mean
favourable and unfavourable, and nothing else is ever green or red.

Display formats: the governed measures carry Excel-style format strings (`#,0.0,,`), which
Power BI renders literally. Every value here is therefore given a display format in Power
BI's own grammar (`#,0,,.0`) at the projection -- a presentation setting, the same scaling,
the same precision, the same bracket convention as the workbook. The finance definition is
untouched; see P6B-D-03 in the defect register.
"""

from __future__ import annotations

from . import layout as L
from . import metadata as META
from . import pbir as P
from . import theme as T
from .layout import Page

# ---------------------------------------------------------------- shared field references
DATE_MONTH = P.column("Date", "month_label")
DATE_MONTH_LONG = P.column("Date", "month_label_long")
DATE_FY = ("Date", "fiscal_year_label", ["FY2026"])
DATE_ACTUAL = ("Date", "is_actual_month", [True])
DATE_TEST = ("Date", "accounting_period", [12])
BASIS_MTD = ("Period Basis", "basis_code", ["MTD"])
ACTUAL = ("Scenario", "scenario_code", ["ACT"])
BU_NAME = P.column("Business Unit", "bu_short_name")
BU_LONG = P.column("Business Unit", "bu_name")
ENTITY = P.column("Entity", "short_name")
ENTITY_LONG = P.column("Entity", "entity_name")
LINE = P.column("Measure Line", "measure_name")
COMPARISON = P.column("Comparison", "comparison_name")
JOB_FAMILY = P.column("Job Family", "job_family_name")
ASSET_CLASS = P.column("Capital Project", "asset_class")
LAYER = P.column("Consolidation Layer", "layer_name")

# display formats in Power BI's grammar: millions to one decimal, brackets for negatives
M1 = '#,0,,.0;(#,0,,.0);"–"'
M1S = '+#,0,,.0;(#,0,,.0);"–"'
PCT = '0.0%;(0.0%);"–"'
RATIO = '0.00"x";(0.00"x");"–"'
FTE = "#,0"
FTE1 = "#,0.0"
COUNT = "#,0"
K0 = "#,0,"

FAV = {"Favourable": T.FAVOURABLE, "Unfavourable": T.UNFAVOURABLE}
STATUS = {"Compliant": T.FAVOURABLE, "Breach": T.UNFAVOURABLE}
FORECAST_SET = {"Actual Revenue": T.NAVY, "Budget Revenue": T.BUDGET,
                "Forecast Revenue": T.COPPER, "Prior Year Revenue": T.PRIOR}
EBITDA_SET = {"Actual Adjusted EBITDA": T.NAVY, "Budget Adjusted EBITDA": T.BUDGET,
              "Forecast Adjusted EBITDA": T.COPPER, "Prior Year Adjusted EBITDA": T.PRIOR}


def scope(*specs, prefix="s"):
    return P.filters(*specs, prefix=prefix)


def trend_scope(*extra, prefix="t"):
    """A full-year monthly trend: FY2026, monthly basis, plus whatever the chart is about."""
    return P.filters(DATE_FY, BASIS_MTD, *extra, prefix=prefix)


def closed_scope(*extra, prefix="c"):
    """Closed months only, for balances the mart carries forward past the close."""
    return P.filters(DATE_FY, DATE_ACTUAL, *extra, prefix=prefix)


def status_card(measure_name: str, mapping: dict[str, str], size: float = 9.0,
                default: str = T.INK_MUTED, align: str = "left") -> dict:
    """A text measure as a small card, coloured by its own value: the word and the colour."""
    v = P.card(measure_name, value_size=size, value_colour=default, align=align)
    cases = [{"Condition": {"Comparison": {"ComparisonKind": 0,
                                           "Left": P.measure(measure_name),
                                           "Right": P.lit(k)["expr"]}},
              "Value": P.lit(c)["expr"]} for k, c in mapping.items()]
    v["objects"]["labels"][0]["properties"]["color"] = {"solid": {"color": {"expr": {
        "Conditional": {"Cases": cases, "Else": P.lit(default)["expr"]}}}}}
    return v


def fav_bar(category: dict, title_text: str, comparison: str, line: str | None = None,
            horizontal: bool = True, sort_desc: bool = True, subtitle_text: str | None = None,
            units: float = 1_000_000.0) -> tuple[dict, dict]:
    """
    Variance by category, each bar coloured by the governed favourability of that variance:
    green favourable, red unfavourable, grey neutral. The measure decides; the chart shows.
    """
    v = P.column_chart(category, [("Variance", "Variance")], title_text, horizontal=horizontal,
                       units=units, precision=1, sort_field=P.measure("Variance"),
                       sort_ascending=not sort_desc, labels=True, subtitle_text=subtitle_text)
    cases = [{"Condition": {"Comparison": {"ComparisonKind": 0,
                                           "Left": P.measure("Variance Favourability"),
                                           "Right": P.lit(k)["expr"]}},
              "Value": P.lit(c)["expr"]} for k, c in FAV.items()]
    v["objects"]["dataPoint"] = [{"properties": {"fill": {"solid": {"color": {"expr": {
        "Conditional": {"Cases": cases, "Else": P.lit(T.RULE_STRONG)["expr"]}}}}}}}]
    for pr in v["query"]["queryState"]["Y"]["projections"]:
        pr["format"] = M1S
    specs = [("Comparison", "comparison_code", [comparison])]
    if line:
        specs.append(("Measure Line", "measure_code", [line]))
    return v, scope(*specs, prefix="fb")


def fmt_values(v: dict, fmt: str, role: str = "Y") -> dict:
    for pr in v["query"]["queryState"][role]["projections"]:
        pr["format"] = fmt
    return v


def kpi(pg: Page, key: str, x: int, y: int, w: int, label: str, value: str, fmt: str,
        comparator: tuple[str, str, str] | None = None, note: str | None = None,
        value_filters: list | None = None, size: float | None = None) -> None:
    """
    One KPI tile: label, value, and either a governed variance line or a note.

    `comparator` is (comparison_code, measure_code, caption): the governed [Variance] for
    that line and comparison, then the governed [Variance Favourability] as a word in its
    colour -- the word is there so the colour is never the only channel.
    """
    pg.add(f"{key}_l", x, y, w, 16, P.textbox(label, T.TYPE["kpi_label"], T.INK_MUTED, False))
    pg.add(f"{key}_v", x - 4, y + 14, w + 4, 32,
           P.card(value, fmt=fmt, value_size=size or T.TYPE["kpi_value"]),
           filters=scope(*(value_filters if value_filters is not None else [ACTUAL]),
                         prefix=f"{key}v") if (value_filters is None or value_filters) else None)
    if comparator:
        comparison, line, caption = comparator
        sc = scope(("Comparison", "comparison_code", [comparison]),
                   ("Measure Line", "measure_code", [line]), prefix=f"{key}c")
        pg.add(f"{key}_d", x - 4, y + 46, 46, 16,
               P.card("Variance", fmt=M1S, value_size=9.0, value_colour=T.INK), filters=sc)
        pg.add(f"{key}_n", x + 42, y + 47, w - 42, 14,
               P.textbox(caption, T.TYPE["small"], T.INK_MUTED, False))
        pg.add(f"{key}_f", x - 4, y + 62, w + 4, 16,
               status_card("Variance Favourability", FAV, size=8.0), filters=sc)
    elif note:
        pg.add(f"{key}_n", x, y + 48, w, 28, P.textbox(note, T.TYPE["small"], T.INK_MUTED, False))


def kpi_band(pg: Page, y: int, groups: list, tile_w: int | None = None, gap: int = 10,
             height: int = 88) -> int:
    """
    Groups of KPI tiles on their grounds, as the workbook's first page lays them out. The
    tile width is derived so the groups fill the content width exactly.
    """
    n_tiles = sum(len(g[3]) for g in groups)
    n_groups = len(groups)
    if tile_w is None:
        tile_w = (L.CONTENT_W - 14 * (n_groups - 1) - 16 * n_groups
                  - gap * (n_tiles - n_groups)) // n_tiles
    x = L.X0
    for gi, (group_name, ground, mark, tiles) in enumerate(groups):
        gw = len(tiles) * tile_w + (len(tiles) - 1) * gap + 16
        pg.add(f"g{gi}_bg", x, y + 18, gw, height, P.shape(ground))
        pg.add(f"g{gi}_mark", x, y + 18, gw, 4, P.shape(mark))
        pg.label(f"g{gi}_l", x, y, gw, group_name, h=16, colour=T.NAVY)
        tx = x + 8
        for spec in tiles:
            key, label, meas, fmt, comp = spec[:5]
            note = spec[5] if len(spec) > 5 else None
            vf = spec[6] if len(spec) > 6 else None
            if vf == "status":
                pg.add(f"{key}_l", tx, y + 24, tile_w, 16,
                       P.textbox(label, T.TYPE["kpi_label"], T.INK_MUTED, False))
                pg.add(f"{key}_v", tx - 4, y + 38, tile_w + 4, 32,
                       status_card(meas, STATUS, size=18.0, default=T.INK_MUTED))
                pg.add(f"{key}_n", tx, y + 72, tile_w, 28,
                       P.textbox(note, T.TYPE["small"], T.INK_MUTED, False))
            else:
                kpi(pg, key, tx, y + 24, tile_w, label, meas, fmt, comparator=comp, note=note,
                    value_filters=vf)
            tx += tile_w + gap
        x += gw + 14
    return y + 18 + height + L.GUTTER


def note(pg: Page, key: str, x: int, y: int, w: int, text: str, h: int = 30) -> None:
    pg.add(key, x, y, w, h, P.textbox(text, T.TYPE["small"], T.INK_MUTED, False, italic=True))


# ================================================================ 01 Executive overview
def executive() -> Page:
    pg = Page("p01_executive", "01 Executive Overview", "Executive overview",
              "How the Group is performing, what is changing, and what needs attention · "
              "USD millions unless stated")
    y = L.CONTENT_Y
    y2 = kpi_band(pg, y, [
        ("Performance", T.PANEL, T.NAVY, [
            ("k_rev", "Revenue", "Revenue", M1, ("ACT_VS_BUD", "REVENUE", "vs budget")),
            ("k_gm", "Gross margin", "Gross Margin %", PCT, None, "of revenue"),
            ("k_ebitda", "Adjusted EBITDA", "Management Adjusted EBITDA", M1,
             ("ACT_VS_BUD", "ADJ_EBITDA", "vs budget")),
            ("k_margin", "EBITDA margin", "EBITDA Margin %", PCT, None, "statutory EBITDA"),
        ]),
        ("Cash and capital", T.COPPER_TINT, T.COPPER, [
            ("k_ocf", "Operating cash flow", "Operating Cash Flow", M1, None,
             "period selected"),
            ("k_cash", "Cash", "Closing Cash", M1, None, "at period end"),
            ("k_nd", "Covenant net debt", "Covenant Net Debt", M1, None,
             "covenant debt less cash"),
        ]),
        ("Risk and capacity", T.COPPER_TINT, T.COPPER, [
            ("k_lev", "Covenant net leverage", "Covenant Net Leverage", RATIO, None,
             "net debt / LTM covenant EBITDA"),
            ("k_head", "Covenant headroom", "Covenant Headroom", RATIO, None,
             "turns against the limit"),
            ("k_fte", "Headcount", "Closing FTE", FTE, None, "full-time equivalents", []),
        ]),
    ])
    g = L.cols(10)
    c3 = [L.span(g, 0, 2), L.span(g, 3, 5), L.span(g, 6, 9)]
    h2 = 232
    pg.add("rev_trend", c3[0][0], y2, c3[0][1], h2, fmt_values(P.line_chart(
        DATE_MONTH, [("Actual Revenue", "Actual"), ("Budget Revenue", "Budget"),
                     ("Forecast Revenue", "Forecast")],
        "Revenue by month — actual, budget and current forecast",
        colours=FORECAST_SET), "#,0.0"), filters=trend_scope())
    pg.add("bu_ebitda", c3[1][0], y2, c3[1][1], h2, fmt_values(P.column_chart(
        BU_NAME, [("Actual Adjusted EBITDA", "Actual"), ("Budget Adjusted EBITDA", "Budget")],
        "Adjusted EBITDA by unit — actual against budget", horizontal=True,
        colours={"Actual Adjusted EBITDA": T.NAVY, "Budget Adjusted EBITDA": T.BUDGET},
        sort_field=P.measure("Actual Adjusted EBITDA"), sort_ascending=False), "#,0.0"))
    pg.add("var_signals", c3[2][0], y2, c3[2][1], h2, P.matrix(
        [LINE], [("Variance", "Var $"), ("Variance %", "Var %"),
                 ("Variance Favourability", "Direction")],
        "Variance to budget by line", stepped=False,
        value_formats={"Variance": M1S, "Variance %": PCT},
        row_names={"Measure Line.measure_name": "Line"},
        widths={"Measure Line.measure_name": 140, "Northstar Measures.Variance": 52,
                "Northstar Measures.Variance %": 58, "Northstar Measures.Variance Favourability": 76},
        conditional=[P.status_colour_rule("Variance Favourability", FAV,
                                          "Variance Favourability")]),
        filters=scope(("Comparison", "comparison_code", ["ACT_VS_BUD"]), prefix="vs"))
    y3 = y2 + h2 + L.GUTTER
    h3 = L.CANVAS_H - 20 - y3
    c2 = L.cols(2)
    pg.add("cash_trend", c2[0][0], y3, c2[0][1], h3, fmt_values(P.line_chart(
        DATE_MONTH, [("Closing Cash", "Cash"), ("Total Liquidity", "Total liquidity")],
        "Cash and total liquidity — month end, closed months",
        colours={"Closing Cash": T.NAVY, "Total Liquidity": T.COPPER}), "#,0.0"),
        filters=closed_scope())
    lev = fmt_values(P.line_chart(
        DATE_MONTH, [("Covenant Net Leverage", "Net leverage"), ("Covenant Limit", "Covenant limit"),
                     ("Economic Leverage", "Economic leverage")],
        "Net leverage against the covenant limit — indicative between test dates",
        colours={"Covenant Net Leverage": T.NAVY, "Covenant Limit": T.COPPER,
                 "Economic Leverage": T.BUDGET}, units=1.0, precision=2, y_start=3.0,
        y_end=5.0), "0.00")
    lev["objects"]["lineStyles"].append(dict(P.props(lineStyle="dashed", strokeWidth=2.0),
                                             selector={"metadata": "Northstar Measures.Covenant Limit"}))
    pg.add("lev_trend", c2[1][0], y3, c2[1][1], h3, lev, filters=closed_scope())
    pg.no_filter("sl_period", "rev_trend", "cash_trend", "lev_trend")
    pg.no_filter("sl_basis", "rev_trend", "cash_trend", "lev_trend")
    # Adjusted EBITDA is defined on the management basis and on it alone; the reporting
    # basis slicer must not blank it. Scope, not compensation: the measure decides.
    pg.no_filter("sl_rbasis", "k_ebitda_v", "k_ebitda_d", "k_ebitda_f", "k_margin_v",
                 "bu_ebitda")
    return pg


# ================================================================ 02 P&L performance
def pnl() -> Page:
    pg = Page("p02_pnl", "02 P&L Performance", "P&L performance",
              "The governed income statement on the period basis selected, against the "
              "comparison selected · USD millions")
    y = L.CONTENT_Y
    # the comparison the page is about, beside the shared slicers
    pg.add("sl_comparison", L.X0, y, 480, 44,
           P.slicer(COMPARISON, "Comparison", style="tile",
                    default=("Comparison", "comparison_name", ["Actual vs Budget"]),
                    sync="sl_comparison"))
    y += 52
    c = L.cols(5)
    left_x, left_w = L.span(c, 0, 2)
    right_x, right_w = L.span(c, 3, 4)
    h = L.CANVAS_H - 20 - y
    pg.add("pnl", left_x, y, left_w, h, P.matrix(
        [LINE, BU_LONG, ENTITY_LONG],
        [("Variance Base", "Base"), ("Variance Comparator", "Comparator"),
         ("Variance", "Variance"), ("Variance %", "Var %"),
         ("Variance Favourability", "Direction")],
        None, value_formats={"Variance Base": M1, "Variance Comparator": M1, "Variance": M1S,
                             "Variance %": PCT},
        conditional=[P.status_colour_rule("Variance Favourability", FAV,
                                          "Variance Favourability")],
        row_header="Line · business unit · entity"))
    v, sc = fav_bar(LINE, "Variance by line — direction is the measure's own favourability",
                    "ACT_VS_BUD", horizontal=True, sort_desc=False)
    pg.add("var_bar", right_x, y, right_w, 250, v)   # comparison follows the slicer
    y4 = y + 250 + L.GUTTER
    pg.add("ebitda_trend", right_x, y4, right_w, L.CANVAS_H - 20 - y4, fmt_values(P.line_chart(
        DATE_MONTH, [("Actual Adjusted EBITDA", "Actual"), ("Budget Adjusted EBITDA", "Budget"),
                     ("Forecast Adjusted EBITDA", "Forecast"),
                     ("Prior Year Adjusted EBITDA", "Prior year")],
        "Adjusted EBITDA by month — the four governed scenarios", colours=EBITDA_SET), "#,0.0"),
        filters=trend_scope())
    pg.no_filter("sl_period", "ebitda_trend")
    pg.no_filter("sl_basis", "ebitda_trend")
    pg.no_filter("sl_comparison", "ebitda_trend")
    pg.no_filter("sl_rbasis", "ebitda_trend")
    return pg


# ================================================================ 03 Business unit & entity
def business_units() -> Page:
    pg = Page("p03_bu", "03 Business Units & Entities", "Business unit and entity performance",
              "Where Group performance comes from · actual on the period basis selected · "
              "USD millions")
    y = L.CONTENT_Y
    c2 = L.cols(2)
    h1 = 236
    pg.add("bu_rev", c2[0][0], y, c2[0][1], h1, fmt_values(P.column_chart(
        BU_NAME, [("Actual Revenue", "Actual"), ("Budget Revenue", "Budget")],
        "Revenue by business unit — actual against budget",
        colours={"Actual Revenue": T.NAVY, "Budget Revenue": T.BUDGET},
        sort_field=P.measure("Actual Revenue"), sort_ascending=False,
        subtitle_text="Select a unit to filter the entities below"), "#,0.0"))
    v, sc = fav_bar(BU_NAME, "Adjusted EBITDA variance to budget by business unit",
                    "ACT_VS_BUD", "ADJ_EBITDA", horizontal=True)
    pg.add("bu_var", c2[1][0], y, c2[1][1], h1, v, filters=sc)
    y2 = y + h1 + L.GUTTER
    h2 = L.CANVAS_H - 20 - y2
    pg.add("bu_matrix", c2[0][0], y2, c2[0][1], h2, P.matrix(
        [BU_LONG, ENTITY_LONG],
        [("Revenue", "Revenue"), ("Gross Margin %", "GM %"),
         ("Management Adjusted EBITDA", "Adj. EBITDA"), ("Adjusted EBITDA Margin %", "Margin")],
        "Unit and entity contribution — expand a unit for its entities",
        value_formats={"Revenue": M1, "Gross Margin %": PCT, "Management Adjusted EBITDA": M1,
                       "Adjusted EBITDA Margin %": PCT}, row_header="Business unit · entity"),
        filters=scope(ACTUAL, prefix="bm"))
    pg.add("ent_bar", c2[1][0], y2, c2[1][1], h2, fmt_values(P.column_chart(
        ENTITY, [("Management Adjusted EBITDA", "Adjusted EBITDA")],
        "Adjusted EBITDA by entity", horizontal=True,
        sort_field=P.measure("Management Adjusted EBITDA"), sort_ascending=False,
        labels=True), "#,0.0"), filters=scope(ACTUAL, prefix="eb"))
    pg.no_filter("sl_rbasis", "bu_var", "bu_matrix", "ent_bar")
    return pg


# ================================================================ 04 Balance sheet & working capital
def balance_sheet() -> Page:
    pg = Page("p04_balance", "04 Balance Sheet & Working Capital",
              "Balance sheet and working capital",
              "Financial position at the period end selected, and how working capital moved · "
              "USD millions", slicers=("sl_period", "sl_rbasis", "sl_bu", "sl_entity"))
    y = L.CONTENT_Y
    y2 = kpi_band(pg, y, [
        ("Position", T.PANEL, T.NAVY, [
            ("b_ta", "Total assets", "Total Assets", M1, None, "at period end", []),
            ("b_tl", "Total liabilities", "Total Liabilities", M1, None, "at period end", []),
            ("b_te", "Total equity", "Total Equity", M1, None, "incl. NCI", []),
            ("b_chk", "Balance check", "Balance Sheet Check", M1, None,
             "assets − liabilities − equity", []),
        ]),
        ("Working capital", T.COPPER_TINT, T.COPPER, [
            ("b_ar", "Receivables", "Accounts Receivable", M1, None, "net", []),
            ("b_inv", "Inventory", "Inventory", M1, None, "net", []),
            ("b_ap", "Payables", "Accounts Payable", M1, None, "trade", []),
            ("b_nwc", "Net working capital", "Net Working Capital", M1, None,
             "AR + inventory − AP ± other", []),
        ]),
        ("Long-term", T.COPPER_TINT, T.COPPER, [
            ("b_ppe", "PP&E", "Property Plant and Equipment", M1, None, "net", []),
            ("b_gw", "Goodwill", "Goodwill", M1, None, "on consolidation", []),
        ]),
    ])
    c2 = L.cols(2)
    h = L.CANVAS_H - 20 - y2
    pg.add("wc_trend", c2[0][0], y2, c2[0][1], h, fmt_values(P.line_chart(
        DATE_MONTH, [("Accounts Receivable", "Receivables"), ("Inventory", "Inventory"),
                     ("Accounts Payable", "Payables"), ("Net Working Capital", "Net working capital")],
        "Working capital components — month end, closed months",
        colours={"Accounts Receivable": T.NAVY, "Inventory": T.BUDGET,
                 "Accounts Payable": T.PRIOR, "Net Working Capital": T.COPPER}), "#,0.0"),
        filters=closed_scope())
    pg.add("bs_trend", c2[1][0], y2, c2[1][1], h, fmt_values(P.line_chart(
        DATE_MONTH, [("Cash", "Cash"), ("Intangible Assets", "Intangibles"),
                     ("Cumulative Translation Adjustment", "CTA"),
                     ("Non-controlling Interest Equity", "NCI")],
        "Cash, intangibles, CTA and NCI — month end, closed months",
        colours={"Cash": T.NAVY, "Intangible Assets": T.BUDGET,
                 "Cumulative Translation Adjustment": T.COPPER,
                 "Non-controlling Interest Equity": T.PRIOR}), "#,0.0"), filters=closed_scope())
    pg.no_filter("sl_period", "wc_trend", "bs_trend")
    return pg


# ================================================================ 05 Cash flow & liquidity
def cash_flow() -> Page:
    pg = Page("p05_cash", "05 Cash Flow & Liquidity", "Cash flow and liquidity",
              "Where cash came from, where it went, and how much liquidity remains · "
              "USD millions · derived from balance sheet movements",
              slicers=("sl_period", "sl_rbasis", "sl_bu", "sl_entity"))
    y = L.CONTENT_Y
    y2 = kpi_band(pg, y, [
        ("Cash flow in the period", T.PANEL, T.NAVY, [
            ("c_ocf", "Operating", "Operating Cash Flow", M1, None, "cash from operations", []),
            ("c_icf", "Investing", "Investing Cash Flow", M1, None, "capital into the business", []),
            ("c_fcf", "Financing", "Financing Cash Flow", M1, None, "debt and equity", []),
            ("c_fx", "FX on cash", "FX Effect on Cash", M1, None, "retranslation", []),
            ("c_net", "Net change", "Net Change in Cash", M1, None, "in the period", []),
        ]),
        ("Liquidity at period end", T.COPPER_TINT, T.COPPER, [
            ("c_cash", "Closing cash", "Closing Cash", M1, None, "cash and equivalents", []),
            ("c_liq", "Total liquidity", "Total Liquidity", M1, None,
             "cash plus undrawn facility", []),
        ]),
    ])
    c2 = L.cols(2)
    h = L.CANVAS_H - 20 - y2
    pg.add("cf_cols", c2[0][0], y2, c2[0][1], h, fmt_values(P.column_chart(
        DATE_MONTH, [("Operating Cash Flow", "Operating"), ("Investing Cash Flow", "Investing"),
                     ("Financing Cash Flow", "Financing")],
        "Cash flow by category and month — closed months",
        colours={"Operating Cash Flow": T.NAVY, "Investing Cash Flow": T.COPPER,
                 "Financing Cash Flow": T.BUDGET}), "#,0.0"), filters=closed_scope())
    pg.add("liq_trend", c2[1][0], y2, c2[1][1], h, fmt_values(P.line_chart(
        DATE_MONTH, [("Closing Cash", "Cash"), ("Total Liquidity", "Total liquidity")],
        "Cash and total liquidity — month end, closed months",
        colours={"Closing Cash": T.NAVY, "Total Liquidity": T.COPPER}), "#,0.0"),
        filters=closed_scope())
    pg.no_filter("sl_period", "cf_cols", "liq_trend")
    return pg


# ================================================================ 06 EBITDA & variance bridge
def ebitda() -> Page:
    pg = Page("p06_ebitda", "06 EBITDA & Variance Bridge", "EBITDA definitions and bridges",
              "Three governed EBITDA definitions, kept apart even where their values meet · "
              "USD millions")
    y = L.CONTENT_Y
    y2 = kpi_band(pg, y, [
        ("Statutory", T.PANEL, T.NAVY, [
            ("e_stat", "Statutory EBITDA", "Statutory EBITDA", M1, None,
             "EBITDA as reported"),
            ("e_add", "Approved add-backs", "Approved Add-backs", M1, None,
             "policy ADR-0013"),
        ]),
        ("Management", T.COPPER_TINT, T.COPPER, [
            ("e_adj", "Adjusted EBITDA", "Management Adjusted EBITDA", M1,
             ("ACT_VS_BUD", "ADJ_EBITDA", "vs budget")),
            ("e_adjm", "Adjusted margin", "Adjusted EBITDA Margin %", PCT, None,
             "of revenue", []),
        ]),
        ("Covenant", T.COPPER_TINT, T.COPPER, [
            ("e_cov", "Covenant EBITDA", "Covenant EBITDA", M1, None,
             "last twelve months, CA-021 to CA-030"),
        ]),
    ])
    c2 = L.cols(2)
    h = L.CANVAS_H - 20 - y2
    bridge = fmt_values(P.column_chart(
        LINE, [("Variance Base", "Actual")],
        "Statutory to management adjusted EBITDA — the add-backs are the bridge",
        sort_field=LINE, labels=True,
        category_colours={"EBITDA": T.NAVY, "Approved add-backs": T.COPPER,
                          "Adjusted EBITDA": T.NAVY},
        category_table_col=("Measure Line", "measure_name")), "#,0.0")
    pg.add("bridge", c2[0][0], y2, c2[0][1], h, bridge,
           filters=scope(("Comparison", "comparison_code", ["ACT_VS_BUD"]),
                         ("Measure Line", "measure_code", ["EBITDA", "ADDBACKS", "ADJ_EBITDA"]),
                         prefix="br"))
    v, sc = fav_bar(BU_NAME, "Adjusted EBITDA variance to budget by business unit",
                    "ACT_VS_BUD", "ADJ_EBITDA", horizontal=True)
    pg.add("bu_var", c2[1][0], y2, c2[1][1], h - 96, v, filters=sc)
    note(pg, "defs", c2[1][0], y2 + h - 92, c2[1][1],
         "Statutory EBITDA is the reported result before interest, tax, depreciation and "
         "amortisation. Management Adjusted EBITDA adds back the approved categories under "
         "ADR-0013. Covenant EBITDA follows the credit agreement (CA-021 to CA-030) on a "
         "rolling twelve months, with the sponsor fee capped. Adjusted and Covenant EBITDA "
         "are equal in this baseline because the cap does not bite and the covenant FX "
         "add-back has no population — an outcome, not a definition.", h=80)
    pg.no_filter("sl_rbasis", "e_adj_v", "e_adj_d", "e_adj_f", "e_adjm_v", "e_add_v", "bu_var")
    return pg


# ================================================================ 07 Debt & covenants
def covenants() -> Page:
    pg = Page("p07_debt", "07 Debt & Covenants", "Debt and covenant compliance",
              "Leverage against the agreement — indicative between test dates, tested at each "
              "fiscal year end · USD millions",
              slicers=("sl_period",))
    y = L.CONTENT_Y
    y2 = kpi_band(pg, y, [
        ("Debt", T.PANEL, T.NAVY, [
            ("d_gross", "Gross debt", "Gross Debt", M1, None, "all instruments", []),
            ("d_cov", "Covenant debt", "Covenant Debt", M1, None, "per the agreement", []),
            ("d_cash", "Cash", "Cash", M1, None, "at period end", []),
            ("d_nd", "Covenant net debt", "Covenant Net Debt", M1, None, "covenant debt − cash", []),
        ]),
        ("Covenant test", T.COPPER_TINT, T.COPPER, [
            ("d_ebitda", "Covenant EBITDA", "Covenant EBITDA", M1, None, "last twelve months", []),
            ("d_lev", "Net leverage", "Covenant Net Leverage", RATIO, None, "net debt / LTM EBITDA", []),
            ("d_lim", "Covenant limit", "Covenant Limit", RATIO, None, "the agreement's term", []),
            ("d_head", "Headroom", "Covenant Headroom", RATIO, None, "turns against the limit", []),
            ("d_econ", "Economic leverage", "Economic Leverage", RATIO, None, "with operating leases", []),
        ]),
        ("Status", T.PANEL, T.NAVY, [
            ("d_status", "At the period selected", "Covenant Status", None, None,
             "Indicative unless a test date", "status"),
        ]),
    ])
    c2 = L.cols(2)
    h = L.CANVAS_H - 20 - y2
    lev = fmt_values(P.line_chart(
        DATE_MONTH, [("Covenant Net Leverage", "Net leverage"), ("Covenant Limit", "Covenant limit"),
                     ("Economic Leverage", "Economic leverage")],
        "Net leverage against the covenant limit — FY2026, closed months",
        colours={"Covenant Net Leverage": T.NAVY, "Covenant Limit": T.COPPER,
                 "Economic Leverage": T.BUDGET}, units=1.0, precision=2, y_start=3.0,
        y_end=5.0, markers=True), "0.00")
    lev["objects"]["lineStyles"].append(dict(P.props(lineStyle="dashed", strokeWidth=2.0),
                                             selector={"metadata": "Northstar Measures.Covenant Limit"}))
    pg.add("lev_trend", c2[0][0], y2, c2[0][1], h, lev, filters=closed_scope())
    pg.add("tests", c2[1][0], y2, c2[1][1], 176, P.table(
        [(DATE_MONTH_LONG, "Test date", None), (P.measure("Covenant Net Leverage"), "Net leverage", RATIO),
         (P.measure("Covenant Limit"), "Limit", RATIO), (P.measure("Covenant Headroom"), "Headroom", RATIO),
         (P.measure("Covenant Status"), "Status", None)],
        "Contractual test dates — the only dates a status is a verdict",
        sort_field=DATE_MONTH_LONG), filters=scope(DATE_TEST, prefix="td"))
    pg.add("instruments", c2[1][0], y2 + 176 + L.GUTTER, c2[1][1], h - 176 - L.GUTTER, P.table(
        [(P.column("Debt Instrument", "instrument_name"), "Instrument", None),
         (P.column("Debt Instrument", "instrument_type"), "Type", None),
         (P.column("Debt Instrument", "rate_type"), "Rate", None),
         (P.column("Debt Instrument", "is_hedged"), "Hedged", None),
         (P.column("Debt Instrument", "maturity_date"), "Maturity", None),
         (P.column("Debt Instrument", "counts_toward_covenant_debt"), "In covenant debt", None)],
        "Instrument register — terms from the debt schedule",
        sort_field=P.column("Debt Instrument", "instrument_type"), ascending=False))
    pg.no_filter("sl_period", "lev_trend", "tests", "instruments")
    return pg


# ================================================================ 08 Workforce & CapEx
def workforce_capex() -> Page:
    pg = Page("p08_workforce", "08 Workforce & CapEx", "Workforce and capital expenditure",
              "People and capital on the period basis selected · FTE, USD millions",
              slicers=("sl_period", "sl_basis", "sl_bu", "sl_entity"))
    y = L.CONTENT_Y
    c2 = L.cols(2)
    # ---- workforce, left
    pg.section("wf", c2[0][0], y, c2[0][1], "Workforce", "full-time equivalents")
    yw = y + 34
    tiles = [("w_open", "Opening FTE", "Opening FTE", FTE1), ("w_hires", "Hires", "Hires", COUNT),
             ("w_exits", "Exits", "Exits", COUNT), ("w_close", "Closing FTE", "Closing FTE", FTE1),
             ("w_cost", "Personnel cost", "Personnel Cost", M1)]
    tw = (c2[0][1] - 4 * 8) // 5
    for i, (key, label, meas, fmt) in enumerate(tiles):
        kpi(pg, key, c2[0][0] + i * (tw + 8), yw, tw, label, meas, fmt,
            value_filters=[ACTUAL] if meas == "Personnel Cost" else [], size=16.0)
    yw2 = yw + 56
    hw = L.CANVAS_H - 20 - yw2
    pg.add("fte_trend", c2[0][0], yw2, c2[0][1], (hw - L.GUTTER) // 2, fmt_values(P.line_chart(
        DATE_MONTH, [("Closing FTE", "Closing FTE")], "Closing FTE by month — closed months",
        colours={"Closing FTE": T.NAVY}, units=1.0, precision=0, legend=False), "#,0"),
        filters=closed_scope())
    pg.add("fte_family", c2[0][0], yw2 + (hw - L.GUTTER) // 2 + L.GUTTER, c2[0][1],
           (hw - L.GUTTER) // 2, fmt_values(P.column_chart(
               JOB_FAMILY, [("Closing FTE", "Closing FTE")], "Closing FTE by job family",
               horizontal=True, units=1.0, precision=0,
               sort_field=P.measure("Closing FTE"), sort_ascending=False, labels=True), "#,0"))
    # ---- capex, right
    pg.section("cx", c2[1][0], y, c2[1][1], "Capital expenditure", "USD millions")
    tiles = [("x_spend", "Spend", "Actual CapEx", M1), ("x_appr", "Approved", "Approved CapEx", M1),
             ("x_var", "Against approval", "CapEx Variance", M1S),
             ("x_n", "Projects", "Capital Projects", COUNT),
             ("x_dep", "CapEx / depreciation", "CapEx to Depreciation", RATIO)]
    for i, (key, label, meas, fmt) in enumerate(tiles):
        kpi(pg, key, c2[1][0] + i * (tw + 8), yw, tw, label, meas, fmt,
            value_filters=[ACTUAL] if meas in ("Actual CapEx", "CapEx to Depreciation") else [],
            size=16.0)
    pg.add("capex_class", c2[1][0], yw2, c2[1][1], (hw - L.GUTTER) // 2, fmt_values(P.column_chart(
        ASSET_CLASS, [("Actual CapEx", "Spend"), ("Approved CapEx", "Approved")],
        "Spend against approval by asset class",
        colours={"Actual CapEx": T.NAVY, "Approved CapEx": T.BUDGET},
        sort_field=P.measure("Actual CapEx"), sort_ascending=False), "#,0.0"),
        filters=scope(ACTUAL, prefix="cc"))
    pg.add("projects", c2[1][0], yw2 + (hw - L.GUTTER) // 2 + L.GUTTER, c2[1][1],
           (hw - L.GUTTER) // 2, P.table(
               [(P.column("Capital Project", "project_id"), "Project", None),
                (P.column("Capital Project", "project_name"), "Programme", None),
                (P.measure("Actual CapEx"), "Spend", M1),
                (P.measure("Approved CapEx"), "Approved", M1),
                (P.measure("CapEx Variance %"), "vs approval", PCT)],
               "Largest programmes — the corrected unique project key",
               sort_field=P.measure("Actual CapEx"), ascending=False,
               widths={"Capital Project.project_id": 150, "Capital Project.project_name": 178,
                       "Northstar Measures.Actual CapEx": 58,
                       "Northstar Measures.Approved CapEx": 64,
                       "Northstar Measures.CapEx Variance %": 66}),
           filters=scope(ACTUAL, prefix="pj"))
    pg.no_filter("sl_period", "fte_trend")
    return pg


# ================================================================ 09 Consolidation & controls
def consolidation() -> Page:
    pg = Page("p09_controls", "09 Consolidation & Controls", "Consolidation and control status",
              "What the consolidation does to the reported numbers, and the evidence that it "
              "is right", slicers=("sl_period", "sl_rbasis"))
    y = L.CONTENT_Y
    c2 = L.cols(2)
    # ---- the architecture, left: the five governed layers and the two views they make
    pg.section("arch", c2[0][0], y, c2[0][1], "Consolidation layers",
               "reported → consolidated")
    ya = y + 34
    pg.add("layers", c2[0][0], ya, c2[0][1], 190, P.table(
        [(P.column("Consolidation Layer", "layer_id"), "#", None),
         (P.column("Consolidation Layer", "layer_code"), "Code", None),
         (P.column("Consolidation Layer", "layer_name"), "Layer", None),
         (P.column("Consolidation Layer", "in_statutory_view"), "Statutory", None),
         (P.column("Consolidation Layer", "in_management_view"), "Management", None)],
        None, sort_field=P.column("Consolidation Layer", "layer_id"),
        widths={"Consolidation Layer.layer_id": 30, "Consolidation Layer.layer_code": 90,
                "Consolidation Layer.layer_name": 210,
                "Consolidation Layer.in_statutory_view": 80,
                "Consolidation Layer.in_management_view": 96}))
    yb = ya + 190 + 12
    pg.section("res", c2[0][0], yb, c2[0][1], "Consolidated result",
               "period and basis selected")
    yb += 34
    tiles = [("r_rev", "Revenue", "Revenue", M1), ("r_ebitda", "Statutory EBITDA", "Statutory EBITDA", M1),
             ("r_ni", "Net income", "Net Income", M1),
             ("r_nci", "Non-controlling interests", "Non-controlling Interests", M1),
             ("r_par", "Attributable to parent", "Net Income Attributable to Parent", M1)]
    tw = (c2[0][1] - 4 * 8) // 5
    for i, (key, label, meas, fmt) in enumerate(tiles):
        kpi(pg, key, c2[0][0] + i * (tw + 8), yb, tw, label, meas, fmt, size=16.0)
    note(pg, "arch_note", c2[0][0], yb + 62, c2[0][1],
         "Statutory = layers 1 + 2 + 3 + 5. Management = statutory + layer 4. The layer-level "
         "amounts live in the Layer Bridge fact and carry no governed measure yet; they are "
         "reported on sheet 13 of the workbook and will follow once a measure is governed.",
         h=56)
    # ---- the control environment, right: read from the registers, never typed
    pg.section("ctl", c2[1][0], y, c2[1][1], "Control environment",
               "every phase, from its own register")
    yc = y + 34
    x0 = c2[1][0]
    cols = [(x0, 66, "Phase"), (x0 + 70, 200, "Scope"), (x0 + 274, 60, "Controls"),
            (x0 + 338, 52, "Passed"), (x0 + 394, 62, "Fixtures"), (x0 + 460, 60, "Status")]
    for cx, cw, text in cols:
        pg.add(f"ch_{text}", cx, yc, cw, 16, P.textbox(text, T.TYPE["small"], T.INK, True,
                                                        align="left" if cw > 100 else "right"))
    pg.add("ch_rule", x0, yc + 18, c2[1][1], 1, P.shape(T.RULE_STRONG))
    yr = yc + 24
    for i, row in enumerate(META.control_status()):
        cells = [row["phase"], row["scope"], f"{row['controls']}", f"{row['passed']}",
                 (f"{row['detected']}/{row['fixtures']}" if row["fixtures"] else "—"),
                 row["status"]]
        for (cx, cw, _), text in zip(cols, cells):
            colour = (T.FAVOURABLE if text == "PASS" else T.UNFAVOURABLE if text == "FAIL"
                      else T.INK)
            pg.add(f"cr{i}_{cx}", cx, yr, cw, 18, P.textbox(
                text, T.TYPE["body"], colour, text in ("PASS", "FAIL"),
                align="left" if cw > 100 else "right"))
        pg.add(f"cr{i}_rule", x0, yr + 20, c2[1][1], 1, P.shape(T.RULE))
        yr += 22
    yr += 10
    pg.section("rec", x0, yr, c2[1][1], "Reconciliations across artefacts",
               "workbook, model, project")
    yr += 34
    for i, row in enumerate(META.reconciliations()):
        ok = row["passed"] == row["total"] and row["total"] > 0
        pending = row["passed"] < row["total"] and row.get("not_executed")
        pg.add(f"rc{i}_n", x0, yr, 300, 18, P.textbox(row["name"], T.TYPE["body"], T.INK, False))
        pg.add(f"rc{i}_v", x0 + 310, yr, 80, 18, P.textbox(
            f"{row['passed']}/{row['total']}", T.TYPE["body"], T.INK, False, align="right"))
        pg.add(f"rc{i}_s", x0 + 400, yr, 60, 18, P.textbox(
            "PASS" if ok else ("—" if pending else "FAIL"), T.TYPE["body"],
            T.FAVOURABLE if ok else (T.INK_MUTED if pending else T.UNFAVOURABLE), True,
            align="right"))
        pg.add(f"rc{i}_rule", x0, yr + 20, c2[1][1], 1, P.shape(T.RULE))
        yr += 22
    note(pg, "ctl_note", x0, yr + 6, c2[1][1],
         "Counts are read from the governed control registers when the report is generated "
         "and checked against them again by P6B-08 on every run. Nothing here is typed.",
         h=40)
    return pg


# ================================================================ 10 Lineage & technical
def lineage() -> Page:
    pg = Page("p10_lineage", "10 Lineage & Technical", "Lineage and technical",
              "From three ERP extracts to this page, and the identifiers that prove it is the "
              "same data at every step", slicers=())
    meta = META.lineage()
    y = L.SLICER_Y + 4
    # ---- the chain, as seven stations
    stations = [
        ("ERP extracts", "Aurora, Sable, Kestrel · 507 native files", f"source {meta['source_digest']}"),
        ("Standardised", "one schema, one calendar, one currency table", f"Phase 3 {meta['phase03']}"),
        ("Governed mappings", "group chart of accounts, entity master", "mapping acceptance"),
        ("Consolidated fact", "five layers, statutory and management views", f"Phase 4 {meta['phase04']}"),
        ("Reporting marts", "thirteen governed marts", f"Phase 5 {meta['phase05']}"),
        ("Semantic model", f"{meta['measures']} measures · {meta['relationships']} + {meta['inactive']} relationships",
         f"definition {meta['definition_digest']}"),
        ("This report", "ten pages, generated from declarations", f"project {meta['project_digest']}"),
    ]
    n = len(stations)
    gap = 10
    sw = (L.CONTENT_W - gap * (n - 1)) // n
    for i, (name, what, ident) in enumerate(stations):
        sx = L.X0 + i * (sw + gap)
        dark = i in (0, 3, 6)
        pg.add(f"st{i}_bg", sx, y, sw, 112, P.shape(T.NAVY if dark else T.PANEL))
        pg.add(f"st{i}_mark", sx, y, sw, 4, P.shape(T.COPPER))
        pg.add(f"st{i}_n", sx + 8, y + 10, sw - 16, 20,
               P.textbox(name, T.TYPE["body"], T.WHITE if dark else T.NAVY, True))
        pg.add(f"st{i}_w", sx + 8, y + 32, sw - 16, 44,
               P.textbox(what, T.TYPE["small"], "#D9E2EA" if dark else T.INK_MUTED, False))
        pg.add(f"st{i}_i", sx + 8, y + 82, sw - 16, 24,
               P.textbox(ident, T.TYPE["small"], T.COPPER_TINT if dark else T.COPPER, True))
    y2 = y + 112 + 24
    c2 = L.cols(2)
    # ---- identifiers, left
    pg.section("ids", c2[0][0], y2, c2[0][1], "Build identifiers", "canonical, checkout-safe")
    rows = [
        ("Source layer digest", meta["source_digest"]),
        ("Phase 3 build id", meta["phase03"]),
        ("Phase 4 build id", meta["phase04"]),
        ("Phase 5 build id", meta["phase05"]),
        ("Phase 6A build id", meta["phase06a"]),
        ("Semantic definition digest", meta["definition_digest"]),
        ("PBIP project digest", meta["project_digest"]),
        ("Excel workbook digest", meta["workbook_digest"]),
    ]
    yr = y2 + 34
    for i, (label, value) in enumerate(rows):
        pg.add(f"id{i}_l", c2[0][0], yr, 240, 18, P.textbox(label, T.TYPE["body"], T.INK, False))
        pg.add(f"id{i}_v", c2[0][0] + 250, yr, 260, 18,
               P.textbox(value, T.TYPE["body"], T.NAVY, True, family="Consolas"))
        pg.add(f"id{i}_rule", c2[0][0], yr + 20, c2[0][1], 1, P.shape(T.RULE))
        yr += 22
    # ---- the model and its validation, right
    pg.section("mdl", c2[1][0], y2, c2[1][1], "Semantic model and validation",
               f"Power BI Desktop {meta['desktop']}")
    rows = [
        ("Measures host", meta["measures_table"]),
        ("Measures", f"{meta['measures']} explicit, no implicit aggregation used on any page"),
        ("Relationships", f"{meta['relationships']} active · {meta['inactive']} inactive, with rationale"),
        ("Semantic controls", f"{meta['semantic_passed']}/{meta['semantic_controls']} · engine and native project"),
        ("Prior year", "PY_DERIVED, a governed derived version"),
        ("Current forecast", "the version flagged default in the version master"),
        ("Actual cutoff", "blank after the reporting close, never zero"),
        ("Refresh", "import from Parquet · Power Query in Desktop and TMSL in the engine"),
    ]
    yr = y2 + 34
    for i, (label, value) in enumerate(rows):
        pg.add(f"md{i}_l", c2[1][0], yr, 150, 18, P.textbox(label, T.TYPE["body"], T.INK, False))
        pg.add(f"md{i}_v", c2[1][0] + 160, yr, c2[1][1] - 160, 18,
               P.textbox(value, T.TYPE["body"], T.NAVY, False))
        pg.add(f"md{i}_rule", c2[1][0], yr + 20, c2[1][1], 1, P.shape(T.RULE))
        yr += 22
    pg.add("rp_l", c2[0][0], yr + 12, 240, 18, P.textbox("Reporting close", T.TYPE["body"], T.INK, False))
    pg.add("rp_v", c2[0][0] + 250, yr + 8, 260, 26, P.card("Reporting Period", value_size=12.0))
    note(pg, "ln_note", c2[0][0], yr + 44, L.CONTENT_W,
         "Every identifier above is recomputed by the build and compared with the committed "
         "manifests by the reproducibility controls. A build id hashes canonical content and "
         "survives a checkout; an artefact digest hashes bytes and does not.", h=40)
    return pg


PAGES = (executive, pnl, business_units, balance_sheet, cash_flow, ebitda, covenants,
         workforce_capex, consolidation, lineage)
