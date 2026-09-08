"""
The workbook's data layer.

Every figure in the workbook comes from one of the tables below, and every one of those is a
query against the governed marts. Nothing in the workbook queries the consolidation directly
and nothing recomputes an accounting definition — the report sheets contain lookups,
subtotals, variance arithmetic and display logic, and no policy.

The tables are written to hidden sheets and read by `SUMIFS`. That is a deliberate choice over
PivotTables for the presentation-sensitive sheets: a pivot resizes when a filter changes and
takes conditional formatting, merged headers and chart ranges with it. A `SUMIFS` grid is the
same shape whatever the reader selects, which is what makes the executive sheets safe to
export to PDF.
"""

from __future__ import annotations

import duckdb

#: The reporting date. FY2026 has eight actual months; the live forecast `FC_FY26_08` covers
#: the remaining four. The consolidation carries generated Actual rows to December 2026, and
#: the workbook deliberately reports Actual only to the close it would really have.
REPORT_PERIOD = 202608
REPORT_FY = 2026
PRIOR_FY = 2025
FIRST_PERIOD = 202301

ACT_VERSION = "ACTUAL"
BUD_VERSION = "BUD_FY26_V1"
FC_VERSION = "FC_FY26_08"
PY_VERSION = "PY_DERIVED"

#: Measures the business-unit and entity grids carry. Deliberately short: a grid with every
#: measure on it is a data dump, and the question those sheets answer is "which unit explains
#: the group", not "what is every number for every unit".
BU_MEASURES = ("REVENUE", "GROSS_PROFIT", "EBITDA", "ADJ_EBITDA")
ENT_MEASURES = ("REVENUE", "GROSS_PROFIT", "EBITDA", "NET_INCOME")


def _fetch(con, sql):
    cur = con.execute(sql)
    return [c[0] for c in cur.description], cur.fetchall()


def collect(con: duckdb.DuckDBPyConnection) -> dict[str, tuple[list[str], list[tuple]]]:
    """Every hidden data table the workbook needs, keyed by the sheet it lands on."""
    out: dict[str, tuple[list[str], list[tuple]]] = {}

    # -------------------------------------------------- group P&L, every scenario
    out["_pl"] = _fetch(con, f"""
        SELECT measure_code, scenario_code, version_code, period_key, fiscal_year,
               measure_name, indent_level, is_subtotal, measure_sort, favourable_direction,
               round(sum(mtd_usd) / 1e6, 6) AS mtd_m,
               round(sum(ytd_usd) / 1e6, 6) AS ytd_m,
               round(sum(fy_usd) / 1e6, 6) AS fy_m
        FROM mart_financial_ytd
        WHERE basis = 'STATUTORY'
        GROUP BY ALL ORDER BY ALL
    """)

    # -------------------------------------------------- group P&L, management basis
    out["_plmgt"] = _fetch(con, """
        SELECT measure_code, scenario_code, period_key,
               round(sum(ytd_usd) / 1e6, 6) AS ytd_m,
               round(sum(fy_usd) / 1e6, 6) AS fy_m
        FROM mart_financial_ytd WHERE basis = 'MANAGEMENT'
        GROUP BY ALL ORDER BY ALL
    """)

    # -------------------------------------------------- business unit
    measures = ", ".join(f"'{m}'" for m in BU_MEASURES)
    out["_bu"] = _fetch(con, f"""
        SELECT bu_code, bu_name, bu_short_name, bu_sort, measure_code, scenario_code,
               version_code, period_key, fiscal_year,
               round(sum(mtd_usd) / 1e6, 6) AS mtd_m,
               round(sum(ytd_usd) / 1e6, 6) AS ytd_m,
               round(sum(fy_usd) / 1e6, 6) AS fy_m
        FROM mart_business_unit
        WHERE basis = 'STATUTORY' AND measure_code IN ({measures})
        GROUP BY ALL ORDER BY ALL
    """)

    # -------------------------------------------------- entity
    ent_measures = ", ".join(f"'{m}'" for m in ENT_MEASURES)
    out["_ent"] = _fetch(con, f"""
        SELECT e.entity_code, e.entity_name, e.functional_currency, e.erp_system, e.bu_code,
               e.country_code, p.measure_code, p.period_key,
               round(p.ytd_usd / 1e6, 6) AS ytd_m,
               round(coalesce(p.cash_usd, 0) / 1e6, 6) AS cash_m,
               round(coalesce(p.working_capital_usd, 0) / 1e6, 6) AS wc_m,
               coalesce(p.fte_closing, 0) AS fte
        FROM mart_entity_performance p JOIN dim_entity e USING (entity_code)
        WHERE p.basis = 'STATUTORY' AND p.scenario_code = 'ACT'
          AND p.measure_code IN ({ent_measures})
        ORDER BY ALL
    """)

    # -------------------------------------------------- balance sheet
    out["_bs"] = _fetch(con, """
        SELECT caption, account_class, sort_order, period_key,
               round(balance_usd / 1e6, 6) AS bal_m,
               round(coalesce(prior_month_usd, 0) / 1e6, 6) AS prior_month_m,
               round(coalesce(prior_year_usd, 0) / 1e6, 6) AS prior_year_m,
               round(coalesce(mom_movement_usd, 0) / 1e6, 6) AS mom_m,
               round(coalesce(yoy_movement_usd, 0) / 1e6, 6) AS yoy_m
        FROM mart_balance_sheet ORDER BY ALL
    """)

    # -------------------------------------------------- cash flow and liquidity
    out["_cf"] = _fetch(con, """
        SELECT period_key, fiscal_year, accounting_period,
               round(opening_cash_usd / 1e6, 6) AS opening_m,
               round(result_usd / 1e6, 6) AS result_m,
               round(non_cash_and_other_usd / 1e6, 6) AS noncash_m,
               round(working_capital_usd / 1e6, 6) AS wc_m,
               round(fx_non_cash_usd / 1e6, 6) AS fxnoncash_m,
               round(close_translation_usd / 1e6, 6) AS closetx_m,
               round(operating_cash_flow_usd / 1e6, 6) AS ocf_m,
               round(investing_cash_flow_usd / 1e6, 6) AS icf_m,
               round(financing_cash_flow_usd / 1e6, 6) AS fcf_m,
               round(fx_effect_on_cash_usd / 1e6, 6) AS fxcash_m,
               round(net_change_in_cash_usd / 1e6, 6) AS net_m,
               round(closing_cash_usd / 1e6, 6) AS closing_m,
               round(operating_ytd_usd / 1e6, 6) AS ocf_ytd_m,
               round(investing_ytd_usd / 1e6, 6) AS icf_ytd_m,
               round(financing_ytd_usd / 1e6, 6) AS fcf_ytd_m,
               round(revolver_drawn_usd / 1e6, 6) AS rcf_drawn_m,
               round(revolver_available_usd / 1e6, 6) AS rcf_avail_m,
               round(liquidity_usd / 1e6, 6) AS liquidity_m
        FROM mart_cash_flow ORDER BY ALL
    """)

    # -------------------------------------------------- working capital
    out["_wc"] = _fetch(con, """
        SELECT period_key, fiscal_year,
               round(ar_usd / 1e6, 6) AS ar_m,
               round(inventory_usd / 1e6, 6) AS inv_m,
               round(ap_usd / 1e6, 6) AS ap_m,
               round(other_wc_usd / 1e6, 6) AS other_m,
               round(nwc_usd / 1e6, 6) AS nwc_m,
               dso_days, dio_days, dpo_days, ccc_days
        FROM mart_working_capital ORDER BY ALL
    """)

    # -------------------------------------------------- EBITDA bridge
    out["_ebitda"] = _fetch(con, """
        SELECT fiscal_year,
               round(statutory_ebitda_usd / 1e6, 6) AS statutory_m,
               round(management_layer4_effect_usd / 1e6, 6) AS layer4_m,
               round(approved_addbacks_usd / 1e6, 6) AS addbacks_m,
               round(adjusted_ebitda_usd / 1e6, 6) AS adjusted_m,
               round(sponsor_fee_cap_effect_usd / 1e6, 6) AS cap_effect_m,
               round(covenant_fx_addback_usd / 1e6, 6) AS fx_addback_m,
               round(covenant_ebitda_usd / 1e6, 6) AS covenant_m
        FROM rpt_ebitda_bridge ORDER BY ALL
    """)

    # the add-back categories behind the bridge, by account
    out["_addback"] = _fetch(con, """
        SELECT a.group_account, a.account_name, f.fiscal_year,
               round(sum(f.amount_usd) / 1e6, 6) AS amount_m,
               CASE WHEN a.group_account = '630400' THEN 'PERMITTED_CAPPED'
                    ELSE 'PERMITTED' END AS covenant_treatment
        FROM vw_statutory_fact f JOIN dim_account a USING (group_account)
        WHERE a.is_ebitda_addback AND f.counts_in_result
        GROUP BY ALL ORDER BY ALL
    """)

    # -------------------------------------------------- debt and covenants
    out["_debt"] = _fetch(con, """
        SELECT instrument_id, instrument_name, instrument_type, borrower_entity,
               currency_code, rate_type, is_hedged, maturity_date, interest_rate_basis,
               counts_toward_covenant_debt, period_key,
               round(closing_principal_usd / 1e6, 6) AS closing_m,
               round(undrawn_commitment_usd / 1e6, 6) AS undrawn_m,
               round(interest_expense_usd / 1e6, 6) AS interest_m,
               round(average_daily_drawn_usd / 1e6, 6) AS avg_drawn_m
        FROM mart_debt ORDER BY ALL
    """)

    out["_cov"] = _fetch(con, """
        SELECT period_key, fiscal_year, max_net_leverage,
               round(covenant_debt_usd / 1e6, 6) AS covenant_debt_m,
               round(gross_debt_usd / 1e6, 6) AS gross_debt_m,
               round(finance_lease_usd / 1e6, 6) AS finance_lease_m,
               round(cash_usd / 1e6, 6) AS cash_m,
               round(net_debt_usd / 1e6, 6) AS net_debt_m,
               round(economic_net_debt_usd / 1e6, 6) AS econ_net_debt_m,
               round(covenant_ebitda_usd / 1e6, 6) AS covenant_ebitda_m,
               round(adjusted_ebitda_usd / 1e6, 6) AS adjusted_ebitda_m,
               net_leverage, economic_leverage, headroom_turns,
               round(headroom_usd / 1e6, 6) AS headroom_m,
               in_compliance
        FROM mart_covenants ORDER BY ALL
    """)

    # -------------------------------------------------- headcount
    out["_hc"] = _fetch(con, """
        SELECT period_key, fiscal_year, entity_code, entity_name, bu_code, country_code,
               function_group, department_name,
               round(sum(fte_opening), 2) AS fte_opening,
               round(sum(hires), 2) AS hires,
               round(sum(leavers), 2) AS leavers,
               round(sum(fte_closing), 2) AS fte_closing,
               round(sum(fte_average), 2) AS fte_average,
               sum(headcount_closing) AS headcount_closing,
               round(sum(base_salary_month_usd) / 1e6, 6) AS salary_month_m
        FROM mart_headcount GROUP BY ALL ORDER BY ALL
    """)

    out["_hcpay"] = _fetch(con, """
        SELECT f.period_key,
               round(sum(f.amount_usd) / 1e6, 6) AS personnel_cost_m
        FROM vw_statutory_fact f JOIN dim_account a USING (group_account)
        WHERE f.counts_in_result AND a.fs_caption_l2 = 'Personnel costs'
        GROUP BY ALL ORDER BY ALL
    """)

    # -------------------------------------------------- capex
    out["_capex"] = _fetch(con, """
        SELECT period_key, fiscal_year, bu_code, bu_name, entity_code, asset_class,
               project_id, project_name,
               round(sum(spend_usd) / 1e6, 6) AS spend_m,
               round(sum(approved_usd) / 1e6, 6) AS approved_m
        FROM mart_capex GROUP BY ALL ORDER BY ALL
    """)

    # -------------------------------------------------- FX
    out["_fx"] = _fetch(con, """
        SELECT currency_code, period_key, fiscal_year, avg_rate, close_rate,
               coalesce(avg_rate_py, 0) AS avg_rate_py,
               round(revenue_usd / 1e6, 6) AS revenue_m,
               round(revenue_constant_ccy_usd / 1e6, 6) AS revenue_cc_m,
               round(cta_movement_usd / 1e6, 6) AS cta_move_m,
               round(cta_group_usd / 1e6, 6) AS cta_group_m,
               round(cta_nci_usd / 1e6, 6) AS cta_nci_m
        FROM mart_fx ORDER BY ALL
    """)

    # -------------------------------------------------- consolidation and governance
    out["_layers"] = _fetch(con, """
        SELECT layer_id, layer_code, layer_name, in_statutory_view, in_management_view,
               fiscal_year, entries, legs,
               round(ebitda_usd / 1e6, 6) AS ebitda_m,
               round(net_income_usd / 1e6, 6) AS net_income_m
        FROM mart_consolidation_bridge ORDER BY ALL
    """)

    # Numeric, with the unit in its own column, so the sheet can right-align and format them
    # consistently. Pre-formatted strings looked like a data dump the moment they were put in
    # a column together: "-3.04" beside "9042.5" beside "0".
    out["_consol"] = _fetch(con, f"""
        SELECT 1 AS sort_order, 'Goodwill recognised' AS item,
               round(sum(goodwill_usd) / 1e6, 1) AS value, 'USD m' AS unit,
               'rpt_goodwill_bridge' AS source FROM rpt_goodwill_bridge
        UNION ALL SELECT 2, 'Acquired intangibles, net book value',
               round(sum(closing_nbv_usd) / 1e6, 1), 'USD m', 'rpt_intangible_schedule'
               FROM rpt_intangible_schedule WHERE period_key = {REPORT_PERIOD}
        UNION ALL SELECT 3, 'Investment in subsidiaries eliminated',
               round(sum(abs(amount_usd)) / 1e6, 1), 'USD m', 'fact_consol_journal'
               FROM fact_consol_journal WHERE process = 'INVESTMENT' AND group_account = '178100'
        UNION ALL SELECT 4, 'Intercompany eliminated, gross',
               round(sum(abs(matched_usd)) / 1e6, 1), 'USD m', 'rpt_ic_exception'
               FROM rpt_ic_exception
        UNION ALL SELECT 5, 'Intercompany relationship-periods matched',
               CAST(count(*) AS DOUBLE), 'count', 'rpt_ic_exception' FROM rpt_ic_exception
        UNION ALL SELECT 6, 'Unrealised profit provision',
               round(sum(provision_usd) / 1e6, 2), 'USD m', 'rpt_pup_provision'
               FROM rpt_pup_provision WHERE period_key = {REPORT_PERIOD}
        UNION ALL SELECT 7, 'Non-controlling interest, closing',
               round(closing_usd / 1e6, 2), 'USD m', 'rpt_nci_rollforward'
               FROM rpt_nci_rollforward WHERE fiscal_year = 2026
        UNION ALL SELECT 8, 'Cumulative translation adjustment',
               round(sum(cta_movement_usd) / 1e6, 2), 'USD m', 'stg_cta_movement'
               FROM stg_cta_movement WHERE period_key <= {REPORT_PERIOD}
        UNION ALL SELECT 9, 'Management adjustments posted',
               CAST(count(*) AS DOUBLE), 'legs', 'fact_consol_journal'
               FROM fact_consol_journal WHERE process = 'MGMT_ADJ'
        ORDER BY 1
    """)

    out["_madj"] = _fetch(con, """
        SELECT adjustment_id, category, basis, group_account, offset_account,
               period_from, period_to, round(amount_usd / 1e6, 6) AS amount_m,
               ebitda_treatment, covenant_treatment, approval_status, preparer, approver,
               legs_posted, rationale
        FROM mart_management_adjustments ORDER BY ALL
    """)

    # -------------------------------------------------- variance detail
    out["_var"] = _fetch(con, """
        SELECT comparison_code, comparison_name, measure_code, measure_name, measure_sort,
               indent_level, is_subtotal, favourable_direction, bu_code, period_key,
               round(sum(base_ytd) / 1e6, 6) AS base_ytd_m,
               round(sum(comp_ytd) / 1e6, 6) AS comp_ytd_m,
               round(sum(var_ytd_usd) / 1e6, 6) AS var_ytd_m,
               round(sum(base_fy) / 1e6, 6) AS base_fy_m,
               round(sum(comp_fy) / 1e6, 6) AS comp_fy_m,
               round(sum(var_fy_usd) / 1e6, 6) AS var_fy_m,
               -- as 1/0 rather than TRUE/FALSE: SUMIFS ignores booleans in a
               -- sum range, so every row came back "Not comparable"
               CAST(min(is_comparable) AS INTEGER) AS is_comparable
        FROM mart_variance WHERE basis = 'STATUTORY'
        GROUP BY ALL ORDER BY ALL
    """)

    # Presented on the management sign convention -- revenue positive, costs positive -- so a
    # column of account variances reads the same way as every other column in the workbook.
    # The fact's own convention is credit-negative, and showing revenue as (14.6) in a report
    # that shows it as 279.0 two sheets earlier is the kind of inconsistency that makes a
    # reader stop trusting the whole pack.
    out["_varacc"] = _fetch(con, """
        SELECT m.bu_code, m.entity_code, e.entity_name, m.cost_center_code,
               m.group_account, l.account_name, l.fs_caption_l1, m.scenario_code,
               m.period_key,
               round(sum(m.amount_usd * CASE WHEN l.line = 'REVENUE' THEN -1 ELSE 1 END)
                     / 1e6, 6) AS amount_m
        FROM mart_financial_monthly m
        JOIN ref_report_line l USING (group_account)
        JOIN dim_entity e USING (entity_code)
        WHERE m.basis = 'STATUTORY' AND NOT m.is_intercompany
          AND m.version_code IN ('ACTUAL', 'BUD_FY26_V1', 'FC_FY26_08', 'PY_DERIVED')
          AND m.fiscal_year = 2026
        GROUP BY ALL ORDER BY ALL
    """)

    # -------------------------------------------------- controls and metadata
    out["_ctl"] = _fetch(con, """
        SELECT 'Phase 2 — generated source' AS phase, control_id, control_name, status,
               severity, measured, threshold FROM read_csv(
                   'data/phase02_control_results.csv', header=true, all_varchar=true)
        UNION ALL BY NAME
        SELECT 'Phase 3 — ingestion and mapping', control_id, control_name, status, severity,
               measured, threshold FROM read_csv(
                   'data/phase03_control_results.csv', header=true, all_varchar=true)
        UNION ALL BY NAME
        SELECT 'Phase 4 — consolidation', control_id, control_name, status, severity,
               measured, threshold FROM read_csv(
                   'data/phase04_control_results.csv', header=true, all_varchar=true)
        UNION ALL BY NAME
        SELECT 'Phase 5 — reporting marts', control_id, control_name, status, severity,
               measured, threshold FROM read_csv(
                   'data/phase05_control_results.csv', header=true, all_varchar=true)
    """)

    out["_scen"] = _fetch(con, """
        SELECT version_code, scenario_code, scenario_name, version_name, fiscal_year,
               actual_months, forecast_months, is_default, is_locked, approved_by,
               approved_date, sort_order, description
        FROM dim_report_scenario ORDER BY sort_order
    """)

    out["_meas"] = _fetch(con, """
        SELECT measure_code, measure_name, indent_level, is_subtotal, favourable_direction,
               sort_order FROM dim_report_measure ORDER BY sort_order
    """)

    out["_period"] = _fetch(con, """
        SELECT DISTINCT period_key,
               CAST(period_key / 100 AS INTEGER) AS fiscal_year,
               CAST(period_key % 100 AS INTEGER) AS accounting_period,
               strftime(make_date(CAST(period_key / 100 AS INTEGER),
                                  CAST(period_key % 100 AS INTEGER), 1), '%b %y') AS label,
               strftime(make_date(CAST(period_key / 100 AS INTEGER),
                                  CAST(period_key % 100 AS INTEGER), 1), '%b %Y') AS label_long
        FROM mart_cash_flow ORDER BY 1
    """)

    return out
