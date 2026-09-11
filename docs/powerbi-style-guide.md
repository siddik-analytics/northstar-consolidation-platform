# Power BI style guide

The report's visual system is the Excel workbook's ([`excel-style-guide.md`](excel-style-guide.md)),
carried across by name, and held by two controls: `P6B-26` fails any colour on any page that
is not a named colour of the palette, and `P6B-27` any font or size off the type scale.

---

## 1. Colour, and what each colour means

| name | hex | means |
|---|---|---|
| navy | `#1B4965` | structure — the rail, titles, section text, the first-tier KPI edge — and the **Actual** scenario |
| navy, hover | `#2A5A78` | the rail button under the pointer; structure still, never data |
| copper | `#B07A45` | **the thing to look at**: the second tier's edge, the reference line (covenant limit), the bridge step (add-backs), the **Forecast** scenario, the active page, the selected unit |
| copper tint | `#E8D8C8` | the wash behind the second tier and the copper-tint groups; never a data colour |
| panel | `#EEF3F7` | the ground under first-tier tiles and navy groups |
| ink · ink muted | `#1F2A37` · `#5B6B7B` | text · captions, notes, axis labels |
| rule · rule strong | `#D5DBE1` · `#9AA7B4` | hairlines · the neutral bar |
| budget · prior year | `#8C9BAB` · `#B7BFC7` | the Budget and Prior Year scenarios, as in the workbook |
| favourable · unfavourable | `#1E7A46` · `#B3261E` | the governed favourability, and nothing else is ever green or red |
| white · canvas | `#FFFFFF` · `#FBFCFD` | visual grounds · the page |

Colour is never the only channel: wherever a bar or a cell is green or red, the word
*Favourable* or *Unfavourable* is beside it, from `[Variance Favourability]`.

**The KPI hierarchy in colour.** First tier: panel ground, navy edge, 26pt value. Second
tier: copper-tint wash, copper edge, 16pt value. On the other pages the tile groups keep the
workbook's convention — performance on the panel with a navy mark, cash, capital and risk on
the copper tint with a copper mark.

## 2. Type

Segoe UI, Segoe UI Semibold for emphasis, Consolas for digests. Seven sizes and nothing in
between:

| role | pt |
|---|---|
| page title | 18 |
| first-tier KPI value | 26 |
| second-tier and group KPI value | 16 · 20 (group tiles) |
| section header | 11 |
| chart title | 10 |
| body, matrix and table text | 9 |
| captions, notes, axis labels, legends | 8 |

Chart titles are sentences with the management question in them; subtitles carry the
scope ("FY2026 to the close", "closed months"). Notes are italic muted ink.

## 3. Grid and alignment

Canvas 1280 × 720. A 176px navy rail; the content area starts at x = 200 and is 1056 wide.
Title at y = 14, subtitle at 46, slicer band at 76 (46 high), content from 136. Columns come
from `layout.cols(n)` with a 16px gutter and `layout.span`; a page's rows are computed from
those, so an edge on one page is the same edge on every page. Visuals have no padding of
their own (`NO_PADDING`), so a 16px textbox is 16px of text. Nothing is placed by eye; every
object is within the canvas and analytical objects never overlap (`P6B-19`).

## 4. Numbers

The model's own format strings render: `#,0,,.0;(#,0,,.0);"–"` on money (millions to one
decimal, brackets for negatives, an en dash for zero), `0.0%` on percentages, `0.00"x"` on
turns, `#,0.0` on FTE. The report sets **no** projection format and holds display units at
None (`P6B-15`); a K/M/B unit on a measure that already scales would scale it twice. One
nuance is recorded rather than hidden: the engine picks the zero section on the rounded
value, so 49,999 prints `–` and a small negative prints `(0.0)`.

## 5. Charts

* Line charts for trends by month, 2px strokes, markers only where a point is a test.
* Clustered columns for actual against budget by category; horizontal bars for rankings.
* The favourability bar (`fav_bar`): one measure, `[Variance]`, each bar coloured by
  `[Variance Favourability]` through a rule evaluated **per data point** (the wildcard
  selector — without it every bar takes the Group's verdict).
* The bridge is a column chart with the add-back step in copper, not a waterfall: the three
  lines are levels, not cumulative steps.
* Reference lines are dashed copper (the covenant limit).
* Legends on top, no legend title; axes without titles; gridlines in `rule`.

## 6. Chrome

The rail carries the brand, the copper mark, ten navigation buttons (the current page in
copper) and the reporting close as a card bound to `[Reporting Period]`. The slicer band is
the same on every page that has one; a page whose facts are Group-level (balance sheet, cash
flow, covenants) carries only the period slicer, and a page by fiscal year (consolidation)
or with no data (lineage) carries none.

## 7. What is deliberately absent

No tooltip pages, no bookmarks, no drill-through, no conditional icons, no gauges, no gradient
fills, no data labels on lines, no eighth data colour. A page that needs them is a page with
too much on it.
