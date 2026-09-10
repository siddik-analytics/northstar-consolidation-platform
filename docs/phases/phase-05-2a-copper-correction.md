# Phase 5.2A correction — the copper design system, implemented

**Status:** complete, awaiting owner visual review
**Baseline:** `4ed6048` (Phase 5.2A first pass, owner-rejected)
**Scope:** formatting only. Zero numeric, zero text and zero added/removed cells against the
baseline workbook; 18 charts with identical source ranges; 17/17 reconciliations; 529 tests.

---

## 1. What was rejected, and why the rejection was right

The first pass declared a copper accent and then used it in one place a reader would notice:
a mark in the gutter beside each page title. The tint `E8D8C8` was defined and never used.
The owner's finding — *"essentially only A1:A2"* — was accurate. A secondary colour that
appears once per page is not a system; it is a logo.

The correction starts from the other end: what does each page need a second colour *for*?
Copper is given five jobs, each a different visual device with one meaning, and each page
gets the treatment that fits what it is saying. The full vocabulary is in
`docs/excel-style-guide.md` § *The copper vocabulary*.

## 2. Where copper now is, page by page

| sheet | treatment | what it means there |
|---|---|---|
| all | copper edge under every navy section bar; title gutter mark | the pack's signature |
| 00 Cover | key square + copper link on *01 Executive Summary* | start here (the description is untouched) |
| 01 Executive Summary | second KPI band on the light copper ground with a copper top edge; FY-outlook column group washed; attention items keyed in the gutter with the measure in copper | two kinds of question; analysis vs reported; what to look at |
| 02 P&L | forecast months washed on the monthly grid; YTD variance pair and full-year outlook washed | forecast vs actual; analysis vs reported |
| 03 Business Units | variance columns and share movement washed; the flagged unit's Actual bar in copper | analysis; the one management is looking at |
| 04 Entities | Margin washed; the flagged unit's two entities keyed in the gutter | the one ratio; the same subject, one level down |
| 05 Balance Sheet | both Movement columns washed; the check row keyed with *must be nil* in copper | analysis; the identity being checked |
| 06 Cash Flow | YTD column washed; minimum cash policy row in copper; total liquidity line and the investing bar in copper | roll-up; a policy term; the capital going in |
| 07 Working Capital | cash conversion cycle keyed in the gutter and drawn in copper | the derived measure that is charted |
| 08 EBITDA Bridge | FY2026 washed on all three tables; adjustment rows keyed; the adjustment bar in copper | reporting year; ledger → adjustments → definition |
| 09 Debt & Covenants | *In covenant debt* and the non-test-date column washed; covenant limit row in copper; limit as a copper dashed reference line | the agreement's terms — never its verdict |
| 10 Headcount | reporting month washed; Total FTE + Personnel cost washed | the month the KPI reads; parts then whole |
| 11 CapEx | YTD, % of total and % spent washed; depreciation as the copper series | roll-ups and ratios; the comparator |
| 12 FX | Constant ccy + FX effect washed; GBP as the copper series | the restatement and what it isolates |
| 13 Consolidation & Controls | layer key squares (navy ledger, copper adjustments, tint management adjustments, grey eliminations/translation); FY2026 washed; Threshold washed | the page's architecture diagram; tolerance as a term |
| 14 Variance Detail | both variance pairs washed | analysis vs reported |
| 15 Data & Technical | section edges and title mark only | a technical page needs no pointer |

**What copper never does:** PASS/FAIL, Compliant/Indicative, favourable/unfavourable, breach
and warning all keep their own colours everywhere. Where copper sits beside a status — the
limit row beside *Compliant*, the threshold beside *PASS*, the flagged unit beside its red
shortfall — an automated audit confirms no status cell carries copper. The second KPI band's
tint is applied to favourable, unfavourable and neutral cards alike: it encodes the band, not
the verdict.

## 3. Measured balance

Over the coloured cells of the sixteen visible sheets: **navy 76%, solid copper 8%, light
copper 11%, other 5%.**

## 4. Defects found by looking, and fixed in passing

All formatting; none touches a value, a formula or a chart source range.

| sheet | defect | fix |
|---|---|---|
| 01 | *Adjusted EBITDA* clipped in the attention table's Measure column (pre-existing) | data columns 12.4 → 13.2, label 32 → 34; still one page |
| 02 | margin chart anchored at column C with a two-slot width ran off the page — Oct–Dec missing (pre-existing) | anchored at the first printed column, one-slot full width |
| 02, 07, 09, 10, 11, 12 | charts split across the page break | opt-in page break before the chart block |
| 03 | the highlight applied to both bars of the flagged unit | point colours scoped to the first series |
| 06 | category labels drawn inside the negative bars | category axis labels at the foot of the plot (`tickLblPos="low"`), bar and line charts |
| 12 | right-hand chart ran past the print area; CTA line drawn through its own month labels | `chart_slots` anchors at the nearest column edge and trims width only for overlap or overflow |
| 00 | first-pass *start here* note had overwritten the Executive Summary's description | description restored; the pointer is the key square and a copper link |

## 5. Before / after

Native Excel renders (COM → PDF → PNG, 150 dpi) of the five sheets the owner named, from the
rejected baseline `4ed6048` and from this correction, in `docs/assets/phase-05-2a/`:

| sheet | before | after |
|---|---|---|
| Executive Summary | `before_01_Executive_Summary_p1.png` | `after_01_Executive_Summary_p1.png` |
| P&L | `before_02_PL_p1.png` | `after_02_PL_p1.png` |
| Cash Flow | `before_06_Cash_Flow_p1.png`, `_p2` | `after_06_Cash_Flow_p1.png`, `_p2` |
| Debt & Covenants | `before_09_Debt__Covenants_p1.png`, `_p2` | `after_09_Debt__Covenants_p1.png`, `_p2` |
| Consolidation & Controls | `before_13_Consolidation__Controls_p1.png` | `after_13_Consolidation__Controls_p1.png` |

The full set of sixteen sheets, 25 pages, is regenerated by `python -m src.excel.qa` into
`data/90_exports/workbook_render/`.

## 6. Invariance evidence

```
tools/workbook_diff.py  <HEAD workbook>  <rebuilt workbook>
  sheets compared        : 42
  cells with a value     : 613,620
  NUMERIC differences    : 0
  text differences       : 0
  cells added / removed  : 0 / 0
chart source ranges      : 18 charts, identical
python -m src.excel.qa   : reconciliation 17/17 · layout 0 blocking, 0 warnings
python -m pytest         : 529 passed
build digest             : 016df00814dc5025 (stable across three consecutive builds)
```

One caveat worth recording: `qa.py` has Excel re-save the workbook, which rewrites floats at
17 significant digits (`-24.886158` → `-24.886158000000002`). A diff of an Excel-saved file
against the openpyxl-written baseline reports those as 28 "numeric" cells at the 1e-15 level.
The committed artefact is the openpyxl form, built last, as on every previous phase.

Phase 6B has not started.
