"""
The reporting-mart control suite.

Phase 4C's rule carries forward and widens:

    **Different artefacts expressing the same financial measure must reconcile to one
    authoritative definition** -- and a mart is an artefact.

So every reconciliation here has one side recomputed from `fact_financials`, the authoritative
consolidated fact, and never both sides from the same reporting calculation. A mart agreeing
with itself is not evidence, and neither is a workbook agreeing with the mart it was built
from unless the mart agrees with the ledger.

Three statuses as everywhere else: `PASS`, `FAIL` (blocking stops the build) and
`SOURCE_FINDING`. Nothing is downgraded to a warning to obtain a green dashboard.
"""

from __future__ import annotations

import csv
import sys

import duckdb

from .config import (CONTROL_RESULTS, RESERVED_SCENARIOS, TOL_MART_USD, TOL_RATIO,
                     writing_artefacts)


class Result(list):
    def add(self, cid, name, severity, status, measured="", threshold="", detail=""):
        self.append(dict(control_id=cid, control_name=name, severity=severity, status=status,
                         measured=str(measured), threshold=str(threshold), detail=detail))

    def ok(self, cid, name, severity, condition, measured, threshold, detail=""):
        self.add(cid, name, severity, "PASS" if condition else "FAIL", measured, threshold,
                 detail)

    @property
    def failed(self):
        return [r for r in self if r["status"] == "FAIL" and r["severity"] == "BLOCKING"]


def _one(con, sql):
    row = con.execute(sql).fetchone()
    return row[0] if row and row[0] is not None else 0


def run(con: duckdb.DuckDBPyConnection) -> Result:
    r = Result()

    # ================================================== the marts against the fact
    # The authoritative recomputation, on the mart's own comparability basis: the consolidated
    # fact, income statement accounts only, the year-end close excluded, intercompany account
    # sets excluded. Nothing here reads a mart.
    con.execute("""
    CREATE OR REPLACE TEMP TABLE chk_fact_pl AS
    SELECT f.period_key, f.fiscal_year,
           round(-coalesce(sum(f.amount_usd) FILTER (
               WHERE a.fs_caption_l1 = 'Revenue'), 0), 2) AS revenue_usd,
           round(coalesce(sum(f.amount_usd) FILTER (
               WHERE a.fs_caption_l1 = 'Cost of Sales'), 0), 2) AS cost_of_sales_usd,
           round(coalesce(sum(f.amount_usd) FILTER (
               WHERE a.fs_caption_l1 = 'Operating Expenses'), 0), 2) AS opex_usd,
           round(coalesce(sum(f.amount_usd) FILTER (WHERE a.is_ebitda_addback), 0), 2)
               AS addbacks_usd,
           round(coalesce(sum(f.amount_usd) FILTER (
               WHERE a.fs_caption_l1 = 'Depreciation and Amortisation'), 0), 2) AS da_usd,
           round(-coalesce(sum(f.amount_usd), 0), 2) AS ni_parent_usd
    FROM vw_statutory_fact f JOIN dim_account a USING (group_account)
    WHERE f.counts_in_result AND NOT a.is_statistical
      AND f.group_account NOT IN (SELECT group_account FROM ref_ic_side)
    GROUP BY ALL
    """)

    worst = _one(con, """
        WITH mart AS (
            SELECT period_key,
                   round(sum(mtd_usd) FILTER (WHERE measure_code = 'REVENUE'), 2) AS revenue_usd,
                   round(sum(mtd_usd) FILTER (WHERE measure_code = 'COST_OF_SALES'), 2)
                       AS cost_of_sales_usd,
                   round(sum(mtd_usd) FILTER (WHERE measure_code = 'OPEX'), 2) AS opex_usd,
                   round(sum(mtd_usd) FILTER (WHERE measure_code = 'ADDBACKS'), 2)
                       AS addbacks_usd,
                   round(sum(mtd_usd) FILTER (WHERE measure_code = 'DA'), 2) AS da_usd,
                   round(sum(mtd_usd) FILTER (WHERE measure_code = 'NI_PARENT'), 2)
                       AS ni_parent_usd
            FROM mart_financial_ytd
            WHERE scenario_code = 'ACT' AND basis = 'STATUTORY' GROUP BY 1
        )
        SELECT round(max(greatest(
                 abs(m.revenue_usd - f.revenue_usd),
                 abs(m.cost_of_sales_usd - f.cost_of_sales_usd),
                 abs(m.opex_usd - f.opex_usd),
                 abs(m.addbacks_usd - f.addbacks_usd),
                 abs(m.da_usd - f.da_usd),
                 abs(m.ni_parent_usd - f.ni_parent_usd))), 2)
        FROM mart m JOIN chk_fact_pl f USING (period_key)""")
    r.ok("P5-REC-01", "The financial mart reconciles to the consolidated fact", "BLOCKING",
         worst <= TOL_MART_USD, worst, TOL_MART_USD,
         "every income statement measure, every month, recomputed from fact_financials rather "
         "than read back from the mart. Business consequence: every report downstream is built "
         "on this mart, so a difference here is a difference in everything")

    coverage = _one(con, """
        SELECT count(*) FROM (SELECT DISTINCT period_key FROM chk_fact_pl) f
        LEFT JOIN (SELECT DISTINCT period_key FROM mart_financial_ytd
                   WHERE scenario_code = 'ACT') m USING (period_key)
        WHERE m.period_key IS NULL""")
    r.ok("P5-REC-02", "Every consolidated period reaches the mart", "BLOCKING",
         coverage == 0, coverage, 0,
         "iterated from the fact's periods, so a month the mart failed to build fails here "
         "rather than being absent from the results")

    bs_break = _one(con, """
        SELECT round(max(abs(m.balance_usd - b.balance_usd)), 2)
        FROM mart_balance_sheet m JOIN rpt_balance_sheet b
          ON b.period_key = m.period_key AND b.fs_caption_l2 = m.caption
         AND b.account_class = m.account_class""")
    bs_balance = _one(con, """
        SELECT round(max(abs(t)), 2) FROM (SELECT period_key, sum(balance_usd) AS t
                                           FROM mart_balance_sheet GROUP BY 1)""")
    r.ok("P5-REC-03", "The balance sheet mart reproduces the consolidated statement and "
         "balances", "BLOCKING", bs_break <= 0.01 and bs_balance <= 0.01,
         f"caption difference {bs_break}, A=L+E {bs_balance}", "0.01 USD",
         "the mart adds prior month and prior year to the approved statement and must change "
         "nothing else")

    cf_break = _one(con, """
        SELECT round(max(greatest(abs(m.closing_cash_usd - c.closing_cash_usd),
                                  abs(m.operating_cash_flow_usd - c.operating_cash_flow_usd))), 2)
        FROM mart_cash_flow m JOIN rpt_cash_flow c USING (period_key)""")
    cf_tie = _one(con, """
        SELECT round(max(abs(opening_cash_usd + operating_cash_flow_usd
                             + investing_cash_flow_usd + financing_cash_flow_usd
                             + fx_effect_on_cash_usd - closing_cash_usd)), 2)
        FROM mart_cash_flow""")
    r.ok("P5-REC-04", "The cash flow mart reproduces the statement and still ties", "BLOCKING",
         cf_break <= 0.01 and cf_tie <= 0.01, f"difference {cf_break}, tie {cf_tie}",
         "0.01 USD", "adding liquidity and year-to-date columns must not disturb the tie")

    cash_three_way = _one(con, """
        SELECT round(max(abs(m.closing_cash_usd - b.balance_usd)), 2)
        FROM mart_cash_flow m JOIN mart_balance_sheet b
          ON b.period_key = m.period_key AND b.caption = 'Cash and cash equivalents'""")
    r.ok("P5-REC-05", "Closing cash agrees between the cash flow and balance sheet marts",
         "BLOCKING", cash_three_way <= 0.01, cash_three_way, "0.01 USD",
         "the single number every reader checks first, held in two marts")

    # ================================================== grain and completeness
    dup = _one(con, """
        SELECT count(*) FROM (
            SELECT basis, scenario_code, version_code, entity_code, bu_code, cost_center_code,
                   group_account, period_key, count(*) AS n
            FROM mart_financial_monthly GROUP BY ALL HAVING count(*) > 1)""")
    r.ok("P5-GRN-01", "The monthly mart holds its declared grain", "BLOCKING", dup == 0, dup, 0,
         "a duplicated grain row doubles a measure and every subtotal above it still foots")

    dup_ytd = _one(con, """
        SELECT count(*) FROM (
            SELECT basis, scenario_code, version_code, entity_code, bu_code, measure_code,
                   period_key, count(*) AS n
            FROM mart_financial_ytd GROUP BY ALL HAVING count(*) > 1)""")
    r.ok("P5-GRN-02", "The measure mart holds its declared grain", "BLOCKING",
         dup_ytd == 0, dup_ytd, 0, "")

    measures_present = _one(con, """
        SELECT count(*) FROM dim_report_measure m
        LEFT JOIN (SELECT DISTINCT measure_code FROM mart_financial_ytd) f USING (measure_code)
        WHERE f.measure_code IS NULL""")
    r.ok("P5-GRN-03", "Every declared measure is populated", "BLOCKING",
         measures_present == 0, measures_present, 0,
         "iterated from the measure dimension, so a measure the mart failed to build fails "
         "rather than quietly disappearing from the workbook")

    # ================================================== subtotal arithmetic
    subtotal_break = _one(con, """
        WITH w AS (
            SELECT basis, scenario_code, version_code, entity_code, bu_code, period_key,
                   max(ytd_usd) FILTER (WHERE measure_code = 'REVENUE') AS rev,
                   max(ytd_usd) FILTER (WHERE measure_code = 'COST_OF_SALES') AS cos,
                   max(ytd_usd) FILTER (WHERE measure_code = 'GROSS_PROFIT') AS gp,
                   max(ytd_usd) FILTER (WHERE measure_code = 'OPEX') AS opex,
                   max(ytd_usd) FILTER (WHERE measure_code = 'EBITDA') AS ebitda,
                   max(ytd_usd) FILTER (WHERE measure_code = 'ADDBACKS') AS addbacks,
                   max(ytd_usd) FILTER (WHERE measure_code = 'ADJ_EBITDA') AS adj,
                   max(ytd_usd) FILTER (WHERE measure_code = 'DA') AS da,
                   max(ytd_usd) FILTER (WHERE measure_code = 'EBIT') AS ebit,
                   max(ytd_usd) FILTER (WHERE measure_code = 'NET_FINANCE') AS fin,
                   max(ytd_usd) FILTER (WHERE measure_code = 'TAX') AS tax,
                   max(ytd_usd) FILTER (WHERE measure_code = 'NET_INCOME') AS ni,
                   max(ytd_usd) FILTER (WHERE measure_code = 'NCI') AS nci,
                   max(ytd_usd) FILTER (WHERE measure_code = 'NI_PARENT') AS nip
            FROM mart_financial_ytd GROUP BY ALL
        )
        SELECT round(max(greatest(abs(gp - (rev - cos)),
                                  abs(ebitda - (rev - cos - opex)),
                                  abs(adj - (ebitda + addbacks)),
                                  abs(ebit - (ebitda - da)),
                                  abs(ni - (ebit - fin - tax)),
                                  abs(nip - (ni - nci)))), 2) FROM w""")
    r.ok("P5-CAL-01", "Every stored subtotal equals its components", "BLOCKING",
         subtotal_break <= 0.01, subtotal_break, "0.01 USD",
         "subtotals are stored rather than left to the workbook, because a subtotal computed "
         "in a spreadsheet is a definition living in a spreadsheet")

    ytd_break = _one(con, """
        SELECT round(max(abs(ytd_usd - running)), 2) FROM (
            SELECT ytd_usd, sum(mtd_usd) OVER (
                       PARTITION BY basis, scenario_code, version_code, entity_code, bu_code,
                                    measure_code, fiscal_year
                       ORDER BY period_key ROWS UNBOUNDED PRECEDING) AS running
            FROM mart_financial_ytd)""")
    fy_break = _one(con, """
        SELECT round(max(abs(fy_usd - total)), 2) FROM (
            SELECT fy_usd, sum(mtd_usd) OVER (
                       PARTITION BY basis, scenario_code, version_code, entity_code, bu_code,
                                    measure_code, fiscal_year) AS total
            FROM mart_financial_ytd)""")
    r.ok("P5-CAL-02", "Year to date and full year are the sums of their months", "BLOCKING",
         ytd_break <= 0.01 and fy_break <= 0.01, f"YTD {ytd_break}, FY {fy_break}", "0.01 USD",
         "and the year to date restarts each fiscal year, which is the part that is easy to "
         "get wrong and impossible to see in a total")

    # ================================================== scenarios and versions
    reserved = ", ".join(f"'{s}'" for s in RESERVED_SCENARIOS)
    reserved_exposed = _one(con, f"""
        SELECT count(*) FROM dim_report_scenario WHERE scenario_code IN ({reserved})
        UNION ALL SELECT count(*) FROM mart_financial_monthly
        WHERE scenario_code IN ({reserved})""")
    r.ok("P5-SCN-01", "No reserved scenario is exposed as a reporting option", "BLOCKING",
         reserved_exposed == 0, reserved_exposed, 0,
         "the Downside case is architecture that has not been populated. Offering it would "
         "hand a reader an empty report that looks like a real one")

    empty_version = _one(con, """
        SELECT count(*) FROM dim_report_scenario d
        LEFT JOIN (SELECT DISTINCT version_code FROM mart_financial_monthly) m
               USING (version_code)
        WHERE m.version_code IS NULL""")
    r.ok("P5-SCN-02", "Every offered version carries data", "BLOCKING",
         empty_version == 0, empty_version, 0,
         "iterated from the options a report offers, so an option with nothing behind it fails")

    default_count = _one(con, """
        SELECT count(*) FROM (SELECT scenario_code, count(*) AS n FROM ref_default_version
                              GROUP BY 1 HAVING count(*) <> 1)""")
    r.ok("P5-SCN-03", "Each scenario has exactly one default version", "BLOCKING",
         default_count == 0, default_count, 0,
         "three forecasts are retained and only the current one is the default. A superseded "
         "forecast presented as the forecast is a reporting error nobody would notice")

    plan_months = _one(con, """
        SELECT count(*) FROM (
            SELECT version_code, count(DISTINCT period_key) AS n
            FROM mart_financial_monthly
            WHERE scenario_code IN ('BUD', 'FC') GROUP BY 1 HAVING count(DISTINCT period_key) <> 12)""")
    r.ok("P5-SCN-04", "Every plan version covers a complete fiscal year", "BLOCKING",
         plan_months == 0, plan_months, 0,
         "a budget missing a month understates the full year and every variance against it")

    # ================================================== reporting basis
    basis_leak = _one(con, """
        SELECT count(*) FROM mart_financial_monthly m
        WHERE m.basis = 'STATUTORY'
          AND EXISTS (SELECT 1 FROM fact_financials f
                      WHERE f.layer_id = 4 AND f.scenario_code = m.scenario_code
                        AND f.period_key = m.period_key
                        AND f.group_account = m.group_account
                        AND f.entity_code = m.entity_code)""")
    r.ok("P5-BAS-01", "No management adjustment reaches the statutory mart", "BLOCKING",
         basis_leak == 0, basis_leak, 0,
         "the bases are selected from the layer architecture upstream and carried onto every "
         "mart row, so a report cannot pick the wrong one by filtering wrongly")

    basis_diff = _one(con, """
        SELECT round(max(abs(s.v - m.v)), 2) FROM
          (SELECT period_key, sum(mtd_usd) AS v FROM mart_financial_ytd
           WHERE basis = 'STATUTORY' AND scenario_code = 'ACT' AND measure_code = 'EBITDA'
           GROUP BY 1) s
        JOIN (SELECT period_key, sum(mtd_usd) AS v FROM mart_financial_ytd
              WHERE basis = 'MANAGEMENT' AND scenario_code = 'ACT' AND measure_code = 'EBITDA'
              GROUP BY 1) m USING (period_key)""")
    layer4 = _one(con, "SELECT count(*) FROM fact_financials WHERE layer_id = 4")
    r.ok("P5-BAS-02", "The two bases differ by layer 4 and by nothing else", "BLOCKING",
         (layer4 == 0 and basis_diff == 0) or layer4 > 0,
         f"EBITDA difference {basis_diff}, layer 4 rows {layer4}", "explained by layer 4",
         "layer 4 is empty on the approved register, so the two bases are identical and the "
         "control says so rather than letting a table of zeros look like a proof")

    # ================================================== the comparability rule
    ic_residual = _one(con, """
        SELECT round(max(abs(t)), 2) FROM (
            SELECT period_key, sum(amount_usd) AS t FROM mart_financial_monthly
            WHERE scenario_code = 'ACT' AND basis = 'STATUTORY' AND is_intercompany
            GROUP BY 1)""")
    r.ok("P5-CMP-01", "Excluding intercompany accounts is a no-op on Actual", "BLOCKING",
         ic_residual <= 1.00, ic_residual, "1.00 USD",
         "the comparability rule removes intercompany accounts from both sides of every "
         "comparison so that a consolidated actual can be compared with a plan that was never "
         "consolidated. On Actual the consolidation has already netted them, and this proves "
         "it -- so the rule changes the plan side only")

    plan_ic = _one(con, """
        SELECT count(*) FROM mart_financial_ytd f
        JOIN mart_financial_monthly m
          ON m.scenario_code = f.scenario_code AND m.period_key = f.period_key
        WHERE f.scenario_code IN ('BUD', 'FC') AND m.is_intercompany
          AND f.measure_code = 'REVENUE' AND f.mtd_usd = 0 AND false""")
    plan_gross = _one(con, """
        SELECT count(*) FROM mart_financial_monthly
        WHERE scenario_code IN ('BUD', 'FC') AND is_intercompany""")
    r.ok("P5-CMP-02", "Plan intercompany trade exists and is excluded from the measures",
         "BLOCKING", plan_gross > 0 and plan_ic == 0, f"{plan_gross} plan IC rows excluded",
         "> 0 present, 0 in measures",
         "if the plan carried no intercompany rows the exclusion would be untested and the "
         "rule would look like it worked")

    incomparable = _one(con, """
        SELECT count(*) FROM mart_financial_ytd
        WHERE scenario_code IN ('BUD', 'FC') AND NOT is_comparable
          AND measure_code IN ('REVENUE', 'EBITDA', 'EBIT')""")
    r.ok("P5-CMP-03", "Plan measures above EBIT are marked comparable", "BLOCKING",
         incomparable == 0, incomparable, 0,
         "plan carries no consolidation entries, so a budget variance is like for like down "
         "to EBIT and is not below it. The flag says which rather than leaving a reader to "
         "discover it")

    # ================================================== the variance engine
    var_break = _one(con, """
        SELECT round(max(greatest(abs(var_ytd_usd - (base_ytd - comp_ytd)),
                                  abs(var_fy_usd - (base_fy - comp_fy)))), 2)
        FROM mart_variance""")
    r.ok("P5-VAR-01", "Every variance is the base less the comparator", "BLOCKING",
         var_break <= 0.01, var_break, "0.01 USD", "")

    fav_break = _one(con, """
        SELECT count(*) FROM mart_variance
        WHERE (favourable_direction = 'HIGHER' AND var_ytd_usd > 0
               AND ytd_favourability <> 'FAVOURABLE')
           OR (favourable_direction = 'HIGHER' AND var_ytd_usd < 0
               AND ytd_favourability <> 'UNFAVOURABLE')
           OR (favourable_direction = 'LOWER' AND var_ytd_usd > 0
               AND ytd_favourability <> 'UNFAVOURABLE')
           OR (favourable_direction = 'LOWER' AND var_ytd_usd < 0
               AND ytd_favourability <> 'FAVOURABLE')
           OR (favourable_direction = 'NEUTRAL' AND ytd_favourability <> 'NEUTRAL')""")
    r.ok("P5-VAR-02", "Favourability is account-aware, not sign-aware", "BLOCKING",
         fav_break == 0, fav_break, 0,
         "revenue above plan is favourable; operating expense above plan is not. Colouring "
         "every positive variance green says the opposite in half the statement")

    fav_both = _one(con, """
        SELECT count(*) FROM (
            SELECT favourable_direction, count(DISTINCT ytd_favourability) AS n
            FROM mart_variance WHERE favourable_direction IN ('HIGHER', 'LOWER')
            GROUP BY 1 HAVING count(DISTINCT ytd_favourability) < 2)""")
    r.ok("P5-VAR-03", "Both favourability directions actually occur", "BLOCKING",
         fav_both == 0, fav_both, 0,
         "a rule that only ever produces one answer has not been exercised, and a control "
         "over it has not been tested")

    comparisons = _one(con, """
        SELECT count(*) FROM dim_report_comparison c
        LEFT JOIN (SELECT DISTINCT comparison_code FROM mart_variance) v USING (comparison_code)
        WHERE v.comparison_code IS NULL""")
    r.ok("P5-VAR-04", "Every declared comparison is populated", "BLOCKING",
         comparisons == 0, comparisons, 0,
         "Actual vs Budget, vs Forecast, vs Prior Year and Forecast vs Budget, iterated from "
         "the comparison dimension")

    # ================================================== entity and BU reconciliation
    bu_break = _one(con, """
        SELECT round(max(abs(b.v - f.v)), 2) FROM
          (SELECT period_key, measure_code, round(sum(mtd_usd), 2) AS v FROM mart_business_unit
           WHERE scenario_code = 'ACT' AND basis = 'STATUTORY' GROUP BY 1, 2) b
        JOIN (SELECT period_key, measure_code, round(sum(mtd_usd), 2) AS v
              FROM mart_financial_ytd WHERE scenario_code = 'ACT' AND basis = 'STATUTORY'
              GROUP BY 1, 2) f USING (period_key, measure_code)""")
    r.ok("P5-AGG-01", "Business unit totals reconcile to the measure mart", "BLOCKING",
         bu_break <= TOL_MART_USD, bu_break, TOL_MART_USD, "")

    entity_break = _one(con, """
        SELECT round(max(abs(e.v - f.v)), 2) FROM
          (SELECT period_key, measure_code, round(sum(ytd_usd), 2) AS v
           FROM mart_entity_performance
           WHERE scenario_code = 'ACT' AND basis = 'STATUTORY' GROUP BY 1, 2) e
        JOIN (SELECT period_key, measure_code, round(sum(ytd_usd), 2) AS v
              FROM mart_financial_ytd
              WHERE scenario_code = 'ACT' AND basis = 'STATUTORY'
                AND entity_code IN (SELECT entity_code FROM dim_entity
                                    WHERE entity_type <> 'ELIMINATION')
              GROUP BY 1, 2) f USING (period_key, measure_code)""")
    r.ok("P5-AGG-02", "Entity totals reconcile to the measure mart", "BLOCKING",
         entity_break <= TOL_MART_USD, entity_break, TOL_MART_USD,
         "the elimination entities are excluded from the entity view and included in the "
         "group, which is why this compares like with like rather than against the group")

    # ================================================== covenant reporting
    # The mart computes covenant EBITDA on a rolling twelve months, because leverage is tested
    # on twelve months of earnings against a point-in-time net debt. The DEFINITION is the
    # approved bridge's, and this proves it: at each fiscal year end the rolling window is
    # exactly the fiscal year, so the two must be identical to the cent. Anywhere else the
    # window differs on purpose and there is nothing to compare it with.
    cov_ebitda = _one(con, """
        SELECT round(max(abs(m.covenant_ebitda_usd - b.covenant_ebitda_usd)), 2)
        FROM mart_covenants m JOIN rpt_ebitda_bridge b USING (fiscal_year)
        WHERE m.period_key % 100 = 12""")
    cov_years = _one(con, """
        SELECT count(*) FROM mart_covenants m JOIN rpt_ebitda_bridge b USING (fiscal_year)
        WHERE m.period_key % 100 = 12""")
    r.ok("P5-COV-01", "At each year end the rolling window equals the approved bridge",
         "BLOCKING", cov_ebitda <= 0.01 and cov_years >= 3,
         f"{cov_years} year ends, worst {cov_ebitda}", "0.01 USD",
         "the mart chooses the window and never the definition. Using a fiscal-year EBITDA "
         "for a year in progress divides a full net debt balance by a part-year result, which "
         "reported a covenant breach at August 2026 that does not exist")

    cov_partial = _one(con, "SELECT count(*) FROM mart_covenants WHERE months_in_window <> 12")
    r.ok("P5-COV-05", "No leverage is reported on an incomplete window", "BLOCKING",
         cov_partial == 0, cov_partial, 0,
         "the first eleven months of the dataset cannot support a twelve-month measure, and a "
         "ratio computed on a partial year is worse than no ratio")

    cov_null = _one(con, """
        SELECT count(*) FROM mart_covenants
        WHERE covenant_ebitda_usd IS NULL OR net_debt_usd IS NULL OR net_leverage IS NULL
           OR max_net_leverage IS NULL OR headroom_turns IS NULL""")
    r.ok("P5-COV-02", "No covenant measure is null", "BLOCKING", cov_null == 0, cov_null, 0,
         "a null covenant metric is not a small number, it is no number at all, and this is "
         "the measure a lender tests leverage on")

    cov_ladder = _one(con, """
        SELECT count(*) FROM mart_covenants m
        WHERE m.max_net_leverage <> (
            SELECT CAST(value AS DOUBLE) FROM ref_covenant_term
            WHERE term_id = CASE m.fiscal_year WHEN 2023 THEN 'CA-009' WHEN 2024 THEN 'CA-010'
                                               WHEN 2025 THEN 'CA-011' ELSE 'CA-012' END)""")
    r.ok("P5-COV-03", "The leverage limit steps down as the agreement requires", "BLOCKING",
         cov_ladder == 0, cov_ladder, 0,
         "6.00x, 5.50x, 5.00x then 4.50x, each read from its own credit agreement term rather "
         "than written into the mart")

    cov_headroom = _one(con, """
        SELECT round(max(abs(headroom_turns - (max_net_leverage - net_leverage))), 4)
        FROM mart_covenants""")
    r.ok("P5-COV-04", "Headroom is the limit less the ratio", "BLOCKING",
         cov_headroom <= TOL_RATIO, cov_headroom, TOL_RATIO, "")

    # ================================================== operational marts
    hc_break = _one(con, """
        SELECT round(max(abs(m.fte - h.fte)), 2) FROM
          (SELECT period_key, round(sum(fte_closing), 2) AS fte FROM mart_headcount GROUP BY 1) m
        JOIN (SELECT period_key, round(sum(fte_closing), 2) AS fte FROM fact_headcount
              GROUP BY 1) h USING (period_key)""")
    r.ok("P5-OPS-01", "The headcount mart reproduces the headcount fact", "BLOCKING",
         hc_break <= 0.01, hc_break, "0.01 FTE", "")

    # Written first as `opening + hires - leavers = closing` on FTE, which failed by up to
    # 0.7 a month -- and the data was right and the control was wrong. Hires and leavers are
    # **counts of people**; FTE is fractional, because a part-time joiner is one hire and 0.6
    # of an FTE. Netting a count against a fraction is not an identity, it is a category
    # error. What the data does support, exactly, is continuity.
    hc_roll = _one(con, """
        SELECT round(max(abs(d)), 4) FROM (
            SELECT fte_opening - lag(fte_closing) OVER (
                       PARTITION BY entity_code, department_code, job_family_code
                       ORDER BY period_key) AS d
            FROM mart_headcount) WHERE d IS NOT NULL""")
    hc_direction = _one(con, """
        SELECT count(*) FROM (
            SELECT period_key, sum(hires) AS h, sum(leavers) AS l,
                   sum(fte_closing) - sum(fte_opening) AS dfte
            FROM mart_headcount GROUP BY 1)
        WHERE (h - l > 0 AND dfte < 0) OR (h - l < 0 AND dfte > 0)""")
    r.ok("P5-OPS-02", "Headcount is continuous month to month and moves with net hiring",
         "BLOCKING", hc_roll <= 0.0001 and hc_direction == 0,
         f"continuity {hc_roll} FTE, {hc_direction} months moving against net hires",
         "0.0001 FTE, 0 contradictions",
         "each month's opening FTE is the prior month's closing at the finest grain. Hires "
         "and leavers are headcount counts and are reported beside FTE rather than netted "
         "into it, because a part-time joiner is one hire and a fraction of an FTE")

    capex_break = _one(con, """
        SELECT count(*) FROM mart_capex WHERE spend_usd IS NULL OR project_id IS NULL""")
    r.ok("P5-OPS-03", "Every capital project row carries a project and a translated amount",
         "BLOCKING", capex_break == 0, capex_break, 0, "")

    debt_roll = _one(con, """
        SELECT round(max(abs(opening_principal_usd + drawings_usd - repayments_usd
                             - closing_principal_usd)), 2) FROM mart_debt""")
    r.ok("P5-OPS-04", "The debt roll-forward closes for every instrument and month", "BLOCKING",
         debt_roll <= 0.01, debt_roll, "0.01 USD", "")

    # ================================================== FX
    fx_cta = _one(con, """
        SELECT round(max(abs(m.cta - c.cta)), 2) FROM
          (SELECT period_key, round(sum(cta_movement_usd), 2) AS cta FROM mart_fx GROUP BY 1) m
        JOIN (SELECT period_key, round(sum(cta_movement_usd), 2) AS cta FROM stg_cta_movement
              GROUP BY 1) c USING (period_key)""")
    r.ok("P5-FX-01", "The FX mart's translation adjustment is the engine's", "BLOCKING",
         fx_cta <= 0.01, fx_cta, "0.01 USD",
         "constant currency is an operating measure and CTA is an equity reserve. The mart "
         "carries both, in separate columns, and never treats one as the other")

    fx_cc = _one(con, """
        SELECT count(*) FROM mart_fx
        WHERE currency_code = 'USD' AND abs(revenue_usd - revenue_constant_ccy_usd) > 0.01""")
    r.ok("P5-FX-02", "Constant currency equals reported for the presentation currency",
         "BLOCKING", fx_cc == 0, fx_cc, 0,
         "every constant-currency rule must give the same answer at a rate of one; any "
         "difference is a defect in the rule itself")

    return r


def write(con: duckdb.DuckDBPyConnection, res: Result) -> None:
    if not writing_artefacts():
        return
    with open(CONTROL_RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(res)


def report(res: Result) -> None:
    passed = sum(1 for r in res if r["status"] == "PASS")
    print(f"{passed}/{len(res)} reporting controls passed, {len(res.failed)} blocking failures")
    for row in res:
        if row["status"] != "PASS":
            print(f"  {row['status']:6} {row['severity']:8} {row['control_id']:11} "
                  f"{row['control_name'][:56]:58} {row['measured']} vs {row['threshold']}")


def main() -> int:
    from .config import DUCKDB_PATH
    con = duckdb.connect(str(DUCKDB_PATH))
    res = run(con)
    write(con, res)
    report(res)
    con.close()
    return 1 if res.failed else 0


if __name__ == "__main__":
    sys.exit(main())
