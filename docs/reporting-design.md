# Reporting Design

What gets built in Phases 6–8, and the specific question each artefact answers. Nothing is
built in Phase 1.

## 1. Design rule

**Every page and every worksheet must answer a question a named person actually asks.** If
we cannot write the question down, the page does not get built. The failure mode this
guards against is the twenty-page dashboard where nineteen pages are looked at once, during
the handover meeting, and never again.

Design priorities, in order: accounting integrity, then reconciliation, then usability, then
appearance. A beautiful chart of a number that does not tie is worse than useless, because
it is believed.

## 2. Audience and cadence

| Audience | Artefact | Cadence | What they need |
|---|---|---|---|
| CFO | Power BI executive pages, Excel management pack | Monthly, working day 5 | Is the group on plan, and if not, why and what is being done |
| Board / sponsor | Board reporting pack (PDF from Power BI + commentary) | Quarterly | Trajectory, covenant position, value-creation progress |
| Group Financial Controller | Consolidation workbook, controls dashboard | Monthly, during close | Does it tie, and can I sign it |
| BU leaders | Entity and BU performance pages | Monthly | My P&L, my variances, my cost centres |
| FP&A team | Forecast model, variance and bridge pages | Continuous | Build and defend the forecast |
| Treasury | Cash, liquidity and covenant page | Monthly + on demand | Liquidity, covenant headroom, FX exposure |

## 3. Excel deliverables

Three workbooks, each with a distinct job. Power Query handles all data acquisition from the
published Parquet marts; Power Pivot holds the model where one is needed. **No workbook
contains a hard-coded number that is not an explicit, labelled assumption.**

### 3.1 `Northstar_Management_Reporting_Pack.xlsx`

The monthly pack the CFO reads. Refreshable, print-formatted.

| Worksheet | Purpose |
|---|---|
| `00_Cover` | Period, version, preparer, refresh timestamp, **control status summary** |
| `01_Executive_Summary` | One page: group KPIs, actual vs budget vs prior year, MTD / YTD / FY outlook |
| `02_Income_Statement` | Group P&L with MTD, YTD and FY outlook columns; $ and % variance, favourable/unfavourable |
| `03_PL_by_Business_Unit` | Same statement pivoted by BU with contribution analysis |
| `04_PL_by_Entity` | Entity-level P&L; the drill from BU to legal entity |
| `05_Balance_Sheet` | Consolidated balance sheet, current vs prior month vs prior year end |
| `06_Cash_Flow` | Indirect cash flow with the reconciliation to balance sheet cash shown on the face |
| `07_EBITDA_Bridge` | Budget → Actual walk: volume, price, mix, cost, FX, one-time |
| `08_Revenue_Bridge` | Budget → Actual walk: organic, acquisition, price/volume, FX |
| `09_Working_Capital` | DSO, DIO, DPO, cash conversion cycle by entity, with movement drivers |
| `10_CapEx` | Capex by project and asset class, budget vs actual, commitments |
| `11_Headcount` | FTE by BU and function, movement, revenue and EBITDA per FTE |
| `12_Debt_and_Covenants` | Debt schedule, covenant calculations, headroom, maturity profile |
| `13_Variance_Commentary` | Structured commentary keyed to variance lines — author, not generated |
| `14_KPI_Trend` | Rolling 24-month trend of the headline metrics |
| `90_Control_Dashboard` | Every control, its status and its measured value for the period |
| `95_Assumptions` | Every assumption in one place, each with an owner and a date |
| `99_Data` | Power Query connections and staging tables. Hidden. |

The control dashboard is inside the reporting pack deliberately. A reader should not have to
go somewhere else to find out whether the numbers they are reading passed their checks.

### 3.2 `Northstar_Consolidation_Workbook.xlsx`

The controller's working file — the evidence that the consolidation is right.

| Worksheet | Purpose |
|---|---|
| `00_Close_Checklist` | Close calendar, task owners, sign-off status |
| `01_TB_by_Entity` | Source trial balance per entity, local currency, with the balancing proof |
| `02_Mapping_Exceptions` | Unmapped accounts, unresolved conditional splits, suspense balances |
| `03_FX_Rates` | Rates applied, by currency, period and rate set, with source |
| `04_Translation_Proof` | Local → USD by entity with the CTA derivation shown line by line |
| `05_IC_Matrix` | Entity-pair intercompany matrix, both sides, differences and ageing |
| `06_Elimination_Schedule` | Every elimination entry with its supporting calculation |
| `07_Consolidation_Adjustments` | Investment eliminations, PPA, NCI, unrealised profit |
| `08_Adjustment_Log` | Every management adjustment: ID, type, preparer, approver, narrative |
| `09_Consolidated_TB` | The consolidated trial balance |
| `10_Source_to_Consol_Recon` | The `CTL-REC-01` reconciliation from ERP sum to board number |
| `11_Statement_Builder` | Financial statements assembled from the consolidated TB |
| `90_Controls` | Full control results with drill-down to failing rows |

Worksheet `10` is the one that would be handed to an auditor first.

### 3.3 `Northstar_Forecast_Model.xlsx`

The driver-based rolling forecast model. This is where forecasts are **built**, not just
reported.

| Worksheet | Purpose |
|---|---|
| `00_Control` | Version, scenario, actual/forecast month split, lock status |
| `01_Drivers` | All forecast drivers in one place: volume, price, margin, days, rates |
| `02_Revenue_Build` | Revenue by BU and entity from volume and price drivers |
| `03_Margin_Build` | Cost of sales by category, driven by revenue and margin assumptions |
| `04_Headcount_Plan` | FTE plan by function, driving personnel cost |
| `05_OpEx_Build` | Operating expense by category, headcount-linked where appropriate |
| `06_Working_Capital` | Days-based working capital projection |
| `07_CapEx_Plan` | Capex by project with depreciation roll-forward |
| `08_Debt_Schedule` | Debt roll-forward, interest, covenant projection |
| `09_PL_Output` | Projected income statement |
| `10_BS_Output` | Projected balance sheet, with the balancing check on the face |
| `11_CF_Output` | Projected cash flow, tying to balance sheet cash |
| `12_Scenario_Compare` | This forecast against budget, prior forecast and prior year |
| `13_Forecast_Accuracy` | Historical accuracy of closed forecast versions by BU |
| `95_Assumptions` | Every assumption with owner and rationale |

The three-statement output must balance and tie inside the workbook, using the same
identities as the anchor model. A forecast whose balance sheet does not balance is not a
forecast.

`13_Forecast_Accuracy` exists because forecast quality should be measured. It is
uncomfortable and it is the point.

## 4. Power BI deliverables

One `.pbip` project in TMDL/PBIR format, source-controlled as text (ADR-0010). One shared
semantic model; report pages grouped by audience.

### 4.1 Report pages

Twelve report pages, two drill-through pages and one information page. Each page below states
the question it answers.

| # | Page | The question it answers |
|---|---|---|
| 1 | **Executive Summary** | *Are we on plan this month and for the year, and what are the three things moving?* Group revenue, Adjusted EBITDA, margin, cash, net leverage — actual vs budget vs prior year, with MTD/YTD/FY-outlook toggles. |
| 2 | **Income Statement** | *Where exactly is the variance?* Full P&L with $ and % variance and favourable/unfavourable logic, drillable Group → BU → Entity → Department → Account Category → GL Account. |
| 3 | **EBITDA Bridge** | *Why is EBITDA different from plan?* Waterfall decomposing volume, price, mix, cost inflation, FX, one-time items. Reported and Adjusted EBITDA both shown, with the add-back list visible. |
| 4 | **Revenue Analytics** | *Where is growth coming from, and how concentrated is it?* Revenue by BU, geography, customer group, product family; organic vs acquisition; bookings and backlog. |
| 5 | **Business Unit & Entity Performance** | *Which parts of the group are performing?* Small multiples across BUs and entities; contribution to group EBITDA; entity league table. |
| 6 | **Balance Sheet & Working Capital** | *Is the balance sheet getting better or worse?* Balance sheet with movement analysis; DSO, DIO, DPO and cash conversion cycle by entity; working capital bridge. |
| 7 | **Cash Flow & Liquidity** | *Where did the cash go, and do we have enough?* Cash bridge, operating/investing/financing, free cash flow, liquidity, revolver availability. |
| 8 | **Debt & Covenant Compliance** | *Are we safe on the covenants, and for how long?* Debt by instrument, maturity profile, covenant net leverage and interest coverage against tested thresholds, headroom trend, swap maturity. Economic Net Leverage shown alongside as a clearly labelled non-covenant measure. Built to accommodate the reserved Downside scenario without redesign. |
| 9 | **Budget, Forecast & Accuracy** | *Do we believe the forecast?* Budget vs current forecast vs prior forecast versions; forecast accuracy by BU over time; FY outlook. |
| 10 | **FX Impact & Constant Currency** | *How much of this is real?* Reported vs constant currency by BU and entity; translation impact on revenue, EBITDA and net assets; CTA movement; rate trends. |
| 11 | **Intercompany & Consolidation** | *Does the consolidation hold together?* Intercompany matrix by entity pair, mismatches and ageing, elimination summary, source-to-consolidated reconciliation. |
| D1 | *Drill-through: Account Detail* | Journal-level detail behind any selected figure |
| D2 | *Drill-through: Entity Detail* | Full entity P&L, balance sheet and KPI card |
| 12 | **Controls & Data Quality** | *Can I trust this pack?* Every control, status, measured value, trend; failing rows listed. |
| i | *Model Information* | Refresh timestamp, period, versions in use, definitions, contact |

Page 10 exists as its own page rather than as a section of page 3 because "how much of the
variance is FX?" is the first question a CFO asks about any international group's numbers,
and the answer needs more than one visual. Page 8 is a separate page because covenant
headroom is tight enough in this business to warrant it (0.70x at FY2026F).

Twelve substantive pages for a group of this complexity is deliberately restrained. The
temptation is thirty.

### 4.2 Semantic model design

**Calculation groups** rather than measure explosion. Two calculation groups do the work
that would otherwise require several hundred near-duplicate measures:

| Calculation group | Items |
|---|---|
| `Time Intelligence` | Current, MTD, QTD, YTD, R12M, FY Outlook, Prior Year, Prior Year YTD |
| `Scenario Comparison` | Actual, Budget, Forecast, Prior Year, Constant Currency, Variance $, Variance %, Variance F/U |

Base measures are defined once (`Revenue`, `Gross Profit`, `EBITDA`, `Adjusted EBITDA`,
`Net Income`, `Operating Cash Flow`, `Net Debt`, `FTE`, …) and the calculation groups apply
the time and scenario context. A new base measure gets all thirty-plus variants for free.

**Favourable/unfavourable logic is account-aware.** A variance is not favourable because it
is positive — an overspend on operating expenses is a positive number and a bad outcome.
Direction is driven by the account's `normal_balance` and `account_class`, so the logic is
defined once in the model rather than re-implemented per visual and inevitably reversed
somewhere.

**Row-level security**: entity-based roles so a BU leader sees their own entities. Defined
in the model, tested in Phase 9.

**Storage mode**: import, with incremental refresh partitioned on `period_key`. At ~3.2m
rows the model compresses to well under a gigabyte, and import gives the interactive
performance that a monthly review meeting needs.

### 4.3 Visual conventions

- Consistent, restrained palette. Scenario colours fixed across every page: Actual, Budget,
  Forecast, Prior Year always the same colour everywhere.
- Favourable green / unfavourable red used **only** for variance direction, never
  decoratively. Both are paired with a sign or an arrow so the meaning survives colour-blind
  readers and monochrome printing.
- No gauges, no donuts, no 3-D, no gradient fills.
- Every number carries its units and its basis (`USD m`, `Actual vs Budget`, `YTD`).
- Every page carries the period, the scenario version and the refresh timestamp.
- Currency shown in USD millions to one decimal at group level; entity detail in thousands.

## 5. Board reporting pack

Produced quarterly (Phase 8). A paginated PDF assembled from Power BI plus a structured
commentary layer.

| Section | Content |
|---|---|
| 1 | Executive summary and the quarter in one page |
| 2 | Financial performance: P&L against budget, prior year and prior forecast |
| 3 | EBITDA and revenue bridges with written explanation of each bar |
| 4 | Business unit review, one page each |
| 5 | Balance sheet, working capital and cash |
| 6 | Debt, liquidity and covenant compliance |
| 7 | Forecast update and FY outlook, with the change from the prior forecast explained |
| 8 | Value-creation plan progress against the sponsor's investment thesis |
| 9 | Risks, watch items and management actions |
| A | Appendix: entity detail, accounting policies, control summary, glossary |

**Commentary framework.** Commentary is authored by finance, not generated. The platform's
job is to make it fast and consistent by supplying, for every material variance: the amount,
the decomposition, the responsible entity and cost centre, and the equivalent prior-period
commentary. A variance qualifies as material and requires commentary if it exceeds **$250k
or 5% of the line, whichever is greater** — a stated rule, applied consistently, so that
commentary coverage is itself measurable.

Generic AI-written commentary is explicitly out of scope. "Revenue decreased due to lower
sales" is worse than no commentary because it consumes the reader's attention and returns
nothing.

## 6. Metric definitions

Defined once, here, and implemented once, in the semantic layer. Ambiguity in these
definitions is where management reporting credibility goes to die.

| Metric | Definition |
|---|---|
| Revenue | External revenue only; intercompany revenue eliminated |
| Gross Profit | Revenue less cost of sales (`5xxxxx`) |
| Gross Margin % | Gross profit ÷ revenue |
| EBITDA | Revenue less cost of sales less operating expenses (`6xxxxx`). Excludes D&A, interest and tax. **Includes** non-recurring operating costs. |
| Adjusted EBITDA | EBITDA plus accounts flagged `is_ebitda_addback`. No run-rate synergy add-backs. |
| Net Debt | Term loan (gross principal) + revolver + finance leases − cash. **Excludes** operating lease liabilities. |
| Net Leverage | Net debt ÷ trailing-twelve-month Adjusted EBITDA |
| Interest Coverage | Trailing-twelve-month Adjusted EBITDA ÷ net interest expense |
| Free Cash Flow | Operating cash flow less capital expenditure |
| Net Working Capital | Receivables + contract assets + inventory + prepaids − payables − contract liabilities − accruals. Excludes cash, debt and tax. |
| DSO | (Trade receivables ÷ revenue) × days in period |
| DIO | (Inventory ÷ cost of sales) × days in period |
| DPO | (Trade payables ÷ cost of sales) × days in period |
| Revenue per FTE | Revenue ÷ average FTE for the period |
| Constant Currency | Actual local amounts translated at budget rates |
| FX Impact | Reported USD less constant-currency USD |
| Organic Growth | Growth excluding entities within twelve months of their acquisition date |
| Forecast Accuracy | 1 − (mean absolute percentage error of the forecast version against actual) |

Two definitions warrant a note because reasonable people disagree about them:

**Covenant net debt excludes operating lease liabilities; Economic Net Leverage includes
them.** Two measures, reported together, neither replacing the other:

| USD m / x | FY2023A | FY2024A | FY2025A | FY2026B | FY2026F |
|---|---|---|---|---|---|
| Covenant net debt | 211.6 | 248.1 | 231.8 | 209.9 | 225.1 |
| Operating lease liabilities | 22.0 | 24.0 | 24.5 | 24.0 | 25.5 |
| **Economic net debt** | **233.6** | **272.1** | **256.3** | **233.9** | **250.6** |
| Covenant net leverage | 5.42x | 5.26x | 4.01x | 3.31x | 3.80x |
| **Economic net leverage** | **5.98x** | **5.77x** | **4.43x** | **3.68x** | **4.23x** |
| Covenant maximum | 6.00x | 5.50x | 5.00x | 4.50x | 4.50x |

**Covenant leverage is the tested ratio and the default** on every covenant and board view,
because it is the definition with consequences — it is what the lender measures and what a
breach would be measured against. Economic Net Leverage is a **non-covenant KPI** presented
alongside it, because a reader assessing the group's real obligations should see that roughly
half a turn of leverage sits in leases that the 2021 credit agreement's definition of
Indebtedness happens to exclude. Presenting only the covenant measure understates the economic
position; presenting only the economic measure misstates covenant compliance.

The two are never mixed into one number and never compared against each other's threshold.
There is **no covenant threshold for Economic Net Leverage**, and none is implied.

**Adjusted EBITDA contains no run-rate synergy add-backs**, and share-based compensation is not
added back. Both follow the credit agreement (`CA-028`, `CA-029`), which expressly disallows
them — so the group's management measure and the lender's measure agree. The sponsor monitoring
fee **is** added back, but only because clause S6.9 explicitly permits it, and only up to the
$1.5m annual cap (`CA-026`, `CA-027`). Add-back composition is anchored account by account in
`config/anchors/anchor_addback_composition.csv`.

## 7. Performance targets

| Target | Threshold |
|---|---|
| Power BI page render, cold | < 3 seconds |
| Power BI page render, warm | < 1 second |
| Excel pack full refresh | < 60 seconds |
| Full warehouse rebuild from raw | < 5 minutes |
| Board pack PDF generation | < 2 minutes |
