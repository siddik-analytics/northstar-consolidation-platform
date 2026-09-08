# Phase 5 — Reporting marts and the Excel management model

Formal completion report. Two deliverables: a governed reporting layer over the frozen
consolidation, and a management reporting workbook built on it.

**Consolidation frozen at `5636f8b`.** Source layer `fd7afb8f…`, consolidation build
`78e406e139662392`, reporting mart build `2caac83888d04d3f`.

No accounting logic changed. The consolidation's own artefacts are byte-identical to the frozen
build.

---

## 1. Scope

| | |
|---|---|
| Reporting marts | 19 published, over the consolidated fact, the plan and the operational facts |
| Mart controls | 36, all passing |
| Excel workbook | 16 report sheets, 26 hidden governed data sheets, 20 charts |
| Workbook checks | 17 reconciliations against the marts, plus a layout inspection |
| Visual review | every sheet exported by Excel and looked at |
| Tests | 18 new, 454 in total |

## 2. The reporting marts

`python -m src.marts.run` — 3 seconds.

| Mart | Rows | Mart | Rows |
|---|---|---|---|
| `mart_financial_monthly` | 133,558 | `mart_working_capital` | 48 |
| `mart_financial_ytd` | 44,184 | `mart_headcount` | 22,215 |
| `mart_variance` | 50,652 | `mart_capex` | 1,846 |
| `mart_business_unit` | 18,032 | `mart_debt` | 595 |
| `mart_entity_performance` | 41,832 | `mart_covenants` | 33 |
| `mart_balance_sheet` | 1,296 | `mart_fx` | 176 |
| `mart_cash_flow` | 48 | `mart_management_adjustments` | 2 |
| `mart_consolidation_bridge` | 20 | four reporting dimensions | 26 |

Design and rationale: [`reporting-marts.md`](../reporting-marts.md).

## 3. Reconciliation to Phase 4

Every reconciliation recomputes one side from `fact_financials` rather than reading it back
from the artefact under test.

| | Threshold | Measured |
|---|---|---|
| Financial mart against the consolidated fact, every measure, every month | 0.05 USD | **0.00** |
| Balance sheet mart reproduces the statement | 0.01 USD | **0.00** |
| Balance sheet still balances, all 48 periods | 0.01 USD | **0.00** |
| Cash flow mart reproduces the statement and still ties | 0.01 USD | **0.00** |
| Closing cash across two marts | 0.01 USD | **0.00** |
| Business unit totals to the measure mart | 0.05 USD | **0.00** |
| Entity totals to the measure mart | 0.05 USD | **0.00** |
| Covenant EBITDA at each year end to the approved bridge | 0.01 USD | **0.00** |
| Headcount, capex, debt and FX marts to their facts | 0.01 | **0.00** |

## 4. The workbook

`data/90_exports/Northstar_Consolidation_Management_Reporting.xlsx` — 3.1 MB.

00 Cover · 01 Executive Summary · 02 P&L · 03 Business Units · 04 Entities · 05 Balance Sheet ·
06 Cash Flow · 07 Working Capital · 08 EBITDA Bridge · 09 Debt & Covenants · 10 Headcount ·
11 CapEx · 12 FX · 13 Consolidation & Controls · 14 Variance Detail · 15 Data & Technical.

Every figure is a `SUMIFS` into a hidden governed data sheet; every hidden sheet is a query
against a mart. The workbook computes variance dollars, percentages, subtotals, ratios of two
mart measures and display logic — and no accounting policy. Detail:
[`excel-model.md`](../excel-model.md).

## 5. Headline results, at August 2026

| USD m | YTD actual | YTD budget | Var | Prior year | FY outlook | FY budget |
|---|---|---|---|---|---|---|
| Revenue | 279.0 | 284.5 | (5.6) | 262.8 | 437.2 | 448.0 |
| Gross profit | 76.0 | 78.3 | (2.3) | 72.1 | 126.3 | 132.4 |
| EBITDA | 28.1 | 31.0 | (2.9) | 27.6 | 53.4 | 60.0 |
| Adjusted EBITDA | 31.9 | 33.3 | (1.4) | 31.8 | 59.2 | 63.5 |
| EBIT | 15.5 | 23.0 | (7.5) | 15.4 | 41.4 | 47.8 |
| Attributable to the parent | (0.8) | 6.3 | (7.0) | (1.6) | 16.5 | 22.4 |

**Balance sheet at 31 August 2026** — total assets 465.5, liabilities 373.2, equity 92.3, and
the check row nil. Goodwill 140.7, acquired intangibles 47.7, non-controlling interests 1.9.

**Cash flow year to date** — operating (7.5), investing (2.0), financing 2.0, FX on cash 0.1,
closing cash 14.6, and the tie nil in every month.

**Covenant** — net debt 243.8 against 57.8 of last-twelve-months covenant EBITDA is **4.21x**
against a 4.50x limit: **0.29 turns of headroom**, compliant at every test date.

**Liquidity** 53.1 — cash 14.6 plus 38.5 undrawn against a 10.0 minimum cash policy.
**Headcount** 2,477 FTE, up 32 on the prior year.

## 6. Variance architecture

Four comparisons — Actual vs Budget, vs Forecast, vs Prior Year, and Forecast vs Budget — on
three period bases (month, year to date, full year), in dollars and percent, with
favourability assigned by the **measure's own favourable direction** rather than by the sign of
the number.

Prior year is derived from Actual by a twelve-month offset and never stored, so it cannot drift
from the actual it is a view of. Three forecast versions are retained and exactly one is the
default. The reserved Downside scenario appears nowhere.

Plan is entity-level and carries no consolidation entries, so plan comparisons are like for
like down to EBIT and are not below it. `is_comparable` says which, on every row.

## 7. Defects found and fixed in this phase

All were in the Phase 5 reporting layer. None reached the consolidation.

| | Found by | Fix |
|---|---|---|
| Covenant leverage on a fiscal-year EBITDA reported **7.38x against a 4.50x limit** for a year in progress | visual review | rolling twelve-month window, proved against the approved bridge at each year end |
| **A covenant breach stamped on two dates the agreement never tests** | visual review | the agreement sets a limit per fiscal year, so the grid shows year ends and labels the current month indicative |
| A control asserting `opening FTE + hires − leavers = closing FTE` | the control failing | the identity was wrong, not the data: hires are counts, FTE is fractional |
| Actual series plotted to zero after the reporting date | visual review | `#N/A` beyond the close, and gaps rather than zeros |
| "Not comparable" on every variance row | visual review | `SUMIFS` ignores booleans; the flag is now 1/0 |
| Revenue shown negative in the account detail | visual review | management sign convention applied |
| Every business unit at a 100% margin | visual review | revenue shows share of group, EBITDA shows margin |
| Charts running off the page on six sheets | visual review | widths derived from the sheet's own columns |
| A note overprinting the band beneath it | visual review | row height computed from the text |
| Layer 4 missing from the consolidation view | visual review | every declared layer appears, including the empty one |
| Truncated headings on six sheets; `IT` rendered as `It` | visual review | column widths and an acronym rule |

## 8. Controls and tests

| | |
|---|---|
| Phase 2 source controls | **80/80** |
| Phase 3 pipeline controls | **62/62** |
| Phase 3 fault sweep | **10/10** |
| Phase 4 consolidation controls | **72/72** |
| Phase 4 fault fixtures | **23/23** |
| **Phase 5 reporting controls** | **36/36** |
| **Workbook reconciliations** | **17/17** |
| **Workbook layout findings** | **0 blocking, 0 warnings** |
| Tests | **454 passed** |

**286 controls across five phases**, all passing.

## 9. Determinism

| | |
|---|---|
| Source layer digest | `fd7afb8f…` **unchanged** |
| Consolidation build id | `78e406e139662392` **unchanged** |
| Consolidation artefacts | **15/15 byte-identical** |
| Reporting mart build id | `2caac83888d04d3f`, a digest of the consolidation manifest and the mart code |
| Mart artefacts | 19 Parquet files with per-file checksums in `data/phase05_manifest.json` |
| Workbook build digest | `ee8bf988bdfe9a56`, identical across three builds |
| Working tree after a full rebuild | clean |

The mart manifest records the consolidation build and source digest it was built on, so a mart
can never silently belong to a different consolidation than the one it claims. The workbook
manifest does the same for the marts.

An `.xlsx` is a zip and a zip records the wall-clock time of each member, so two builds of
identical data differed for no reason anyone would care about. Timestamps and document
properties are fixed at build time and the archive is rewritten in a stable order, which makes
the **build** a pure function of the marts. The QA step then opens the file in Excel and saves
the calculated values back — an intended change, so that a reader who opens the workbook
without recalculating still sees numbers, and one Excel does not make byte-identically. The
reproducibility claim is therefore made where it can be: on the build, and `data/phase05_workbook_manifest.json`
records the digest.

## 10. Limitations

* **The workbook's QA step needs Windows and Excel.** The file builds anywhere; calculating,
  inspecting and rendering it uses Excel through COM.
* **Actual is reported to August 2026.** The consolidation generates Actual rows for the whole
  of FY2026 and the group has closed eight months; the workbook reports the close it would
  really have and the forecast covers the rest.
* **Plan comparisons stop at EBIT**, because a plan carries no consolidation entries.
* **The management basis equals the statutory basis**, because layer 4 is empty under the
  approved register. The workbook reports statutory and says so.
* **No invoice-level ageing** exists, so working capital days are derived from the consolidated
  statements and no ageing profile is shown.
* **No PivotTables or Data Model.** The presentation sheets are formula-driven by design; a
  Power Pivot model is the right home for exploratory analysis and belongs with Phase 6.
* **Deterministic commentary only.** The attention list is generated by rule and states the
  calculation behind each line. No narrative is generated.

## 11. Recommendation for Phase 6

**Power BI semantic model and report suite**, per [`roadmap.md`](roadmap.md), reading the same
marts:

1. **A semantic model over the mart layer** — `mart_financial_ytd`, `mart_variance`,
   `mart_balance_sheet`, `mart_cash_flow` and the operational marts as fact tables, with the
   reporting dimensions already built. The measure definitions and the favourability rule are
   settled, so DAX expresses them rather than deciding them.
2. **A `P6-XAR` control family** comparing published Power BI measures with the marts, exactly
   as `P5` compares the workbook. The lesson of Phase 4C and Phase 5 is the same: a second tool
   expressing the same measure is a second chance to disagree.
3. **Report pages mirroring the workbook's questions**, not its layout — a dashboard is a
   different medium and copying a spreadsheet into it produces a worse version of both.

The Excel model and the Power BI model should be two presentations of one governed layer, and
the control that proves it should exist before the second one is built.
