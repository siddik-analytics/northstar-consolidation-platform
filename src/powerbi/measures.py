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

#: The Actual cutoff, as a reusable fragment.
#:
#: This is not a nicety. `mart_financial_ytd` publishes ACTUAL rows for every month of FY2026,
#: including the four after the August close, and they carry **0.00** -- so the naive
#: `SUM ( 'Financials'[ytd_usd] )` returns zero for September 2026 rather than blank. Zero says
#: the group earned nothing that month. Blank says the month has not happened, which is what is
#: true. A chart then breaks the line instead of drawing a cliff to the axis.
#:
#: The guard fires only when the filter context resolves to Actual *alone*. A trend showing
#: Actual and Forecast together is showing the forecast on purpose and must not be blanked, so
#: a mixed selection is left to report what it selected.
ACTUAL_CUTOFF = """VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]"""

#: Read a governed measure column on the period basis the report has selected. The three
#: columns are stored results, so the switch is a column choice and not a recalculation.
PERIOD_SWITCH = """VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = {basis}
{cutoff}
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "{code}" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), {wrap} )"""

#: The reporting basis a measure reads.
#:
#: `mart_financial_ytd` publishes **both** bases, statutory and management, as separate rows.
#: A measure that does not state which one it wants sums both and reports exactly twice the
#: truth -- which is what every statement measure did until the model was deployed to a real
#: engine and `Revenue` came back at 557,961,779.56 against a mart holding 278,980,889.78.
#: Nothing in the TMDL could have shown that; only running it could.
#:
#: Most lines follow the reader's selection and default to statutory. Two do not: Statutory
#: EBITDA and Management Adjusted EBITDA are *definitions*, and a definition that changes when
#: someone moves a slicer is not a definition.
SELECTED_BASIS = 'SELECTEDVALUE ( \'Reporting Basis\'[basis], "STATUTORY" )'


def statement_measure(code: str, coalesce: bool = False, basis: str | None = None) -> str:
    """
    A governed income statement line, on the selected period basis, with the Actual cutoff.

    `basis` pins the reporting basis for a measure whose name already fixes it. Left as None,
    the measure follows the Reporting Basis selection and defaults to statutory.

    `coalesce` adds `+ 0` for a component of a bridge -- the Phase 4C rule that a component
    with no population contributes zero rather than voiding the total. It is applied *inside*
    the cutoff, never instead of it: a nil add-back category is zero, and an unclosed month is
    blank, and those are different statements.
    """
    pinned = f'"{basis}"' if basis else SELECTED_BASIS
    return PERIOD_SWITCH.format(code=code, cutoff=ACTUAL_CUTOFF, basis=pinned,
                                wrap="_Value + 0" if coalesce else "_Value")


#: The cutoff guard for a measure that does not go through `PERIOD_SWITCH`.
def cutoff(inner: str) -> str:
    return (f"{ACTUAL_CUTOFF}\n"
            f"RETURN IF ( _PastClose, BLANK (), {inner} )")


#: A variance column on the selected period basis. The comparison itself is precomputed in
#: `mart_variance` -- base, comparator, variance and favourability all arrive decided. What
#: DAX chooses here is which of the three governed period columns to read.
def variance_measure(mtd: str, ytd: str, fy: str, decimals: int = 2) -> str:
    return (f"""VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = {SELECTED_BASIS}
RETURN
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Variance'[{mtd}] ),
            "FY", SUM ( 'Variance'[{fy}] ),
            SUM ( 'Variance'[{ytd}] )
        ),
        KEEPFILTERS ( 'Variance'[basis] = _Reporting )
    )""")


def caption(name: str, account_class: str, negate: bool = False) -> str:
    sign = "-" if negate else ""
    return (f"{sign}CALCULATE (\n"
            f"    SUM ( 'Balance Sheet'[balance_usd] ),\n"
            f"    'Balance Sheet'[caption] = \"{name}\",\n"
            f"    'Balance Sheet'[account_class] = \"{account_class}\",\n"
            f"    'Date'[period_key] = MAX ( 'Date'[period_key] )\n"
            f")")


#: A consolidation-layer amount on the selected period basis. The bridge fact is monthly,
#: so the month is a plain sum, the year to date is the fiscal year's months up to the one
#: selected, and the fiscal year is all of it -- the same three readings `PERIOD_SWITCH`
#: takes from the stored mart columns, computed here because the bridge stores months. The
#: cutoff is unconditional: the bridge is Actual by nature and has no scenario to test.
def layer_measure(column: str) -> str:
    return f"""VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _Year = MAX ( 'Date'[fiscal_year] )
VAR _PastClose = _Latest > [Reporting Period Key]
VAR _Value =
    SWITCH (
        _Basis,
        "MTD", SUM ( 'Layer Bridge'[{column}] ),
        "FY", CALCULATE (
            SUM ( 'Layer Bridge'[{column}] ),
            REMOVEFILTERS ( 'Date' ),
            'Date'[fiscal_year] = _Year
        ),
        CALCULATE (
            SUM ( 'Layer Bridge'[{column}] ),
            REMOVEFILTERS ( 'Date' ),
            'Date'[fiscal_year] = _Year,
            'Date'[period_key] <= _Latest
        )
    )
RETURN IF ( _PastClose, BLANK (), _Value )"""


def at_latest(table: str, column: str, aggregate: str = "SUM") -> str:
    return (f"CALCULATE (\n"
            f"    {aggregate} ( '{table}'[{column}] ),\n"
            f"    'Date'[period_key] = MAX ( 'Date'[period_key] )\n"
            f")")


#: Display formats, in Power BI's VBA-style grammar and proven by rendering (Phase 6A.3).
#:
#: The scaling commas go **before** the decimal: `#,0,,.0` is millions to one decimal, and
#: Power BI's engine renders 5,553,457.50 as `5.6`, -5,553,457.50 as `(5.6)`, zero as `–`,
#: 278,980,889.78 as `279.0`. The Excel form `#,0.0,,` -- which these carried until
#: P6B-D-03 -- scales nothing in Power BI and renders `(5,553,457.5,)` on a page. One
#: engine nuance is recorded rather than hidden: the zero section is chosen on the *rounded*
#: value, so an amount under 50,000 prints `–` where the workbook prints `0.0`.
#:
#: Visuals that show these measures keep display units at *None*; a K/M/B display unit on
#: top of a scaled format would scale twice (`P6-FMT-06` reads the report for that).
M_USD = '#,0,,.0;(#,0,,.0);"–"'
M_USD2 = '#,0,,.00;(#,0,,.00);"–"'
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
    ("Consolidation Bridge Title",
     "SELECTEDVALUE ( 'Period Basis'[basis_name], \"Year to date\" )\n"
     "    & \" consolidation bridge — \"\n"
     "    & SELECTEDVALUE ( 'Date'[month_label_long], \"period selected\" )", None,
     "00 Model context",
     "The consolidation bridge's title, as words that state its scope -- \"Year to date "
     "consolidation bridge — Aug 2026\" -- so the bridge can never look like it reconciles a "
     "figure on another basis. A title that follows the slicers is a title that cannot go "
     "stale."),
    ("Reporting Period",
     "VAR _Key = [Reporting Period Key]\n"
     "RETURN\n"
     "    CALCULATE (\n"
     "        SELECTEDVALUE ( 'Date'[month_label_long] ),\n"
     "        FILTER ( ALL ( 'Date' ), 'Date'[period_key] = _Key )\n"
     "    )", None, "00 Model context",
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
    ("Statutory EBITDA", statement_measure("EBITDA", basis="STATUTORY"), M_USD, "01 Income statement",
     "EBITDA on the reported result, driven by the `is_ebitda` attribute on the account in "
     "the consolidation rather than by an account list here. **Distinct from Management "
     "Adjusted EBITDA and from Covenant EBITDA**, each of which has its own lineage."),
    ("Approved Add-backs",
     statement_measure("ADDBACKS", coalesce=True, basis="MANAGEMENT"), M_USD,
     "01 Income statement",
     "The approved add-back policy (ADR-0013): restructuring, transaction and integration "
     "costs, legal settlements, retention bonuses and the sponsor monitoring fee. "
     "**Coalesced to zero**, because a category with no population in a period contributes "
     "nothing and must not propagate a blank into Adjusted EBITDA."),
    ("Management Adjusted EBITDA",
     statement_measure("ADJ_EBITDA", basis="MANAGEMENT"), M_USD,
     "01 Income statement",
     "**Definition** statutory EBITDA plus the approved add-backs plus any layer-4 management "
     "adjustment -- the management view of trading performance. The add-back policy is "
     "settled upstream (ADR-0013) and arrives as a governed measure line; this measure "
     "selects it and decides nothing about what may be added back. **This is not Covenant "
     "EBITDA.** The two are equal in the current baseline because the sponsor fee runs "
     "below its cap and the covenant foreign exchange add-back has no population -- an "
     "outcome, not a definition. **Source** `mart_financial_ytd`, measure line ADJ_EBITDA. "
     "**Basis** pinned to MANAGEMENT and deliberately does not follow the Reporting Basis "
     "slicer: a definition that changes when someone moves a slicer is not a definition. "
     "**Scenario** follows the selection -- Actual, Budget, Forecast or Prior Year. "
     "**Blank policy** blank for an Actual month after the reporting close; a nil add-back "
     "category contributes zero."),
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
    # Eight pinned measures, not eighty. A report that puts Actual, Budget, Forecast and Prior
    # Year in four columns of one table needs each pinned to its scenario, because a single
    # measure cannot be four things at once. Everything else -- every comparison, of every
    # statement line, on every period basis -- goes through the Variance fact and its six
    # measures below. That is the reusable architecture; this is the small deliberate set that
    # side-by-side layouts genuinely require.
    ("Actual Revenue",
     cutoff("CALCULATE ( [Revenue], 'Scenario'[scenario_code] = \"ACT\" )"),
     M_USD, "02 Scenario",
     "Revenue on the Actual scenario, **blank after the reporting close**. The consolidation "
     "publishes Actual rows for the whole fiscal year and the group has closed eight months of "
     "it; the remaining rows carry 0.00, so without the guard this reads as a company that "
     "stopped trading in September. Blank policy: BLANK past the close, never zero."),
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
     "VAR _Version = [Current Forecast Version]\n"
     "RETURN\n"
     "    CALCULATE (\n"
     "        [Revenue],\n"
     "        FILTER ( ALL ( 'Scenario' ), 'Scenario'[version_code] = _Version )\n"
     "    )",
     M_USD, "02 Scenario",
     "Revenue on the **current** forecast, selected by the upstream default flag rather than "
     "by name, so a superseded forecast can never be presented as the forecast."),
    ("Forecast Adjusted EBITDA",
     "VAR _Version = [Current Forecast Version]\n"
     "RETURN\n"
     "    CALCULATE (\n"
     "        [Management Adjusted EBITDA],\n"
     "        FILTER ( ALL ( 'Scenario' ), 'Scenario'[version_code] = _Version )\n"
     "    )",
     M_USD, "02 Scenario",
     "Management Adjusted EBITDA on the current forecast, selected by the default flag."),
    ("Prior Year Revenue",
     "CALCULATE ( [Revenue], 'Scenario'[scenario_code] = \"PY\" )", M_USD, "02 Scenario",
     "Revenue twelve months earlier. Prior Year is derived upstream from Actual by a date "
     "offset and stored nowhere (ADR-0004), under the governed version `PY_DERIVED` "
     "(ADR-0027). No cutoff applies: prior year is complete by definition."),
    ("Prior Year Adjusted EBITDA",
     "CALCULATE ( [Management Adjusted EBITDA], 'Scenario'[scenario_code] = \"PY\" )",
     M_USD, "02 Scenario",
     "Management Adjusted EBITDA twelve months earlier, on the governed `PY_DERIVED` "
     "version."),
    ("Prior Year Version",
     "CALCULATE (\n"
     "    SELECTEDVALUE ( 'Scenario'[version_code] ),\n"
     "    ALL ( 'Scenario' ),\n"
     "    'Scenario'[scenario_code] = \"PY\"\n"
     ")", None, "02 Scenario",
     "The governed version behind Prior Year, read from the dimension rather than written "
     "into DAX. It reads `PY_DERIVED`. If this ever returns blank, the version master has "
     "lost the member and `P6-XAR-VER-01` fails -- which is precisely the defect P7-D-01 "
     "was, seen from the semantic layer."),

    # ================================================================ variance
    ("Variance Base", variance_measure("base_mtd", "base_ytd", "base_fy"), M_USD,
     "03 Variance",
     "The measure being assessed, on the selected comparison and the selected period basis. "
     "Reads the governed variance mart; the model does not derive a comparison."),
    ("Variance Comparator", variance_measure("comp_mtd", "comp_ytd", "comp_fy"), M_USD,
     "03 Variance",
     "What the base is assessed against, on the selected comparison and period basis."),
    ("Variance", variance_measure("var_mtd_usd", "var_ytd_usd", "var_fy_usd"), M_USD,
     "03 Variance",
     "Base less comparator in dollars, on the selected period basis. Precomputed upstream so "
     "the sign convention cannot differ between two reporting tools. Month, year to date and "
     "full year are three governed columns, so switching basis changes which column is read "
     "and never how the variance is computed."),
    ("Variance %",
     "DIVIDE ( [Variance], ABS ( [Variance Comparator] ) )", PCT, "03 Variance",
     "Variance as a percentage of the comparator, at every grain: the governed additive "
     "variance over the absolute governed comparator, with safe division. This is exactly the "
     "convention `mart_variance` stores per entity and line (`var / |comparator|`, verified on "
     "all 17,462 rows with a non-zero comparator), so at leaf grain it agrees with the mart to "
     "the cent, and at group, unit or statement grain it is a real percentage rather than a "
     "sum of percentages -- which is what it was until Phase 6A.3 (P6B-D-04: EBIT read "
     "2,713.9% where the workbook reads (32.8%)). Percentages are never additive; this "
     "measure never adds them."),
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
     "IF (\n"
     "    COUNTROWS ( FILTER ( 'Variance', NOT 'Variance'[is_comparable] ) ) = 0,\n"
     "    \"Yes\",\n"
     "    \"Not comparable\"\n"
     ")", None,
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
     "04 Balance sheet", "Trade and other payables at the latest period in context, from the governed balance "
     "sheet caption and shown positive. Statutory basis, Actual only."),
    ("Net Working Capital", at_latest("Working Capital", "nwc_usd"), M_USD,
     "04 Balance sheet",
     "Receivables plus inventory less payables plus other working capital, from the governed "
     "working capital mart rather than re-added here."),
    ("Property Plant and Equipment",
     caption("Property, plant and equipment, net", "ASSET"), M_USD, "04 Balance sheet",
     "Owned property, plant and equipment at net book value -- cost less accumulated "
     "depreciation, both settled upstream. Statutory basis, Actual only."),
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
     "**Definition** the equity reserve arising because assets and liabilities translate at "
     "closing rates while equity translates at historical rates. Derived upstream as a "
     "residual of the translation itself and **never plugged** (ADR-0017). **Not the foreign "
     "exchange effect on cash**, which is a cash-flow item with a different value and a "
     "different cause; the two are separate measures here for that reason. "
     "**Source** `mart_balance_sheet`, caption 'Cumulative translation adjustment', class "
     "EQUITY, at the latest period in context. **Basis** statutory. **Scenario** Actual only. "
     "**Blank policy** blank when the caption has no row."),
    ("Non-controlling Interest Equity",
     caption("Non-controlling interests", "EQUITY", negate=True), M_USD, "04 Balance sheet",
     "**Definition** the minority's share of consolidated net assets, a separate component "
     "of equity, attributed by the Phase 4 NCI engine and never derived here. "
     "**Source** `mart_balance_sheet`, caption 'Non-controlling interests', class EQUITY, at "
     "the latest period in context; sign-flipped for presentation because equity is stored "
     "credit-negative. **Basis** statutory and management are identical for NCI -- layer 4 "
     "carries no minority attribution. **Scenario** balance sheet is published on Actual "
     "only; a plan selection returns nothing rather than a plan balance sheet that was never "
     "built. **Blank policy** blank when the caption has no row, never zero: a period with no "
     "balance sheet is not a period with no minority interest."),

    # ================================================================ cash flow
    ("Operating Cash Flow", "SUM ( 'Cash Flow'[operating_cash_flow_usd] )", M_USD,
     "05 Cash flow",
     "Operating cash flow, derived upstream from balance sheet movements (ADR-0006)."),
    ("Investing Cash Flow", "SUM ( 'Cash Flow'[investing_cash_flow_usd] )", M_USD,
     "05 Cash flow", "Cash used in investing for the period, principally capital expenditure. Classified "
     "upstream by each account's cash flow category, never by a rule written here."),
    ("Financing Cash Flow", "SUM ( 'Cash Flow'[financing_cash_flow_usd] )", M_USD,
     "05 Cash flow", "Cash from financing for the period: debt drawn and repaid, and interest paid. "
     "Classified upstream by each account's cash flow category."),
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
     "**Definition** cash and equivalents at the end of the selected range. "
     "**Source** `mart_cash_flow.closing_cash_usd` at the latest period in context -- taken "
     "from the cash flow rather than re-derived, so the statement that explains the movement "
     "and the balance it moves to cannot disagree. **Basis** statutory; the cash position is "
     "not a management-adjusted figure. **Scenario** Actual only. **Blank policy** blank "
     "outside the published range. `P6-XAR` reconciles it to the balance sheet cash caption "
     "and to the Excel cash sheet, both to 0.00."),
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
     "**Definition** covenant debt less unrestricted cash, per credit agreement CA-019. "
     "There is no cash-netting cap (CA-020), so the full cash balance nets. This is **not** "
     "the balance sheet's net debt: covenant debt counts only the instruments the agreement "
     "counts, and `Economic Leverage` is the measure that uses the wider definition. "
     "**Source** `mart_covenants.net_debt_usd` at the latest period in context, computed "
     "upstream from the debt schedule's covenant flag. **Basis** the covenant basis, which is "
     "neither statutory nor management -- it is the agreement's. **Scenario** Actual only; "
     "the covenant is tested on reported results. **Blank policy** blank before the first "
     "measurable period, never zero."),
    ("Covenant EBITDA", at_latest("Covenants", "covenant_ebitda_usd"), M_USD,
     "06 Debt and covenants",
     "**Definition** EBITDA as the **credit agreement** defines it, on a rolling twelve "
     "months. A third definition, not an alias of Adjusted EBITDA: the agreement caps the "
     "sponsor fee and adds back an FX item management reporting does not, so the two differ "
     "by construction even where they happen to sit close together. **Source** "
     "`mart_covenants.covenant_ebitda_usd`, where the bridge from statutory EBITDA is built "
     "and evidenced. **Basis** the agreement's, which is neither statutory nor management. "
     "**Scenario** Actual only -- a covenant is tested on reported results. **Blank policy** "
     "blank before twelve months of history exist, because a rolling twelve-month figure "
     "taken over eight months is not a smaller number, it is a different measure."),
    ("Covenant Net Leverage", "DIVIDE ( [Covenant Net Debt], [Covenant EBITDA] )", TURNS,
     "06 Debt and covenants",
     "**Definition** covenant net debt over **rolling twelve-month** covenant EBITDA. The "
     "rolling window is the whole point: dividing a full net debt balance by a part-year "
     "EBITDA reports a breach that does not exist, which is exactly what the Phase 5 visual "
     "review caught at 7.38x against a 4.50x limit. **Source** `[Covenant Net Debt]` over "
     "`[Covenant EBITDA]`, both from `mart_covenants`, both computed upstream. **Basis** the "
     "agreement's. **Scenario** Actual only. **Blank policy** blank when either input is "
     "blank -- a leverage ratio with no EBITDA is not zero turns, it is unmeasurable. Read it "
     "with `[Covenant Status]`, which reports **Indicative** on any date the agreement does "
     "not test."),
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
     "The amount approved for the projects in scope. **This is the capital plan.** The capex "
     "subledger carries no scenario dimension -- there is no separate budget or forecast "
     "version of capital spend anywhere upstream -- so the approved amount on the project is "
     "the plan a variance is measured against, and no Budget CapEx or Forecast CapEx measure "
     "is offered. Inventing one would mean inventing the data behind it."),
    ("CapEx Variance", "[Actual CapEx] - [Approved CapEx]", M_USD, "08 Capital expenditure",
     "Spend less approved. **Positive is over-approval, and over-approval is unfavourable** — "
     "capital spend follows the same account-aware favourability rule as operating expense, "
     "and colouring a positive variance green here would say the opposite of what it means."),
    ("CapEx Variance %", "DIVIDE ( [CapEx Variance], ABS ( [Approved CapEx] ) )", PCT,
     "08 Capital expenditure",
     "Spend against approval as a percentage of the approved amount."),
    ("CapEx Variance Favourability",
     "VAR _Var = [CapEx Variance]\n"
     "RETURN\n"
     "    SWITCH (\n"
     "        TRUE (),\n"
     "        ISBLANK ( _Var ), BLANK (),\n"
     "        _Var > 0, \"Unfavourable\",\n"
     "        _Var < 0, \"Favourable\",\n"
     "        \"Neutral\"\n"
     "    )", None, "08 Capital expenditure",
     "Favourable when spend is inside approval. Stated explicitly rather than inherited from "
     "the statement favourability rule, because CapEx does not sit on the income statement "
     "and has no Measure Line row to take a direction from."),
    ("Capital Projects", "DISTINCTCOUNT ( 'CapEx'[project_id] )", COUNT,
     "08 Capital expenditure",
     "How many capital projects are in scope. A distinct count on the **corrected** business "
     "key (ADR-0026): before the correction this counted 395 against 1,846 real projects, "
     "because five programmes in an entity-month shared one identifier."),
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
    # ================================================================ reporting (Phase 6A.3)
    ("Account Amount",
     "VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], \"YTD\" )\n"
     "VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], \"STATUTORY\" )\n"
     "VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )\n"
     "VAR _ActualOnly =\n"
     "    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = \"ACT\"\n"
     "VAR _Latest = MAX ( 'Date'[period_key] )\n"
     "VAR _Year = MAX ( 'Date'[fiscal_year] )\n"
     "VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]\n"
     "VAR _Value =\n"
     "    SWITCH (\n"
     "        _Basis,\n"
     "        \"MTD\",\n"
     "            CALCULATE (\n"
     "                SUM ( 'Financial Detail'[amount_usd] ),\n"
     "                KEEPFILTERS ( 'Financial Detail'[basis] = _Reporting )\n"
     "            ),\n"
     "        \"FY\",\n"
     "            CALCULATE (\n"
     "                SUM ( 'Financial Detail'[amount_usd] ),\n"
     "                REMOVEFILTERS ( 'Date' ),\n"
     "                'Date'[fiscal_year] = _Year,\n"
     "                KEEPFILTERS ( 'Financial Detail'[basis] = _Reporting )\n"
     "            ),\n"
     "        CALCULATE (\n"
     "            SUM ( 'Financial Detail'[amount_usd] ),\n"
     "            REMOVEFILTERS ( 'Date' ),\n"
     "            'Date'[fiscal_year] = _Year,\n"
     "            'Date'[period_key] <= _Latest,\n"
     "            KEEPFILTERS ( 'Financial Detail'[basis] = _Reporting )\n"
     "        )\n"
     "    )\n"
     "RETURN IF ( _PastClose, BLANK (), _Value )", M_USD, "10 Reporting",
     "The account-grain amount from the monthly mart, on the period basis, reporting basis "
     "and Actual cutoff the statement measures use. It exists so a statement line can be "
     "drilled to the accounts behind it (Group → unit → entity → account) and it adds nothing "
     "the mart does not already hold: month = the month's rows, year to date = the fiscal "
     "year's rows to the selected month, full year = the fiscal year's rows. No accounting "
     "logic lives here; the sign, the basis and the mapping to a line are the mart's."),
    ("Layer EBITDA", layer_measure("ebitda_usd"), M_USD, "10 Reporting",
     "EBITDA contributed by each consolidation layer on the period basis selected -- the "
     "month, the fiscal year to the month, or the fiscal year -- and blank after the "
     "reporting close, exactly as Statutory EBITDA is. From the governed consolidation "
     "bridge at month grain: Entity Reported, Intercompany Eliminations, Consolidation "
     "Adjustments, Management Adjustments and Translation Adjustment. Statutory is layers "
     "1 + 2 + 3 + 5 and sums to [Statutory EBITDA] on every basis (`P6B1-BR`); management "
     "adds layer 4. Presentation of the approved layers, not a new policy."),
    ("Layer Net Income", layer_measure("net_income_usd"), M_USD, "10 Reporting",
     "Net income contributed by each consolidation layer on the period basis selected, "
     "blank after the reporting close, from the governed consolidation bridge at month "
     "grain; the statutory layers sum to [Net Income] on every basis."),
    ("Layer Entries", "SUM ( 'Layer Bridge'[entries] )", COUNT, "10 Reporting",
     "Journal entries posted at each consolidation layer in the months in context -- a "
     "count over the months selected, not a period-basis measure; a visual says which months "
     "it counts."),
    ("Revenue Share of Group",
     "DIVIDE (\n"
     "    [Revenue],\n"
     "    CALCULATE ( [Revenue], REMOVEFILTERS ( 'Business Unit' ), REMOVEFILTERS ( 'Entity' ) )\n"
     ")", PCT, "10 Reporting",
     "Revenue in the current context as a share of Group revenue in the same period, scenario "
     "and reporting basis. The denominator removes only the Business Unit and Entity filters, "
     "by name: on a unit row it is the Group, on an entity row it is still the Group. For the "
     "share of the parent unit use Revenue Share of Unit -- one measure, one denominator."),
    ("Revenue Share of Unit",
     "DIVIDE ( [Revenue], CALCULATE ( [Revenue], REMOVEFILTERS ( 'Entity' ) ) )", PCT,
     "10 Reporting",
     "Revenue in the current context as a share of the revenue of the business unit(s) in "
     "context, in the same period, scenario and reporting basis. The denominator removes only "
     "the Entity filter: on an entity row it is the entity's unit; on a unit row it is 100%."),

)

#: The disconnected dimension the statement measures switch on. Not related to any fact by
#: design -- it selects a column, it does not filter rows.
PERIOD_BASIS_ROWS: tuple[tuple[str, str, int], ...] = (
    ("MTD", "Month", 1),
    ("YTD", "Year to date", 2),
    ("FY", "Full year", 3),
)
