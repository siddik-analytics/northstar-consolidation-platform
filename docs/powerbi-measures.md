# Power BI measures

*Generated from `src/powerbi/measures.py` by `tools/powerbi_docs.py`. Do not edit by hand: a
measure reference maintained beside the code is a measure reference that is wrong the first
time somebody changes an expression and does not think to open the document.*

**96 measures** across 11 display
folders. Every one is declared once, written into TMDL, deployed to Analysis Services and
evaluated there by the `P6-SEM-14` control, and reconciled to the governed marts by `P6-XAR`.

## The rule this layer honours

**Power BI is not a second accounting engine.** EBITDA, the add-back policy, FX translation,
CTA, NCI, PPA, unrealised profit, statutory and management membership, the covenant definition
and the cash-flow classification are settled upstream and arrive on the mart row. What DAX does
here is aggregate a governed column and occasionally divide one by another. Where a measure
looks like it is deciding something, it is selecting something that was decided upstream.

## Two things every statement measure states

**The period basis.** `mart_financial_ytd` publishes three governed columns -- `mtd_usd`,
`ytd_usd`, `fy_usd` -- and a disconnected `Period Basis` table drives which one is read:
`MTD` (Month), `YTD` (Year to date), `FY` (Full year). One slicer, every
statement measure, no hidden machinery.

**The reporting basis.** The same mart publishes *both* bases as separate rows, so a measure
that does not say which one it wants sums both and reports exactly twice the truth. Most lines
follow the reader's selection and default to statutory; `Statutory EBITDA` and
`Management Adjusted EBITDA` are pinned, because a definition that changes when someone moves a
slicer is not a definition.

## Blank is not zero

A measure returns `BLANK()` when the population has not happened -- an Actual month after the
202608 close -- and **zero** when a component exists and is nil, which is the Phase
4C rule carried forward. The distinction matters here more than usual: the mart publishes
Actual rows for the whole fiscal year and the four after the close carry `0.00`, so a measure
without the guard reports a company that stopped trading in September.

---


## 00 Model context

### `Reporting Period Key`

The period key of the reporting close, August 2026. Held as one measure so the cutoff is defined once and everything that depends on it moves together when the close moves.

*Format:* `0`

```dax
202608
```

### `Consolidation Bridge Title`

The consolidation bridge's title, as words that state its scope -- "Year to date consolidation bridge — Aug 2026" -- so the bridge can never look like it reconciles a figure on another basis. A title that follows the slicers is a title that cannot go stale.

```dax
SELECTEDVALUE ( 'Period Basis'[basis_name], "Year to date" )
    & " consolidation bridge — "
    & SELECTEDVALUE ( 'Date'[month_label_long], "period selected" )
```

### `Reporting Period`

The reporting close as a label, for a report header. Reads the Date dimension, so it cannot disagree with the calendar.

```dax
VAR _Key = [Reporting Period Key]
RETURN
    CALCULATE (
        SELECTEDVALUE ( 'Date'[month_label_long] ),
        FILTER ( ALL ( 'Date' ), 'Date'[period_key] = _Key )
    )
```

### `Current Forecast Version`

The one forecast version marked default upstream. Three forecasts are retained and exactly one is current; a superseded forecast presented as THE forecast is a reporting error nobody would notice, so the model never selects by name or by sort order.

```dax
CALCULATE (
    MAX ( 'Scenario'[version_code] ),
    ALL ( 'Scenario' ),
    'Scenario'[scenario_code] = "FC",
    'Scenario'[is_default] = TRUE
)
```

### `Selected Basis`

The reporting basis in force, defaulting to Statutory. Membership of a basis is settled upstream and carried on every fact row; this only says which one is being looked at.

```dax
SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
```

### `Selected Period Basis`

Month, Year to date or Full year. Chooses which governed column the statement measures read; it does not change how any of them is calculated.

```dax
SELECTEDVALUE ( 'Period Basis'[basis_name], "Year to date" )
```


## 01 Income statement

### `Revenue`

Consolidated revenue from the governed measure mart. Intercompany revenue is excluded upstream on both sides of every comparison, so a plan variance is like for like.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "REVENUE" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `Cost of Sales`

Cost of sales, positive on the management sign convention.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "COST_OF_SALES" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `Gross Profit`

Gross profit. Stored as a subtotal upstream rather than computed here, because a subtotal computed in a reporting tool is a definition living in a reporting tool.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "GROSS_PROFIT" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `Gross Margin %`

Gross profit over revenue. A ratio of two governed measures, which is presentation arithmetic rather than a definition.

*Format:* `0.0%;(0.0%);"–"`

```dax
DIVIDE ( [Gross Profit], [Revenue] )
```

### `Operating Expenses`

Operating expenses, positive. Includes the non-recurring items the add-back policy later removes, because they sit inside operating expenses at layer 1 (ADR-0013).

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "OPEX" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `Statutory EBITDA`

EBITDA on the reported result, driven by the `is_ebitda` attribute on the account in the consolidation rather than by an account list here. **Distinct from Management Adjusted EBITDA and from Covenant EBITDA**, each of which has its own lineage.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = "STATUTORY"
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "EBITDA" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `Approved Add-backs`

The approved add-back policy (ADR-0013): restructuring, transaction and integration costs, legal settlements, retention bonuses and the sponsor monitoring fee. **Coalesced to zero**, because a category with no population in a period contributes nothing and must not propagate a blank into Adjusted EBITDA.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = "MANAGEMENT"
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "ADDBACKS" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value + 0 )
```

### `Management Adjusted EBITDA`

**Definition** statutory EBITDA plus the approved add-backs plus any layer-4 management adjustment -- the management view of trading performance. The add-back policy is settled upstream (ADR-0013) and arrives as a governed measure line; this measure selects it and decides nothing about what may be added back. **This is not Covenant EBITDA.** The two are equal in the current baseline because the sponsor fee runs below its cap and the covenant foreign exchange add-back has no population -- an outcome, not a definition. **Source** `mart_financial_ytd`, measure line ADJ_EBITDA. **Basis** pinned to MANAGEMENT and deliberately does not follow the Reporting Basis slicer: a definition that changes when someone moves a slicer is not a definition. **Scenario** follows the selection -- Actual, Budget, Forecast or Prior Year. **Blank policy** blank for an Actual month after the reporting close; a nil add-back category contributes zero.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = "MANAGEMENT"
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "ADJ_EBITDA" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `EBITDA Margin %`

Statutory EBITDA over revenue.

*Format:* `0.0%;(0.0%);"–"`

```dax
DIVIDE ( [Statutory EBITDA], [Revenue] )
```

### `Adjusted EBITDA Margin %`

Management Adjusted EBITDA over revenue.

*Format:* `0.0%;(0.0%);"–"`

```dax
DIVIDE ( [Management Adjusted EBITDA], [Revenue] )
```

### `Depreciation and Amortisation`

Depreciation and the amortisation of acquired intangibles, positive.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "DA" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `EBIT`

Statutory EBITDA less depreciation and amortisation. Stored upstream.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "EBIT" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `Net Finance Costs`

Interest expense and income, foreign exchange and other non-operating items, net and positive as a cost.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "NET_FINANCE" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `Income Tax`

Current and deferred tax, positive as a charge.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "TAX" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `Net Income`

Consolidated net income before the non-controlling attribution.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "NET_INCOME" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `Non-controlling Interests`

The minority's share of the result, below tax and outside EBITDA. Coalesced to zero: most entities have no minority, and a blank must not void the parent attribution.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "NCI" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value + 0 )
```

### `Net Income Attributable to Parent`

Net income less the non-controlling attribution. The bottom line of the group.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Financials'[mtd_usd] ),
            "FY", SUM ( 'Financials'[fy_usd] ),
            SUM ( 'Financials'[ytd_usd] )
        ),
        KEEPFILTERS ( 'Measure Line'[measure_code] = "NI_PARENT" ),
        KEEPFILTERS ( 'Financials'[basis] = _Reporting )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```


## 02 Scenario

### `Actual Revenue`

Revenue on the Actual scenario, **blank after the reporting close**. The consolidation publishes Actual rows for the whole fiscal year and the group has closed eight months of it; the remaining rows carry 0.00, so without the guard this reads as a company that stopped trading in September. Blank policy: BLANK past the close, never zero.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
RETURN IF ( _PastClose, BLANK (), CALCULATE ( [Revenue], 'Scenario'[scenario_code] = "ACT" ) )
```

### `Actual Adjusted EBITDA`

Management Adjusted EBITDA on Actual, blank after the reporting close.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
RETURN IF ( _PastClose, BLANK (), CALCULATE ( [Management Adjusted EBITDA], 'Scenario'[scenario_code] = "ACT" ) )
```

### `Actual EBIT`

EBIT on Actual, blank after the reporting close.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
RETURN IF ( _PastClose, BLANK (), CALCULATE ( [EBIT], 'Scenario'[scenario_code] = "ACT" ) )
```

### `Budget Revenue`

Revenue on the board-approved budget, which covers the whole fiscal year and is therefore not subject to the actual cutoff.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE ( [Revenue], 'Scenario'[scenario_code] = "BUD" )
```

### `Budget Adjusted EBITDA`

Management Adjusted EBITDA on the approved budget.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE ( [Management Adjusted EBITDA], 'Scenario'[scenario_code] = "BUD" )
```

### `Forecast Revenue`

Revenue on the **current** forecast, selected by the upstream default flag rather than by name, so a superseded forecast can never be presented as the forecast.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Version = [Current Forecast Version]
RETURN
    CALCULATE (
        [Revenue],
        FILTER ( ALL ( 'Scenario' ), 'Scenario'[version_code] = _Version )
    )
```

### `Forecast Adjusted EBITDA`

Management Adjusted EBITDA on the current forecast, selected by the default flag.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Version = [Current Forecast Version]
RETURN
    CALCULATE (
        [Management Adjusted EBITDA],
        FILTER ( ALL ( 'Scenario' ), 'Scenario'[version_code] = _Version )
    )
```

### `Prior Year Revenue`

Revenue twelve months earlier. Prior Year is derived upstream from Actual by a date offset and stored nowhere (ADR-0004), under the governed version `PY_DERIVED` (ADR-0027). No cutoff applies: prior year is complete by definition.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE ( [Revenue], 'Scenario'[scenario_code] = "PY" )
```

### `Prior Year Adjusted EBITDA`

Management Adjusted EBITDA twelve months earlier, on the governed `PY_DERIVED` version.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE ( [Management Adjusted EBITDA], 'Scenario'[scenario_code] = "PY" )
```

### `Prior Year Version`

The governed version behind Prior Year, read from the dimension rather than written into DAX. It reads `PY_DERIVED`. If this ever returns blank, the version master has lost the member and `P6-XAR-VER-01` fails -- which is precisely the defect P7-D-01 was, seen from the semantic layer.

```dax
CALCULATE (
    SELECTEDVALUE ( 'Scenario'[version_code] ),
    ALL ( 'Scenario' ),
    'Scenario'[scenario_code] = "PY"
)
```


## 03 Variance

### `Variance Base`

The measure being assessed, on the selected comparison and the selected period basis. Reads the governed variance mart; the model does not derive a comparison.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
RETURN
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Variance'[base_mtd] ),
            "FY", SUM ( 'Variance'[base_fy] ),
            SUM ( 'Variance'[base_ytd] )
        ),
        KEEPFILTERS ( 'Variance'[basis] = _Reporting )
    )
```

### `Variance Comparator`

What the base is assessed against, on the selected comparison and period basis.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
RETURN
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Variance'[comp_mtd] ),
            "FY", SUM ( 'Variance'[comp_fy] ),
            SUM ( 'Variance'[comp_ytd] )
        ),
        KEEPFILTERS ( 'Variance'[basis] = _Reporting )
    )
```

### `Variance`

Base less comparator in dollars, on the selected period basis. Precomputed upstream so the sign convention cannot differ between two reporting tools. Month, year to date and full year are three governed columns, so switching basis changes which column is read and never how the variance is computed.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
RETURN
    CALCULATE (
        SWITCH (
            _Basis,
            "MTD", SUM ( 'Variance'[var_mtd_usd] ),
            "FY", SUM ( 'Variance'[var_fy_usd] ),
            SUM ( 'Variance'[var_ytd_usd] )
        ),
        KEEPFILTERS ( 'Variance'[basis] = _Reporting )
    )
```

### `Variance %`

Variance as a percentage of the comparator, at every grain: the governed additive variance over the absolute governed comparator, with safe division. This is exactly the convention `mart_variance` stores per entity and line (`var / |comparator|`, verified on all 17,462 rows with a non-zero comparator), so at leaf grain it agrees with the mart to the cent, and at group, unit or statement grain it is a real percentage rather than a sum of percentages -- which is what it was until Phase 6A.3 (P6B-D-04: EBIT read 2,713.9% where the workbook reads (32.8%)). Percentages are never additive; this measure never adds them.

*Format:* `0.0%;(0.0%);"–"`

```dax
DIVIDE ( [Variance], ABS ( [Variance Comparator] ) )
```

### `Variance Favourability`

Favourable, Unfavourable or Neutral, decided by the **measure's own favourable direction** and not by the sign of the number. Revenue above plan is favourable; operating expense above plan is not, and colouring every positive variance green says the opposite on half a statement.

```dax
VAR _Fav = SELECTEDVALUE ( 'Measure Line'[favourable_direction] )
VAR _Var = [Variance]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( _Var ), BLANK (),
        _Fav = "NEUTRAL", "Neutral",
        _Fav = "HIGHER" && _Var > 0, "Favourable",
        _Fav = "HIGHER" && _Var < 0, "Unfavourable",
        _Fav = "LOWER" && _Var < 0, "Favourable",
        _Fav = "LOWER" && _Var > 0, "Unfavourable",
        "Neutral"
    )
```

### `Variance Is Comparable`

Whether the selected comparison is like for like. Budget and forecast are built at entity level and carry no consolidation entries, so a plan comparison is comparable down to EBIT and is not below it. The flag is set upstream.

```dax
IF (
    COUNTROWS ( FILTER ( 'Variance', NOT 'Variance'[is_comparable] ) ) = 0,
    "Yes",
    "Not comparable"
)
```


## 04 Balance sheet

### `Total Assets`

Total assets at the selected month end, from the approved consolidated balance sheet.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Balance Sheet'[balance_usd] ),
    'Balance Sheet'[account_class] = "ASSET",
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Total Liabilities`

Total liabilities, sign-flipped to the positive presentation a reader expects.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
-CALCULATE (
    SUM ( 'Balance Sheet'[balance_usd] ),
    'Balance Sheet'[account_class] = "LIABILITY",
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Total Equity`

Total equity, including the unclosed result for the period, the translation reserve and the non-controlling interest.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
-CALCULATE (
    SUM ( 'Balance Sheet'[balance_usd] ),
    'Balance Sheet'[account_class] = "EQUITY",
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Balance Sheet Check`

Assets less liabilities and equity. Nil in every period, and shown rather than assumed.

*Format:* `#,0,,.00;(#,0,,.00);"–"`

```dax
[Total Assets] - [Total Liabilities] - [Total Equity]
```

### `Cash`

Cash and cash equivalents at the month end.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Balance Sheet'[balance_usd] ),
    'Balance Sheet'[caption] = "Cash and cash equivalents",
    'Balance Sheet'[account_class] = "ASSET",
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Accounts Receivable`

Trade receivables, net of provision.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Balance Sheet'[balance_usd] ),
    'Balance Sheet'[caption] = "Accounts receivable, net",
    'Balance Sheet'[account_class] = "ASSET",
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Inventory`

Inventory, net of the unrealised profit provision the consolidation posts against it.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Balance Sheet'[balance_usd] ),
    'Balance Sheet'[caption] = "Inventory, net",
    'Balance Sheet'[account_class] = "ASSET",
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Accounts Payable`

Trade and other payables at the latest period in context, from the governed balance sheet caption and shown positive. Statutory basis, Actual only.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
-CALCULATE (
    SUM ( 'Balance Sheet'[balance_usd] ),
    'Balance Sheet'[caption] = "Accounts payable",
    'Balance Sheet'[account_class] = "LIABILITY",
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Net Working Capital`

Receivables plus inventory less payables plus other working capital, from the governed working capital mart rather than re-added here.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Working Capital'[nwc_usd] ),
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Property Plant and Equipment`

Owned property, plant and equipment at net book value -- cost less accumulated depreciation, both settled upstream. Statutory basis, Actual only.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Balance Sheet'[balance_usd] ),
    'Balance Sheet'[caption] = "Property, plant and equipment, net",
    'Balance Sheet'[account_class] = "ASSET",
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Goodwill`

Goodwill on eleven acquisitions, derived from the goodwill bridge in the consolidation and never plugged.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Balance Sheet'[balance_usd] ),
    'Balance Sheet'[caption] = "Goodwill",
    'Balance Sheet'[account_class] = "ASSET",
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Intangible Assets`

Acquired customer relationships and technology at fair value, less accumulated amortisation.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Balance Sheet'[balance_usd] ),
    'Balance Sheet'[caption] = "Intangible assets, net",
    'Balance Sheet'[account_class] = "ASSET",
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Retained Earnings`

Accumulated earnings closed into reserves. Positive means accumulated profit.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
-CALCULATE (
    SUM ( 'Balance Sheet'[balance_usd] ),
    'Balance Sheet'[caption] = "Retained earnings",
    'Balance Sheet'[account_class] = "EQUITY",
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Cumulative Translation Adjustment`

**Definition** the equity reserve arising because assets and liabilities translate at closing rates while equity translates at historical rates. Derived upstream as a residual of the translation itself and **never plugged** (ADR-0017). **Not the foreign exchange effect on cash**, which is a cash-flow item with a different value and a different cause; the two are separate measures here for that reason. **Source** `mart_balance_sheet`, caption 'Cumulative translation adjustment', class EQUITY, at the latest period in context. **Basis** statutory. **Scenario** Actual only. **Blank policy** blank when the caption has no row.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
-CALCULATE (
    SUM ( 'Balance Sheet'[balance_usd] ),
    'Balance Sheet'[caption] = "Cumulative translation adjustment",
    'Balance Sheet'[account_class] = "EQUITY",
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Non-controlling Interest Equity`

**Definition** the minority's share of consolidated net assets, a separate component of equity, attributed by the Phase 4 NCI engine and never derived here. **Source** `mart_balance_sheet`, caption 'Non-controlling interests', class EQUITY, at the latest period in context; sign-flipped for presentation because equity is stored credit-negative. **Basis** statutory and management are identical for NCI -- layer 4 carries no minority attribution. **Scenario** balance sheet is published on Actual only; a plan selection returns nothing rather than a plan balance sheet that was never built. **Blank policy** blank when the caption has no row, never zero: a period with no balance sheet is not a period with no minority interest.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
-CALCULATE (
    SUM ( 'Balance Sheet'[balance_usd] ),
    'Balance Sheet'[caption] = "Non-controlling interests",
    'Balance Sheet'[account_class] = "EQUITY",
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```


## 05 Cash flow

### `Operating Cash Flow`

Operating cash flow, derived upstream from balance sheet movements (ADR-0006).

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
SUM ( 'Cash Flow'[operating_cash_flow_usd] )
```

### `Investing Cash Flow`

Cash used in investing for the period, principally capital expenditure. Classified upstream by each account's cash flow category, never by a rule written here.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
SUM ( 'Cash Flow'[investing_cash_flow_usd] )
```

### `Financing Cash Flow`

Cash from financing for the period: debt drawn and repaid, and interest paid. Classified upstream by each account's cash flow category.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
SUM ( 'Cash Flow'[financing_cash_flow_usd] )
```

### `FX Effect on Cash`

The retranslation of foreign-currency cash balances. **Not the cumulative translation adjustment**, which arises on net assets and sits in equity. Conflating the two makes a cash flow tie while reporting an implausible exchange effect on a mostly-USD balance.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
SUM ( 'Cash Flow'[fx_effect_on_cash_usd] )
```

### `Net Change in Cash`

The movement in cash, measured from the cash accounts themselves. Cash is never the residual of the statement.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
SUM ( 'Cash Flow'[net_change_in_cash_usd] )
```

### `Opening Cash`

Cash at the start of the selected range.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Cash Flow'[opening_cash_usd] ),
    'Date'[period_key] = MIN ( 'Date'[period_key] )
)
```

### `Closing Cash`

**Definition** cash and equivalents at the end of the selected range. **Source** `mart_cash_flow.closing_cash_usd` at the latest period in context -- taken from the cash flow rather than re-derived, so the statement that explains the movement and the balance it moves to cannot disagree. **Basis** statutory; the cash position is not a management-adjusted figure. **Scenario** Actual only. **Blank policy** blank outside the published range. `P6-XAR` reconciles it to the balance sheet cash caption and to the Excel cash sheet, both to 0.00.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Cash Flow'[closing_cash_usd] ),
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Cash Flow Check`

Opening plus the movements less closing. Nil in every period.

*Format:* `#,0,,.00;(#,0,,.00);"–"`

```dax
[Opening Cash] + [Operating Cash Flow] + [Investing Cash Flow]
    + [Financing Cash Flow] + [FX Effect on Cash] - [Closing Cash]
```

### `Total Liquidity`

Cash plus the undrawn revolving facility at the selected month end.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Cash Flow'[liquidity_usd] ),
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```


## 06 Debt and covenants

### `Gross Debt`

All debt instruments at the month end, whether or not the agreement counts them.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Covenants'[gross_debt_usd] ),
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Covenant Debt`

Debt that counts toward the covenant, per the instrument's own flag in the debt schedule: the term loan, the revolver and finance leases, and not operating leases (CA-018).

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Covenants'[covenant_debt_usd] ),
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Covenant Net Debt`

**Definition** covenant debt less unrestricted cash, per credit agreement CA-019. There is no cash-netting cap (CA-020), so the full cash balance nets. This is **not** the balance sheet's net debt: covenant debt counts only the instruments the agreement counts, and `Economic Leverage` is the measure that uses the wider definition. **Source** `mart_covenants.net_debt_usd` at the latest period in context, computed upstream from the debt schedule's covenant flag. **Basis** the covenant basis, which is neither statutory nor management -- it is the agreement's. **Scenario** Actual only; the covenant is tested on reported results. **Blank policy** blank before the first measurable period, never zero.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Covenants'[net_debt_usd] ),
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Covenant EBITDA`

**Definition** EBITDA as the **credit agreement** defines it, on a rolling twelve months. A third definition, not an alias of Adjusted EBITDA: the agreement caps the sponsor fee and adds back an FX item management reporting does not, so the two differ by construction even where they happen to sit close together. **Source** `mart_covenants.covenant_ebitda_usd`, where the bridge from statutory EBITDA is built and evidenced. **Basis** the agreement's, which is neither statutory nor management. **Scenario** Actual only -- a covenant is tested on reported results. **Blank policy** blank before twelve months of history exist, because a rolling twelve-month figure taken over eight months is not a smaller number, it is a different measure.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Covenants'[covenant_ebitda_usd] ),
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Covenant Net Leverage`

**Definition** covenant net debt over **rolling twelve-month** covenant EBITDA. The rolling window is the whole point: dividing a full net debt balance by a part-year EBITDA reports a breach that does not exist, which is exactly what the Phase 5 visual review caught at 7.38x against a 4.50x limit. **Source** `[Covenant Net Debt]` over `[Covenant EBITDA]`, both from `mart_covenants`, both computed upstream. **Basis** the agreement's. **Scenario** Actual only. **Blank policy** blank when either input is blank -- a leverage ratio with no EBITDA is not zero turns, it is unmeasurable. Read it with `[Covenant Status]`, which reports **Indicative** on any date the agreement does not test.

*Format:* `0.00"x";(0.00"x");"–"`

```dax
DIVIDE ( [Covenant Net Debt], [Covenant EBITDA] )
```

### `Covenant Limit`

The maximum leverage the agreement permits for the fiscal year: 6.00x FY2023, 5.50x FY2024, 5.00x FY2025 and 4.50x from FY2026, each read from its own agreement term.

*Format:* `0.00"x";(0.00"x");"–"`

```dax
CALCULATE (
    MAX ( 'Covenants'[max_net_leverage] ),
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Covenant Headroom`

Turns of headroom against the limit. Negative would be a breach.

*Format:* `0.00"x";(0.00"x");"–"`

```dax
[Covenant Limit] - [Covenant Net Leverage]
```

### `Is Covenant Test Date`

Whether the selected month is a date the agreement actually tests. The agreement sets a maximum per **fiscal year**, so the test dates are the year ends. A quarterly presentation once stamped BREACH on two dates the agreement never tests.

```dax
IF ( SELECTEDVALUE ( 'Date'[accounting_period] ) = 12, TRUE, FALSE )
```

### `Covenant Status`

Compliant or Breach at a real test date, and **Indicative** anywhere else. Telling a board it breached a covenant it did not breach is the most expensive mistake a reporting layer can make, so a verdict is given only where the agreement gives one.

```dax
VAR _Headroom = [Covenant Headroom]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( _Headroom ), BLANK (),
        NOT [Is Covenant Test Date], "Indicative",
        _Headroom >= 0, "Compliant",
        "Breach"
    )
```

### `Economic Leverage`

Leverage including operating lease liabilities, which the agreement excludes. Shown because a reader should see both.

*Format:* `0.00"x";(0.00"x");"–"`

```dax
CALCULATE (
    MAX ( 'Covenants'[economic_leverage] ),
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```


## 07 Workforce

### `Opening FTE`

Full-time equivalents at the start of the selected range.

*Format:* `#,0.0`

```dax
CALCULATE (
    SUM ( 'Headcount'[fte_opening] ),
    'Date'[period_key] = MIN ( 'Date'[period_key] )
)
```

### `Hires`

People joining. A **count**, not an FTE: a part-time joiner is one hire and a fraction of an FTE, so hires are never netted against the FTE movement.

*Format:* `#,0`

```dax
SUM ( 'Headcount'[hires] )
```

### `Exits`

People leaving, on the same basis as hires.

*Format:* `#,0`

```dax
SUM ( 'Headcount'[leavers] )
```

### `Closing FTE`

Full-time equivalents at the end of the selected range. Continuous with the prior month at the finest grain.

*Format:* `#,0.0`

```dax
CALCULATE (
    SUM ( 'Headcount'[fte_closing] ),
    'Date'[period_key] = MAX ( 'Date'[period_key] )
)
```

### `Average FTE`

The mean of the monthly averages over the selected range, rather than the average of a sum, which would scale with the number of months.

*Format:* `#,0.0`

```dax
AVERAGEX (
    VALUES ( 'Date'[period_key] ),
    CALCULATE ( SUM ( 'Headcount'[fte_average] ) )
)
```

### `Personnel Cost`

Personnel cost from the income statement detail, so it agrees with operating expenses rather than with a payroll extract.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
CALCULATE (
    SUM ( 'Financial Detail'[amount_usd] ),
    'Account'[fs_caption_l2] = "Personnel costs"
)
```

### `Cost per Average FTE`

Personnel cost over average full-time equivalents.

*Format:* `#,0`

```dax
DIVIDE ( [Personnel Cost], [Average FTE] )
```


## 08 Capital expenditure

### `Actual CapEx`

Capital spend, blank after the reporting close on the same rule as every other Actual measure.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
RETURN IF ( _PastClose, BLANK (), SUM ( 'CapEx'[spend_usd] ) )
```

### `Approved CapEx`

The amount approved for the projects in scope. **This is the capital plan.** The capex subledger carries no scenario dimension -- there is no separate budget or forecast version of capital spend anywhere upstream -- so the approved amount on the project is the plan a variance is measured against, and no Budget CapEx or Forecast CapEx measure is offered. Inventing one would mean inventing the data behind it.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
SUM ( 'CapEx'[approved_usd] )
```

### `CapEx Variance`

Spend less approved. **Positive is over-approval, and over-approval is unfavourable** — capital spend follows the same account-aware favourability rule as operating expense, and colouring a positive variance green here would say the opposite of what it means.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
[Actual CapEx] - [Approved CapEx]
```

### `CapEx Variance %`

Spend against approval as a percentage of the approved amount.

*Format:* `0.0%;(0.0%);"–"`

```dax
DIVIDE ( [CapEx Variance], ABS ( [Approved CapEx] ) )
```

### `CapEx Variance Favourability`

Favourable when spend is inside approval. Stated explicitly rather than inherited from the statement favourability rule, because CapEx does not sit on the income statement and has no Measure Line row to take a direction from.

```dax
VAR _Var = [CapEx Variance]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( _Var ), BLANK (),
        _Var > 0, "Unfavourable",
        _Var < 0, "Favourable",
        "Neutral"
    )
```

### `Capital Projects`

How many capital projects are in scope. A distinct count on the **corrected** business key (ADR-0026): before the correction this counted 395 against 1,846 real projects, because five programmes in an entity-month shared one identifier.

*Format:* `#,0`

```dax
DISTINCTCOUNT ( 'CapEx'[project_id] )
```

### `CapEx to Depreciation`

Capital spend as a multiple of the depreciation charge — the usual test of whether an asset base is being maintained.

*Format:* `0.00"x";(0.00"x");"–"`

```dax
DIVIDE ( [Actual CapEx], [Depreciation and Amortisation] )
```


## 09 Foreign exchange

### `Constant Currency Revenue`

This year's activity restated at last year's average rate. An **operating** measure: what a reader means by how much of the revenue movement was currency. Not the translation adjustment.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
SUM ( 'FX'[revenue_constant_ccy_usd] )
```

### `FX Translation Effect on Revenue`

Reported revenue less constant currency revenue.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
SUM ( 'FX'[revenue_usd] ) - [Constant Currency Revenue]
```

### `CTA Movement`

The movement in the cumulative translation adjustment, an equity reserve. Derived by the consolidation as the residual of the translated trial balance, never plugged.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
SUM ( 'FX'[cta_movement_usd] )
```


## 10 Reporting

### `Account Amount`

The account-grain amount from the monthly mart, on the period basis, reporting basis and Actual cutoff the statement measures use. It exists so a statement line can be drilled to the accounts behind it (Group → unit → entity → account) and it adds nothing the mart does not already hold: month = the month's rows, year to date = the fiscal year's rows to the selected month, full year = the fiscal year's rows. No accounting logic lives here; the sign, the basis and the mapping to a line are the mart's.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Reporting = SELECTEDVALUE ( 'Reporting Basis'[basis], "STATUTORY" )
VAR _Scenarios = VALUES ( 'Scenario'[scenario_code] )
VAR _ActualOnly =
    COUNTROWS ( _Scenarios ) = 1 && MAXX ( _Scenarios, 'Scenario'[scenario_code] ) = "ACT"
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _Year = MAX ( 'Date'[fiscal_year] )
VAR _PastClose = _ActualOnly && _Latest > [Reporting Period Key]
VAR _Value =
    SWITCH (
        _Basis,
        "MTD",
            CALCULATE (
                SUM ( 'Financial Detail'[amount_usd] ),
                KEEPFILTERS ( 'Financial Detail'[basis] = _Reporting )
            ),
        "FY",
            CALCULATE (
                SUM ( 'Financial Detail'[amount_usd] ),
                REMOVEFILTERS ( 'Date' ),
                'Date'[fiscal_year] = _Year,
                KEEPFILTERS ( 'Financial Detail'[basis] = _Reporting )
            ),
        CALCULATE (
            SUM ( 'Financial Detail'[amount_usd] ),
            REMOVEFILTERS ( 'Date' ),
            'Date'[fiscal_year] = _Year,
            'Date'[period_key] <= _Latest,
            KEEPFILTERS ( 'Financial Detail'[basis] = _Reporting )
        )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `Layer EBITDA`

EBITDA contributed by each consolidation layer on the period basis selected -- the month, the fiscal year to the month, or the fiscal year -- and blank after the reporting close, exactly as Statutory EBITDA is. From the governed consolidation bridge at month grain: Entity Reported, Intercompany Eliminations, Consolidation Adjustments, Management Adjustments and Translation Adjustment. Statutory is layers 1 + 2 + 3 + 5 and sums to [Statutory EBITDA] on every basis (`P6B1-BR`); management adds layer 4. Presentation of the approved layers, not a new policy.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _Year = MAX ( 'Date'[fiscal_year] )
VAR _PastClose = _Latest > [Reporting Period Key]
VAR _Value =
    SWITCH (
        _Basis,
        "MTD", SUM ( 'Layer Bridge'[ebitda_usd] ),
        "FY", CALCULATE (
            SUM ( 'Layer Bridge'[ebitda_usd] ),
            REMOVEFILTERS ( 'Date' ),
            'Date'[fiscal_year] = _Year
        ),
        CALCULATE (
            SUM ( 'Layer Bridge'[ebitda_usd] ),
            REMOVEFILTERS ( 'Date' ),
            'Date'[fiscal_year] = _Year,
            'Date'[period_key] <= _Latest
        )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `Layer Net Income`

Net income contributed by each consolidation layer on the period basis selected, blank after the reporting close, from the governed consolidation bridge at month grain; the statutory layers sum to [Net Income] on every basis.

*Format:* `#,0,,.0;(#,0,,.0);"–"`

```dax
VAR _Basis = SELECTEDVALUE ( 'Period Basis'[basis_code], "YTD" )
VAR _Latest = MAX ( 'Date'[period_key] )
VAR _Year = MAX ( 'Date'[fiscal_year] )
VAR _PastClose = _Latest > [Reporting Period Key]
VAR _Value =
    SWITCH (
        _Basis,
        "MTD", SUM ( 'Layer Bridge'[net_income_usd] ),
        "FY", CALCULATE (
            SUM ( 'Layer Bridge'[net_income_usd] ),
            REMOVEFILTERS ( 'Date' ),
            'Date'[fiscal_year] = _Year
        ),
        CALCULATE (
            SUM ( 'Layer Bridge'[net_income_usd] ),
            REMOVEFILTERS ( 'Date' ),
            'Date'[fiscal_year] = _Year,
            'Date'[period_key] <= _Latest
        )
    )
RETURN IF ( _PastClose, BLANK (), _Value )
```

### `Layer Entries`

Journal entries posted at each consolidation layer in the months in context -- a count over the months selected, not a period-basis measure; a visual says which months it counts.

*Format:* `#,0`

```dax
SUM ( 'Layer Bridge'[entries] )
```

### `Revenue Share of Group`

Revenue in the current context as a share of Group revenue in the same period, scenario and reporting basis. The denominator removes only the Business Unit and Entity filters, by name: on a unit row it is the Group, on an entity row it is still the Group. For the share of the parent unit use Revenue Share of Unit -- one measure, one denominator.

*Format:* `0.0%;(0.0%);"–"`

```dax
DIVIDE (
    [Revenue],
    CALCULATE ( [Revenue], REMOVEFILTERS ( 'Business Unit' ), REMOVEFILTERS ( 'Entity' ) )
)
```

### `Revenue Share of Unit`

Revenue in the current context as a share of the revenue of the business unit(s) in context, in the same period, scenario and reporting basis. The denominator removes only the Entity filter: on an entity row it is the entity's unit; on a unit row it is 100%.

*Format:* `0.0%;(0.0%);"–"`

```dax
DIVIDE ( [Revenue], CALCULATE ( [Revenue], REMOVEFILTERS ( 'Entity' ) ) )
```
