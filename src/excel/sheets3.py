"""
Report sheets 10 to 15: headcount, capital expenditure, FX, the consolidation and control
view, the variance drilldown, and the technical sheet.
"""

from __future__ import annotations

from openpyxl.chart import Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Font
from openpyxl.worksheet.datavalidation import DataValidation

from . import style as S
from .data import ACT_VERSION, BUD_VERSION, FC_VERSION, PY_VERSION, REPORT_FY, REPORT_PERIOD
from .sheets import (ACTUAL_MONTHS, FIRST_DATA_COL, MONTHS, _colour_variance, bar_chart,
                     chart_slots, col, headers, line_chart, note, put, section,
                     std_widths, title)


# ------------------------------------------------------------------ 10 Headcount
def headcount(wb, meta):
    ws = wb.create_sheet("10 Headcount")
    S.sheet_setup(ws, freeze="C8", zoom=100)
    std_widths(ws, label_width=36, data_width=10.5, n_data=9)
    for letter, width in (("F", 13), ("G", 15)):    # Total and Personnel cost carry headings
        ws.column_dimensions[letter].width = width

    title(ws, "Headcount and personnel cost",
          f"FY{REPORT_FY} to {meta['report_label']} · full-time equivalents", width_cols=11)

    section(ws, 5, "Group movement", last_col=11, right_text="FTE")
    headers(ws, 7, [meta["period_labels"][p] for p in ACTUAL_MONTHS])
    r = 8
    for field, name, sub, fmt in (("fte_opening", "Opening FTE", False, "ns_fte1"),
                                  ("hires", "Hires", False, "ns_fte1"),
                                  ("leavers", "Leavers", False, "ns_fte1"),
                                  ("fte_closing", "Closing FTE", True, "ns_fte1"),
                                  ("fte_average", "Average FTE", False, "ns_fte1"),
                                  ("headcount_closing", "Closing headcount", False, "ns_fte")):
        put(ws, f"B{r}", name, "ns_label_sub" if sub else "ns_label")
        for i, p in enumerate(ACTUAL_MONTHS):
            c = col(FIRST_DATA_COL + i)
            ws[f"{c}{r}"] = f"=SUMIFS(hc_{field},hc_period,{p})"
            ws[f"{c}{r}"].style = fmt
        r += 1
    put(ws, f"B{r}", "Personnel cost, USD m", "ns_label")
    for i, p in enumerate(ACTUAL_MONTHS):
        c = col(FIRST_DATA_COL + i)
        ws[f"{c}{r}"] = f"=SUMIFS(pay_cost,pay_period,{p})"
        ws[f"{c}{r}"].style = "ns_m1"
    pay_row = r
    r += 1
    put(ws, f"B{r}", "Cost per average FTE, USD k per month", "ns_label_i")
    for i, p in enumerate(ACTUAL_MONTHS):
        c = col(FIRST_DATA_COL + i)
        ws[f"{c}{r}"] = f'=IFERROR({c}{pay_row}*1000/{c}{pay_row - 2},"")'
        ws[f"{c}{r}"].style = "ns_m1_i"
    r += 2

    note(ws, r, "Hires and leavers are counts of people; FTE is fractional, because a "
                "part-time joiner is one hire and a fraction of an FTE. The two are reported "
                "beside each other rather than netted, and closing FTE is continuous with the "
                "prior month at the finest grain — which is the identity the data actually "
                "supports.", last_col=11)
    r += 2

    section(ws, r, "By business unit and function", last_col=11,
            right_text=f"Closing FTE at {meta['report_label']}")
    r += 1
    headers(ws, r, [f["name"] for f in meta["functions"]] + ["Total FTE", "Personnel cost"],
            label_text="Business unit")
    r += 1
    first = r
    for bu, bu_name in meta["bus"]:
        put(ws, f"B{r}", bu_name, "ns_label")
        for i, f in enumerate(meta["functions"]):
            c = col(FIRST_DATA_COL + i)
            ws[f"{c}{r}"] = (f'=SUMIFS(hc_fte_closing,hc_bu,"{bu}",hc_function,'
                             f'"{f["code"]}",hc_period,{REPORT_PERIOD})')
            ws[f"{c}{r}"].style = "ns_fte"
        tc = col(FIRST_DATA_COL + len(meta["functions"]))
        ws[f"{tc}{r}"] = (f'=SUMIFS(hc_fte_closing,hc_bu,"{bu}",hc_period,{REPORT_PERIOD})')
        ws[f"{tc}{r}"].style = "ns_fte"
        pc = col(FIRST_DATA_COL + len(meta["functions"]) + 1)
        ws[f"{pc}{r}"] = (f'=SUMIFS(hc_salary,hc_bu,"{bu}",hc_period,{REPORT_PERIOD})')
        ws[f"{pc}{r}"].style = "ns_m1"
        r += 1
    put(ws, f"B{r}", "Group", "ns_label_sub")
    for i in range(len(meta["functions"]) + 2):
        c = col(FIRST_DATA_COL + i)
        ws[f"{c}{r}"] = f"=SUM({c}{first}:{c}{r-1})"
        ws[f"{c}{r}"].style = ("ns_m1_sub" if i == len(meta["functions"]) + 1 else "ns_fte")
    r += 2

    section(ws, r, "Trend", last_col=11)
    slots, chart_w = chart_slots(ws, 11)
    line_chart(ws, f"{slots[0]}{r + 2}", "Closing headcount and personnel cost — FY2026",
               Reference(wb["_chart"], min_col=2, min_row=2, max_row=13),
               [(Reference(wb["_chart"], min_col=35, min_row=2, max_row=13), "Closing FTE",
                 S.ACTUAL, None)], width=chart_w, height=7.4, number_format=S.FTE)
    bar_chart(ws, f"{slots[1]}{r + 2}", f"Closing FTE by business unit at {meta['report_label']}",
              Reference(wb["_chart"], min_col=8, min_row=2, max_row=6),
              [(Reference(wb["_chart"], min_col=36, min_row=2, max_row=6), "FTE",
                S.ACTUAL)], width=chart_w, height=7.4, number_format=S.FTE)
    ws.print_area = f"A1:L{r + 18}"
    return ws


def _asset_class(code: str) -> str:
    """`str.title()` turns IT into It. Acronyms need saying, not title-casing."""
    label = code.replace("_", " ").title()
    for acronym in ("It", "Erp", "Hvac"):
        label = label.replace(acronym, acronym.upper())
    return label


# ------------------------------------------------------------------ 11 CapEx
def capex(wb, meta):
    ws = wb.create_sheet("11 CapEx")
    S.sheet_setup(ws, freeze="C8", zoom=100)
    std_widths(ws, label_width=44, data_width=10.5, n_data=9)
    ws.column_dimensions["C"].width = 24   # the project table puts the unit here

    title(ws, "Capital expenditure",
          f"FY{REPORT_FY} to {meta['report_label']} · USD millions", width_cols=11)

    section(ws, 5, "By business unit", last_col=11, right_text="Year-to-date spend")
    headers(ws, 7, [meta["period_labels"][p] for p in ACTUAL_MONTHS] + ["YTD"],
            label_text="Business unit")
    r = 8
    first = r
    for bu, bu_name in meta["bus"]:
        put(ws, f"B{r}", bu_name, "ns_label")
        for i, p in enumerate(ACTUAL_MONTHS):
            c = col(FIRST_DATA_COL + i)
            ws[f"{c}{r}"] = f'=SUMIFS(cx_spend,cx_bu,"{bu}",cx_period,{p})'
            ws[f"{c}{r}"].style = "ns_m1"
        tc = col(FIRST_DATA_COL + len(ACTUAL_MONTHS))
        ws[f"{tc}{r}"] = (f"=SUM({col(FIRST_DATA_COL)}{r}:"
                          f"{col(FIRST_DATA_COL + len(ACTUAL_MONTHS) - 1)}{r})")
        ws[f"{tc}{r}"].style = "ns_m1"
        r += 1
    put(ws, f"B{r}", "Total capital expenditure", "ns_label_sub")
    for i in range(len(ACTUAL_MONTHS) + 1):
        c = col(FIRST_DATA_COL + i)
        ws[f"{c}{r}"] = f"=SUM({c}{first}:{c}{r-1})"
        ws[f"{c}{r}"].style = "ns_m1_sub"
    total_row = r
    r += 1
    put(ws, f"B{r}", "Depreciation charge, group", "ns_label_i")
    for i, p in enumerate(ACTUAL_MONTHS):
        c = col(FIRST_DATA_COL + i)
        ws[f"{c}{r}"] = f'=SUMIFS(pl_mtd,pl_measure,"DA",pl_ver,"{ACT_VERSION}",pl_period,{p})'
        ws[f"{c}{r}"].style = "ns_m1_i"
    tc = col(FIRST_DATA_COL + len(ACTUAL_MONTHS))
    ws[f"{tc}{r}"] = (f"=SUM({col(FIRST_DATA_COL)}{r}:"
                      f"{col(FIRST_DATA_COL + len(ACTUAL_MONTHS) - 1)}{r})")
    ws[f"{tc}{r}"].style = "ns_m1_i"
    r += 1
    put(ws, f"B{r}", "Capital expenditure as a multiple of depreciation", "ns_label_i")
    ws[f"{tc}{r}"] = f'=IFERROR({tc}{total_row}/{tc}{r-1},"")'
    ws[f"{tc}{r}"].style = "ns_ratio"
    r += 2

    section(ws, r, "By asset class", last_col=11, right_text="Year to date")
    r += 1
    headers(ws, r, ["YTD spend", "% of total"], label_text="Asset class")
    r += 1
    ac_first = r
    for cls in meta["asset_classes"]:
        put(ws, f"B{r}", _asset_class(cls), "ns_label")
        ws[f"C{r}"] = (f'=SUMIFS(cx_spend,cx_class,"{cls}",cx_year,{REPORT_FY})'
                       f'-SUMIFS(cx_spend,cx_class,"{cls}",cx_period,">{REPORT_PERIOD}")')
        ws[f"C{r}"].style = "ns_m1"
        ws[f"D{r}"] = f'=IFERROR(C{r}/$C${ac_first + len(meta["asset_classes"])},"")'
        ws[f"D{r}"].style = "ns_pct"
        r += 1
    put(ws, f"B{r}", "Total", "ns_label_sub")
    ws[f"C{r}"] = f"=SUM(C{ac_first}:C{r-1})"
    ws[f"C{r}"].style = "ns_m1_sub"
    r += 2

    section(ws, r, "Largest projects", last_col=11, right_text="By year-to-date spend")
    r += 1
    headers(ws, r, ["Business unit", "Asset class", "Approved", "YTD spend", "% spent"],
            label_text="Project")
    r += 1
    for pid, pname, bu_name, cls, approved, spend in meta["top_projects"]:
        put(ws, f"B{r}", pname, "ns_label")
        put(ws, f"C{r}", bu_name, "ns_text_mut")
        put(ws, f"D{r}", _asset_class(cls), "ns_text_mut")
        put(ws, f"E{r}", approved, "ns_m1")
        put(ws, f"F{r}", spend, "ns_m1")
        ws[f"G{r}"] = f'=IFERROR(F{r}/E{r},"")'
        ws[f"G{r}"].style = "ns_pct"
        r += 1
    r += 1

    section(ws, r, "Trend", last_col=11)
    slots, chart_w = chart_slots(ws, 11)
    bar_chart(ws, f"{slots[0]}{r + 2}", "Capital expenditure by month — FY2026",
              Reference(wb["_chart"], min_col=2, min_row=2, max_row=13),
              [(Reference(wb["_chart"], min_col=38, min_row=2, max_row=13), "CapEx",
                S.ACTUAL)], width=chart_w, height=7.4)
    line_chart(ws, f"{slots[1]}{r + 2}", "Capital expenditure against depreciation",
               Reference(wb["_chart"], min_col=2, min_row=2, max_row=13),
               [(Reference(wb["_chart"], min_col=38, min_row=2, max_row=13), "CapEx",
                 S.ACTUAL, None),
                (Reference(wb["_chart"], min_col=39, min_row=2, max_row=13), "Depreciation",
                 S.FORECAST, "dash")], width=chart_w, height=7.4)
    ws.print_area = f"A1:L{r + 18}"
    return ws


# ------------------------------------------------------------------ 12 FX
def fx(wb, meta):
    ws = wb.create_sheet("12 FX")
    S.sheet_setup(ws, freeze="C8", zoom=100)
    std_widths(ws, label_width=30, data_width=13.5, n_data=9)

    title(ws, "Foreign exchange",
          f"FY{REPORT_FY} to {meta['report_label']} · rates, exposure and translation",
          width_cols=11)

    section(ws, 5, "Currency exposure", last_col=11,
            right_text="Revenue by functional currency, year to date")
    headers(ws, 7, ["Revenue YTD", "% of group", "Avg rate", "PY rate",
                    "Rate move", "Constant ccy", "FX effect"], label_text="Currency")
    r = 8
    first = r
    for ccy in meta["currencies"]:
        put(ws, f"B{r}", ccy, "ns_label")
        ws[f"C{r}"] = (f'=SUMIFS(fx_revenue,fx_ccy,"{ccy}",fx_year,{REPORT_FY})'
                       f'-SUMIFS(fx_revenue,fx_ccy,"{ccy}",fx_period,">{REPORT_PERIOD}")')
        ws[f"C{r}"].style = "ns_m1"
        ws[f"D{r}"] = f'=IFERROR(C{r}/$C${first + len(meta["currencies"])},"")'
        ws[f"D{r}"].style = "ns_pct"
        ws[f"E{r}"] = f'=SUMIFS(fx_avg,fx_ccy,"{ccy}",fx_period,{REPORT_PERIOD})'
        ws[f"E{r}"].style = "ns_rate"
        ws[f"F{r}"] = f'=SUMIFS(fx_avg_py,fx_ccy,"{ccy}",fx_period,{REPORT_PERIOD})'
        ws[f"F{r}"].style = "ns_rate"
        ws[f"G{r}"] = f'=IFERROR(E{r}/F{r}-1,"")'
        ws[f"G{r}"].style = "ns_pct"
        ws[f"H{r}"] = (f'=SUMIFS(fx_revenue_cc,fx_ccy,"{ccy}",fx_year,{REPORT_FY})'
                       f'-SUMIFS(fx_revenue_cc,fx_ccy,"{ccy}",fx_period,">{REPORT_PERIOD}")')
        ws[f"H{r}"].style = "ns_m1"
        ws[f"I{r}"] = f"=C{r}-H{r}"
        ws[f"I{r}"].style = "ns_m1"
        r += 1
    put(ws, f"B{r}", "Group", "ns_label_sub")
    for c in "CHI":
        ws[f"{c}{r}"] = f"=SUM({c}{first}:{c}{r-1})"
        ws[f"{c}{r}"].style = "ns_m1_sub"
    r += 2

    note(ws, r, "The translation effect above is an OPERATING measure: this year's activity "
                "restated at last year's average rate, which is what a reader means by "
                "\"how much of the revenue movement was currency\". It is not the cumulative "
                "translation adjustment below, which arises on net assets and never touches "
                "the income statement.", last_col=11)
    r += 2

    section(ws, r, "Cumulative translation adjustment", last_col=11,
            right_text="An equity reserve, not an operating item")
    r += 1
    headers(ws, r, ["Movement YTD", "Group share", "NCI share"],
            label_text="Entity currency")
    r += 1
    cta_first = r
    for ccy in meta["cta_currencies"]:
        put(ws, f"B{r}", ccy, "ns_label")
        for c, field in (("C", "fx_cta_move"), ("D", "fx_cta_group"), ("E", "fx_cta_nci")):
            ws[f"{c}{r}"] = (f'=SUMIFS({field},fx_ccy,"{ccy}",fx_year,{REPORT_FY})'
                             f'-SUMIFS({field},fx_ccy,"{ccy}",fx_period,">{REPORT_PERIOD}")')
            ws[f"{c}{r}"].style = "ns_m1"
        r += 1
    put(ws, f"B{r}", "Total translation movement", "ns_label_sub")
    for c in "CDE":
        ws[f"{c}{r}"] = f"=SUM({c}{cta_first}:{c}{r-1})"
        ws[f"{c}{r}"].style = "ns_m1_sub"
    r += 2

    section(ws, r, "Rate trend", last_col=11)
    slots, chart_w = chart_slots(ws, 11)
    line_chart(ws, f"{slots[0]}{r + 2}", "Average rates against USD — FY2026",
               Reference(wb["_chart"], min_col=2, min_row=2, max_row=13),
               [(Reference(wb["_chart"], min_col=41, min_row=2, max_row=13), "EUR",
                 S.ACTUAL, None),
                (Reference(wb["_chart"], min_col=42, min_row=2, max_row=13), "GBP",
                 S.FORECAST, None),
                (Reference(wb["_chart"], min_col=43, min_row=2, max_row=13), "CAD",
                 S.BUDGET, None)], width=chart_w, height=7.4, number_format=S.RATE)
    line_chart(ws, f"{slots[1]}{r + 2}", "Cumulative translation adjustment — monthly movement",
               Reference(wb["_chart"], min_col=2, min_row=2, max_row=13),
               [(Reference(wb["_chart"], min_col=44, min_row=2, max_row=13),
                 "CTA movement", S.ACTUAL, None)], width=chart_w, height=7.4)
    ws.print_area = f"A1:K{r + 18}"
    return ws


# ------------------------------------------------------------------ 13 Consolidation & controls
def consolidation(wb, meta):
    ws = wb.create_sheet("13 Consolidation & Controls")
    S.sheet_setup(ws, freeze="C8", zoom=100)
    S.widths(ws, {"A": 2.2, "B": 46, "C": 13, "D": 13, "E": 13, "F": 13, "G": 11, "H": 11,
                  "I": 30, "J": 13, "K": 13})

    title(ws, "Consolidation and control status",
          "What the consolidation does to the reported numbers, and the evidence that it is "
          "right", width_cols=11)

    section(ws, 5, "Consolidation layers", last_col=11,
            right_text="Net income contribution, USD m")
    headers(ws, 7, [f"FY{y}" for y in meta["fy_list"]] + ["Entries", "Legs", "In statutory",
                                                          "In management"], label_text="Layer")
    r = 8
    for layer_id, layer_code, layer_name, in_stat, in_mgmt in meta["layers"]:
        put(ws, f"B{r}", f"{layer_id}  {layer_name}", "ns_label")
        for i, y in enumerate(meta["fy_list"]):
            c = col(FIRST_DATA_COL + i)
            ws[f"{c}{r}"] = f"=SUMIFS(lay_ni,lay_id,{layer_id},lay_year,{y})"
            ws[f"{c}{r}"].style = "ns_m1"
        ec = col(FIRST_DATA_COL + len(meta["fy_list"]))
        lc = col(FIRST_DATA_COL + len(meta["fy_list"]) + 1)
        ws[f"{ec}{r}"] = f"=SUMIFS(lay_entries,lay_id,{layer_id})"
        ws[f"{ec}{r}"].style = "ns_fte"
        ws[f"{lc}{r}"] = f"=SUMIFS(lay_legs,lay_id,{layer_id})"
        ws[f"{lc}{r}"].style = "ns_fte"
        put(ws, f"{col(FIRST_DATA_COL + len(meta['fy_list']) + 2)}{r}",
            "Yes" if in_stat else "No", "ns_text_c")
        put(ws, f"{col(FIRST_DATA_COL + len(meta['fy_list']) + 3)}{r}",
            "Yes" if in_mgmt else "No", "ns_text_c")
        r += 1
    put(ws, f"B{r}", "Consolidated net income", "ns_label_sub")
    for i in range(len(meta["fy_list"])):
        c = col(FIRST_DATA_COL + i)
        ws[f"{c}{r}"] = f"=SUM({c}8:{c}{r-1})"
        ws[f"{c}{r}"].style = "ns_m1_sub"
    r += 2

    section(ws, r, "What the consolidation contributed", last_col=11,
            right_text=f"At {meta['report_label']}")
    r += 1
    headers(ws, r, ["Value", "Unit", "Source artefact"], label_text="")
    r += 1
    for _sort, item, value, unit, source in meta["consol_items"]:
        put(ws, f"B{r}", item, "ns_label")
        put(ws, f"C{r}", value, "ns_m2" if unit == "USD m" else "ns_fte")
        put(ws, f"D{r}", unit, "ns_text_mut")
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=7)
        put(ws, f"E{r}", source, "ns_text_mut")
        r += 1
    r += 1

    section(ws, r, "Control status", last_col=11, right_text="Every phase, every control")
    r += 1
    headers(ws, r, ["Controls", "Passed", "Failed", "Status"], label_text="Phase")
    r += 1
    ctl_first = r
    for phase, total, passed in meta["control_summary"]:
        put(ws, f"B{r}", phase, "ns_label")
        put(ws, f"C{r}", total, "ns_fte")
        put(ws, f"D{r}", passed, "ns_fte")
        put(ws, f"E{r}", total - passed, "ns_fte")
        put(ws, f"F{r}", "PASS" if total == passed else "FAIL",
            "ns_status_ok" if total == passed else "ns_status_bad")
        r += 1
    put(ws, f"B{r}", "Total", "ns_label_sub")
    for c in "CDE":
        ws[f"{c}{r}"] = f"=SUM({c}{ctl_first}:{c}{r-1})"
        ws[f"{c}{r}"].style = "ns_m1_sub"
        ws[f"{c}{r}"].number_format = S.FTE
    r += 2

    section(ws, r, "Reconciliations exposed in this workbook", last_col=11)
    r += 1
    headers(ws, r, ["Result", "Threshold", "Status"], label_text="Check")
    r += 1
    for name, result, threshold, ok in meta["workbook_checks"]:
        put(ws, f"B{r}", name, "ns_label")
        put(ws, f"C{r}", result, "ns_text_c")
        put(ws, f"D{r}", threshold, "ns_text_c")
        put(ws, f"E{r}", "PASS" if ok else "FAIL",
            "ns_status_ok" if ok else "ns_status_bad")
        r += 1
    note(ws, r + 1, "Control results are read from the governed control registers, not "
                    "recomputed here. The workbook exposes them so that a reader can see the "
                    "evidence beside the numbers rather than being asked to trust them.",
         last_col=11)
    ws.print_area = f"A1:K{r + 3}"
    return ws


# ------------------------------------------------------------------ 14 Variance detail
def variance_detail(wb, meta):
    ws = wb.create_sheet("14 Variance Detail")
    S.sheet_setup(ws, freeze="C11", zoom=100)
    S.widths(ws, {"A": 2.2, "B": 44, "C": 26, "D": 13, "E": 13, "F": 13,
                  "G": 13, "H": 13, "I": 14, "J": 12})

    title(ws, "Variance detail",
          "Select a comparison and a business unit; the grid below responds", width_cols=10)

    section(ws, 5, "Selection", last_col=10)
    put(ws, "B6", "Comparison", "ns_input_label")
    put(ws, "C6", meta["default_comparison"], "ns_input")
    put(ws, "B7", "Business unit", "ns_input_label")
    put(ws, "C7", "All", "ns_input")
    put(ws, "E6", "Period basis", "ns_input_label")
    put(ws, "F6", "Year to date", "ns_input")

    dv_cmp = DataValidation(type="list",
                            formula1='"' + ",".join(meta["comparison_names"]) + '"',
                            allow_blank=False, showDropDown=False)
    ws.add_data_validation(dv_cmp)
    dv_cmp.add(ws["C6"])
    dv_bu = DataValidation(type="list",
                           formula1='"All,' + ",".join(b[1] for b in meta["bus"]) + '"',
                           allow_blank=False, showDropDown=False)
    ws.add_data_validation(dv_bu)
    dv_bu.add(ws["C7"])
    dv_basis = DataValidation(type="list", formula1='"Year to date,Full year"',
                              allow_blank=False, showDropDown=False)
    ws.add_data_validation(dv_basis)
    dv_basis.add(ws["F6"])

    put(ws, "H6", "Comparison code", "ns_input_label")
    ws["I6"] = '=INDEX(cmp_code,MATCH($C$6,cmp_name,0))'
    ws["I6"].style = "ns_text_c"
    put(ws, "H7", "Business unit code", "ns_input_label")
    ws["I7"] = '=IF($C$7="All","",INDEX(bu_list_code,MATCH($C$7,bu_list_name,0)))'
    ws["I7"].style = "ns_text_c"

    section(ws, 9, "Group and business unit", last_col=10,
            right_text="Variance on the selected basis")
    headers(ws, 10, ["Base", "Comparator", "Variance $", "Variance %", "Comparable"],
            label_text="Measure")
    r = 11
    first = r
    for code, name, indent, sub, total in meta["pl_rows"]:
        put(ws, f"B{r}", name,
            "ns_label_tot" if total else "ns_label_sub" if sub else
            "ns_label_i" if indent else "ns_label")
        base = ('=IF($F$6="Year to date",SUMIFS(var_base_ytd,var_cmp,$I$6,var_measure,'
                f'"{code}",var_bu,IF($I$7="","*",$I$7),var_period,{REPORT_PERIOD}),'
                'SUMIFS(var_base_fy,var_cmp,$I$6,var_measure,'
                f'"{code}",var_bu,IF($I$7="","*",$I$7),var_period,{REPORT_PERIOD}))')
        comp = base.replace("var_base_ytd", "var_comp_ytd").replace("var_base_fy",
                                                                    "var_comp_fy")
        ws[f"C{r}"] = base
        ws[f"D{r}"] = comp
        ws[f"E{r}"] = f"=C{r}-D{r}"
        ws[f"F{r}"] = f'=IF(D{r}=0,"",E{r}/ABS(D{r}))'
        ws[f"G{r}"] = (f'=IF(SUMIFS(var_comparable,var_cmp,$I$6,var_measure,"{code}",'
                       f'var_bu,IF($I$7="","*",$I$7),var_period,{REPORT_PERIOD})>0,'
                       f'"Yes","Not comparable")')
        for c in "CDE":
            ws[f"{c}{r}"].style = ("ns_m1_tot" if total else "ns_m1_sub" if sub else "ns_m1")
        ws[f"F{r}"].style = "ns_pct_sub" if sub or total else "ns_pct"
        ws[f"G{r}"].style = "ns_status_info"
        r += 1
    _colour_variance(ws, ["E"], first, r - 1)
    r += 1

    section(ws, r, "Account detail", last_col=10,
            right_text=f"FY{REPORT_FY} year to date, actual against budget")
    r += 1
    headers(ws, r, ["Entity", "Actual YTD", "Budget YTD", "Variance $", "Variance %"],
            label_text="Account")
    r += 1
    for account, name, entity, act, bud, line in meta["account_detail"]:
        put(ws, f"B{r}", f"{account}  {name}", "ns_label")
        put(ws, f"C{r}", entity, "ns_text_mut")
        put(ws, f"D{r}", act, "ns_m1")
        put(ws, f"E{r}", bud, "ns_m1")
        ws[f"F{r}"] = f"=D{r}-E{r}"
        # Favourability is a property of the ACCOUNT, not of the sign. Revenue above budget is
        # good news and subcontract cost above budget is not, and a conditional format that
        # greens every positive number says the opposite on half these rows. The style is
        # therefore chosen per row from the account's own reporting line.
        higher_is_better = line == "REVENUE"
        good = (act - bud > 0) == higher_is_better
        ws[f"F{r}"].style = "ns_var_fav" if good else "ns_var_unf"
        ws[f"G{r}"] = f'=IF(E{r}=0,"",F{r}/ABS(E{r}))'
        ws[f"G{r}"].style = "ns_var_pct_fav" if good else "ns_var_pct_unf"
        r += 1
    note(ws, r + 1, "The account detail lists the largest year-to-date account variances "
                    "against budget across the group, at entity grain. The full "
                    "group → business unit → entity → cost centre → account population is on "
                    "the hidden data sheet the grid reads and is available to Power BI in "
                    "Phase 6.", last_col=10)
    ws.print_area = f"A1:J{r + 3}"
    return ws


# ------------------------------------------------------------------ 15 Data & technical
def technical(wb, meta):
    ws = wb.create_sheet("15 Data & Technical")
    S.sheet_setup(ws, freeze="A1", zoom=100, landscape=False)
    S.widths(ws, {"A": 2.2, "B": 40, "C": 58, "D": 16, "E": 16})

    title(ws, "Data and technical reference", "Lineage, refresh and build identifiers",
          width_cols=5)

    section(ws, 5, "Build identifiers", last_col=5)
    r = 6
    for label, value in meta["build_meta"]:
        put(ws, f"B{r}", label, "ns_label")
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
        put(ws, f"C{r}", value, "ns_text_mut")
        r += 1
    r += 1

    section(ws, r, "Lineage", last_col=5,
            right_text="Report figure back to the source journal line")
    r += 1
    for step, detail in meta["lineage"]:
        put(ws, f"B{r}", step, "ns_label")
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
        put(ws, f"C{r}", detail, "ns_text_mut")
        r += 1
    r += 1

    section(ws, r, "Reporting marts consumed", last_col=5)
    r += 1
    headers(ws, r, ["Rows", "Grain"], label_text="Mart")
    r += 1
    for name, rows_n, grain in meta["marts"]:
        put(ws, f"B{r}", name, "ns_label")
        put(ws, f"C{r}", rows_n, "ns_fte")
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=5)
        put(ws, f"D{r}", grain, "ns_text_mut")
        r += 1
    r += 1

    section(ws, r, "Refresh", last_col=5)
    r += 1
    for step, detail in meta["refresh"]:
        put(ws, f"B{r}", step, "ns_label")
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=5)
        put(ws, f"C{r}", detail, "ns_text_mut")
        r += 1

    note(ws, r + 1, "The hidden sheets prefixed with an underscore hold the governed data this "
                    "workbook reads. They are extracts of the reporting marts and are not "
                    "editable inputs: changing one changes the report and not the ledger, "
                    "which is why the reconciliation checks on sheet 13 exist.", last_col=5)
    ws.print_area = f"A1:E{r + 3}"
    return ws
