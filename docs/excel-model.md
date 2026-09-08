# The Excel management reporting model

`data/90_exports/Northstar_Consolidation_Management_Reporting.xlsx` — sixteen report sheets
over the governed marts, built as code.

    python -m src.marts.run      # the marts
    python -m src.excel.build    # the workbook
    python -m src.excel.qa       # calculate, inspect and render it in Excel

---

## 1. What it is, and what it is not

It is a **reporting and analysis layer** over the approved consolidation. It is **not** a second
financial model, and the difference is enforced rather than intended: every figure is a
`SUMIFS` into a hidden governed data sheet, and every hidden data sheet is a query against a
reporting mart.

The workbook may compute:

* variance dollars and percentages
* subtotals of measures the mart already defines
* ratios of two mart measures — a margin, a multiple of depreciation, cost per FTE
* display logic — which column to read, what to call a status

The workbook may **not** compute: EBITDA, the add-back policy, FX translation, eliminations,
NCI, the covenant rules, the cash flow, or a variance definition. Those live upstream and
`test_the_workbook_reconciles_to_the_marts` reads them back out of the calculated file to prove
it.

## 2. Why it is authored, not edited

There is no template. Every sheet, style, number format, chart, defined name, data validation
and print area in the output is created by `src/excel/`, which means the workbook is in version
control **as code** and a change to it is a diff rather than a description of what somebody did
in Excel. It also means the file is reproducible: the same marts produce the same workbook.

The concern about libraries stripping a Data Model, PivotCaches, slicers or Power Query from a
workbook applies to *round-tripping* an existing file. Nothing is round-tripped here, so
nothing can be stripped. Excel itself is then used for what only Excel can do — calculate,
resolve the rendered layout, and produce the images the visual review is done from.

## 3. Why formulas rather than pivots

The presentation sheets are `SUMIFS` grids, not PivotTables, and that is deliberate:

* a pivot **resizes** when a filter changes, and takes conditional formatting, merged headers
  and chart source ranges with it;
* a pivot's layout is a property of the data, so a sheet that looks right today looks different
  after a refresh that adds an entity;
* a `SUMIFS` grid is the same shape whatever the reader selects, which is what makes the
  executive sheets safe to export to PDF or paste into a board deck.

Formulas read defined names — `SUMIFS(pl_ytd, pl_measure, "EBITDA", pl_ver, "ACTUAL",
pl_period, 202608)` — so a reviewer can read a formula rather than decode a range.

Interaction is provided where it belongs: **sheet 14** has three validated dropdowns
(comparison, business unit, period basis) and the grid below responds. Three controls, not
twenty-five.

## 4. The sheets

| | Sheet | Answers |
|---|---|---|
| 00 | Cover | What is this, on what basis, from which build, and is it in control |
| 01 | Executive Summary | How is the group performing, why, and what needs attention |
| 02 | P&L | The management income statement, monthly and year to date |
| 03 | Business Units | Which business unit explains group performance |
| 04 | Entities | What each legal entity contributed, with currency and ERP context |
| 05 | Balance Sheet | The financial position, against prior month and prior year |
| 06 | Cash Flow | Where the cash went, and what liquidity is available |
| 07 | Working Capital | Receivables, inventory, payables and the conversion cycle |
| 08 | EBITDA Bridge | Statutory to management adjusted, and separately to covenant |
| 09 | Debt & Covenants | Debt by instrument, net leverage and covenant headroom |
| 10 | Headcount | Headcount movement, by business unit and function |
| 11 | CapEx | Capital expenditure by unit, asset class and project |
| 12 | FX | Currency exposure, constant currency and the translation adjustment |
| 13 | Consolidation & Controls | What the consolidation does, and the evidence it is right |
| 14 | Variance Detail | Selectable variance analysis down to account level |
| 15 | Data & Technical | Lineage, marts consumed, build identifiers, refresh |

Twenty-six hidden `_`-prefixed sheets hold the governed extracts. A reader opening the pack
sees sixteen reports, not forty tabs.

## 5. The Executive Summary

The sheet a CFO reads first, and the only one designed around a question rather than a
statement: **how is the group performing, why, and what requires attention?**

**Ten KPIs**, in two rows of five, each with its value, its movement against budget coloured by
whether that movement is good news, and its unit. Revenue, gross margin, EBITDA, Adjusted
EBITDA, EBITDA margin; operating cash flow, net debt, net leverage, covenant headroom,
headcount. Ten, not thirty: a panel of thirty numbers is a data sheet with rounded corners.

**Six headline measures** on actual, budget, prior year and full-year outlook, with variance in
dollars and percent, coloured by the measure's own favourable direction.

**Two charts** — revenue and Adjusted EBITDA, each actual against budget. Not three: the
business unit comparison has a sheet of its own.

**Requires management attention**, generated by a deterministic rule: the three largest
unfavourable year-to-date variances by absolute value, the business unit with the largest
adjusted EBITDA shortfall, and the covenant headroom whenever it is inside one turn. Each line
states the calculation that produced it. There is no generated prose, because commentary the
model cannot evidence is worse than no commentary.

## 6. What the numbers show

At August 2026, eight months into FY2026:

| | YTD | Budget | Var | FY outlook | FY budget |
|---|---|---|---|---|---|
| Revenue | 279.0 | 284.5 | (5.6) | 437.2 | 448.0 |
| Gross profit | 76.0 | 78.3 | (2.3) | 126.3 | 132.4 |
| EBITDA | 28.1 | 31.0 | (2.9) | 53.4 | 60.0 |
| Adjusted EBITDA | 31.9 | 33.3 | (1.4) | 59.2 | 63.5 |
| EBIT | 15.5 | 23.0 | (7.5) | 41.4 | 47.8 |

Net debt 243.8, net leverage **4.21x** against a 4.50x covenant, headroom **0.29 turns**.
Liquidity 53.1 — cash 14.6 plus 38.5 undrawn. Headcount 2,477.

The group is behind budget on revenue and materially behind on EBIT, and the covenant is
compliant with headroom narrowing. That is what the pack says, on every sheet, consistently.

## 7. Style

One system, in `src/excel/style.py`, applied everywhere. See
[`excel-style-guide.md`](excel-style-guide.md). The short version: Calibri throughout; a
six-colour palette where colour carries meaning and everything else is greyscale; negatives in
parentheses; **zero shown as a dash**; money in USD millions to one decimal, ratios to two,
percentages to one, headcount and days to none; column A a gutter, column B the label, data
from column C, freeze panes on every report sheet.

## 8. Controls exposed in the workbook

Sheet 13 puts the evidence beside the numbers rather than asking the reader to trust them:

* the five consolidation layers and what each contributed
* what the consolidation did — goodwill, intangibles, investment eliminated, intercompany
  matched, unrealised profit, NCI, CTA, management adjustments
* **286 controls across five phases**, with pass and fail counts by phase
* five reconciliations computed in the workbook itself: the balance sheet balances, the cash
  flow ties, closing cash agrees between two statements, Covenant EBITDA is never null, no
  reserved scenario is offered

Control results are read from the governed registers, not recomputed.

## 9. Refresh

| | |
|---|---|
| 1 | `python -m src.marts.run` — rebuild the marts and run their 36 controls |
| 2 | `python -m src.excel.build` — rebuild the workbook |
| 3 | `python -m src.excel.qa` — calculate in Excel, inspect, reconcile and render |

The **build** is byte-reproducible: document properties and every zip member's timestamp are
fixed, so the same marts produce the same file, and `data/phase05_workbook_manifest.json`
records its digest. Step 3 then saves Excel's calculated values back into the file, which
rewrites the archive — intended, so a reader who opens the workbook without recalculating sees
numbers rather than formulas.

Step 3 is not optional. openpyxl writes formulas and does not evaluate them, so a workbook full
of `#REF!` looks perfect to the library that produced it.

## 10. Known limitations

* **Windows and Excel are required for step 3.** The workbook builds anywhere; calculating,
  inspecting and rendering it needs Excel through COM.
* **Actual is reported to August 2026.** The consolidation generates Actual rows for the whole
  of FY2026 and the group has closed eight months of it; the workbook reports the close it
  would really have, and the forecast covers the rest.
* **Plan comparisons stop at EBIT** — see the comparability rule in
  [`reporting-marts.md`](reporting-marts.md).
* **No invoice-level ageing** exists in the model, so sheet 07 shows days computed from the
  consolidated statements and no ageing profile.
* **The management basis equals the statutory basis**, because layer 4 is empty on the approved
  register. The workbook reports the statutory basis and says so.
