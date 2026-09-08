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
| Forecast | `C9772E` | the Forecast scenario, everywhere |
| Prior year | `B7BFC7` | the prior-year comparison |
| Favourable | `1E7A46` | a variance that is good news |
| Unfavourable | `B3261E` | a variance that is not |

Scenario colours are identical on every chart and in every table. A reader should not have to
re-learn the legend on each sheet.

Backgrounds are two: `EEF3F7` for KPI panels, `FFF6E5` for anything a user may change. Nothing
else is filled, because a filled cell is a claim that the cell is special.

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
