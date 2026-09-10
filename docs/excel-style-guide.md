# Workbook style guide

One style system for the whole pack, defined in `src/excel/style.py` and applied by every
sheet. No sheet formats a cell by hand.

That is the difference between a workbook that looks designed and one that looks assembled:
consistency is not a matter of care applied sixteen times, it is a matter of the decision being
made once.

---

## Typeface

**Calibri**, throughout, at four sizes: 20pt title, 12pt section header, 11pt body, 10pt column
headings and secondary text, 9pt notes. One family, because a workbook that mixes two looks
like two workbooks.

## Palette

Six colours carry meaning. Everything else is greyscale, so that when something *is* coloured
the reader knows it matters.

| | Hex | Used for |
|---|---|---|
| Ink | `1F2A37` | body text |
| Muted ink | `5B6B7B` | secondary text, notes, units |
| Header | `1B4965` | section bands, titles, totals — **and Actual** |
| Budget | `8C9BAB` | the Budget scenario, everywhere |
| Forecast | `B07A45` | the Forecast scenario, everywhere — and the secondary copper (see *The palette*) |
| Prior year | `B7BFC7` | the prior-year comparison |
| Favourable | `1E7A46` | a variance that is good news |
| Unfavourable | `B3261E` | a variance that is not |

Scenario colours are identical on every chart and in every table. A reader should not have to
re-learn the legend on each sheet.

Backgrounds are three: `EEF3F7` for the first KPI band, `E8D8C8` — the light copper — for the
second KPI band and for the column-group washes, and `FFF6E5` for anything a user may change.
Nothing else is filled, because a filled cell is a claim that the cell is special; the copper
wash makes exactly that claim, and only of a column that is analysis rather than a reported
figure.

### Colour carries meaning, not sign

Green and red are assigned by the **measure's favourable direction**, never by the sign of the
number. Revenue above plan is favourable; operating expense above plan is not. On the account
detail the style is chosen per row from the account's own reporting line, because a conditional
format cannot know whether row 34 is revenue or subcontract cost.

## Number formats

```
USD millions, 1dp   #,##0.0;(#,##0.0);"–"
USD millions, 2dp   #,##0.00;(#,##0.00);"–"
Percent, 1dp        0.0%;(0.0%);"–"
Margin movement     0.0" pp";(0.0" pp");"–"
Leverage            0.00"x";(0.00"x");"–"
Headcount, days     #,##0;(#,##0);"–"
FX rate             0.0000
```

Three rules behind those:

**Negatives in parentheses.** The accounting convention, and far easier to spot down a column
than a minus sign.

**Zero shown as a dash.** A nil line and a line that rounds to nil look identical as `0.0`, and
neither is worth the reader's attention. A dash says "nothing here" at a glance.

**Precision follows the metric.** Money to one decimal in millions, ratios to two, percentages
to one, headcount and days to none. A leverage ratio quoted to four decimals is not more
precise, it is less readable.

## Layout

Every report sheet:

| | |
|---|---|
| Column A | a 2-character gutter, so nothing touches the left edge |
| Column B | the row label, at a fixed width per sheet |
| Column C onward | data, every column the same width |
| Rows 1–3 | title, subtitle, context |
| Row 5 | the first section band |
| Row 7 | column headings |
| Row 8 | content |
| Freeze | always, locking the labels and the headings |
| Gridlines | off — a financial report is not a spreadsheet grid |
| Merged cells | the title and wrapped notes only; merged cells break sorting, filtering and copying |

Section bands are a full-width filled row with the section name at the left and, where useful,
the basis or period at the right. They are the only strong horizontal element, which is what
lets the eye find the structure of a dense page.

## Hierarchy in a statement

Four levels, and no more:

* **normal** — a line item
* *indented, muted* — a component of the line above
* **bold with a rule above** — a subtotal
* **bold, coloured, ruled above and below** — the final total

The same four appear on every statement, so gross profit looks like EBITDA looks like net
income.

## Charts

Every chart answers a management question, and the title states the question rather than naming
the series.

* **Scenario colours are the palette's**, everywhere.
* **A single-series chart has no legend.** A legend for one series names it once and then lists
  every category, which on a twelve-month chart is twelve entries of noise under one line.
* **Multi-series legends sit at the bottom**, never overlaying the plot.
* **Blanks are gaps, not zeros.** An actual series stops at the reporting date; Excel's default
  plots the empty months as zero, which showed the group falling off a cliff every September
  until `#N/A` was written instead.
* **Widths are derived from the sheet**, not fixed. `chart_slots()` computes the anchor and
  width from the sheet's own column widths, so a chart cannot be wider than the report it sits
  under. Fixed 16.5 cm charts ran off the page on every sheet narrower than 33 cm.
* No pie charts, no 3D, no gradients, no data labels on a twelve-point line.

### Axes, and the defect that wrote these rules

Phase 5.2 rendered all sixteen sheets and looked at them, and found that **all seventeen charts
had no axes at all** — no value scale, no category labels, just lines and bars over gridlines
that implied a scale nobody could read. `openpyxl` writes `<c:delete val="1"/>` on an axis whose
`delete` attribute is left unset, and nothing set it.

The same pass found a second defect the first had hidden: **all 26 series references started at
row 1** of the chart data sheet — the *header* row — while their categories started at row 2.
Excel plots a text header as zero, so every line dived to the axis before it began, every bar
chart was shifted one category, and the leverage chart's scale was dragged to zero by a point
that did not exist.

Neither is visible in the XML, in a formula audit or in a reconciliation. Both needed someone to
look at the picture.

| element | rule |
|---|---|
| axes | always visible. `delete = False` is set centrally in `_style_axis`, never at a call site where the next chart would forget it |
| axis line | hairline in the rule colour, no tick marks |
| axis text | 8pt muted |
| gridlines | value axis only, hairline. Never on the category axis |
| title | 9.5pt bold ink, the workbook's own font |
| border and fill | none — the section header already frames the chart |
| negative bars | keep their series colour. Excel's hollow-outline default reads as missing data |
| series range | starts at **row 2**. Row 1 is a header |
| page breaks | a chart band starts on a fresh page, so no chart is cut in half — unless the sheet is designed as one page, as the Executive Summary is |

### A chart must earn its place

One chart was built during Phase 5.2, reviewed, and removed: a bar of six year-to-date variances
said exactly what the Var $ column beside it already said. A chart that repeats its own table is
decoration.

### Scales

An axis starts at zero unless a non-zero start is what the reader needs. The leverage chart runs
3.00x–5.00x because the question is distance to a 4.50x covenant, and a 0–5 axis compresses the
whole covenant band into the top fifth of the plot.

## Sizing the page

Every sheet is reviewed at 100% zoom, in Excel, from the rendered PDF — not from the code that
produced it. The rules that came out of doing that:

* content fits the declared print area, and the section bands stop at the same column as the
  print area (a band one column wider is a page that clips);
* a note's row height is **computed from its text and the merged width**, because Excel does
  not auto-fit a merged cell and a fixed height silently overflows onto whatever is below;
* a column that carries words is wide enough for its own heading — a truncated heading tells a
  reader less than a shorter one that is not;
* `str.title()` does not know that IT is an acronym, and a report is not a database dump.

## What is deliberately absent

No gradients. No 3D. No rainbow. No borders around every cell. No merged cells holding data.
No slicers floating over the model. No KPI card with a giant coloured tile. No decoration that
carries no information.

The value is meant to come from the finance architecture, the reconciliations and the analysis
— not from the styling. The styling's job is to get out of the way.

---

## The palette

Navy is the workbook. Copper is the accent. Everything else is neutral, and the financial
status colours mean what they have always meant.

Measured balance over the coloured cells of the sixteen visible sheets: **navy 76%, solid
copper 8%, light copper 11%, other 5%.** Copper is the second colour of the system, not a
decoration on it, and it appears on every report tab — differently on each, because the
treatment is chosen to fit what the page is saying.

### Structure

| purpose | hex | RGB | where |
|---|---|---|---|
| Primary navy | `1B4965` | 27, 73, 101 | section bars, page titles, Actual series, primary bars, the ledger layer |
| **Secondary copper** | `B07A45` | 176, 122, 69 | the copper edge under every section bar, the title gutter mark, key squares, the flagged unit, terms and thresholds, the warm chart series |
| Light copper tint | `E8D8C8` | 232, 216, 200 | column-group wash behind analytical columns, the ground of the second KPI band, the management-adjustment layer key |
| Body text | `1F2A37` | 31, 42, 55 | all body and table text |
| Muted text | `5B6B7B` | 91, 107, 123 | units, notes, footnotes, chart axes and legends |
| Hairline | `D5DBE1` | 213, 219, 225 | table rules, chart axis lines, gridlines |
| Strong rule | `9AA7B4` | 154, 167, 180 | subtotal and total rules, the elimination and translation layer keys |
| Zebra band | `F5F8FA` | 245, 248, 250 | very light row banding |
| Panel | `EEF3F7` | 238, 243, 247 | the ground of the first KPI band |
| Input | `FFF6E5` | 255, 246, 229 | anything a user may change |

### The copper vocabulary

Copper has five jobs. Each is a different visual device, and each means one thing.

| device | what it is | what it means | where it appears |
|---|---|---|---|
| **Section edge** | a medium copper border on the bottom of every navy section bar | the signature of the pack; the one treatment that repeats, because a section system is meant to be consistent | every sheet |
| **Title mark** | a solid copper cell in the gutter beside the page title | the page's own mark | every sheet |
| **Column wash** | light copper behind the header of a column group | *this is analysis, not a reported figure*: variance pairs, full-year outlook, the forecast months, movement columns, ratios and shares, the year-to-date roll-up, the reporting month or year, a column that is not a test date | P&L, Business Units, Entities, Balance Sheet, Cash Flow, EBITDA Bridge, Debt & Covenants, Headcount, CapEx, FX, Consolidation, Variance Detail |
| **Key square** | a solid cell in the gutter beside a row | a pointer or a category key — *the one management is looking at*, *the adjustment layers*, *the derived measure that is charted*, *the identity being checked* | Executive Summary (attention items), Entities (the flagged unit's entities), Balance Sheet (the check), Working Capital (the cycle), EBITDA Bridge (adjustment rows), Consolidation (layer key), Cover (start here) |
| **Copper figure or label** | bold copper text, short | *a term, not a result*: the covenant limit, the minimum cash policy, the measure named in an attention item | Executive Summary, Cash Flow, Debt & Covenants |

On charts, copper is the second series or the highlighted element: the flagged unit's Actual
bar on the Business Units chart, the investing bar on the cash-flow categories, the
adjustment bar on the EBITDA bridge, the covenant limit as a dashed reference line, total
liquidity, the cash conversion cycle, EBITDA margin, depreciation, GBP. Navy remains the
Actual and the primary series everywhere.

The second KPI band on the Executive Summary — cash, leverage and capacity — sits on the light
copper ground with a copper top edge, so the two bands read as two kinds of question rather
than ten cards. The ground is the band's; the status colour of each card's delta line stays
green, red or neutral on top of it, and the tint is applied to favourable, unfavourable and
neutral cards alike. It encodes the band, not the verdict.

### Scenario colours — semantic, not decorative

| scenario | hex | RGB |
|---|---|---|
| Actual | `1B4965` | 27, 73, 101 |
| Budget | `8C9BAB` | 140, 155, 171 |
| **Forecast** | `B07A45` | 176, 122, 69 |
| Prior year | `B7BFC7` | 183, 191, 199 |

Forecast **is** the copper. The workbook already carried a warm colour — a saturated amber used,
without ever being named as such, for whatever a chart's second series happened to be.
Introducing a separate copper beside it would have left two warm hues competing at slightly
different saturations, which reads as indecision. So the amber was retuned to copper and there
is one warm colour in the system.

Retuning it also exposed a scenario inconsistency and fixed it: the Adjusted EBITDA chart on the
Executive Summary drew **Actual** in the warm colour while the revenue chart beside it drew
Actual in navy. Two charts on the flagship page disagreed about what the same scenario looks
like. Actual is navy everywhere.

### Financial status — never branding

| meaning | hex | RGB |
|---|---|---|
| Favourable | `1E7A46` | 30, 122, 70 |
| Unfavourable | `B3261E` | 179, 38, 30 |
| Neutral | `5B6B7B` | 91, 107, 123 |
| Warning / breach | `B3261E` | 179, 38, 30 |
| Control pass | `1E7A46` | 30, 122, 70 |

**Copper never carries a financial meaning.** It is not favourable, not unfavourable, not a
warning, not a breach, and not a control state. Where copper sits next to a status — the
covenant limit beside the Compliant row, the threshold beside a PASS, the flagged unit beside
its red shortfall — the status keeps its own colour and copper says only *this is the term*
or *this is the one to look at*. A covenant limit in red read as an alarm on a page where
nothing was wrong; in copper it reads as the reference line it is.

### Contrast

Copper on white is about **3.7:1** — enough for a line, a fill, a marker or a short bold label,
and **not** enough for body text under WCAG AA. It is therefore never used for body text, and
never for small type. Fill, line, marker, accent only.

### For Power BI

This palette is the visual foundation for Phase 6B. The scenario colours in particular must
carry across unchanged: a reader who learns that navy is Actual and copper is Forecast in the
workbook must not have to relearn it in the report.
