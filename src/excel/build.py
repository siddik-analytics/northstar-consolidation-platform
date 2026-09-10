"""
Build the management reporting workbook.

    python -m src.excel.build

## Why openpyxl and not a template

The workbook is **authored**, not edited. There is no template to round-trip, so nothing can
be stripped from one: every sheet, style, number format, chart and defined name in the output
is created here and is therefore in version control as code. That is the property that makes
the workbook reproducible — the same marts produce the same workbook, and a change to it is a
diff rather than a description of what somebody did in Excel.

Excel itself is then used for what only Excel can do: calculate the formulas, resolve the
final rendered layout, and produce the images the visual review is done from.

## Why formulas and not values

Every reported figure is a `SUMIFS` into a hidden governed data sheet rather than a pasted
number. A reader can select any cell and see where it came from; changing the selection on the
variance sheet re-queries rather than needing a rebuild; and a pasted-value workbook cannot be
audited by the person holding it.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

import duckdb
from openpyxl import Workbook
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.utils import absolute_coordinate, get_column_letter, quote_sheetname

from . import sheets, sheets2, sheets3
from . import style as S
from .data import (ACT_VERSION, BUD_VERSION, FC_VERSION, PY_VERSION, REPORT_FY, REPORT_PERIOD,
                   collect)
from ..marts.config import DATA, DUCKDB_PATH, EXPORTS

WORKBOOK = EXPORTS / "Northstar_Consolidation_Management_Reporting.xlsx"

#: A fixed timestamp for every document property and every entry in the archive. An .xlsx is a
#: zip, and a zip records the wall-clock time of each member -- so two builds of identical data
#: produce different bytes for no reason anyone would care about. ADR-0022 says a build whose
#: bytes move between runs of identical data cannot be used as evidence, and the workbook is
#: not exempt from that just because it is the deliverable.
EPOCH = datetime.datetime(2020, 1, 1, 0, 0, 0)

WORKBOOK_MANIFEST = DATA / "phase05_workbook_manifest.json"

#: Which columns of each hidden data sheet get a defined name, and what to call it. Formulas
#: read `pl_ytd` rather than `_pl!$K$2:$K$1849`, which is the difference between a formula a
#: reviewer can read and one they have to decode.
NAMES: dict[str, dict[str, str]] = {
    "_pl": {"measure_code": "pl_measure", "scenario_code": "pl_scen", "version_code": "pl_ver",
            "period_key": "pl_period", "mtd_m": "pl_mtd", "ytd_m": "pl_ytd", "fy_m": "pl_fy"},
    "_bu": {"measure_code": "bu_measure", "bu_code": "bu_bu", "version_code": "bu_ver",
            "period_key": "bu_period", "ytd_m": "bu_ytd", "mtd_m": "bu_mtd"},
    "_ent": {"measure_code": "ent_measure", "entity_code": "ent_entity",
             "period_key": "ent_period", "ytd_m": "ent_ytd", "cash_m": "ent_cash",
             "fte": "ent_fte", "wc_m": "ent_wc"},
    "_bs": {"caption": "bs_caption", "account_class": "bs_class", "period_key": "bs_period",
            "bal_m": "bs_bal", "prior_month_m": "bs_prior_month",
            "prior_year_m": "bs_prior_year"},
    "_cf": {"period_key": "cf_period", "opening_m": "cf_opening_m", "result_m": "cf_result_m",
            "noncash_m": "cf_noncash_m", "wc_m": "cf_wc_m", "fxnoncash_m": "cf_fxnoncash_m",
            "closetx_m": "cf_closetx_m", "ocf_m": "cf_ocf_m", "icf_m": "cf_icf_m",
            "fcf_m": "cf_fcf_m", "fxcash_m": "cf_fxcash_m", "net_m": "cf_net_m",
            "closing_m": "cf_closing_m", "rcf_drawn_m": "cf_rcf_drawn_m",
            "rcf_avail_m": "cf_rcf_avail_m", "liquidity_m": "cf_liquidity_m"},
    "_wc": {"period_key": "wc_period", "ar_m": "wc_ar_m", "inv_m": "wc_inv_m",
            "ap_m": "wc_ap_m", "other_m": "wc_other_m", "nwc_m": "wc_nwc_m",
            "dso_days": "wc_dso_days", "dio_days": "wc_dio_days", "dpo_days": "wc_dpo_days",
            "ccc_days": "wc_ccc_days"},
    "_ebitda": {"fiscal_year": "eb_year", "statutory_m": "eb_statutory_m",
                "layer4_m": "eb_layer4_m", "addbacks_m": "eb_addbacks_m",
                "adjusted_m": "eb_adjusted_m", "cap_effect_m": "eb_cap_effect_m",
                "fx_addback_m": "eb_fx_addback_m", "covenant_m": "eb_covenant_m"},
    "_addback": {"group_account": "ab_account", "fiscal_year": "ab_year",
                 "amount_m": "ab_amount"},
    "_debt": {"instrument_id": "dbt_id", "period_key": "dbt_period",
              "instrument_type": "dbt_type",
              "closing_m": "dbt_closing", "undrawn_m": "dbt_undrawn"},
    "_cov": {"period_key": "cov_period", "max_net_leverage": "cov_max_net_leverage",
             "covenant_debt_m": "cov_covenant_debt_m", "cash_m": "cov_cash_m",
             "net_debt_m": "cov_net_debt_m", "covenant_ebitda_m": "cov_covenant_ebitda_m",
             "net_leverage": "cov_net_leverage", "headroom_turns": "cov_headroom_turns",
             "headroom_m": "cov_headroom_m", "economic_leverage": "cov_economic_leverage"},
    "_hc": {"period_key": "hc_period", "bu_code": "hc_bu", "function_group": "hc_function",
            "fte_opening": "hc_fte_opening", "hires": "hc_hires", "leavers": "hc_leavers",
            "fte_closing": "hc_fte_closing", "fte_average": "hc_fte_average",
            "headcount_closing": "hc_headcount_closing", "salary_month_m": "hc_salary"},
    "_hcpay": {"period_key": "pay_period", "personnel_cost_m": "pay_cost"},
    "_capex": {"period_key": "cx_period", "fiscal_year": "cx_year", "bu_code": "cx_bu",
               "asset_class": "cx_class", "spend_m": "cx_spend"},
    "_fx": {"currency_code": "fx_ccy", "period_key": "fx_period", "fiscal_year": "fx_year",
            "avg_rate": "fx_avg", "avg_rate_py": "fx_avg_py", "revenue_m": "fx_revenue",
            "revenue_cc_m": "fx_revenue_cc", "cta_move_m": "fx_cta_move",
            "cta_group_m": "fx_cta_group", "cta_nci_m": "fx_cta_nci"},
    "_layers": {"layer_id": "lay_id", "fiscal_year": "lay_year", "net_income_m": "lay_ni",
                "entries": "lay_entries", "legs": "lay_legs"},
    "_var": {"comparison_code": "var_cmp", "measure_code": "var_measure", "bu_code": "var_bu",
             "period_key": "var_period", "base_ytd_m": "var_base_ytd",
             "comp_ytd_m": "var_comp_ytd", "base_fy_m": "var_base_fy",
             "comp_fy_m": "var_comp_fy", "is_comparable": "var_comparable"},
}


def _write_data(wb, tables):
    """Hidden sheets holding the governed extracts, plus a defined name per useful column."""
    for name, (header, rows) in tables.items():
        ws = wb.create_sheet(name)
        ws.append(header)
        for row in rows:
            ws.append(list(row))
        ws.sheet_state = "hidden"
        ws.freeze_panes = "A2"
        last = len(rows) + 1
        for column, alias in NAMES.get(name, {}).items():
            idx = header.index(column) + 1
            letter = get_column_letter(idx)
            ref = (f"{quote_sheetname(name)}!"
                   f"{absolute_coordinate(f'{letter}2')}:{absolute_coordinate(f'{letter}{last}')}")
            wb.defined_names.add(DefinedName(alias, attr_text=ref))


def _named_range(wb, alias, sheet, letter, first, last):
    ref = (f"{quote_sheetname(sheet)}!{absolute_coordinate(f'{letter}{first}')}:"
           f"{absolute_coordinate(f'{letter}{last}')}")
    wb.defined_names.add(DefinedName(alias, attr_text=ref))


def _chart_sheet(wb, con, meta):
    """
    A small, purpose-built block of chart source values.

    Charts read this rather than the report grids, for one reason: a chart bound to a report
    range moves when the report does, and every layout change becomes a chart repair. Bound to
    a fixed block, the charts are stable and the report is free to change.
    """
    ws = wb.create_sheet("_chart")
    ws.sheet_state = "hidden"
    months = [REPORT_FY * 100 + m for m in range(1, 13)]

    def q(sql):
        return {r[0]: r[1] for r in con.execute(sql).fetchall()}

    rev_act = q(f"""SELECT period_key, round(sum(mtd_usd)/1e6,4) FROM mart_financial_ytd
                    WHERE measure_code='REVENUE' AND basis='STATUTORY'
                      AND version_code='{ACT_VERSION}' AND fiscal_year={REPORT_FY}
                    GROUP BY 1""")
    rev_bud = q(f"""SELECT period_key, round(sum(mtd_usd)/1e6,4) FROM mart_financial_ytd
                    WHERE measure_code='REVENUE' AND basis='STATUTORY'
                      AND version_code='{BUD_VERSION}' GROUP BY 1""")
    adj_act = q(f"""SELECT period_key, round(sum(mtd_usd)/1e6,4) FROM mart_financial_ytd
                    WHERE measure_code='ADJ_EBITDA' AND basis='STATUTORY'
                      AND version_code='{ACT_VERSION}' AND fiscal_year={REPORT_FY}
                    GROUP BY 1""")
    gm = q(f"""SELECT period_key,
                      round(sum(mtd_usd) FILTER (WHERE measure_code='GROSS_PROFIT')
                            / nullif(sum(mtd_usd) FILTER (WHERE measure_code='REVENUE'),0), 5)
               FROM mart_financial_ytd WHERE basis='STATUTORY' AND version_code='{ACT_VERSION}'
                 AND fiscal_year={REPORT_FY} GROUP BY 1""")
    netdebt = q("SELECT period_key, round(net_debt_m,4) FROM (SELECT period_key, "
                "net_debt_usd/1e6 AS net_debt_m FROM mart_covenants)")
    cash = q("SELECT period_key, round(closing_cash_usd/1e6,4) FROM mart_cash_flow")
    liq = q("SELECT period_key, round(liquidity_usd/1e6,4) FROM mart_cash_flow")
    nwc = q("SELECT period_key, round(nwc_usd/1e6,4) FROM mart_working_capital")
    ccc = q("SELECT period_key, ccc_days FROM mart_working_capital")
    lev = q("SELECT period_key, round(net_leverage,4) FROM mart_covenants")
    lim = q("SELECT period_key, round(max_net_leverage,4) FROM mart_covenants")
    econ = q("SELECT period_key, round(economic_leverage,4) FROM mart_covenants")
    fte = q("SELECT period_key, round(sum(fte_closing),1) FROM mart_headcount GROUP BY 1")
    cx = q("SELECT period_key, round(sum(spend_usd)/1e6,4) FROM mart_capex GROUP BY 1")
    dep = q(f"""SELECT period_key, round(sum(mtd_usd)/1e6,4) FROM mart_financial_ytd
                WHERE measure_code='DA' AND basis='STATUTORY' AND version_code='{ACT_VERSION}'
                  AND fiscal_year={REPORT_FY} GROUP BY 1""")
    rates = {c: q(f"SELECT period_key, round(avg_rate,5) FROM mart_fx "
                  f"WHERE currency_code='{c}'") for c in ("EUR", "GBP", "CAD")}
    cta = q("SELECT period_key, round(sum(cta_movement_usd)/1e6,4) FROM mart_fx GROUP BY 1")

    adj_bud = q(f"""SELECT period_key, round(sum(mtd_usd)/1e6,4) FROM mart_financial_ytd
                    WHERE measure_code='ADJ_EBITDA' AND basis='STATUTORY'
                      AND version_code='{BUD_VERSION}' GROUP BY 1""")

    headings = {3: "Revenue actual", 4: "Revenue budget", 5: "Adjusted EBITDA actual",
                6: "Gross margin", 7: "Adjusted EBITDA budget",
                9: "Adjusted EBITDA actual", 10: "Adjusted EBITDA budget",
                12: "Revenue actual", 13: "Revenue budget", 15: "Net debt", 16: "Cash",
                17: "Total liquidity", 20: "USD m", 22: "Net working capital",
                23: "Cash conversion cycle", 26: "USD m", 28: "Net leverage",
                29: "Covenant limit", 30: "Economic leverage", 33: "Drawn USD m",
                35: "Closing FTE", 36: "Closing FTE", 38: "CapEx", 39: "Depreciation",
                41: "EUR", 42: "GBP", 43: "CAD", 44: "CTA movement"}
    for c, text in headings.items():
        ws.cell(row=1, column=c, value=text)

    def na(value, period=None, actual_only=False):
        """
        Excel plots an empty cell as zero and skips `#N/A`.

        `actual_only` stops an actual series after the reporting date. The consolidation
        generates Actual rows for the whole of FY2026 and the group has only closed eight
        months of it, so the remaining months carry a few residual postings and almost no
        trading. Plotted, that is a company falling off a cliff every September. It is not
        a defect in the data -- the workbook reports Actual to the close it would really
        have, and the chart has to say the same thing the tables do.
        """
        if actual_only and period is not None and period > REPORT_PERIOD:
            return "=NA()"
        return value if value is not None else "=NA()"

    for i, p in enumerate(months):
        row = 2 + i
        ws.cell(row=row, column=2, value=meta["period_labels"][p])
        ws.cell(row=row, column=3, value=na(rev_act.get(p), p, actual_only=True))
        ws.cell(row=row, column=4, value=rev_bud.get(p))
        ws.cell(row=row, column=5, value=na(adj_act.get(p), p, actual_only=True))
        ws.cell(row=row, column=6, value=na(gm.get(p), p, actual_only=True))
        ws.cell(row=row, column=7, value=adj_bud.get(p))
        ws.cell(row=row, column=15, value=na(netdebt.get(p), p, actual_only=True))
        ws.cell(row=row, column=16, value=na(cash.get(p), p, actual_only=True))
        ws.cell(row=row, column=17, value=na(liq.get(p), p, actual_only=True))
        ws.cell(row=row, column=22, value=na(nwc.get(p), p, actual_only=True))
        ws.cell(row=row, column=23, value=na(ccc.get(p), p, actual_only=True))
        ws.cell(row=row, column=28, value=na(lev.get(p), p, actual_only=True))
        ws.cell(row=row, column=29, value=na(lim.get(p)))
        ws.cell(row=row, column=30, value=na(econ.get(p), p, actual_only=True))
        ws.cell(row=row, column=35, value=na(fte.get(p), p, actual_only=True))
        ws.cell(row=row, column=38, value=na(cx.get(p), p, actual_only=True))
        ws.cell(row=row, column=39, value=na(dep.get(p), p, actual_only=True))
        for j, c in enumerate(("EUR", "GBP", "CAD")):
            ws.cell(row=row, column=41 + j, value=na(rates[c].get(p), p, actual_only=True))
        ws.cell(row=row, column=44, value=na(cta.get(p), p, actual_only=True))

    bu_adj = con.execute(f"""
        SELECT bu_code, bu_name,
               round(sum(ytd_usd) FILTER (WHERE version_code='{ACT_VERSION}')/1e6, 4),
               round(sum(ytd_usd) FILTER (WHERE version_code='{BUD_VERSION}')/1e6, 4)
        FROM mart_business_unit
        WHERE measure_code='ADJ_EBITDA' AND basis='STATUTORY' AND period_key={REPORT_PERIOD}
        GROUP BY 1,2 ORDER BY bu_code""").fetchall()
    bu_rev = con.execute(f"""
        SELECT bu_code,
               round(sum(ytd_usd) FILTER (WHERE version_code='{ACT_VERSION}')/1e6, 4),
               round(sum(ytd_usd) FILTER (WHERE version_code='{BUD_VERSION}')/1e6, 4)
        FROM mart_business_unit
        WHERE measure_code='REVENUE' AND basis='STATUTORY' AND period_key={REPORT_PERIOD}
        GROUP BY 1 ORDER BY bu_code""").fetchall()
    bu_fte = {r[0]: r[1] for r in con.execute(
        f"""SELECT bu_code, round(sum(fte_closing),1) FROM mart_headcount
            WHERE period_key={REPORT_PERIOD} GROUP BY 1""").fetchall()}
    for i, (bu, bu_name, act, bud) in enumerate(bu_adj):
        row = 2 + i
        ws.cell(row=row, column=8, value=bu_name)
        ws.cell(row=row, column=9, value=act)
        ws.cell(row=row, column=10, value=bud)
        ws.cell(row=row, column=12, value=bu_rev[i][1])
        ws.cell(row=row, column=13, value=bu_rev[i][2])
        ws.cell(row=row, column=36, value=bu_fte.get(bu))

    cf_cats = con.execute(f"""
        SELECT 'Operating', round(sum(operating_cash_flow_usd)/1e6,4) FROM mart_cash_flow
        WHERE period_key <= {REPORT_PERIOD} AND fiscal_year={REPORT_FY}
        UNION ALL SELECT 'Investing', round(sum(investing_cash_flow_usd)/1e6,4)
        FROM mart_cash_flow WHERE period_key <= {REPORT_PERIOD} AND fiscal_year={REPORT_FY}
        UNION ALL SELECT 'Financing', round(sum(financing_cash_flow_usd)/1e6,4)
        FROM mart_cash_flow WHERE period_key <= {REPORT_PERIOD} AND fiscal_year={REPORT_FY}
        UNION ALL SELECT 'FX on cash', round(sum(fx_effect_on_cash_usd)/1e6,4)
        FROM mart_cash_flow WHERE period_key <= {REPORT_PERIOD} AND fiscal_year={REPORT_FY}
    """).fetchall()
    for i, (label, value) in enumerate(cf_cats):
        ws.cell(row=2 + i, column=19, value=label)
        ws.cell(row=2 + i, column=20, value=value)

    eb = con.execute(f"""SELECT statutory_ebitda_usd/1e6, approved_addbacks_usd/1e6,
                                management_layer4_effect_usd/1e6, adjusted_ebitda_usd/1e6
                         FROM rpt_ebitda_bridge WHERE fiscal_year={REPORT_FY}""").fetchone()
    for i, (label, value) in enumerate(zip(
            ("Statutory EBITDA", "Add-backs", "Layer 4", "Adjusted EBITDA"), eb)):
        ws.cell(row=2 + i, column=25, value=label)
        ws.cell(row=2 + i, column=26, value=round(float(value), 4))

    debt_rows = con.execute(f"""
        SELECT instrument_type, round(sum(closing_principal_usd)/1e6, 4)
        FROM mart_debt WHERE period_key={REPORT_PERIOD} GROUP BY 1 ORDER BY 2 DESC""").fetchall()
    for i, (label, value) in enumerate(debt_rows[:4]):
        ws.cell(row=2 + i, column=32, value=label.replace("_", " ").title())
        ws.cell(row=2 + i, column=33, value=value)

    # ---- the P&L page's own two charts, in free columns beyond the FX block
    ebitda_margin = q(f"""
        SELECT period_key,
               round(sum(mtd_usd) FILTER (WHERE measure_code='EBITDA')
                     / nullif(sum(mtd_usd) FILTER (WHERE measure_code='REVENUE'), 0), 6)
        FROM mart_financial_ytd
        WHERE basis='STATUTORY' AND version_code='{ACT_VERSION}' AND fiscal_year={REPORT_FY}
          AND period_key <= {REPORT_PERIOD}
        GROUP BY 1""")
    ws.cell(row=1, column=46, value="EBITDA margin")
    for i, period in enumerate(months):
        ws.cell(row=2 + i, column=46, value=ebitda_margin.get(period))

    # Year-to-date variance against budget, by statement line. The bridge a reader wants when
    # the tables above tell them the group is 5.6 behind: behind on what.
    var_lines = con.execute(f"""
        SELECT measure_name, round(sum(var_ytd_usd)/1e6, 4)
        FROM mart_variance
        WHERE comparison_code='ACT_VS_BUD' AND basis='STATUTORY'
          AND period_key={REPORT_PERIOD}
          AND measure_code IN ('REVENUE','COST_OF_SALES','OPEX','EBITDA','DA','EBIT')
        GROUP BY 1, measure_sort ORDER BY measure_sort""").fetchall()
    ws.cell(row=1, column=48, value="Line")
    ws.cell(row=1, column=49, value="Variance")
    for i, (label, value) in enumerate(var_lines):
        ws.cell(row=2 + i, column=48, value=label)
        ws.cell(row=2 + i, column=49, value=value)
    return ws


def _meta(con, tables):
    """Everything the sheets need that is not a formula: labels, row plans, KPI values."""
    periods = {r[0]: r[3] for r in tables["_period"][1]}
    period_long = {r[0]: r[4] for r in tables["_period"][1]}

    def scalar(sql, default=0.0):
        row = con.execute(sql).fetchone()
        return float(row[0]) if row and row[0] is not None else default

    ytd = (lambda m, v: scalar(
        f"""SELECT sum(ytd_usd)/1e6 FROM mart_financial_ytd WHERE measure_code='{m}'
            AND basis='STATUTORY' AND version_code='{v}' AND period_key={REPORT_PERIOD}"""))
    fy = (lambda m, v: scalar(
        f"""SELECT sum(fy_usd)/1e6 FROM mart_financial_ytd WHERE measure_code='{m}'
            AND basis='STATUTORY' AND version_code='{v}' AND period_key={REPORT_FY}12"""))

    rev_a, rev_b = ytd("REVENUE", ACT_VERSION), ytd("REVENUE", BUD_VERSION)
    gp_a, gp_b = ytd("GROSS_PROFIT", ACT_VERSION), ytd("GROSS_PROFIT", BUD_VERSION)
    eb_a, eb_b = ytd("EBITDA", ACT_VERSION), ytd("EBITDA", BUD_VERSION)
    adj_a, adj_b = ytd("ADJ_EBITDA", ACT_VERSION), ytd("ADJ_EBITDA", BUD_VERSION)
    ocf = scalar(f"""SELECT sum(operating_cash_flow_usd)/1e6 FROM mart_cash_flow
                     WHERE fiscal_year={REPORT_FY} AND period_key<={REPORT_PERIOD}""")
    cov = con.execute(f"""SELECT net_debt_usd/1e6, net_leverage, headroom_turns,
                                 max_net_leverage FROM mart_covenants
                          WHERE period_key={REPORT_PERIOD}""").fetchone()
    fte_now = scalar(f"SELECT sum(fte_closing) FROM mart_headcount "
                     f"WHERE period_key={REPORT_PERIOD}")
    fte_py = scalar(f"SELECT sum(fte_closing) FROM mart_headcount "
                    f"WHERE period_key={REPORT_PERIOD - 100}")

    def money(value: float, decimals: int = 1) -> str:
        """
        A negative in brackets, the way the rest of the workbook writes one.

        The KPI comparators used a leading minus while every table on every sheet used
        parentheses, so the flagship page disagreed with the pack behind it about how to
        write a negative number. One convention, chosen to match the tables because there
        are far more of them.
        """
        return (f"({abs(value):,.{decimals}f})" if value < 0
                else f"{value:,.{decimals}f}")

    def delta(actual, budget, higher_is_good=True):
        d = actual - budget
        fav = "NEUTRAL" if abs(d) < 1e-9 else (
            "FAVOURABLE" if (d > 0) == higher_is_good else "UNFAVOURABLE")
        # The brackets ARE the minus sign, so the percentage carries its own pair and is not
        # then wrapped in another: "(2.0%)", never "((2.0)%)".
        ratio = d / abs(budget) * 100 if budget else 0
        pct = (f" ({abs(ratio):,.1f}%)" if ratio < 0 else f" ({ratio:,.1f}%)") if budget else ""
        return f"{money(d)} vs budget{pct}", fav

    kpi = {}
    kpi["REVENUE"] = dict(zip(("delta", "fav"), delta(rev_a, rev_b)))
    kpi["REVENUE"]["value"] = round(rev_a, 4)
    kpi["GROSS_MARGIN"] = {"value": round(gp_a / rev_a, 6) if rev_a else 0}
    d, f = delta(gp_a / rev_a if rev_a else 0, gp_b / rev_b if rev_b else 0)
    kpi["GROSS_MARGIN"].update(
        {"delta": f"{money((gp_a/rev_a - gp_b/rev_b)*100)} pp vs budget"
         if rev_a and rev_b else "", "fav": f})
    kpi["EBITDA"] = dict(zip(("delta", "fav"), delta(eb_a, eb_b)))
    kpi["EBITDA"]["value"] = round(eb_a, 4)
    kpi["ADJ_EBITDA"] = dict(zip(("delta", "fav"), delta(adj_a, adj_b)))
    kpi["ADJ_EBITDA"]["value"] = round(adj_a, 4)
    kpi["EBITDA_MARGIN"] = {"value": round(eb_a / rev_a, 6) if rev_a else 0,
                            "delta": f"{(eb_a/rev_a - eb_b/rev_b)*100:+.1f} pp vs budget"
                                     if rev_a and rev_b else "",
                            "fav": "FAVOURABLE" if rev_a and rev_b and
                                   eb_a / rev_a >= eb_b / rev_b else "UNFAVOURABLE"}
    kpi["OCF"] = {"value": round(ocf, 4), "delta": "year to date", "fav": "NEUTRAL"}
    kpi["NET_DEBT"] = {"value": round(float(cov[0]), 4),
                       "delta": f"{float(cov[0]) / adj_a:.1f}x YTD adjusted EBITDA"
                                if adj_a else "", "fav": "NEUTRAL"}
    kpi["LEVERAGE"] = {"value": round(float(cov[1]), 4),
                       "delta": f"limit {float(cov[3]):.2f}x",
                       "fav": "FAVOURABLE" if float(cov[2]) >= 0 else "UNFAVOURABLE"}
    kpi["HEADROOM"] = {"value": round(float(cov[2]), 4),
                       "delta": "turns against the covenant",
                       "fav": "FAVOURABLE" if float(cov[2]) >= 1 else "UNFAVOURABLE"}
    kpi["FTE"] = {"value": round(fte_now, 0),
                  "delta": f"{fte_now - fte_py:+,.0f} vs prior year", "fav": "NEUTRAL"}

    measures = con.execute("""SELECT measure_code, measure_name, indent_level, is_subtotal,
                                     sort_order FROM dim_report_measure ORDER BY sort_order"""
                           ).fetchall()
    pl_rows = [(c, n, lv, bool(sub), c == "NI_PARENT") for c, n, lv, sub, _ in measures]
    summary_rows = [(c, n, bool(sub)) for c, n, lv, sub, _ in measures
                    if c in ("REVENUE", "GROSS_PROFIT", "EBITDA", "ADJ_EBITDA", "EBIT",
                             "NI_PARENT")]

    bus = con.execute("""SELECT bu_code, bu_name FROM dim_business_unit
                         ORDER BY sort_order""").fetchall()
    entities = con.execute("""SELECT entity_code, entity_name, bu_code, functional_currency,
                                     erp_system FROM dim_entity
                              WHERE entity_type <> 'ELIMINATION' ORDER BY entity_code"""
                           ).fetchall()

    # ---------------- balance sheet row plan
    bs_rows: list[tuple[str, str, str]] = []
    plan = [("Non-current assets", "ASSET", ("Property, plant and equipment, net",
                                             "Operating lease right-of-use assets", "Goodwill",
                                             "Intangible assets, net",
                                             "Investments in subsidiaries",
                                             "Other non-current assets")),
            ("Current assets", "ASSET", ("Cash and cash equivalents",
                                         "Accounts receivable, net", "Intercompany balances",
                                         "Contract assets", "Inventory, net",
                                         "Prepaid and other current assets")),
            ("Current liabilities", "LIABILITY", ("Accounts payable", "Intercompany balances",
                                                  "Contract liabilities",
                                                  "Accrued liabilities", "Income taxes payable",
                                                  "Current portion of debt")),
            ("Non-current liabilities", "LIABILITY", ("Long-term debt",
                                                      "Operating lease liabilities",
                                                      "Deferred tax liabilities",
                                                      "Other long-term liabilities")),
            ("Equity", "EQUITY", ("Contributed capital", "Retained earnings",
                                  "Result for the period",
                                  "Cumulative translation adjustment",
                                  "Non-controlling interests"))]
    for header, cls, captions in plan:
        bs_rows.append((header, cls, "SECTION"))
        for cap in captions:
            bs_rows.append((cap, cls, "LINE"))
        bs_rows.append((f"Total {header.lower()}", cls, "SUBTOTAL"))
        if header == "Current assets":
            bs_rows.append(("Total assets", cls, "GRANDTOTAL"))
        if header == "Equity":
            bs_rows.append(("Total liabilities and equity", cls, "GRANDTOTAL"))

    bs_grand = {
        "Total assets": ["Total non-current assets", "Total current assets"],
        "Total liabilities and equity": ["Total current liabilities",
                                         "Total non-current liabilities", "Total equity"],
    }

    # Row numbers, walked exactly as the sheet builder walks the plan. Getting this wrong is
    # how the "% of total assets" column once divided by current assets and the balance check
    # compared current assets with equity -- both of which look plausible and are not.
    row = 8
    row_of: dict[str, int] = {}
    for caption, cls, kind in bs_rows:
        if kind in ("SUBTOTAL", "GRANDTOTAL"):
            row_of[caption] = row
        row += 1
    total_assets_row = row_of["Total assets"]
    total_le_row = row_of["Total liabilities and equity"]

    cf_rows = [("opening_m", "Opening cash", False),
               ("result_m", "Result for the period", False),
               ("noncash_m", "Non-cash and other items", False),
               ("wc_m", "Working capital movement", False),
               ("fxnoncash_m", "Foreign exchange on non-cash balances", False),
               ("closetx_m", "Translation on the year-end close", False),
               ("ocf_m", "Operating cash flow", True),
               ("icf_m", "Investing cash flow", True),
               ("fcf_m", "Financing cash flow", True),
               ("fxcash_m", "Effect of exchange rates on cash", False),
               ("net_m", "Net change in cash", True),
               ("closing_m", "Closing cash", True)]

    fy_list = [r[0] for r in con.execute(
        "SELECT DISTINCT fiscal_year FROM rpt_ebitda_bridge ORDER BY 1").fetchall()]
    addback_accounts = con.execute("""SELECT DISTINCT group_account, account_name
                                      FROM dim_account WHERE is_ebitda_addback
                                      ORDER BY group_account""").fetchall()
    # The agreement's rate wording runs to fifty characters and does not fit a column. The
    # full text stays on the mart; the sheet shows the pricing and the Hedged column already
    # says which instrument is swapped, because a truncated column tells a reader less than a
    # shorter one that is not.
    # Capital structure, largest first, with the twelve finance leases on one line.
    #
    # Listing them individually gave twelve near-identical rows -- same rate, same maturity,
    # same everything but the entity -- above the two instruments that are 96% of the debt.
    # A reader's eye went to the noise. The leases are one economic exposure and are presented
    # as one, with the count so nothing is hidden; the mart still holds every instrument and
    # the total still sums from the rows on the page.
    rows = con.execute(f"""
        SELECT instrument_id, instrument_name, instrument_type, currency_code,
               CASE WHEN interest_rate_basis LIKE '%SOFR%' THEN 'SOFR + 425bps'
                    ELSE interest_rate_basis END AS rate,
               rate_type, is_hedged,
               strftime(CAST(maturity_date AS DATE), '%b %Y') AS maturity,
               counts_toward_covenant_debt, closing_principal_usd
        FROM mart_debt WHERE period_key = {REPORT_PERIOD}
        ORDER BY instrument_type, instrument_id""").fetchall()

    leases = [r for r in rows if r[2] == "FINANCE_LEASE"]
    others = [r for r in rows if r[2] != "FINANCE_LEASE"]
    # ("id" | "type", criterion, name, type label, ccy, rate, rate type, hedged, maturity,
    #  in covenant)
    instruments = [("id", r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8])
                   for r in sorted(others, key=lambda r: -(r[9] or 0))]
    if leases:
        lead = leases[0]
        instruments.append(
            ("type", "FINANCE_LEASE",
             f"Finance leases ({len(leases)} instruments)", "FINANCE_LEASE",
             "Various" if len({r[3] for r in leases}) > 1 else lead[3],
             lead[4], lead[5], lead[6], lead[7], lead[8]))
    # The credit agreement sets a maximum leverage per FISCAL YEAR (CA-009 to CA-012), so the
    # test dates are the fiscal year ends and nothing else. An earlier draft presented
    # quarterly columns and stamped BREACH on September 2024 and March 2025 -- dates the
    # agreement never tests, at levels that step down at the year boundary. Telling a board it
    # breached a covenant it did not breach is the most expensive mistake this pack could
    # make, so the grid shows the real test dates and the current month is labelled
    # indicative.
    cov_periods = [r[0] for r in con.execute(
        f"""SELECT period_key FROM mart_covenants
            WHERE period_key % 100 = 12 AND period_key <= {REPORT_PERIOD}
            ORDER BY period_key""").fetchall()]
    cov_indicative = con.execute(
        f"SELECT max(period_key) FROM mart_covenants WHERE period_key <= {REPORT_PERIOD}"
    ).fetchone()[0]
    if cov_indicative not in cov_periods:
        cov_periods = cov_periods + [cov_indicative]
    # The dimension stores function groups in upper case; a report is not a database dump
    functions = [{"code": r[0], "name": r[0].replace("_", " ").title()} for r in con.execute(
        """SELECT DISTINCT function_group FROM mart_headcount
           WHERE function_group IS NOT NULL ORDER BY 1""").fetchall()]
    asset_classes = [r[0] for r in con.execute(
        "SELECT DISTINCT asset_class FROM mart_capex ORDER BY 1").fetchall()]
    # Eight projects named "Machinery and equipment programme" is a list, not information.
    # The entity distinguishes them, and one project per business unit says more about where
    # the capital went than the eight largest all belonging to one unit.
    top_projects = con.execute(f"""
        SELECT project_id, project_name || ' — ' || entity_code, bu_name, asset_class,
               round(sum(approved_usd)/1e6, 4), round(sum(spend_usd)/1e6, 4)
        FROM mart_capex WHERE period_key <= {REPORT_PERIOD}
        GROUP BY 1, 2, 3, 4
        QUALIFY row_number() OVER (PARTITION BY bu_name
                                   ORDER BY sum(spend_usd) DESC) <= 2
        ORDER BY 6 DESC LIMIT 10""").fetchall()
    currencies = [r[0] for r in con.execute(
        "SELECT DISTINCT currency_code FROM mart_fx ORDER BY 1").fetchall()]
    cta_currencies = [r[0] for r in con.execute(
        "SELECT DISTINCT currency_code FROM mart_fx WHERE abs(cta_movement_usd) > 0 ORDER BY 1"
    ).fetchall()]
    layers = con.execute("""SELECT DISTINCT layer_id, layer_code, layer_name,
                                   in_statutory_view, in_management_view
                            FROM mart_consolidation_bridge ORDER BY layer_id""").fetchall()
    consol_items = tables["_consol"][1]

    control_summary = con.execute("""
        SELECT phase, count(*), count(*) FILTER (WHERE status = 'PASS')
        FROM (SELECT 'Phase 2 — generated source' AS phase, status
              FROM read_csv('data/phase02_control_results.csv', header=true, all_varchar=true)
              UNION ALL SELECT 'Phase 3 — ingestion and mapping', status
              FROM read_csv('data/phase03_control_results.csv', header=true, all_varchar=true)
              UNION ALL SELECT 'Phase 4 — consolidation', status
              FROM read_csv('data/phase04_control_results.csv', header=true, all_varchar=true)
              UNION ALL SELECT 'Phase 5 — reporting marts', status
              FROM read_csv('data/phase05_control_results.csv', header=true, all_varchar=true)
              -- The control environment did not stop at Phase 5. The key, grain and version
              -- framework and the Power BI semantic suite are governed control registers like
              -- any other, and a page that claims to show "every phase, every control" while
              -- omitting them is understating the platform it is describing.
              UNION ALL SELECT 'Phase 5.1 — keys, grain and versions', status
              FROM read_csv('data/phase07_key_control_results.csv', header=true,
                            all_varchar=true)
              UNION ALL SELECT 'Phase 6A — Power BI semantic model', status
              FROM read_csv('data/phase06a_control_results.csv', header=true,
                            all_varchar=true))
        GROUP BY 1 ORDER BY 1""").fetchall()

    # ---------------- deterministic attention list
    attention = []
    worst = con.execute(f"""
        SELECT measure_name, round(sum(var_ytd_usd)/1e6, 3) AS v
        FROM mart_variance
        WHERE comparison_code = 'ACT_VS_BUD' AND basis = 'STATUTORY'
          AND period_key = {REPORT_PERIOD} AND ytd_favourability = 'UNFAVOURABLE'
          AND measure_code IN ('REVENUE', 'GROSS_PROFIT', 'EBITDA', 'ADJ_EBITDA', 'EBIT')
        GROUP BY 1 ORDER BY abs(v) DESC LIMIT 3""").fetchall()
    # The three largest shortfalls, ranked. The comment used to be the same sentence three
    # times over, which reads as generated text and tells a reader nothing they cannot see
    # from the ordering; each line now says where it sits and how big the gap is.
    ordinal = ("Largest", "Second largest", "Third largest")
    for rank, (name, value) in enumerate(worst):
        pct = ""
        attention.append((
            f"{name} below budget", "YTD variance", round(float(value), 3),
            f"{ordinal[rank] if rank < len(ordinal) else 'Further'} unfavourable variance "
            f"against budget year to date — {abs(float(value)):,.1f}m behind plan.{pct}"))
    bu_worst = con.execute(f"""
        SELECT b.bu_name, round((sum(a.ytd_usd) - sum(bud.ytd_usd))/1e6, 3) AS v
        FROM mart_business_unit a
        JOIN mart_business_unit bud
          ON bud.bu_code = a.bu_code AND bud.period_key = a.period_key
         AND bud.measure_code = a.measure_code AND bud.basis = a.basis
         AND bud.version_code = '{BUD_VERSION}'
        JOIN dim_business_unit b ON b.bu_code = a.bu_code
        WHERE a.version_code = '{ACT_VERSION}' AND a.basis = 'STATUTORY'
          AND a.measure_code = 'ADJ_EBITDA' AND a.period_key = {REPORT_PERIOD}
        GROUP BY 1 ORDER BY v LIMIT 1""").fetchall()
    for name, value in bu_worst:
        attention.append((f"{name}", "Adjusted EBITDA vs budget", round(float(value), 3),
                          "Business unit with the largest adjusted EBITDA shortfall against "
                          "budget, year to date."))
    if float(cov[2]) < 1.0:
        attention.append(("Covenant headroom below one turn", "Headroom",
                          round(float(cov[2]), 2),
                          "Net leverage is within one turn of the covenant limit."))
    else:
        attention.append(("Covenant headroom", "Turns", round(float(cov[2]), 2),
                          f"Net leverage {float(cov[1]):.2f}x against a "
                          f"{float(cov[3]):.2f}x limit. No action required."))

    account_detail = con.execute(f"""
        WITH act AS (
            SELECT m.group_account, l.account_name, e.entity_name, min(l.line) AS line,
                   round(sum(m.amount_usd
                             * CASE WHEN l.line = 'REVENUE' THEN -1 ELSE 1 END) / 1e6, 4) AS v
            FROM mart_financial_monthly m JOIN ref_report_line l USING (group_account)
            JOIN dim_entity e USING (entity_code)
            WHERE m.basis='STATUTORY' AND NOT m.is_intercompany
              AND m.version_code='{ACT_VERSION}' AND m.fiscal_year={REPORT_FY}
              AND m.period_key <= {REPORT_PERIOD}
            GROUP BY ALL
        ),
        bud AS (
            SELECT m.group_account, e.entity_name,
                   round(sum(m.amount_usd
                             * CASE WHEN l.line = 'REVENUE' THEN -1 ELSE 1 END) / 1e6, 4) AS v
            FROM mart_financial_monthly m JOIN dim_entity e USING (entity_code)
            JOIN ref_report_line l USING (group_account)
            WHERE m.basis='STATUTORY' AND NOT m.is_intercompany
              AND m.version_code='{BUD_VERSION}' AND m.period_key <= {REPORT_PERIOD}
            GROUP BY ALL
        )
        SELECT a.group_account, a.account_name, a.entity_name,
               a.v, coalesce(b.v, 0), a.line
        FROM act a LEFT JOIN bud b
          ON b.group_account = a.group_account AND b.entity_name = a.entity_name
        ORDER BY abs(a.v - coalesce(b.v, 0)) DESC LIMIT 12""").fetchall()

    scen = {r[0]: r for r in con.execute(
        "SELECT version_code, version_name, actual_months, forecast_months, approved_date "
        "FROM dim_report_scenario").fetchall()}
    consol_manifest = json.loads((DATA / "phase04_manifest.json").read_text(encoding="utf-8"))
    mart_manifest = json.loads((DATA / "phase05_manifest.json").read_text(encoding="utf-8"))

    navigation = [
        ("01 Executive Summary", "Group performance, key indicators and what needs attention"),
        ("02 P&L", "Management income statement, monthly and year to date"),
        ("03 Business Units", "Which business unit explains group performance"),
        ("04 Entities", "Legal entity contribution, currency and ERP context"),
        ("05 Balance Sheet", "Financial position with prior month and prior year movement"),
        ("06 Cash Flow", "Cash flow by category and the liquidity position"),
        ("07 Working Capital", "Receivables, inventory, payables and the conversion cycle"),
        ("08 EBITDA Bridge", "Statutory to management adjusted, and to covenant"),
        ("09 Debt & Covenants", "Debt by instrument, net leverage and covenant headroom"),
        ("10 Headcount", "Headcount movement, by business unit and function"),
        ("11 CapEx", "Capital expenditure by unit, asset class and project"),
        ("12 FX", "Currency exposure, constant currency and the translation adjustment"),
        ("13 Consolidation & Controls", "What the consolidation does, and the control evidence"),
        ("14 Variance Detail", "Selectable variance analysis down to account level"),
        ("15 Data & Technical", "Lineage, marts consumed and build identifiers"),
    ]

    return {
        "report_label": period_long[REPORT_PERIOD],
        "period_labels": periods,
        "kpi": kpi,
        "pl_rows": pl_rows,
        "summary_rows": summary_rows,
        "bus": bus,
        "entities": entities,
        "bs_rows": bs_rows,
        "bs_grand": bs_grand,
        "bs_total_assets_row": total_assets_row,
        "bs_total_le_row": total_le_row,
        "cf_rows": cf_rows,
        "cf_check_formula": "={c}8+{c}14+{c}15+{c}16+{c}17-{c}19",
        "min_cash_policy": 10.0,
        "fy_list": fy_list,
        "addback_accounts": addback_accounts,
        "ebitda_policy": [
            ("Restructuring, transaction, integration, legal, retention",
             "Added back", "Added back (CA-021 to CA-025)"),
            ("Sponsor monitoring fee", "Added back in full",
             "Added back, capped at USD 1.5m a year (CA-027)"),
            ("Unrealised foreign exchange", "Not an add-back", "Added back (CA-030)"),
            ("Share-based compensation", "Not an add-back", "Not permitted (CA-029)"),
            ("Run-rate synergies", "Not claimed", "Not permitted (CA-028)"),
            ("Management adjustments (layer 4)", "Included", "Not recognised"),
        ],
        "instruments": instruments,
        "cov_periods": cov_periods,
        "cov_indicative": cov_indicative,
        "functions": functions,
        "asset_classes": asset_classes,
        "top_projects": top_projects,
        "currencies": currencies,
        "cta_currencies": cta_currencies,
        "layers": layers,
        "consol_items": consol_items,
        "control_summary": control_summary,
        "attention": attention,
        "account_detail": account_detail,
        "default_comparison": "Actual vs Budget",
        "comparison_names": [r[0] for r in con.execute(
            "SELECT comparison_name FROM dim_report_comparison ORDER BY sort_order").fetchall()],
        "bud_name": scen[BUD_VERSION][1],
        "bud_approved": str(scen[BUD_VERSION][4]),
        "fc_name": scen[FC_VERSION][1],
        "fc_actual_months": scen[FC_VERSION][2],
        "fc_forecast_months": scen[FC_VERSION][3],
        "source_digest": consol_manifest["source_layer_digest"],
        "consol_build": consol_manifest["build_id"],
        "mart_build": mart_manifest["build_id"],
        "navigation": navigation,
        "workbook_checks": [],
        "build_meta": [
            ("Source layer digest", consol_manifest["source_layer_digest"]),
            ("Consolidation build id", consol_manifest["build_id"]),
            ("Reporting mart build id", mart_manifest["build_id"]),
            ("Reporting date", period_long[REPORT_PERIOD]),
            ("Reporting basis", "Statutory (layers 1+2+3+5)"),
            ("Presentation currency", "USD, millions"),
        ],
        "lineage": [
            ("1  Report figure", "A SUMIFS into a hidden governed data sheet on this workbook"),
            ("2  Reporting mart", "mart_financial_ytd, mart_balance_sheet, mart_cash_flow "
                                  "and the operational marts"),
            ("3  Consolidated fact", "fact_financials — entity × account × cost centre × "
                                     "partner × period × scenario × version × layer"),
            ("4  Consolidation entry", "fact_consol_journal — process, rule_id, narrative and "
                                       "the register row that required it"),
            ("5  Conformed journal line", "fact_journal_line, keyed by line_uid"),
            ("6  Source extract", "erp_system, source_file, journal_id, line_number"),
        ],
        "marts": [(name, count, grain) for name, count, grain in (
            ("mart_financial_monthly", mart_manifest["row_counts"]["mart_financial_monthly"],
             "basis × scenario × entity × BU × cost centre × account × month"),
            ("mart_financial_ytd", mart_manifest["row_counts"]["mart_financial_ytd"],
             "basis × scenario × entity × BU × measure × month"),
            ("mart_variance", mart_manifest["row_counts"]["mart_variance"],
             "comparison × basis × entity × BU × measure × month"),
            ("mart_business_unit", mart_manifest["row_counts"]["mart_business_unit"],
             "basis × scenario × BU × measure × month"),
            ("mart_entity_performance", mart_manifest["row_counts"]["mart_entity_performance"],
             "basis × scenario × entity × measure × month"),
            ("mart_balance_sheet", mart_manifest["row_counts"]["mart_balance_sheet"],
             "caption × account class × month"),
            ("mart_cash_flow", mart_manifest["row_counts"]["mart_cash_flow"], "month"),
            ("mart_working_capital", mart_manifest["row_counts"]["mart_working_capital"],
             "month"),
            ("mart_headcount", mart_manifest["row_counts"]["mart_headcount"],
             "entity × department × month"),
            ("mart_capex", mart_manifest["row_counts"]["mart_capex"], "project × month"),
            ("mart_debt", mart_manifest["row_counts"]["mart_debt"], "instrument × month"),
            ("mart_covenants", mart_manifest["row_counts"]["mart_covenants"], "month"),
            ("mart_fx", mart_manifest["row_counts"]["mart_fx"], "currency × month"),
        )],
        "refresh": [
            ("1  Rebuild the marts", "python -m src.marts.run"),
            ("2  Rebuild the workbook", "python -m src.excel.build"),
            ("3  Verify", "python -m src.excel.qa  — formulas, errors, layout and reconciliation"),
            ("Determinism", "The same marts produce the same workbook. Build identifiers are "
                            "digests of the inputs, not of the run."),
        ],
    }


def build(destination: Path | None = None) -> Path:
    """Build the workbook. `destination` lets a test rebuild without
    overwriting the calculated file a reader would open."""
    out = destination or WORKBOOK
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    tables = collect(con)
    meta = _meta(con, tables)

    wb = Workbook()
    wb.remove(wb.active)
    S.register(wb)

    _write_data(wb, tables)
    _chart_sheet(wb, con, meta)

    # business unit lookup lists for the variance sheet's dropdowns
    lookup = wb.create_sheet("_lookup")
    lookup.sheet_state = "hidden"
    lookup.append(["bu_code", "bu_name", "cmp_code", "cmp_name"])
    comparisons = con.execute(
        "SELECT comparison_code, comparison_name FROM dim_report_comparison ORDER BY sort_order"
    ).fetchall()
    for i in range(max(len(meta["bus"]), len(comparisons))):
        row = ["", "", "", ""]
        if i < len(meta["bus"]):
            row[0], row[1] = meta["bus"][i]
        if i < len(comparisons):
            row[2], row[3] = comparisons[i]
        lookup.append(row)
    n = lookup.max_row
    _named_range(wb, "bu_list_code", "_lookup", "A", 2, n)
    _named_range(wb, "bu_list_name", "_lookup", "B", 2, n)
    _named_range(wb, "cmp_code", "_lookup", "C", 2, n)
    _named_range(wb, "cmp_name", "_lookup", "D", 2, n)

    # the workbook's own reconciliation checks, read from the governed control results
    meta["workbook_checks"] = _checks(con)

    sheets.cover(wb, meta)
    sheets.executive(wb, meta)
    sheets.profit_and_loss(wb, meta)
    sheets2.business_units(wb, meta)
    sheets2.entities(wb, meta)
    sheets2.balance_sheet(wb, meta)
    sheets2.cash_flow(wb, meta)
    sheets2.working_capital(wb, meta)
    sheets2.ebitda_bridge(wb, meta)
    sheets2.debt_covenants(wb, meta)
    sheets3.headcount(wb, meta)
    sheets3.capex(wb, meta)
    sheets3.fx(wb, meta)
    sheets3.consolidation(wb, meta)
    sheets3.variance_detail(wb, meta)
    sheets3.technical(wb, meta)

    # report sheets first, data sheets after, and the cover selected on open
    order = [ws.title for ws in wb.worksheets if not ws.title.startswith("_")]
    order += [ws.title for ws in wb.worksheets if ws.title.startswith("_")]
    wb._sheets = [wb[t] for t in order]
    wb.active = 0

    # Fixed document properties. openpyxl stamps the created and modified times with the
    # clock, which alone makes two builds of identical data differ.
    wb.properties.created = wb.properties.modified = EPOCH
    wb.properties.lastModifiedBy = "Northstar FP&A Platform"
    wb.properties.title = "Northstar Industrial Group — Management Reporting"
    wb.properties.creator = "Northstar FP&A Platform"
    wb.properties.description = (
        f"Management reporting pack at {meta['report_label']}. Built from the Phase 5 "
        f"governed reporting marts (build {meta['mart_build']}) over consolidation build "
        f"{meta['consol_build']}.")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    _make_reproducible(out)

    # The digest of the workbook AS BUILT, before Excel is asked to calculate it. The QA step
    # opens the file, evaluates every formula and saves the cached values back, which rewrites
    # the archive -- an intended change, and not one Excel makes byte-identically. So the
    # reproducibility claim is made where it can be: the build is a pure function of the marts.
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    if destination is None:
        WORKBOOK_MANIFEST.write_text(json.dumps({
            "phase": 5,
            "workbook": WORKBOOK.name,
            "build_digest": digest,
            "reporting_mart_build_id": meta["mart_build"],
            "consolidation_build_id": meta["consol_build"],
            "source_layer_digest": meta["source_digest"],
            "report_period": REPORT_PERIOD,
            "sheets": [ws.title for ws in wb.worksheets
                       if not ws.title.startswith("_")],
        }, indent=2) + chr(10), encoding="utf-8")

    con.close()
    print(f"workbook written: {out}")
    print(f"  build digest: {digest[:16]}")
    print(f"  {len([t for t in order if not t.startswith('_')])} report sheets, "
          f"{len([t for t in order if t.startswith('_')])} hidden data sheets")
    return out


def _make_reproducible(path: Path) -> None:
    """Rewrite the archive with a fixed timestamp on every member, in a stable order."""
    stamp = EPOCH.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    with zipfile.ZipFile(path) as src:
        members = []
        for info in src.infolist():
            payload = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                # openpyxl rewrites dcterms:modified at save time whatever the property was
                # set to, so the one member that records a clock is normalised here.
                payload = re.sub(
                    rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*(</dcterms:(?:created|modified)>)",
                    rb"\g<1>" + stamp + rb"\g<2>", payload)
            members.append((info, payload))
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
        for info, payload in members:
            fixed = zipfile.ZipInfo(info.filename, date_time=EPOCH.timetuple()[:6])
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.external_attr = info.external_attr
            out.writestr(fixed, payload)
    shutil.move(tmp, path)


def _checks(con):
    """The reconciliations the workbook puts in front of the reader, from governed results."""
    def one(sql):
        row = con.execute(sql).fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0

    bs = one("SELECT max(abs(t)) FROM (SELECT period_key, sum(balance_usd) AS t "
             "FROM mart_balance_sheet GROUP BY 1)")
    cf = one("""SELECT max(abs(opening_cash_usd + operating_cash_flow_usd
                              + investing_cash_flow_usd + financing_cash_flow_usd
                              + fx_effect_on_cash_usd - closing_cash_usd))
                FROM mart_cash_flow""")
    cash = one("""SELECT max(abs(c.closing_cash_usd - b.balance_usd)) FROM mart_cash_flow c
                  JOIN mart_balance_sheet b ON b.period_key = c.period_key
                   AND b.caption = 'Cash and cash equivalents'""")
    cta = one("SELECT count(*) FROM mart_covenants WHERE covenant_ebitda_usd IS NULL")
    scen = one("SELECT count(*) FROM dim_report_scenario WHERE scenario_code = 'DS'")
    return [
        ("Balance sheet balances, every period", f"{bs:,.2f} USD", "0.01 USD", bs <= 0.01),
        ("Cash flow ties, every period", f"{cf:,.2f} USD", "0.01 USD", cf <= 0.01),
        ("Closing cash agrees with the balance sheet", f"{cash:,.2f} USD", "0.01 USD",
         cash <= 0.01),
        ("Covenant EBITDA is never null", f"{cta:,.0f} nulls", "0", cta == 0),
        ("No reserved scenario is offered", f"{scen:,.0f} exposed", "0", scen == 0),
    ]


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
