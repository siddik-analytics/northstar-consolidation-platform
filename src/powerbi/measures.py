"""
The DAX measure layer, declared once.

Every measure below is written into TMDL, documented in `docs/powerbi-measures.md`, and
reconciled by the `P6-XAR` controls against a figure computed independently from the marts.
Declaring them in one place is what keeps those three in step: a measure cannot enter the model
without acquiring a description and a reconciliation.

## The rule this layer exists to honour

**Power BI is not a second accounting engine.** EBITDA, the add-back policy, FX translation,
CTA, NCI, PPA, unrealised profit, statutory and management membership, the covenant definition
and the cash-flow classification are all settled upstream and arrive on the mart row. What DAX
does is aggregate a governed column and occasionally divide one governed column by another.
Where a measure looks like it is deciding something, it is selecting a column that was decided
upstream.

## Period basis: a disconnected dimension, not a calculation group

`mart_financial_ytd` publishes three governed columns for every measure -- `mtd_usd`,
`ytd_usd`, `fy_usd`. Three ways to expose them were available:

* **forty-two measures**, three per statement line. Rejected: the same definition written three
  times drifts three ways;
* **a calculation group.** Rejected on inspection rather than on principle. A calculation group
  rewrites a measure's *filter context*; these three columns are not a filter of one another,
  they are three stored results, and switching between them needs a column reference to change.
  That is not what calculation groups do, and forcing it produces something a reviewer cannot
  read;
* **a disconnected `Period Basis` table read by `SWITCH`.** One slicer drives month,
  year-to-date and full-year across every statement measure, each measure states its own three
  columns, and there is no hidden machinery. This is what the model does.

The brief warns against sophistication introduced to demonstrate skill. A calculation group
here would have been exactly that.

## Blank is not zero

A measure returns `BLANK()` when the population is genuinely absent -- an Actual month after
the reporting close has not happened, and reporting it as zero says the group earned nothing.
A measure returns **zero** when a component exists and is nil, which is the Phase 4C rule
carried forward: an add-back category with no population contributes zero, never NULL, because
one nil component must not void a bridge.

Both are enforced explicitly. Actual measures carry the cutoff guard; every additive bridge
component is coalesced with `+ 0` where it is summed.
"""

from __future__ import annotations

REPORT_PERIOD = 202608

#: Read a governed measure column on the period basis the report has selected. The three
#: columns are stored results, so the switch is a column choice and not a recalculation.
PERIOD_SWITCH = """VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "{code}" )
    )
RETURN {wrap}"""


def statement_measure(code: str, coalesce: bool = False) -> str:
    return PERIOD_SWITCH.format(code=code, wrap="_Value + 0" if coalesce else "_Value")


#: The cutoff guard. A month the group has not closed returns BLANK rather than zero, so a
#: chart breaks the line instead of drawing a cliff and a total does not quietly include
#: months that do not exist.
def cutoff(inner: str) -> str:
    return (f"VAR _Latest = MAX ( 'Date'[period_key] )\n"
            f"RETURN IF ( _Latest > [Reporting Period Key], BLANK (), {inner} )")


def caption(name: str, account_class: str, negate: bool = False) -> str:
    sign = "-" if negate else ""
    return (f"{sign}CALCULATE (\n"
            f"    SUM ( 'Balance Sheet'[balance_usd] ),\n"
            f"    'Balance Sheet'[caption] = \"{name}\",\n"
            f"    'Balance Sheet'[account_class] = \"{account_class}\",\n"
            f"    'Date'[period_key] = MAX ( 'Date'[period_key] )\n"
            f")")


def at_latest(table: str, column: str, aggregate: str = "SUM") -> str:
    return (f"CALCULATE (\n"
            f"    {aggregate} ( '{table}'[{column}] ),\n"
            f"    'Date'[period_key] = MAX ( 'Date'[period_key] )\n"
            f")")


M_USD = '#,0.0,,;(#,0.0,,);"–"'
M_USD2 = '#,0.00,,;(#,0.00,,);"–"'
PCT = '0.0%;(0.0%);"–"'
TURNS = '0.00"x";(0.00"x");"–"'
FTE = "#,0.0"
COUNT = "#,0"
WHOLE = "#,0"

#: (name, expression, format string or None, display folder, description)
MEASURES: tuple[tuple[str, str, str | None, str, str], ...] = (
    # ================================================================ model context
    ("Reporting Period Key", str(REPORT_PERIOD), "0", "00 Model context",
     "The period key of the reporting close, August 2026. Held as one measure so the cutoff "
     "is defined once and everything that depends on it moves together when the close moves."),
    ("Reporting Period",
     "CALCULATE (\n"
     "    MAX ( 'Date'[month_label_long] ),\n"
     "    ALL ( 'Date' ),\n"
     "    'Date'[period_key] = [Reporting Period Key]\n"
     ")", None, "00 Model context",
     "The reporting close as a label, for a report header. Reads the Date dimension, so it "
     "cannot disagree with the calendar."),
    ("Current Forecast Version",
     "CALCULATE (\n"
     "    MAX ( 'Scenario'[version_code] ),\n"
     "    ALL ( 'Scenario' ),\n"
     "    'Scenario'[scenario_code] = \"FC\",\n"
     "    'Scenario'[is_default] = TRUE\n"
     ")", None, "00 Model context",
     "The one forecast version marked default upstream. Three forecasts are retained and "
     "exactly one is current; a superseded forecast presented as THE forecast is a reporting "
     "error nobody would notice, so the model never selects by name or by sort order."),
    ("Selected Basis",
     "SELECTEDVALUE ( 'Reporting Basis'[basis], \"STATUTORY\" )", None, "00 Model context",
     "The reporting basis in force, defaulting to Statutory. Membership of a basis is settled "
     "upstream and carried on every fact row; this only says which one is being looked at."),
    ("Selected Period Basis",
     "SELECTEDVALUE ( 'Period Basis'[basis_name], \"Year to date\" )", None,
     "00 Model context",
     "Month, Year to date or Full year. Chooses which governed column the statement measures "
     "read; it does not change how any of them is calculated."),

    # ================================================================ income statement
    ("Revenue", statement_measure("REVENUE"), M_USD, "01 Income statement",
     "Consolidated revenue from the governed measure mart. Intercompany revenue is excluded "
     "upstream on both sides of every comparison, so a plan variance is like for like."),
    ("Cost of Sales", statement_measure("COST_OF_SALES"), M_USD, "01 Income statement",
     "Cost of sales, positive on the management sign convention."),
    ("Gross Profit", statement_measure("GROSS_PROFIT"), M_USD, "01 Income statement",
     "Gross profit. Stored as a subtotal upstream rather than computed here, because a "
     "subtotal computed in a reporting tool is a definition living in a reporting tool."),
    ("Gross Margin %", "DIVIDE ( [Gross Profit], [Revenue] )", PCT, "01 Income statement",
     "Gross profit over revenue. A ratio of two governed measures, which is presentation "
     "arithmetic rather than a definition."),
    ("Operating Expenses", statement_measure("OPEX"), M_USD, "01 Income statement",
     "Operating expenses, positive. Includes the non-recurring items the add-back policy "
     "later removes, because they sit inside operating expenses at layer 1 (ADR-0013)."),
    ("Statutory EBITDA", statement_measure("EBITDA"), M_USD, "01 Income statement",
     "EBITDA on the reported result, driven by the `is_ebitda` attribute on the account in "
     "the consolidation rather than by an account list here. **Distinct from Management "
     "Adjusted EBITDA and from Covenant EBITDA**, each of which has its own lineage."),
    ("Approved Add-backs", statement_measure("ADDBACKS", coalesce=True), M_USD,
     "01 Income statement",
     "The approved add-back policy (ADR-0013): restructuring, transaction and integration "
     "costs, legal settlements, retention bonuses and the sponsor monitoring fee. "
     "**Coalesced to zero**, because a category with no population in a period contributes "
     "nothing and must not propagate a blank into Adjusted EBITDA."),
    ("Management Adjusted EBITDA", statement_measure("ADJ_EBITDA"), M_USD,
     "01 Income statement",
     "Statutory EBITDA plus the approved add-backs plus any layer-4 management adjustment. "
     "**This is not Covenant EBITDA.** The two are equal in the current baseline because the "
     "sponsor fee runs below its cap and the covenant foreign exchange add-back has no "
     "population — an outcome, not a definition."),
    ("EBITDA Margin %", "DIVIDE ( [Statutory EBITDA], [Revenue] )", PCT, "01 Income statement",
     "Statutory EBITDA over revenue."),
    ("Adjusted EBITDA Margin %", "DIVIDE ( [Management Adjusted EBITDA], [Revenue] )", PCT,
     "01 Income statement", "Management Adjusted EBITDA over revenue."),
    ("Depreciation and Amortisation", statement_measure("DA"), M_USD, "01 Income statement",
     "Depreciation and the amortisation of acquired intangibles, positive."),
    ("EBIT", statement_measure("EBIT"), M_USD, "01 Income statement",
     "Statutory EBITDA less depreciation and amortisation. Stored upstream."),
    ("Net Finance Costs", statement_measure("NET_FINANCE"), M_USD, "01 Income statement",
     "Interest expense and income, foreign exchange and other non-operating items, net and "
     "positive as a cost."),
    ("Income Tax", statement_measure("TAX"), M_USD, "01 Income statement",
     "Current and deferred tax, positive as a charge."),
    ("Net Income", statement_measure("NET_INCOME"), M_USD, "01 Income statement",
     "Consolidated net income before the non-controlling attribution."),
    ("Non-controlling Interests", statement_measure("NCI", coalesce=True), M_USD,
     "01 Income statement",
     "The minority's share of the result, below tax and outside EBITDA. Coalesced to zero: "
     "most entities have no minority, and a blank must not void the parent attribution."),
    ("Net Income Attributable to Parent", statement_measure("NI_PARENT"), M_USD,
     "01 Income statement",
     "Net income less the non-controlling attribution. The bottom line of the group."),

    # ================================================================ scenario
    ("Actual Revenue",
     cutoff("CALCULATE ( [Revenue], 'Scenario'[scenario_code] = \"ACT\" )"),
     M_USD, "02 Scenario",
     "Revenue on the Actual scenario, **blank after the reporting close**. The consolidation "
     "generates Actual rows for the whole fiscal year and the group has closed eight months "
     "of it; returning zero for the rest draws a company falling off a cliff."),
    ("Actual Adjusted EBITDA",
     cutoff("CALCULATE ( [Management Adjusted EBITDA], 'Scenario'[scenario_code] = \"ACT\" )"),
     M_USD, "02 Scenario",
     "Management Adjusted EBITDA on Actual, blank after the reporting close."),
    ("Actual EBIT",
     cutoff("CALCULATE ( [EBIT], 'Scenario'[scenario_code] = \"ACT\" )"),
     M_USD, "02 Scenario", "EBIT on Actual, blank after the reporting close."),
    ("Budget Revenue",
     "CALCULATE ( [Revenue], 'Scenario'[scenario_code] = \"BUD\" )", M_USD, "02 Scenario",
     "Revenue on the board-approved budget, which covers the whole fiscal year and is "
     "therefore not subject to the actual cutoff."),
    ("Budget Adjusted EBITDA",
     "CALCULATE ( [Management Adjusted EBITDA], 'Scenario'[scenario_code] = \"BUD\" )",
     M_USD, "02 Scenario", "Management Adjusted EBITDA on the approved budget."),
    ("Forecast Revenue",
     "CALCULATE ( [Revenue], 'Scenario'[version_code] = [Current Forecast Version] )",
     M_USD, "02 Scenario",
     "Revenue on the **current** forecast, selected by the upstream default flag rather than "
     "by name, so a superseded forecast can never be presented as the forecast."),
    ("Prior Year Revenue",
     "CALCULATE ( [Revenue], 'Scenario'[scenario_code] = \"PY\" )", M_USD, "02 Scenario",
     "Revenue twelve months earlier. Derived upstream from Actual by a date offset and never "
     "stored (ADR-0004), so it cannot drift from the actual it is a view of."),

    # ================================================================ variance
    ("Variance Base", "SUM ( 'Variance'[base_ytd] )", M_USD, "03 Variance",
     "The measure being assessed, on the selected comparison. Reads the governed variance "
     "mart; the model does not derive a comparison."),
    ("Variance Comparator", "SUM ( 'Variance'[comp_ytd] )", M_USD, "03 Variance",
     "What the base is assessed against, on the selected comparison."),
    ("Variance", "SUM ( 'Variance'[var_ytd_usd] )", M_USD, "03 Variance",
     "Base less comparator in dollars, precomputed upstream so the sign convention cannot "
     "differ between two reporting tools."),
    ("Variance %", "DIVIDE ( [Variance], ABS ( [Variance Comparator] ) )", PCT, "03 Variance",
     "Variance over the absolute comparator, so a percentage against a negative base still "
     "reads in the same direction as the dollars."),
    ("Variance Favourability",
     "VAR _Fav = SELECTEDVALUE ( 'Measure Line'[favourable_direction] )\n"
     "VAR _Var = [Variance]\n"
     "RETURN\n"
     "    SWITCH (\n"
     "        TRUE (),\n"
     "        ISBLANK ( _Var ), BLANK (),\n"
     "        _Fav = \"NEUTRAL\", \"Neutral\",\n"
     "        _Fav = \"HIGHER\" && _Var > 0, \"Favourable\",\n"
     "        _Fav = \"HIGHER\" && _Var < 0, \"Unfavourable\",\n"
     "        _Fav = \"LOWER\" && _Var < 0, \"Favourable\",\n"
     "        _Fav = \"LOWER\" && _Var > 0, \"Unfavourable\",\n"
     "        \"Neutral\"\n"
     "    )", None, "03 Variance",
     "Favourable, Unfavourable or Neutral, decided by the **measure's own favourable "
     "direction** and not by the sign of the number. Revenue above plan is favourable; "
     "operating expense above plan is not, and colouring every positive variance green says "
     "the opposite on half a statement."),
    ("Variance Is Comparable",
     "IF ( MIN ( 'Variance'[is_comparable] ) = 1, \"Yes\", \"Not comparable\" )", None,
     "03 Variance",
     "Whether the selected comparison is like for like. Budget and forecast are built at "
     "entity level and carry no consolidation entries, so a plan comparison is comparable "
     "down to EBIT and is not below it. The flag is set upstream."),

    # ================================================================ balance sheet
    ("Total Assets",
     at_latest("Balance Sheet", "balance_usd").replace(
         "'Date'[period_key] = MAX ( 'Date'[period_key] )",
         "'Balance Sheet'[account_class] = \"ASSET\",\n"
         "    'Date'[period_key] = MAX ( 'Date'[period_key] )"),
     M_USD, "04 Balance sheet",
     "Total assets at the selected month end, from the approved consolidated balance sheet."),
    ("Total Liabilities",
     "-" + at_latest("Balance Sheet", "balance_usd").replace(
         "'Date'[period_key] = MAX ( 'Date'[period_key] )",
         "'Balance Sheet'[account_class] = \"LIABILITY\",\n"
         "    'Date'[period_key] = MAX ( 'Date'[period_key] )"),
     M_USD, "04 Balance sheet",
     "Total liabilities, sign-flipped to the positive presentation a reader expects."),
    ("Total Equity",
     "-" + at_latest("Balance Sheet", "balance_usd").replace(
         "'Date'[period_key] = MAX ( 'Date'[period_key] )",
         "'Balance Sheet'[account_class] = \"EQUITY\",\n"
         "    'Date'[period_key] = MAX ( 'Date'[period_key] )"),
     M_USD, "04 Balance sheet",
     "Total equity, including the unclosed result for the period, the translation reserve and "
     "the non-controlling interest."),
    ("Balance Sheet Check", "[Total Assets] - [Total Liabilities] - [Total Equity]", M_USD2,
     "04 Balance sheet",
     "Assets less liabilities and equity. Nil in every period, and shown rather than assumed."),
    ("Cash", caption("Cash and cash equivalents", "ASSET"), M_USD, "04 Balance sheet",
     "Cash and cash equivalents at the month end."),
    ("Accounts Receivable", caption("Accounts receivable, net", "ASSET"), M_USD,
     "04 Balance sheet", "Trade receivables, net of provision."),
    ("Inventory", caption("Inventory, net", "ASSET"), M_USD, "04 Balance sheet",
     "Inventory, net of the unrealised profit provision the consolidation posts against it."),
    ("Accounts Payable", caption("Accounts payable", "LIABILITY", negate=True), M_USD,
     "04 Balance sheet", "Trade payables, positive."),
    ("Net Working Capital", at_latest("Working Capital", "nwc_usd"), M_USD,
     "04 Balance sheet",
     "Receivables plus inventory less payables plus other working capital, from the governed "
     "working capital mart rather than re-added here."),
    ("Property Plant and Equipment",
     caption("Property, plant and equipment, net", "ASSET"), M_USD, "04 Balance sheet",
     "Owned fixed assets, net."),
    ("Goodwill", caption("Goodwill", "ASSET"), M_USD, "04 Balance sheet",
     "Goodwill on eleven acquisitions, derived from the goodwill bridge in the consolidation "
     "and never plugged."),
    ("Intangible Assets", caption("Intangible assets, net", "ASSET"), M_USD,
     "04 Balance sheet",
     "Acquired customer relationships and technology at fair value, less accumulated "
     "amortisation."),
    ("Retained Earnings", caption("Retained earnings", "EQUITY", negate=True), M_USD,
     "04 Balance sheet",
     "Accumulated earnings closed into reserves. Positive means accumulated profit."),
    ("Cumulative Translation Adjustment",
     caption("Cumulative translation adjustment", "EQUITY", negate=True), M_USD,
     "04 Balance sheet",
     "The equity reserve arising because assets and liabilities translate at closing rates "
     "while equity translates at historical rates. **Not the foreign exchange effect on "
     "cash**, which is an operating item on the cash flow."),
    ("Non-controlling Interest Equity",
     caption("Non-controlling interests", "EQUITY", negate=True), M_USD, "04 Balance sheet",
     "The minority's share of net assets, a separate component of equity."),

    # ================================================================ cash flow
    ("Operating Cash Flow", "SUM ( 'Cash Flow'[operating_cash_flow_usd] )", M_USD,
     "05 Cash flow",
     "Operating cash flow, derived upstream from balance sheet movements (ADR-0006)."),
    ("Investing Cash Flow", "SUM ( 'Cash Flow'[investing_cash_flow_usd] )", M_USD,
     "05 Cash flow", "Investing cash flow."),
    ("Financing Cash Flow", "SUM ( 'Cash Flow'[financing_cash_flow_usd] )", M_USD,
     "05 Cash flow", "Financing cash flow."),
    ("FX Effect on Cash", "SUM ( 'Cash Flow'[fx_effect_on_cash_usd] )", M_USD, "05 Cash flow",
     "The retranslation of foreign-currency cash balances. **Not the cumulative translation "
     "adjustment**, which arises on net assets and sits in equity. Conflating the two makes a "
     "cash flow tie while reporting an implausible exchange effect on a mostly-USD balance."),
    ("Net Change in Cash", "SUM ( 'Cash Flow'[net_change_in_cash_usd] )", M_USD,
     "05 Cash flow",
     "The movement in cash, measured from the cash accounts themselves. Cash is never the "
     "residual of the statement."),
    ("Opening Cash",
     "CALCULATE (\n"
     "    SUM ( 'Cash Flow'[opening_cash_usd] ),\n"
     "    'Date'[period_key] = MIN ( 'Date'[period_key] )\n"
     ")", M_USD, "05 Cash flow", "Cash at the start of the selected range."),
    ("Closing Cash", at_latest("Cash Flow", "closing_cash_usd"), M_USD, "05 Cash flow",
     "Cash at the end of the selected range. Ties to the balance sheet's cash caption at 0.00 "
     "in every period."),
    ("Cash Flow Check",
     "[Opening Cash] + [Operating Cash Flow] + [Investing Cash Flow]\n"
     "    + [Financing Cash Flow] + [FX Effect on Cash] - [Closing Cash]", M_USD2,
     "05 Cash flow", "Opening plus the movements less closing. Nil in every period."),
    ("Total Liquidity", at_latest("Cash Flow", "liquidity_usd"), M_USD, "05 Cash flow",
     "Cash plus the undrawn revolving facility at the selected month end."),

    # ================================================================ debt and covenants
    ("Gross Debt", at_latest("Covenants", "gross_debt_usd"), M_USD, "06 Debt and covenants",
     "All debt instruments at the month end, whether or not the agreement counts them."),
    ("Covenant Debt", at_latest("Covenants", "covenant_debt_usd"), M_USD,
     "06 Debt and covenants",
     "Debt that counts toward the covenant, per the instrument's own flag in the debt "
     "schedule: the term loan, the revolver and finance leases, and not operating leases "
     "(CA-018)."),
    ("Covenant Net Debt", at_latest("Covenants", "net_debt_usd"), M_USD,
     "06 Debt and covenants",
     "Covenant debt less unrestricted cash (CA-019). There is no cash netting cap (CA-020)."),
    ("Covenant EBITDA", at_latest("Covenants", "covenant_ebitda_usd"), M_USD,
     "06 Debt and covenants",
     "EBITDA on the **credit agreement's** definition, over a rolling twelve months: the "
     "permitted add-backs (CA-021 to CA-025), the sponsor fee capped at USD 1.5m (CA-027) and "
     "unrealised foreign exchange (CA-030). **Its own lineage, not Management Adjusted "
     "EBITDA** — the two are equal in this baseline only because the cap does not bite and "
     "the foreign exchange add-back has no population."),
    ("Covenant Net Leverage", "DIVIDE ( [Covenant Net Debt], [Covenant EBITDA] )", TURNS,
     "06 Debt and covenants",
     "Covenant net debt over twelve months of covenant EBITDA. Using a fiscal-year EBITDA for "
     "a year in progress divides a full net debt balance by a part-year result and reports a "
     "breach that does not exist."),
    ("Covenant Limit", at_latest("Covenants", "max_net_leverage", aggregate="MAX"), TURNS,
     "06 Debt and covenants",
     "The maximum leverage the agreement permits for the fiscal year: 6.00x FY2023, 5.50x "
     "FY2024, 5.00x FY2025 and 4.50x from FY2026, each read from its own agreement term."),
    ("Covenant Headroom", "[Covenant Limit] - [Covenant Net Leverage]", TURNS,
     "06 Debt and covenants",
     "Turns of headroom against the limit. Negative would be a breach."),
    ("Is Covenant Test Date",
     "IF ( SELECTEDVALUE ( 'Date'[accounting_period] ) = 12, TRUE, FALSE )", None,
     "06 Debt and covenants",
     "Whether the selected month is a date the agreement actually tests. The agreement sets a "
     "maximum per **fiscal year**, so the test dates are the year ends. A quarterly "
     "presentation once stamped BREACH on two dates the agreement never tests."),
    ("Covenant Status",
     "VAR _Headroom = [Covenant Headroom]\n"
     "RETURN\n"
     "    SWITCH (\n"
     "        TRUE (),\n"
     "        ISBLANK ( _Headroom ), BLANK (),\n"
     "        NOT [Is Covenant Test Date], \"Indicative\",\n"
     "        _Headroom >= 0, \"Compliant\",\n"
     "        \"Breach\"\n"
     "    )", None, "06 Debt and covenants",
     "Compliant or Breach at a real test date, and **Indicative** anywhere else. Telling a "
     "board it breached a covenant it did not breach is the most expensive mistake a "
     "reporting layer can make, so a verdict is given only where the agreement gives one."),
    ("Economic Leverage", at_latest("Covenants", "economic_leverage", aggregate="MAX"), TURNS,
     "06 Debt and covenants",
     "Leverage including operating lease liabilities, which the agreement excludes. Shown "
     "because a reader should see both."),

    # ================================================================ workforce
    ("Opening FTE",
     "CALCULATE (\n"
     "    SUM ( 'Headcount'[fte_opening] ),\n"
     "    'Date'[period_key] = MIN ( 'Date'[period_key] )\n"
     ")", FTE, "07 Workforce",
     "Full-time equivalents at the start of the selected range."),
    ("Hires", "SUM ( 'Headcount'[hires] )", COUNT, "07 Workforce",
     "People joining. A **count**, not an FTE: a part-time joiner is one hire and a fraction "
     "of an FTE, so hires are never netted against the FTE movement."),
    ("Exits", "SUM ( 'Headcount'[leavers] )", COUNT, "07 Workforce",
     "People leaving, on the same basis as hires."),
    ("Closing FTE", at_latest("Headcount", "fte_closing"), FTE, "07 Workforce",
     "Full-time equivalents at the end of the selected range. Continuous with the prior "
     "month at the finest grain."),
    ("Average FTE",
     "AVERAGEX (\n"
     "    VALUES ( 'Date'[period_key] ),\n"
     "    CALCULATE ( SUM ( 'Headcount'[fte_average] ) )\n"
     ")", FTE, "07 Workforce",
     "The mean of the monthly averages over the selected range, rather than the average of a "
     "sum, which would scale with the number of months."),
    ("Personnel Cost",
     "CALCULATE (\n"
     "    SUM ( 'Financial Detail'[amount_usd] ),\n"
     "    'Account'[fs_caption_l2] = \"Personnel costs\"\n"
     ")", M_USD, "07 Workforce",
     "Personnel cost from the income statement detail, so it agrees with operating expenses "
     "rather than with a payroll extract."),
    ("Cost per Average FTE", "DIVIDE ( [Personnel Cost], [Average FTE] )", WHOLE,
     "07 Workforce", "Personnel cost over average full-time equivalents."),

    # ================================================================ capital expenditure
    ("Actual CapEx", cutoff("SUM ( 'CapEx'[spend_usd] )"), M_USD, "08 Capital expenditure",
     "Capital spend, blank after the reporting close on the same rule as every other Actual "
     "measure."),
    ("Approved CapEx", "SUM ( 'CapEx'[approved_usd] )", M_USD, "08 Capital expenditure",
     "The approved budget for the projects in scope."),
    ("CapEx to Depreciation",
     "DIVIDE ( [Actual CapEx], [Depreciation and Amortisation] )", TURNS,
     "08 Capital expenditure",
     "Capital spend as a multiple of the depreciation charge — the usual test of whether an "
     "asset base is being maintained."),

    # ================================================================ foreign exchange
    ("Constant Currency Revenue", "SUM ( 'FX'[revenue_constant_ccy_usd] )", M_USD,
     "09 Foreign exchange",
     "This year's activity restated at last year's average rate. An **operating** measure: "
     "what a reader means by how much of the revenue movement was currency. Not the "
     "translation adjustment."),
    ("FX Translation Effect on Revenue",
     "SUM ( 'FX'[revenue_usd] ) - [Constant Currency Revenue]", M_USD, "09 Foreign exchange",
     "Reported revenue less constant currency revenue."),
    ("CTA Movement", "SUM ( 'FX'[cta_movement_usd] )", M_USD, "09 Foreign exchange",
     "The movement in the cumulative translation adjustment, an equity reserve. Derived by "
     "the consolidation as the residual of the translated trial balance, never plugged."),
)

#: The disconnected dimension the statement measures switch on. Not related to any fact by
#: design -- it selects a column, it does not filter rows.
PERIOD_BASIS_ROWS: tuple[tuple[str, str, int], ...] = (
    ("MTD", "Month", 1),
    ("YTD", "Year to date", 2),
    ("FY", "Full year", 3),
)
