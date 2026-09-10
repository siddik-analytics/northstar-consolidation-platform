# Phase 5.2 — Excel executive design and visual polish

**Status:** owner-approved (with the Phase 5.2A copper system); the workbook is frozen
**Baseline:** `65b7b48` (Phase 6A.1, approved and frozen)
**Scope:** visual, UX and presentation only. No finance logic, no reporting definitions.

---

## 1. The assessment before

The workbook was technically correct and every automated check was green — 17/17 reconciliations,
0 layout findings — and it did not look like a premium deliverable. Rendering all sixteen sheets
through Excel's own PDF writer and *looking at them* found why.

**Every chart in the workbook was broken.** All seventeen rendered with no value axis and no
category axis: bare lines and bars floating over gridlines that implied a scale nobody could
read. A reader could not tell whether revenue was 30 or 300, or which month any point belonged
to.

That single defect had hidden a second one. **Every chart also plotted a phantom leading zero**,
because all 26 series references began at row 1 of the chart data sheet — the *header* row —
while their categories began at row 2. Excel plots a text header as zero, so every line dived to
the axis before starting, every bar chart was shifted one category to the right, and the
leverage chart's y-axis was dragged down to zero by a value that did not exist.

Neither is visible in a spreadsheet's XML, in a formula audit, or in a reconciliation. Both
needed someone to look at the picture.

Beyond the charts: repeated content burying material figures on the debt page, a control summary
that understated the platform it described, two negative-number conventions on the same sheet,
and a P&L whose lower 40% was empty canvas.

---

## 2. Issues identified

| # | sheet | finding |
|---|---|---|
| 1 | **all** | **both axes deleted on all 17 charts** — `openpyxl` writes `<c:delete val="1"/>` unless `delete` is set to `False`, and nothing set it |
| 2 | **all** | **26 chart series started at the header row**, plotting a phantom zero and shifting every bar chart by one category |
| 3 | all | gridlines heavy and black, implying a scale that was never drawn |
| 4 | all | chart borders, default fonts, no shared chart language |
| 5 | Cash Flow, Debt, others | charts straddled the page break — top clipped on one page, bottom on the next, legend orphaned from its plot |
| 6 | Cash Flow | negative bars rendered as hollow outlines, reading as missing data |
| 7 | Debt & Covenants | 12 near-identical finance-lease rows above the two instruments that are 96% of the debt |
| 8 | Debt & Covenants | chart titled "maturity profile" plotted drawn amount by type |
| 9 | Debt & Covenants | leverage chart scaled 0–5.00x, compressing the 3.8–4.7x covenant band into the top fifth |
| 10 | Executive Summary | ten KPIs in an undifferentiated grid, no hierarchy |
| 11 | Executive Summary | KPI comparators used `-5.6` while every table used `(5.6)` |
| 12 | Executive Summary | the same attention comment repeated verbatim three times |
| 13 | P&L | lower 40% of the sheet empty; no chart at all |
| 14 | Consolidation & Controls | control status stopped at Phase 5 — 250 controls, omitting the integrity and semantic registers |
| 15 | QA harness | PNG rasterisation was a manual step, so a visual review could read images from a previous build. **It did**: the first chart fix appeared to change nothing |

---

## 3. Changes by worksheet

**Every sheet** — the chart system was rebuilt: axes visible and styled (hairline rules in the
table-rule colour, 8pt muted labels, no tick marks), gridlines reduced to a hairline on the value
axis only, chart borders and fills removed, titles set in the workbook's own font at one size,
legends styled to match, negative bars keeping their series colour, and charts starting on a clean
page so none is ever cut in half.

**Executive Summary** — see §4.

**P&L** — a gross and EBITDA margin trend now occupies the empty lower half, full width. A second
chart (year-to-date variance by line) was built, reviewed, and **removed**: it said exactly what
the Var $ column beside it already said, and a chart that repeats its own table is decoration.

**Cash Flow** — charts moved whole onto their own page; all four cash-flow categories now render,
negatives filled rather than hollow; the liquidity line is visible where it was previously clipped.

**Debt & Covenants** — the twelve finance leases collapse to one line, `Finance leases (12
instruments)`, so the capital structure reads Term Loan B → Revolver → leases, largest first.
Total unchanged and still summed from the rows on the page (258.339 drawn, 38.5 undrawn, both
agreeing with the mart to the cent). The maturity chart is correctly titled *Drawn debt by
instrument type*. The leverage chart is scaled 3.00x–5.00x so the covenant band is legible.

**Consolidation & Controls** — the control status now covers the whole environment: Phase 2 (80),
Phase 3 (62), Phase 4 (72), Phase 5 (36), Phase 5.1 keys/grain/versions (295) and Phase 6A
semantic (49). **594 controls, 594 passed.**

---

## 4. Executive Summary

The flagship sheet now answers the CFO's thirty-second question on one page.

**KPI hierarchy.** The ten metrics are grouped and labelled — **Performance** (revenue, gross
margin, EBITDA, adjusted EBITDA, EBITDA margin) and **Cash, leverage and capacity** (operating
cash flow, net debt, net leverage, covenant headroom, headcount). Ten things to read became two
groups of five.

All ten were kept. Each answers a question a CFO asks, none duplicates another, and dropping one
to demonstrate editorial courage would have removed information rather than noise.

**One negative convention.** Comparators read `(5.6) vs budget (2.0%)`, matching the tables
beneath them, instead of `-5.6 vs budget (-2.0%)`.

**Trend charts** now have scales, stop at the reporting close, and show the budget continuing —
which is what makes the actual cutoff legible rather than looking like missing data.

**Attention list** — three identical sentences became *Largest / Second largest / Third largest
unfavourable variance against budget year to date — 9.0m behind plan.* Still deterministic, still
generated from the variance mart, no interpretation added.

**One page.** The charts here deliberately opt out of the automatic page break: keeping a chart
whole matters less than keeping the executive summary whole.

---

## 5. Chart changes

All 17 charts: axes restored, series corrected, gridlines quietened, borders removed, fonts
unified, legends styled, negatives filled.

Removed: 1 (P&L variance bar — duplicated its own table).
Added: 1 (P&L margin trend).
Retitled: 1 (debt maturity → drawn debt by type).
Rescaled: 1 (leverage, to the covenant band).

Every remaining chart answers a management question the tables cannot: is the margin holding,
where is cash going, how much covenant headroom is left, which business unit is behind.

---

## 6–8. The systems

**Typography** — one family, Calibri, throughout sheets and charts. Sizes: page title 20,
section header 12, table header and body 10, KPI metric 20, KPI label 8, notes and chart axes 8,
chart titles 9.5. Weight is used to mean *subtotal* and *total*, not for emphasis.

**Colour** — unchanged from the approved palette, now applied to charts as well as cells: ink
`1F2A37`, muted `5B6B7B`, rules `D5DBE1`, header `1B4965`. Scenario colours are constant
everywhere — Actual `1B4965`, Budget `8C9BAB`, Forecast `C9772E`, Prior year `B7BFC7` — and
favourable `1E7A46` / unfavourable `B3261E` are reserved for favourability, never for sign.

**Number formats** — `$#,##0.0;($#,##0.0);"–"` for USD millions, `0.0%;(0.0%);"–"` for
percentages, `0.0" pp"` for margin movements, `0.00"x"` for leverage, `#,##0` for headcount.
Zero prints as `–` everywhere. Negatives are always brackets, now including the KPI comparators.

---

## 9. Viewport

Executive Summary reads as a single page at 100% zoom: KPIs, group performance, both trend
charts and the attention list, with no horizontal scrolling. Charts sit beside the content they
belong to rather than far to the right. Freeze panes were reviewed and left as they were — they
hold the label column and header rows without eating usable width.

---

## 10. Print and PDF

All sixteen visible sheets export cleanly through Excel's own PDF writer at their own print
settings. No clipped objects, no orphan titles, no chart split across a page. The page-break rule
means a chart band starts on a fresh page and carries its section header with it.

**0 blocking, 0 warnings** from the layout inspection.

---

## 11. Screenshot review

Sixteen sheets rendered to PDF and rasterised to PNG at 150 dpi — now automatically, as part of
the QA step. Every sheet was reviewed twice: once to find the issues above, once after the
changes.

The second pass found three regressions from my own edits, all fixed: doubled brackets in the
KPI percentage (`((2.0)%)`), the new page-break rule splitting the Executive Summary, and two P&L
charts bound to the wrong data columns because a column-renumbering patch ran before the code it
was meant to renumber.

---

## 12. Portfolio value

**Before:** technically credible, visually generated. Seventeen charts with no axes would be the
first thing a reviewer noticed, and it would undermine the analysis behind them.

**After:** the Executive Summary, P&L, Cash Flow, Debt & Covenants and Consolidation & Controls
pages would each stand as a portfolio screenshot. What carries them is not decoration but the
content: an actual cutoff visible in the chart line, a covenant page that distinguishes a
contractual test date from an indicative month, and a control page showing 594 governed controls
across six phases.

Where it remains short of a bespoke engagement: this is a *management pack*, not a board pack —
there is no narrative commentary, and deliberately so, because every word in it is generated
deterministically and an interpretation would be a claim the platform cannot evidence.

---

## 13–14. Financial invariance

Compared cell by cell against the approved pre-polish workbook, and by value multiset per sheet
so that content moving between cells is not mistaken for content changing.

**No reported financial value changed.** Four sheets show a difference in their set of numbers,
and each is an intended presentation change:

| sheet | change |
|---|---|
| `09 Debt & Covenants` | 12 lease rows replaced by one aggregate — total 258.339 / 38.5 unchanged and still agreeing with the mart |
| `13 Consolidation & Controls`, `00 Cover` | control count 250 → 594, because Phase 5.1 and 6A registers are now included |
| `_chart` (hidden) | 14 new values feeding the P&L margin chart |

Every other sheet — P&L, Balance Sheet, Cash Flow, Business Units, Entities, Working Capital,
EBITDA Bridge, Headcount, CapEx, FX, Variance Detail — is numerically identical.

**17/17 workbook reconciliations pass.** No formula was changed.

---

## 15. Native Excel validation

Everything was calculated, rendered and inspected in Microsoft Excel through COM — full
recalculation, native chart rendering, native PDF export. No LibreOffice, and openpyxl was used
only to author the workbook, never to re-save one Excel had touched.

---

## 16. Regression

| | |
|---|---|
| workbook reconciliations | **17/17** |
| layout inspection | 0 blocking, 0 warnings |
| Phase 5 mart controls | 36/36 |
| Phase 5.1 key, grain, version controls | 295/295 |
| Phase 6A semantic controls | 49/49 |
| `pytest` | **529 passed** |
| determinism | two rebuilds, identical digest `508f1173b6a99404` |
| upstream | `src/generation`, `src/pipeline`, `src/consol`, `src/marts`, `src/powerbi`, `src/integrity`, `config/` untouched |

---

## 17. Remaining visual limitations

1. **Category labels sit inside downward bars** on the cash flow category chart — Excel places
   them at the value axis and the bar covers them. Legible, but not ideal.
2. **No waterfall charts.** A true bridge needs invisible connector series; the EBITDA bridge is a
   column chart of its components. Honest, and less elegant than a real waterfall.
3. **Rate and maturity columns on the debt page** carry more whitespace than they need — the
   header alignment and the column widths do not quite agree.
4. **The workbook is landscape A4 throughout.** It reads well on screen and prints well, but a
   wide monitor leaves margin at both sides on the narrower sheets.
