# Phase 6B — Power BI executive report

**Status:** STOPPED, work in progress — awaiting owner decision on P6B-D-03, P6B-D-04, P6B-D-05
**Baseline:** `e186cf8` (Phase 6A.2 sealed); Excel frozen at `bde5ead1fbd6f945`
**Docs:** [defect register](../defect-register.md) · [semantic model](../powerbi-semantic-model.md)

---

## 1. Where it stopped, and why

The report was built, opened natively in Power BI Desktop 2.157.1354.0, refreshed through
Desktop's own Power Query, and every one of its ten pages was rendered and inspected. Three
of the things the inspection found are not report defects: they are in the sealed semantic
model, and the Phase 6B brief says a semantic defect exposed by report construction is a
**stop**, not something to compensate for in the report.

| id | in one line | seen on |
|---|---|---|
| P6B-D-05 | `Entity → Business Unit` was never declared; every unit shows the Group total | 01, 03, 06 |
| P6B-D-04 | `[Variance %]` sums entity-level stored percentages at group level (EBIT 2,713.9%) | 01, 02 |
| P6B-D-03 | measure format strings are Excel-style and render literally (`(5,553,457.5,)`) | every value |

Each has a one-line correction proposed in the register. None was worked around here: the
Business Unit visuals show the model's answer, the Variance % column shows the model's
answer, and the display formats are set at the projection — a presentation setting, the same
scaling and precision as the workbook — with the definitions untouched.

## 2. What exists

**Generator.** `src/powerbi/report/` — `theme.py` (the Excel palette, verbatim), `pbir.py`
(builders in the exact JSON shape Desktop 2.157 accepts), `layout.py` (the grid and the
chrome: rail, navigation, title, slicer band), `pages.py` (ten pages, declared),
`metadata.py` (control counts and digests read from the registers, never typed), `build.py`
(writes `powerbi/Northstar.Report/` in the enhanced PBIR format). `model.generate()` calls
it, so one command produces model and report. 624 visuals; every field reference resolves
against the model; no implicit aggregation anywhere.

**Native validation.** `src/powerbi/desktop.py` opens the project through Desktop's own Open
dialog, refreshes it, switches to Report view, walks the page tabs, reads any visual error
text, collapses the panes and ribbon, and captures each page cropped to the canvas from the
window's own handle. The whole report opened and refreshed with **zero visual errors on
every page**.

**Grammar, verified natively rather than assumed** (each cost a lab round in Desktop):

| question | answer |
|---|---|
| slicer default selection | `visual.objects.general[0].properties.filter = {"filter": <v2 filter>}`; a `filterConfig` on a slicer restricts its items instead |
| slicer sync | `visual.syncGroup` |
| a visual ignoring a slicer | `page.visualInteractions[] type NoFilter` |
| a flat band or rule | the `shape` visual ignores its own `fill`; its container `background` is exact. Visuals have a ~14 px minimum, so there are no hairlines |
| KPI number | the classic `card`; the new `cardVisual` clips at tile size |
| text placement | Power BI's default 8 px visual padding shrinks a 28 px button to 12 px; chrome sets padding 0 |
| navigation | `pageNavigator` ignores orientation in this build; the rail is ten `actionButton`s with `visualLink.type = PageNavigation`, and the page you are on is the copper one |
| page-level formats | Power BI wants `#,0,,.0`, not Excel's `#,0.0,,` (→ P6B-D-03) |

## 3. What the pages say (design intent)

Ten pages on one grid: navy rail with the brand, the ten-page navigation and the reporting
close; a title, a subtitle and a synced slicer band (period, period basis as tiles, reporting
basis, business unit, entity) on every page that needs one. KPI tiles sit on grounds the way
the workbook's first page does — performance on the cool panel, cash and risk on the copper
tint — each with a governed variance and its favourability *as a word* in its colour.
Trends are full-year and monthly regardless of the slicers; balances stop at the close;
Actual stops at August and Budget and Forecast carry on. Copper is the highlighted unit, the
reference line, the bridge step, the forecast and the active page, and nothing else.

## 4. Not built, and why

No governed measure exists for account-level amounts (so no Group → BU → Entity → Account
drill), the consolidation layer bridge, DSO/DIO/DPO/CCC, revolver drawn and available, or
principal by instrument. The brief asks for each "where governed data supports it"; the data
exists in the marts, the measures do not, and a report-level measure would be a new finance
definition. Recommended as a Phase 6A.3 measure extension alongside the three corrections.

## 5. Next

On the owner's decision: correct the three items at the emitter (Phase 6A.3), reseal with
the native-open control, then resume 6B from this commit — the report needs no change for
D-04 or D-05 to take effect, and the projection formats can be dropped once D-03 is fixed at
source.
