"""
The governed reporting marts.

Everything downstream — the Excel workbook now, Power BI later — reads these and nothing else.
The rule that makes that worth doing:

    **No reporting tool re-derives an accounting definition.** EBITDA, the add-back policy, FX
    translation, eliminations, NCI, the covenant rules, the cash flow and the reporting bases
    are all settled upstream. A mart may reshape them and a workbook may add presentation
    mathematics on top -- subtotals, variance dollars, percentages -- and neither may restate
    a policy.

## What the marts are built from

| | |
|---|---|
| Actual | `fact_financials` through `vw_statutory_fact` and `vw_management_fact` — fully consolidated |
| Budget, Forecast | `fact_plan`, entity-level layer 1, translated at the scenario's own approved rate set |
| Prior year | Actual, offset twelve months (ADR-0004). Never stored |

## The one comparability rule

Budget and Forecast are **not consolidated**: no elimination engine ever runs on them, because
a plan is built at entity level and no group ever posts a consolidation journal to a budget. So
every reporting measure **excludes the intercompany account sets on both sides**. On Actual
that changes nothing — the consolidation has already netted them to zero. On plan it removes
the internal trade, which is what makes the two comparable at all.

That is a presentation rule and not a second elimination engine: the account sets come from
`ref_ic_side`, the same configuration the Phase 4 engine matches on, and `P5-CMP-01` proves the
rule is a no-op on Actual.

## What plan comparisons can and cannot say

Plan carries no PPA amortisation, no unrealised profit, no NCI attribution and no CTA, because
those are consolidation entries and a plan has none. A budget variance on EBITDA is therefore
like for like; a budget variance on net income is not, and the marts do not offer one. The
`is_comparable` flag on `mart_financial_ytd` says which is which, rather than leaving a reader
to find out.
"""

from __future__ import annotations

import duckdb

from .config import BASES, COMPARISONS, MEASURES, RATIOS, RESERVED_SCENARIOS


def _measure_sql() -> str:
    """The measure definitions, once, as a SQL expression over an account-grain relation."""
    return """
        round(-coalesce(sum(amount_usd) FILTER (WHERE line = 'REVENUE'), 0), 2) AS REVENUE,
        round(coalesce(sum(amount_usd) FILTER (WHERE line = 'COST_OF_SALES'), 0), 2)
            AS COST_OF_SALES,
        round(coalesce(sum(amount_usd) FILTER (WHERE line = 'OPEX'), 0), 2) AS OPEX,
        round(coalesce(sum(amount_usd) FILTER (WHERE is_addback), 0), 2) AS ADDBACKS,
        round(coalesce(sum(amount_usd) FILTER (WHERE line = 'DA'), 0), 2) AS DA,
        round(coalesce(sum(amount_usd) FILTER (WHERE line = 'NET_FINANCE'), 0), 2)
            AS NET_FINANCE,
        round(coalesce(sum(amount_usd) FILTER (WHERE line = 'TAX'), 0), 2) AS TAX,
        round(coalesce(sum(amount_usd) FILTER (WHERE line = 'NCI'), 0), 2) AS NCI
    """


def build(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    counts: dict[str, int] = {}

    def rows(name: str) -> None:
        counts[name] = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]

    # ================================================================= reporting dimensions
    reserved = ", ".join(f"'{s}'" for s in RESERVED_SCENARIOS)
    con.execute(f"""
    CREATE OR REPLACE TABLE dim_report_scenario AS
    -- Every scenario and version a report may offer, and no others. A reserved scenario is
    -- architecture that has not been populated: offering it would hand a reader an empty
    -- report that looks like a real one, so `P5-SCN-02` requires it to be absent.
    --
    -- "Populated" means something different for a derived version. A stored version is
    -- populated when rows exist carrying its code. A DERIVED version has no stored rows by
    -- construction -- Prior Year is the approved Actual shifted twelve months and is
    -- materialised nowhere (ADR-0004) -- so it is populated when *the version it derives
    -- from* is. Testing a derived version for stored rows is what excluded PY_DERIVED from
    -- this dimension while 12,516 mart rows joined on it (P7-D-01, ADR-0027).
    SELECT v.version_code, v.scenario_code, s.scenario_name, v.version_name,
           v.scenario_type AS version_type, s.derived_from_scenario_code,
           v.fiscal_year, v.actual_months, v.forecast_months,
           v.is_default, v.is_locked, v.approved_by, v.approved_date,
           s.sort_order * 1000 + v.sort_order AS sort_order,
           v.description
    FROM dim_version v JOIN dim_scenario s USING (scenario_code)
    WHERE NOT v.is_reserved AND NOT s.is_reserved
      AND v.scenario_code NOT IN ({reserved})
      AND CASE WHEN v.scenario_type = 'DERIVED'
               -- the scenario it derives from has a populated default version
               THEN EXISTS (SELECT 1 FROM dim_version sv
                            JOIN fact_financials f ON f.version_code = sv.version_code
                            WHERE sv.scenario_code = s.derived_from_scenario_code
                              AND sv.is_default)
               ELSE EXISTS (SELECT 1 FROM fact_plan p WHERE p.version_code = v.version_code
                            UNION ALL SELECT 1 FROM fact_financials f
                            WHERE f.version_code = v.version_code)
          END
    ORDER BY sort_order
    """)
    rows("dim_report_scenario")

    con.execute(f"""
    CREATE OR REPLACE TABLE dim_report_measure AS
    SELECT * FROM (VALUES {", ".join(
        f"('{c}', '{n}', {lv}, {str(sub).lower()}, '{fav}', {i})"
        for i, (c, n, lv, sub, fav) in enumerate(MEASURES))})
        AS t(measure_code, measure_name, indent_level, is_subtotal,
             favourable_direction, sort_order)
    """)
    rows("dim_report_measure")

    # ================================================================= the account spine
    # One classification of every income statement account into a reporting line, applied to
    # Actual and to plan alike. `fs_caption_l1` is the chart's own grouping, so the marts
    # inherit the classification rather than inventing one.
    con.execute("""
    CREATE OR REPLACE TABLE ref_report_line AS
    SELECT group_account, account_name, fs_caption_l1, fs_caption_l2,
           CASE fs_caption_l1
                WHEN 'Revenue' THEN 'REVENUE'
                WHEN 'Cost of Sales' THEN 'COST_OF_SALES'
                WHEN 'Operating Expenses' THEN 'OPEX'
                WHEN 'Depreciation and Amortisation' THEN 'DA'
                WHEN 'Non-Operating' THEN 'NET_FINANCE'
                WHEN 'Income Tax' THEN 'TAX'
                WHEN 'Non-Controlling Interests' THEN 'NCI'
           END AS line,
           is_ebitda, is_ebitda_addback AS is_addback,
           -- the intercompany sets, taken from the elimination engine's own configuration
           group_account IN (SELECT group_account FROM ref_ic_side) AS is_intercompany
    FROM dim_account
    WHERE statement = 'IS' AND NOT is_statistical
    """)
    rows("ref_report_line")

    # ================================================================= mart_financial_monthly
    # Account grain, every scenario, both bases. This is the flexible base the variance detail
    # reads; every other financial mart is an aggregate of it.
    basis_union = "\n        UNION ALL BY NAME\n".join(f"""
        SELECT '{b}' AS basis, f.scenario_code, f.version_code, f.entity_code, f.bu_code,
               f.cost_center_code, f.group_account, f.period_key, f.fiscal_year,
               sum(f.amount_usd) AS amount_usd
        FROM vw_{b.lower()}_fact f
        WHERE f.counts_in_result
        GROUP BY ALL""" for b in BASES)

    con.execute(f"""
    CREATE OR REPLACE TABLE mart_financial_monthly AS
    WITH actual AS ({basis_union}),
    -- Plan is translated at the rate set its own scenario declares -- BUDGET rates for the
    -- budget, FORECAST rates for a forecast -- so a plan variance is never contaminated by a
    -- rate movement the plan could not have known about. Income statement lines take the
    -- monthly average rate, exactly as FX-P01 requires of actuals.
    plan AS (
        SELECT b.basis, p.scenario_code, p.version_code, p.entity_code, p.bu_code,
               p.cost_center_code, p.group_account, p.period_key, p.fiscal_year,
               sum(p.amount_local * r.rate_usd_per_unit) AS amount_usd
        FROM fact_plan p
        JOIN dim_scenario s USING (scenario_code)
        JOIN ref_fx_rate r
          ON r.currency_code = p.currency_code AND r.period_key = p.period_key
         AND r.rate_set = s.fx_rate_set AND r.rate_type = 'AVG'
        CROSS JOIN (SELECT unnest([{", ".join(f"'{b}'" for b in BASES)}]) AS basis) b
        WHERE NOT s.is_reserved
        GROUP BY ALL
    ),
    -- Prior year is the same actual twelve months earlier (ADR-0004). It is derived here and
    -- stored nowhere, so it can never drift from the actual it is a view of.
    prior AS (
        SELECT basis, 'PY' AS scenario_code, 'PY_DERIVED' AS version_code,
               entity_code, bu_code, cost_center_code, group_account,
               period_key + 100 AS period_key, fiscal_year + 1 AS fiscal_year, amount_usd
        FROM actual WHERE scenario_code = 'ACT'
    )
    SELECT m.basis, m.scenario_code, m.version_code, m.entity_code, m.bu_code,
           m.cost_center_code, m.group_account, l.line, l.is_addback, l.is_intercompany,
           m.period_key, m.fiscal_year,
           CAST(m.period_key % 100 AS INTEGER) AS accounting_period,
           CAST((m.period_key % 100 - 1) / 3 + 1 AS INTEGER) AS fiscal_quarter,
           CAST(round(m.amount_usd, 2) AS DECIMAL(18,2)) AS amount_usd
    FROM (SELECT * FROM actual UNION ALL BY NAME SELECT * FROM plan
          UNION ALL BY NAME SELECT * FROM prior) m
    JOIN ref_report_line l USING (group_account)
    WHERE m.period_key BETWEEN (SELECT min(period_key) FROM fact_financials)
                           AND (SELECT max(period_key) FROM fact_financials)
    ORDER BY ALL
    """)
    rows("mart_financial_monthly")

    # ================================================================= mart_financial_ytd
    # Measure grain, at three period bases. Subtotals are stored rather than left to the
    # workbook: a subtotal computed in a spreadsheet is a definition living in a spreadsheet.
    con.execute(f"""
    CREATE OR REPLACE TABLE stg_measure_monthly AS
    SELECT basis, scenario_code, version_code, entity_code, bu_code, period_key, fiscal_year,
           accounting_period, fiscal_quarter,
           {_measure_sql()}
    FROM mart_financial_monthly
    WHERE NOT is_intercompany
    GROUP BY ALL
    """)

    con.execute("""
    CREATE OR REPLACE TABLE mart_financial_ytd AS
    WITH derived AS (
        SELECT *,
               REVENUE - COST_OF_SALES AS GROSS_PROFIT,
               REVENUE - COST_OF_SALES - OPEX AS EBITDA,
               REVENUE - COST_OF_SALES - OPEX + ADDBACKS AS ADJ_EBITDA,
               REVENUE - COST_OF_SALES - OPEX - DA AS EBIT,
               REVENUE - COST_OF_SALES - OPEX - DA - NET_FINANCE - TAX AS NET_INCOME,
               REVENUE - COST_OF_SALES - OPEX - DA - NET_FINANCE - TAX - NCI AS NI_PARENT
        FROM stg_measure_monthly
    ),
    unpivoted AS (
        UNPIVOT derived ON REVENUE, COST_OF_SALES, GROSS_PROFIT, OPEX, EBITDA, ADDBACKS,
                           ADJ_EBITDA, DA, EBIT, NET_FINANCE, TAX, NET_INCOME, NCI, NI_PARENT
        INTO NAME measure_code VALUE amount_usd
    ),
    periods AS (
        SELECT basis, scenario_code, version_code, entity_code, bu_code, measure_code,
               period_key, fiscal_year, accounting_period, fiscal_quarter,
               amount_usd AS mtd_usd,
               sum(amount_usd) OVER (
                   PARTITION BY basis, scenario_code, version_code, entity_code, bu_code,
                                measure_code, fiscal_year
                   ORDER BY period_key ROWS UNBOUNDED PRECEDING) AS ytd_usd,
               sum(amount_usd) OVER (
                   PARTITION BY basis, scenario_code, version_code, entity_code, bu_code,
                                measure_code, fiscal_year) AS fy_usd
        FROM unpivoted
    )
    SELECT p.*,
           m.measure_name, m.indent_level, m.is_subtotal, m.favourable_direction,
           m.sort_order AS measure_sort,
           -- Plan carries no consolidation entries -- no PPA amortisation, no unrealised
           -- profit, no NCI attribution, no CTA -- because a budget has none to carry. So a
           -- plan comparison is like for like down to EBIT and is not below it, and the flag
           -- says which rather than leaving a reader to discover it.
           (p.scenario_code IN ('ACT', 'PY')
            OR m.measure_code IN ('REVENUE', 'COST_OF_SALES', 'GROSS_PROFIT', 'OPEX',
                                  'EBITDA', 'ADDBACKS', 'ADJ_EBITDA', 'DA', 'EBIT'))
               AS is_comparable
    FROM periods p JOIN dim_report_measure m USING (measure_code)
    ORDER BY ALL
    """)
    rows("mart_financial_ytd")

    # ================================================================= mart_variance
    ratio_rows = " UNION ALL ".join(
        f"SELECT '{c}' AS ratio_code, '{n}' AS ratio_name, '{num}' AS numerator_code, "
        f"'{den}' AS denominator_code" for c, n, num, den in RATIOS)
    con.execute(f"CREATE OR REPLACE TABLE dim_report_ratio AS {ratio_rows}")
    rows("dim_report_ratio")

    comparison_rows = " UNION ALL ".join(
        f"SELECT '{c}' AS comparison_code, '{n}' AS comparison_name, '{b}' AS base_scenario, "
        f"'{cm}' AS comparator_scenario, {i} AS sort_order"
        for i, (c, n, b, cm) in enumerate(COMPARISONS))
    con.execute(f"CREATE OR REPLACE TABLE dim_report_comparison AS {comparison_rows}")
    rows("dim_report_comparison")

    # The default version for each scenario: the one a report offers unless a reader picks
    # another. Superseded forecasts stay available and are never the default.
    con.execute("""
    CREATE OR REPLACE TABLE ref_default_version AS
    -- One authoritative source for version membership: the governed dimension, and nothing
    -- unioned in by hand. Prior Year used to be appended here because it had no version row
    -- to be the default of; it has one now (ADR-0027), so the workaround is gone and there
    -- is no second definition of what a valid version is.
    SELECT scenario_code, version_code FROM dim_report_scenario WHERE is_default
    """)

    con.execute("""
    CREATE OR REPLACE TABLE mart_variance AS
    WITH base AS (
        SELECT c.comparison_code, c.comparison_name, c.sort_order,
               b.basis, b.entity_code, b.bu_code, b.measure_code, b.measure_name,
               b.indent_level, b.is_subtotal, b.favourable_direction, b.measure_sort,
               b.period_key, b.fiscal_year, b.accounting_period,
               b.version_code AS base_version, k.version_code AS comparator_version,
               b.mtd_usd AS base_mtd, b.ytd_usd AS base_ytd, b.fy_usd AS base_fy,
               coalesce(k.mtd_usd, 0) AS comp_mtd, coalesce(k.ytd_usd, 0) AS comp_ytd,
               coalesce(k.fy_usd, 0) AS comp_fy,
               b.is_comparable AND coalesce(k.is_comparable, true) AS is_comparable
        FROM dim_report_comparison c
        JOIN ref_default_version bv ON bv.scenario_code = c.base_scenario
        JOIN mart_financial_ytd b
          ON b.scenario_code = c.base_scenario AND b.version_code = bv.version_code
        LEFT JOIN ref_default_version kv ON kv.scenario_code = c.comparator_scenario
        LEFT JOIN mart_financial_ytd k
          ON k.scenario_code = c.comparator_scenario AND k.version_code = kv.version_code
         AND k.basis = b.basis AND k.entity_code = b.entity_code AND k.bu_code = b.bu_code
         AND k.measure_code = b.measure_code AND k.period_key = b.period_key
    )
    SELECT *,
           round(base_mtd - comp_mtd, 2) AS var_mtd_usd,
           round(base_ytd - comp_ytd, 2) AS var_ytd_usd,
           round(base_fy - comp_fy, 2) AS var_fy_usd,
           round((base_mtd - comp_mtd) / nullif(abs(comp_mtd), 0), 6) AS var_mtd_pct,
           round((base_ytd - comp_ytd) / nullif(abs(comp_ytd), 0), 6) AS var_ytd_pct,
           round((base_fy - comp_fy) / nullif(abs(comp_fy), 0), 6) AS var_fy_pct,
           -- Favourability is a property of the MEASURE, not of the sign. Revenue above plan
           -- is good news; operating expense above plan is not, and colouring every positive
           -- variance green would say the opposite in half the statement.
           CASE favourable_direction
                WHEN 'HIGHER' THEN CASE WHEN base_ytd - comp_ytd > 0 THEN 'FAVOURABLE'
                                        WHEN base_ytd - comp_ytd < 0 THEN 'UNFAVOURABLE'
                                        ELSE 'NEUTRAL' END
                WHEN 'LOWER'  THEN CASE WHEN base_ytd - comp_ytd < 0 THEN 'FAVOURABLE'
                                        WHEN base_ytd - comp_ytd > 0 THEN 'UNFAVOURABLE'
                                        ELSE 'NEUTRAL' END
                ELSE 'NEUTRAL' END AS ytd_favourability,
           CASE favourable_direction
                WHEN 'HIGHER' THEN CASE WHEN base_fy - comp_fy > 0 THEN 'FAVOURABLE'
                                        WHEN base_fy - comp_fy < 0 THEN 'UNFAVOURABLE'
                                        ELSE 'NEUTRAL' END
                WHEN 'LOWER'  THEN CASE WHEN base_fy - comp_fy < 0 THEN 'FAVOURABLE'
                                        WHEN base_fy - comp_fy > 0 THEN 'UNFAVOURABLE'
                                        ELSE 'NEUTRAL' END
                ELSE 'NEUTRAL' END AS fy_favourability
    FROM base
    ORDER BY ALL
    """)
    rows("mart_variance")

    # ================================================================= business unit / entity
    con.execute("""
    CREATE OR REPLACE TABLE mart_business_unit AS
    SELECT f.basis, f.scenario_code, f.version_code, f.bu_code, b.bu_name, b.bu_short_name,
           b.segment_type, b.is_reportable_segment, b.sort_order AS bu_sort,
           f.period_key, f.fiscal_year, f.accounting_period, f.measure_code, f.measure_name,
           f.measure_sort, f.indent_level, f.is_subtotal,
           round(sum(f.mtd_usd), 2) AS mtd_usd,
           round(sum(f.ytd_usd), 2) AS ytd_usd,
           round(sum(f.fy_usd), 2) AS fy_usd
    FROM mart_financial_ytd f JOIN dim_business_unit b USING (bu_code)
    GROUP BY ALL
    ORDER BY ALL
    """)
    rows("mart_business_unit")

    con.execute("""
    CREATE OR REPLACE TABLE mart_entity_performance AS
    WITH pl AS (
        SELECT basis, scenario_code, version_code, entity_code, period_key, fiscal_year,
               measure_code, round(sum(ytd_usd), 2) AS ytd_usd, round(sum(fy_usd), 2) AS fy_usd
        FROM mart_financial_ytd GROUP BY ALL
    ),
    bs AS (
        SELECT entity_code, period_key,
               round(coalesce(sum(amount_usd) FILTER (
                   WHERE cash_flow_category = 'CASH'), 0), 2) AS cash_usd,
               round(coalesce(sum(amount_usd) FILTER (
                   WHERE cash_flow_category = 'OP_WC'), 0), 2) AS working_capital_usd
        FROM (SELECT f.entity_code, d.period_key, f.amount_usd, f.cash_flow_category
              FROM (SELECT DISTINCT period_key FROM fact_financials) d
              JOIN vw_statutory_fact f ON f.period_key <= d.period_key
              WHERE f.statement = 'BS')
        GROUP BY ALL
    ),
    hc AS (
        SELECT entity_code, period_key, round(sum(fte_closing), 1) AS fte_closing
        FROM fact_headcount GROUP BY ALL
    )
    SELECT p.basis, p.scenario_code, p.version_code, p.entity_code, e.entity_name,
           e.functional_currency, e.erp_system, e.bu_code, e.country_code,
           p.period_key, p.fiscal_year, p.measure_code, p.ytd_usd, p.fy_usd,
           bs.cash_usd, bs.working_capital_usd, hc.fte_closing
    FROM pl p
    JOIN dim_entity e USING (entity_code)
    LEFT JOIN bs USING (entity_code, period_key)
    LEFT JOIN hc USING (entity_code, period_key)
    WHERE e.entity_type <> 'ELIMINATION'
    ORDER BY ALL
    """)
    rows("mart_entity_performance")

    # ================================================================= balance sheet / cash
    con.execute("""
    CREATE OR REPLACE TABLE mart_balance_sheet AS
    SELECT b.period_key, b.fiscal_year, b.fs_caption_l2 AS caption, b.account_class,
           b.sort_order, b.balance_usd, b.movement_usd,
           lag(b.balance_usd) OVER w AS prior_month_usd,
           lag(b.balance_usd, 12) OVER w AS prior_year_usd,
           round(b.balance_usd - lag(b.balance_usd) OVER w, 2) AS mom_movement_usd,
           round(b.balance_usd - lag(b.balance_usd, 12) OVER w, 2) AS yoy_movement_usd
    FROM rpt_balance_sheet b
    WINDOW w AS (PARTITION BY b.fs_caption_l2, b.account_class ORDER BY b.period_key)
    ORDER BY ALL
    """)
    rows("mart_balance_sheet")

    con.execute("""
    CREATE OR REPLACE TABLE mart_cash_flow AS
    SELECT c.period_key, c.fiscal_year,
           CAST(c.period_key % 100 AS INTEGER) AS accounting_period,
           c.opening_cash_usd, c.result_usd, c.non_cash_and_other_usd, c.working_capital_usd,
           c.fx_non_cash_usd, c.close_translation_usd, c.operating_cash_flow_usd,
           c.investing_cash_flow_usd, c.financing_cash_flow_usd, c.fx_effect_on_cash_usd,
           c.net_change_in_cash_usd, c.closing_cash_usd,
           sum(c.operating_cash_flow_usd) OVER w AS operating_ytd_usd,
           sum(c.investing_cash_flow_usd) OVER w AS investing_ytd_usd,
           sum(c.financing_cash_flow_usd) OVER w AS financing_ytd_usd,
           round(coalesce(d.closing_drawn, 0), 2) AS revolver_drawn_usd,
           round(coalesce(d.undrawn_commitment, 0), 2) AS revolver_available_usd,
           round(c.closing_cash_usd + coalesce(d.undrawn_commitment, 0), 2) AS liquidity_usd
    FROM rpt_cash_flow c
    LEFT JOIN (SELECT period_key, sum(closing_principal) AS closing_drawn,
                      sum(undrawn_commitment) AS undrawn_commitment
               FROM ref_debt_schedule WHERE instrument_type = 'RCF' GROUP BY 1) d
           USING (period_key)
    WINDOW w AS (PARTITION BY c.fiscal_year ORDER BY c.period_key ROWS UNBOUNDED PRECEDING)
    ORDER BY ALL
    """)
    rows("mart_cash_flow")

    con.execute("""
    CREATE OR REPLACE TABLE mart_working_capital AS
    WITH bal AS (
        SELECT d.period_key,
               round(coalesce(sum(f.amount_usd) FILTER (
                   WHERE f.fs_caption_l2 = 'Accounts receivable, net'), 0), 2) AS ar_usd,
               round(coalesce(sum(f.amount_usd) FILTER (
                   WHERE f.fs_caption_l2 = 'Inventory, net'), 0), 2) AS inventory_usd,
               round(-coalesce(sum(f.amount_usd) FILTER (
                   WHERE f.fs_caption_l2 = 'Accounts payable'), 0), 2) AS ap_usd,
               round(coalesce(sum(f.amount_usd) FILTER (
                   WHERE f.cash_flow_category = 'OP_WC'
                     AND f.fs_caption_l2 NOT IN ('Accounts receivable, net', 'Inventory, net',
                                                 'Accounts payable')), 0), 2) AS other_wc_usd
        FROM (SELECT DISTINCT period_key FROM fact_financials) d
        JOIN vw_statutory_fact f ON f.period_key <= d.period_key
        WHERE f.statement = 'BS'
        GROUP BY 1
    ),
    flow AS (
        -- trailing three months, annualised: the ratios need a rate of activity and a single
        -- month of a seasonal business is not one
        SELECT period_key,
               sum(revenue) OVER w AS revenue_3m,
               sum(cost_of_sales) OVER w AS cos_3m
        FROM (SELECT period_key,
                     round(-coalesce(sum(amount_usd) FILTER (WHERE line = 'REVENUE'), 0), 2)
                         AS revenue,
                     round(coalesce(sum(amount_usd) FILTER (
                         WHERE line = 'COST_OF_SALES'), 0), 2) AS cost_of_sales
              FROM mart_financial_monthly
              WHERE scenario_code = 'ACT' AND basis = 'STATUTORY' AND NOT is_intercompany
              GROUP BY 1)
        WINDOW w AS (ORDER BY period_key ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
    )
    SELECT b.period_key,
           CAST(b.period_key / 100 AS INTEGER) AS fiscal_year,
           b.ar_usd, b.inventory_usd, b.ap_usd, b.other_wc_usd,
           round(b.ar_usd + b.inventory_usd - b.ap_usd + b.other_wc_usd, 2) AS nwc_usd,
           round(b.ar_usd / nullif(f.revenue_3m, 0) * 91.25, 1) AS dso_days,
           round(b.inventory_usd / nullif(f.cos_3m, 0) * 91.25, 1) AS dio_days,
           round(b.ap_usd / nullif(f.cos_3m, 0) * 91.25, 1) AS dpo_days,
           round(b.ar_usd / nullif(f.revenue_3m, 0) * 91.25
                 + b.inventory_usd / nullif(f.cos_3m, 0) * 91.25
                 - b.ap_usd / nullif(f.cos_3m, 0) * 91.25, 1) AS ccc_days
    FROM bal b JOIN flow f USING (period_key)
    ORDER BY ALL
    """)
    rows("mart_working_capital")

    # ================================================================= operational marts
    con.execute("""
    CREATE OR REPLACE TABLE mart_headcount AS
    SELECT h.period_key, CAST(h.period_key / 100 AS INTEGER) AS fiscal_year,
           h.entity_code, e.entity_name, e.bu_code, e.country_code, e.functional_currency,
           c.department_code, c.department_name, c.function_group, h.job_family_code,
           round(sum(h.fte_opening), 2) AS fte_opening,
           round(sum(h.hires), 2) AS hires,
           round(sum(h.leavers), 2) AS leavers,
           round(sum(h.fte_closing), 2) AS fte_closing,
           round(sum(h.fte_average), 2) AS fte_average,
           sum(h.headcount_closing) AS headcount_closing,
           round(sum(h.annual_base_salary_local * r.rate_usd_per_unit) / 12.0, 2)
               AS base_salary_month_usd
    FROM fact_headcount h
    JOIN dim_entity e USING (entity_code)
    LEFT JOIN dim_cost_center c USING (entity_code, cost_center_code)
    JOIN ref_fx_rate r ON r.currency_code = h.currency_code AND r.period_key = h.period_key
                      AND r.rate_set = 'ACTUAL' AND r.rate_type = 'AVG'
    GROUP BY ALL
    ORDER BY ALL
    """)
    rows("mart_headcount")

    con.execute("""
    CREATE OR REPLACE TABLE mart_capex AS
    SELECT c.period_key, CAST(c.period_key / 100 AS INTEGER) AS fiscal_year,
           c.project_id, c.project_name, c.asset_class, c.entity_code, e.entity_name,
           c.bu_code, b.bu_name,
           round(sum(c.spend_local * r.rate_usd_per_unit), 2) AS spend_usd,
           round(sum(c.approved_amount_local * r.rate_usd_per_unit), 2) AS approved_usd
    FROM fact_capex_project c
    JOIN dim_entity e ON e.entity_code = c.entity_code
    JOIN dim_business_unit b ON b.bu_code = c.bu_code
    JOIN ref_fx_rate r ON r.currency_code = c.currency_code AND r.period_key = c.period_key
                      AND r.rate_set = 'ACTUAL' AND r.rate_type = 'AVG'
    GROUP BY ALL
    ORDER BY ALL
    """)
    rows("mart_capex")

    con.execute("""
    CREATE OR REPLACE TABLE mart_debt AS
    SELECT d.period_key, CAST(d.period_key / 100 AS INTEGER) AS fiscal_year,
           d.instrument_id, d.instrument_name, d.instrument_type, d.borrower_entity,
           d.currency_code, d.rate_type, d.is_hedged, d.maturity_date,
           d.interest_rate_basis, d.counts_toward_covenant_debt, d.covenant_reference,
           round(d.opening_principal, 2) AS opening_principal_usd,
           round(d.drawings, 2) AS drawings_usd,
           round(d.repayments, 2) AS repayments_usd,
           round(d.closing_principal, 2) AS closing_principal_usd,
           round(d.undrawn_commitment, 2) AS undrawn_commitment_usd,
           round(d.interest_expense_local, 2) AS interest_expense_usd,
           round(d.commitment_fee_local, 2) AS commitment_fee_usd,
           round(d.average_daily_drawn, 2) AS average_daily_drawn_usd
    FROM ref_debt_schedule d
    ORDER BY ALL
    """)
    rows("mart_debt")

    # Covenant reporting.
    #
    # Leverage is tested on a **last-twelve-months** EBITDA, which is what the credit
    # agreement means and what a lender computes. Using the fiscal-year figure for a year in
    # progress divides a full net debt balance by a part-year result: at August 2026 that
    # produced 7.38x against a 4.50x limit and reported a covenant breach that does not exist.
    # The twelve months to August 2026 is 4.21x, and compliant.
    #
    # The DEFINITION is not restated here -- which add-backs are permitted, and the sponsor
    # fee cap, are settled in `rpt_ebitda_bridge` and in the credit agreement's own terms. Only
    # the WINDOW changes, and `P5-COV-01` proves it: at each fiscal year end the rolling
    # twelve months must equal the approved bridge for that year, to the cent.
    con.execute("""
    CREATE OR REPLACE TABLE stg_covenant_ltm AS
    WITH monthly AS (
        -- deliberately NOT rounded here: rounding twelve months and then summing them differs
        -- from summing and rounding once, and the difference is exactly what made this
        -- disagree with the approved bridge by three cents at a year end
        SELECT m.period_key,
               -coalesce(sum(m.amount_usd) FILTER (WHERE a.is_ebitda), 0) AS ebitda_usd,
               coalesce(sum(m.amount_usd) FILTER (WHERE a.is_ebitda_addback), 0)
                   AS addbacks_usd,
               coalesce(sum(m.amount_usd) FILTER (
                   WHERE m.group_account = '630400'), 0) AS sponsor_fee_usd,
               coalesce(sum(m.amount_usd) FILTER (
                   WHERE m.group_account IN ('740100', '740200')), 0) AS unrealised_fx_usd
        FROM mart_financial_monthly m JOIN dim_account a USING (group_account)
        -- Intercompany accounts are NOT excluded here, unlike every plan comparison. The
        -- comparability rule exists so a consolidated actual can be compared with a plan that
        -- was never consolidated, and a covenant measure has no plan side: it is the group's
        -- own EBITDA on the approved definition, where the consolidation has already
        -- eliminated the intercompany trade. Excluding it again removed the few cents of
        -- currency rounding the elimination leaves behind and put this three cents away from
        -- the approved bridge at a year end.
        WHERE m.scenario_code = 'ACT' AND m.basis = 'STATUTORY'
        GROUP BY 1
    )
    SELECT period_key,
           round(sum(ebitda_usd) OVER w, 2) AS ltm_ebitda_usd,
           round(sum(addbacks_usd) OVER w, 2) AS ltm_addbacks_usd,
           round(sum(sponsor_fee_usd) OVER w, 2) AS ltm_sponsor_fee_usd,
           round(sum(unrealised_fx_usd) OVER w, 2) AS ltm_unrealised_fx_usd,
           count(*) OVER w AS months_in_window
    FROM monthly
    WINDOW w AS (ORDER BY period_key ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
    """)

    cap = con.execute("""
        SELECT CAST(value AS DOUBLE) * 1e6 FROM ref_covenant_term WHERE term_id = 'CA-027'
    """).fetchone()[0]

    con.execute(f"""
    CREATE OR REPLACE TABLE mart_covenants AS
    WITH limits AS (
        SELECT CAST(regexp_extract(term, 'FY(\\d{{4}})', 1) AS INTEGER) AS fiscal_year,
               CAST(value AS DOUBLE) AS max_net_leverage
        FROM ref_covenant_term
        WHERE term_id IN ('CA-009', 'CA-010', 'CA-011', 'CA-012')
    ),
    ladder AS (
        SELECT y.fiscal_year,
               coalesce(l.max_net_leverage,
                        (SELECT CAST(value AS DOUBLE) FROM ref_covenant_term
                         WHERE term_id = 'CA-012')) AS max_net_leverage
        FROM (SELECT DISTINCT CAST(period_key / 100 AS INTEGER) AS fiscal_year
              FROM stg_covenant_ltm) y
        LEFT JOIN limits l USING (fiscal_year)
    ),
    debt AS (
        SELECT CAST(period_key / 100 AS INTEGER) AS fiscal_year, period_key,
               round(coalesce(sum(closing_principal) FILTER (
                   WHERE counts_toward_covenant_debt), 0), 2) AS covenant_debt_usd,
               round(coalesce(sum(closing_principal), 0), 2) AS gross_debt_usd,
               round(coalesce(sum(closing_principal) FILTER (
                   WHERE instrument_type = 'FINANCE_LEASE'), 0), 2) AS finance_lease_usd
        FROM ref_debt_schedule GROUP BY ALL
    ),
    cash AS (SELECT period_key, closing_cash_usd FROM rpt_cash_flow),
    leases AS (
        SELECT d.period_key,
               round(-coalesce(sum(f.amount_usd) FILTER (
                   WHERE f.fs_caption_l2 = 'Operating lease liabilities'), 0), 2) AS oplease_usd
        FROM (SELECT DISTINCT period_key FROM fact_financials) d
        JOIN vw_statutory_fact f ON f.period_key <= d.period_key
        WHERE f.statement = 'BS' GROUP BY 1
    ),
    ltm AS (
        SELECT period_key, months_in_window,
               ltm_ebitda_usd,
               round(ltm_ebitda_usd + ltm_addbacks_usd, 2) AS ltm_adjusted_ebitda_usd,
               round(ltm_ebitda_usd + ltm_addbacks_usd
                     + least(ltm_sponsor_fee_usd, {cap}) - ltm_sponsor_fee_usd
                     + ltm_unrealised_fx_usd, 2) AS ltm_covenant_ebitda_usd,
               round(least(ltm_sponsor_fee_usd, {cap}) - ltm_sponsor_fee_usd, 2)
                   AS sponsor_fee_cap_effect_usd,
               ltm_unrealised_fx_usd AS covenant_fx_addback_usd
        FROM stg_covenant_ltm
    )
    SELECT d.period_key, d.fiscal_year, l.max_net_leverage,
           t.months_in_window,
           d.covenant_debt_usd, d.gross_debt_usd, d.finance_lease_usd,
           c.closing_cash_usd AS cash_usd,
           round(d.covenant_debt_usd - c.closing_cash_usd, 2) AS net_debt_usd,
           round(d.covenant_debt_usd - c.closing_cash_usd + le.oplease_usd, 2)
               AS economic_net_debt_usd,
           t.ltm_covenant_ebitda_usd AS covenant_ebitda_usd,
           t.ltm_adjusted_ebitda_usd AS adjusted_ebitda_usd,
           t.sponsor_fee_cap_effect_usd,
           t.covenant_fx_addback_usd,
           round((d.covenant_debt_usd - c.closing_cash_usd)
                 / nullif(t.ltm_covenant_ebitda_usd, 0), 4) AS net_leverage,
           round((d.covenant_debt_usd - c.closing_cash_usd + le.oplease_usd)
                 / nullif(t.ltm_adjusted_ebitda_usd, 0), 4) AS economic_leverage,
           round(l.max_net_leverage
                 - (d.covenant_debt_usd - c.closing_cash_usd)
                   / nullif(t.ltm_covenant_ebitda_usd, 0), 4) AS headroom_turns,
           round(t.ltm_covenant_ebitda_usd * l.max_net_leverage
                 - (d.covenant_debt_usd - c.closing_cash_usd), 2) AS headroom_usd,
           l.max_net_leverage
             >= (d.covenant_debt_usd - c.closing_cash_usd)
                / nullif(t.ltm_covenant_ebitda_usd, 0) AS in_compliance
    FROM debt d
    JOIN ladder l USING (fiscal_year)
    JOIN cash c USING (period_key)
    JOIN leases le USING (period_key)
    JOIN ltm t USING (period_key)
    -- the first eleven months of the window are incomplete, so no leverage is reported for
    -- them rather than a ratio computed on a partial year
    WHERE t.months_in_window = 12
    ORDER BY ALL
    """)
    rows("mart_covenants")

    con.execute("""
    CREATE OR REPLACE TABLE mart_fx AS
    WITH rates AS (
        SELECT currency_code, period_key,
               max(rate_usd_per_unit) FILTER (WHERE rate_type = 'AVG') AS avg_rate,
               max(rate_usd_per_unit) FILTER (WHERE rate_type = 'CLOSE') AS close_rate
        FROM ref_fx_rate WHERE rate_set = 'ACTUAL' GROUP BY ALL
    ),
    exposure AS (
        SELECT e.functional_currency AS currency_code, m.period_key,
               round(-coalesce(sum(m.amount_usd) FILTER (WHERE m.line = 'REVENUE'), 0), 2)
                   AS revenue_usd,
               round(-coalesce(sum(m.amount_usd) FILTER (
                   WHERE m.line IN ('REVENUE', 'COST_OF_SALES', 'OPEX')), 0), 2) AS ebitda_usd
        FROM mart_financial_monthly m JOIN dim_entity e USING (entity_code)
        WHERE m.scenario_code = 'ACT' AND m.basis = 'STATUTORY' AND NOT m.is_intercompany
        GROUP BY ALL
    ),
    cta AS (
        SELECT entity_code, period_key, currency_code,
               round(cta_movement_usd, 2) AS cta_movement_usd,
               round(cta_group_usd, 2) AS cta_group_usd,
               round(cta_nci_usd, 2) AS cta_nci_usd
        FROM stg_cta_movement
    )
    SELECT r.currency_code, r.period_key,
           CAST(r.period_key / 100 AS INTEGER) AS fiscal_year,
           r.avg_rate, r.close_rate,
           lag(r.avg_rate, 12) OVER (PARTITION BY r.currency_code ORDER BY r.period_key)
               AS avg_rate_py,
           coalesce(x.revenue_usd, 0) AS revenue_usd,
           coalesce(x.ebitda_usd, 0) AS ebitda_usd,
           -- constant currency: this year's activity at last year's average rate. It is an
           -- operating measure and is NOT the translation adjustment, which is an equity
           -- reserve arising on net assets and appears in its own column.
           round(coalesce(x.revenue_usd, 0)
                 / nullif(r.avg_rate, 0)
                 * coalesce(lag(r.avg_rate, 12) OVER (PARTITION BY r.currency_code
                                                      ORDER BY r.period_key), r.avg_rate), 2)
               AS revenue_constant_ccy_usd,
           round(coalesce(c.cta_movement_usd, 0), 2) AS cta_movement_usd,
           round(coalesce(c.cta_group_usd, 0), 2) AS cta_group_usd,
           round(coalesce(c.cta_nci_usd, 0), 2) AS cta_nci_usd
    FROM rates r
    LEFT JOIN exposure x USING (currency_code, period_key)
    LEFT JOIN (SELECT currency_code, period_key, sum(cta_movement_usd) AS cta_movement_usd,
                      sum(cta_group_usd) AS cta_group_usd, sum(cta_nci_usd) AS cta_nci_usd
               FROM cta GROUP BY ALL) c USING (currency_code, period_key)
    ORDER BY ALL
    """)
    rows("mart_fx")

    # ================================================================= governance marts
    con.execute("""
    CREATE OR REPLACE TABLE mart_management_adjustments AS
    SELECT a.adjustment_id, a.category, a.basis, a.entity_code, a.group_account,
           a.offset_account, a.period_from, a.period_to, a.amount_usd,
           a.ebitda_treatment, a.covenant_treatment, a.approval_status,
           a.preparer, a.approver, a.rationale,
           coalesce(j.legs_posted, 0) AS legs_posted,
           round(coalesce(j.posted_usd, 0), 2) AS posted_usd
    FROM ref_management_adjustment a
    LEFT JOIN (SELECT rule_id, count(*) AS legs_posted,
                      sum(abs(amount_usd)) / 2 AS posted_usd
               FROM fact_consol_journal WHERE process = 'MGMT_ADJ' GROUP BY 1) j
           ON j.rule_id = a.adjustment_id
    ORDER BY ALL
    """)
    rows("mart_management_adjustments")

    con.execute("""
    CREATE OR REPLACE TABLE mart_consolidation_bridge AS
    -- Every declared layer appears, including any that posted nothing. Layer 4 is empty on
    -- the approved register, and a reader who cannot see it on the page has no way to know
    -- the management layer exists at all -- which is the one thing this sheet is for.
    SELECT l.layer_id, l.layer_code, l.layer_name, l.in_statutory_view, l.in_management_view,
           y.fiscal_year,
           round(coalesce(b.ebitda_usd, 0), 2) AS ebitda_usd,
           round(coalesce(b.net_income_usd, 0), 2) AS net_income_usd,
           round(coalesce(b.total_assets_movement_usd, 0), 2) AS total_assets_movement_usd,
           round(coalesce(b.total_equity_movement_usd, 0), 2) AS total_equity_movement_usd,
           coalesce(p.entries, 0) AS entries, coalesce(p.legs, 0) AS legs
    FROM dim_consolidation_layer l
    CROSS JOIN (SELECT DISTINCT fiscal_year FROM rpt_layer_bridge) y
    LEFT JOIN rpt_layer_bridge b ON b.layer_id = l.layer_id AND b.fiscal_year = y.fiscal_year
    LEFT JOIN (SELECT layer_id, fiscal_year, count(DISTINCT consol_journal_id) AS entries,
                      count(*) AS legs
               FROM fact_consol_journal GROUP BY ALL) p
           ON p.layer_id = l.layer_id AND p.fiscal_year = y.fiscal_year
    ORDER BY ALL
    """)
    rows("mart_consolidation_bridge")

    return counts
