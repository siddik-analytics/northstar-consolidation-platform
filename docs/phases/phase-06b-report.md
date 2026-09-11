# Phase 6B — Power BI executive report

**Status:** reviewed at `2fe00ee` — architecture, controls, native validation, interactions and
density **approved**; final sign-off held for two corrections, made in
[Phase 6B.1](phase-06b-1-reporting-integrity.md)
**Baseline:** `89d1369` (Phase 6A.3 sealed); Excel frozen at `bf847b4327526a39`, untouched
**Docs:** [the report](../powerbi-report.md) · [style guide](../powerbi-style-guide.md) ·
[controls](../powerbi-controls.md#the-report-on-the-model-p6b) · [defect register](../defect-register.md) ·
[lessons §17](../architecture-lessons.md) · [screenshots](../assets/phase-06b/MANIFEST.md)

---

## 1. What this phase delivered

The report that stopped at `331814d` on three semantic defects resumed on the corrected
model, was not restarted, and was taken through visual QA, a control family of its own, a
fixture suite, a native pass in Power BI Desktop and a three-way reconciliation on real
values. The semantic model was not touched: definition digest `af1c6264f61aeb66` before and
after. The Excel workbook was not touched: `bf847b4327526a39` before and after.

| | |
|---|---|
| pages | 10, from `src/powerbi/report/pages.py` |
| visuals | 655 — 28 analytical, 160 KPI, 27 slicers, 100 navigation, 224 text, 116 shapes |
| report controls | **43 (`P6B`), 43/43 pass, 0 not executed** |
| report fixtures | **12, 12/12 detected by the control named for each** |
| reconciliations | 13 measures, report scope → engine → mart, every one to the cent or 1e-5 turns |
| native pass | Desktop 2.157.1354.0: opened through its own dialog, refreshed, **0 visual errors on 10 pages**, 10/10 navigation, unit slicer narrows, Actual line ends at the close, 10 rendered cards equal the engine |
| semantic model | unchanged; 68/68, 16/16 |

## 2. Corrections propagated natively (§1 of the brief)

Verified in Desktop and in the engine, not assumed:

| correction | evidence |
|---|---|
| **P6B-D-05** Business Unit filters | choosing *Industrial Services* in the slicer: Revenue 279.0 → 84.1, Adjusted EBITDA 31.9 → 4.6, gross margin 27.2% → 20.1%, FTE 2,477.4 → 1,051.7; Group cash, net debt, leverage and headroom hold, as the tiles say (`P6B-22`). Units sum to the Group for Revenue, Adjusted EBITDA and FTE in the page's own scope (`P6B-05`) |
| **P6B-D-04** `[Variance %]` | the P&L reads EBIT (32.8%), Revenue (2.0%), EBITDA (9.4%), Net income (115.0%) — the workbook's figures; the outlook's full-year Var % is the same measure at FY basis |
| **P6B-D-03** formats | `279.0`, `(5.6)`, `(0.9)` for net income, `–` for a zero, `27.2%`, `4.21x`, `2,477.4` FTE, all from the model's own formats; no projection format, no display unit (`P6B-15`) |
| visual workarounds | none remain: `fmt_values` is a no-op kept only for the record, the KPI tiles bind measures directly |

## 3. What changed in the report since `331814d`

**Executive Overview rebuilt as three tiers.** First tier navy-edged and large — Revenue,
Adjusted EBITDA, Cash, Covenant net leverage, the two performance tiles with the governed
variance and its favourability word. Second tier on the copper wash — gross margin, EBITDA
margin, operating cash flow, covenant net debt, headroom, headcount. Middle: revenue by
month, the **full-year outlook** (current forecast against budget on five lines, from
`[Variance Base]`/`[Variance Comparator]` at FY basis), Adjusted EBITDA variance by unit
coloured by favourability. Bottom: cash and liquidity, leverage against the dashed limit.
The variance matrix with the truncated "Direction" column is gone.

**The new measures in use.** `[Account Amount]` gives the P&L page an account-detail matrix;
`[Revenue Share of Group]` and `[Revenue Share of Unit]` are two columns of the unit → entity
matrix with a subtitle stating both denominators; `[Layer EBITDA]`, `[Layer Net Income]`
and `[Layer Entries]` replace the typed note on the Controls page with the bridge by layer
and entries by layer and year.

**Scope honesty.** Balance sheet, cash flow, working capital and covenants are Group facts,
so pages 04 and 05 carry a period slicer only and the Controls page none; the Executive
Overview's Group-level tiles say *Group*. Workforce and capital measures are date-range
measures, so page 08 has no basis slicer, its tiles are the month selected and its charts
FY2026 to the close, and it says so.

**Every switched-off interaction has a reason** (29 edges, `layout.Page.no_filter` refuses
one without), every visual is classified for the object inventory, every page states the
question it answers, and the ten questions are printed on the Lineage page.

**Polish.** No scrollbars where the content fits; no caption textbox shorter than its line
(the grey marks in the first render were scrollbars); tables sized to their columns; the tab
tooltip kept out of every capture; the covenant limit no longer typed in a note.

## 4. Three scope faults the QA found — and the controls that now hold them

None was a measure. Each was a page saying the right number in the wrong scope, and none of
the 68 semantic controls could have seen it because each evaluates a measure in a filter the
control writes. Lessons §17.

| fault | seen as | held by |
|---|---|---|
| the outlook ignored the month slicer, so a full-year figure carried on every month's row was summed twelve times | revenue 5,246.4m against a budget of 5,376.0m | `P6B-30…42` reconcile in the visual's own scope, derived from the generated files |
| the favourability rule was declared once for the series and evaluated at the Group | every unit bar red, including the one that beat budget | the data-point wildcard selector; `P6B-25` re-evaluates the rendered cards |
| unit and entity slicers on pages whose facts have no entity grain | a slicer that changed nothing | `P6B-24` walks each slicer's dimension along the active paths to the tables the page's measures read |

## 5. The `P6B` family and its fixtures

Twenty-three static controls on the generated files, seven live in the engine, five native
from the Desktop record, thirteen reconciliations — the table is in
[`powerbi-controls.md`](../powerbi-controls.md#the-report-on-the-model-p6b). The eight
fixtures the brief named (typed KPI, implicit measure, cutoff bypass, typed covenant verdict,
stale project key, typed control count, report-side variance %, double-scaled money) and
four more (broken navigation, an axis display unit, an unreasoned NoFilter, an inert slicer):
**12/12 detected by the intended control.**

## 6. Report ↔ semantic ↔ mart, on real values

The visual's scope (its filters, the page's slicer defaults, minus the interactions it
switched off) is evaluated in the engine and compared with the semantic controls' mart SQL.
Aug 2026, year to date, statutory, USD:

| concept | page / visual | value | mart | Δ |
|---|---|---|---|---|
| Revenue | 01 `p_rev_v` | 278,980,889.78 | 278,980,889.78 | 0 |
| Gross Profit | 02 P&L row | 75,980,813.59 | 75,980,813.59 | 0 |
| Statutory EBITDA | 02 P&L row | 28,100,907.83 | 28,100,907.83 | 0 |
| Adjusted EBITDA | 01 `p_ebitda_v` | 31,911,102.90 | 31,911,102.90 | 0 |
| EBIT | 02 P&L row | 15,473,409.60 | 15,473,409.60 | 0 |
| Net Income | 02 P&L row | (939,022.82) | (939,022.82) | 0 |
| Cash | 01 `p_cash_v` | 14,579,689.06 | 14,579,689.06 | 0 |
| Net Debt | 01 `s_nd_v` | 243,759,330.75 | 243,759,330.75 | 0 |
| Covenant EBITDA | 07 `d_ebitda_v` | 57,842,615.47 | 57,842,615.47 | 0 |
| Covenant Leverage | 01 `p_lev_v` | 4.21x | 4.21x | 1.8e-5 |
| Covenant Headroom | 01 `s_head_v` | 0.29x | 0.29x | 1.8e-5 |
| FTE | 01 `s_fte_v` | 2,477.4 | 2,477.4 | 0 |
| CapEx (August) | 08 `x_spend_v` | 1,895,221.42 | 1,895,221.42 | 0 |

And what Desktop drew, read back from its accessibility tree and re-evaluated: Revenue
`279.0`, Adjusted EBITDA `31.9`, Cash `14.6`, leverage `4.21x`, gross margin `27.2%`,
EBITDA margin `10.1%`, operating cash flow `5.0`, net debt `243.8`, headroom `0.29x`,
FTE `2,477.4` — ten cards, ten equal (`P6B-25`).

## 7. Native QA

`src/powerbi/report/native_qa.py`, five minutes, machine idle, PrintWindow captures only:
opened through Desktop's Open dialog · refreshed every partition · panes and ribbon
collapsed · each page visited, its error text read (none), captured · the rendered cards
read · *Industrial Services* chosen in the unit slicer, the cards read again, the page
captured, the selection cleared · every rail button Ctrl+clicked and the landing tab read
· the Actual revenue line's last pixel measured against the position of August on the
rendered chart. The record is bound to the report build id and the model's definition digest
and accepted by `P6B-20…25` only while both are the ones on disk.

## 8. Excel / Power BI coherence

Same palette by name, same type roles, same scenario colours, same tile grouping (performance
on the panel, cash and risk on the copper tint), same favourability words, same KPI figures:
the Executive Overview's revenue, EBITDA, cash and leverage are the workbook's Executive
Summary figures to the displayed digit (`P6-XLS-01…08` on the model; the workbook's own QA
evidence on the other side). The workbook's control-status tables read 68 for Phase 6A, as
the report's page 09 does; the workbook is frozen and was not regenerated.

## 9. For the owner

1. **P6B-D-06, open.** `Account[fs_caption_l2]` sorts by an account-grain column, so a
   level-2 caption repeats once per account beneath it. No number is affected; the report
   groups by the level-1 caption instead. Correcting the sort is a model change (a
   presentation property) and is the owner's call.
2. **The layer bridge and the close, an observation.** The bridge mart is annual and carries
   every entry dated in FY2026, including the source's post-close months (1.1m of EBITDA), so
   `[Layer EBITDA]` reads 29.2m against 28.1m year-to-date statutory. The measure is as
   approved; the page says what it carries; whether the bridge should stop at the close is a
   Phase 5 question.
3. **Hires and exits.** The source has none in August 2026; the tiles read 0 for the month,
   correctly.
4. The seven requested screenshots plus the unit-selected and cutoff evidence are in
   [`docs/assets/phase-06b/final/`](../assets/phase-06b/MANIFEST.md); nothing is published to
   the README.

## 10. Digests

| | value |
|---|---|
| semantic definition digest | `af1c6264f61aeb66` (unchanged) |
| Phase 6A build id | `cfefefbaa93f16a1` (unchanged; nothing in the sealed declarations moved) |
| Phase 6B build id (report package) | `3ae52c995de48892` |
| project digest | `6a7239d6772b92f6` — the native record was taken at `a6ec6ca6a830788a`, before this run's register was written into page 09 |
| Excel workbook | `bf847b4327526a39` (frozen, unchanged) |
