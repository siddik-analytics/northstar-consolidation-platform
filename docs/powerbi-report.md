# Power BI executive report

    python -m src.powerbi.report.build          write powerbi/Northstar.Report from the declarations
    python -m src.powerbi.report.controls       the report's own control suite (P6B)
    python -m src.powerbi.report.faults         twelve report faults, each caught by its control
    python -m src.powerbi.report.native_qa      open, refresh and exercise it in Power BI Desktop
    python -m src.powerbi.run --native          all of the above after the semantic phase

**Ten pages, generated from declarations, on the sealed Phase 6A.3 model.** No number on any
page is typed, computed in the report, or scaled twice; every one is a governed measure in a
scope the visual states. The report is an artefact of its own and is controlled as one:
43 controls in the `P6B` family, 12 fault fixtures, a native pass through Power BI Desktop
that reads what was actually rendered, and 13 three-way reconciliations (report scope →
engine → mart) on real values.

Style: [`powerbi-style-guide.md`](powerbi-style-guide.md) · controls:
[`powerbi-controls.md`](powerbi-controls.md) · model: [`powerbi-semantic-model.md`](powerbi-semantic-model.md)
· phase record: [`phases/phase-06b-report.md`](phases/phase-06b-report.md)

---

## 1. How it is built

```
src/powerbi/report/
  theme.py      the Excel palette and type scale, carried across by name
  pbir.py       builders that emit the exact JSON Desktop 2.157 accepts
  layout.py     the 1280×720 grid, the chrome (rail, navigation, title, slicer band),
                the Page class -- with a mandatory reason on every switched-off interaction
                and a kind for every visual (the object inventory)
  pages.py      the ten pages, declared; QUESTIONS, the question each page answers
  metadata.py   the registers and manifests the Controls and Lineage pages read
  build.py      writes powerbi/Northstar.Report (PBIR); model.generate() calls it
  controls.py   P6B-00…42
  faults.py     F6B-01…12
  native_qa.py  the Desktop pass: open, refresh, errors, cards, slicer, navigation, cutoff
```

A change to the report is a change to a declaration and a regeneration. Nothing in
`powerbi/Northstar.Report/` is edited by hand, and `tests/test_phase06b_report.py` regenerates
into a scratch folder and asserts it equals the committed one file for file.

**Field references.** Every value role on every visual binds a measure of `Northstar Measures`
(`P6B-02`). A dimension attribute may sit on an axis, in a matrix row or in a register table;
a fact column never appears in a value role; no visual carries an aggregation, an arithmetic
expression or a projection-level format.

**Scope, not compensation.** A visual says what it is about with a filter on a dimension
(`Scenario[scenario_code] = "ACT"`, `Comparison[comparison_code] = "FC_VS_BUD"`,
`Date[is_actual_month] = TRUE`). The number still comes from the governed measure. Where a
slicer must not reach a visual -- a full-year trend beside a month slicer, a management-basis
measure beside the reporting-basis slicer -- the page declares `NoFilter` **with a reason**,
and `P6B-16` fails an edge without one.

## 2. The pages, and the question each answers

| page | question (printed on the Lineage page) | analytical objects |
|---|---|---|
| 01 Executive Overview | How is the Group doing, where is it heading, what needs attention? | 5 |
| 02 P&L Performance | Which lines moved, and which accounts drove them? | 3 |
| 03 Business Units & Entities | Where does performance come from, and which unit is off plan? | 4 |
| 04 Balance Sheet & Working Capital | Is the position sound, and is working capital moving the right way? | 2 |
| 05 Cash Flow & Liquidity | Where did cash come from and go, and how much room remains? | 2 |
| 06 EBITDA & Variance Bridge | Which EBITDA is which, and what bridges statutory to adjusted? | 2 |
| 07 Debt & Covenants | How close is leverage to the limit, and when is it actually tested? | 3 |
| 08 Workforce & CapEx | Are people and capital moving with the plan? | 4 |
| 09 Consolidation & Controls | What does consolidation do, and what proves it right? | 3 |
| 10 Lineage & Technical | Is this the same data as the source, and which build is it? | 0 |

Every chart title is the management question it answers, in words a CFO would use
(`Cash and total liquidity at month end — how much room remains`), never a field name.

### 01 Executive Overview — the thirty-second read

Three tiers, top to bottom, in the order a reader needs them.

* **First tier, navy edge, large:** Revenue, Adjusted EBITDA, Cash, Covenant net leverage —
  the four numbers the owner named. Revenue and Adjusted EBITDA carry the governed variance to
  budget and its favourability *as a word* in its colour; Cash and leverage carry their scope
  (Group, at the period end; indicative between test dates).
* **Second tier, copper wash, compact:** gross margin, EBITDA margin, operating cash flow,
  covenant net debt, covenant headroom, headcount.
* **Middle row:** revenue by month (actual to the close, budget and forecast beyond it) · the
  full-year outlook, the current forecast against budget on five lines · Adjusted EBITDA
  variance to budget by unit, each bar coloured by the measure's own favourability, so the
  unit that needs attention is the red bar.
* **Bottom row:** cash and total liquidity by month end · net leverage against the dashed
  copper covenant limit.

The period, basis and reporting-basis slicers scope the tiles. The trends keep the whole
year and the outlook is full-year by its own filter; the reasons are on record.

### 02 P&L Performance

The governed income statement is the primary object: fourteen lines, expandable to business
unit and entity, on the period basis and comparison selected, with base, comparator, variance,
`[Variance %]` and the favourability word in its colour. Beside it, the variance on the six
key lines as bars, and the **account detail** — `[Account Amount]` by caption and account,
actual, credits negative — so a line can be taken to the accounts behind it without leaving
the page.

### 03 Business Units & Entities

Revenue by unit against budget; Adjusted EBITDA variance to budget by unit; the unit → entity
matrix with revenue, **share of Group**, **share of unit**, Adjusted EBITDA and margin; and
Adjusted EBITDA by entity. The two share measures have intentionally different denominators
and are two governed measures, so a denominator never changes meaning invisibly. Selecting a
unit narrows every unit-sensitive number natively (`P6B-22`: Revenue 279.0 → 84.1 for
Industrial Services; FTE 2,477.4 → 1,051.7; Group-level cash and leverage hold).

### 04 Balance Sheet & Working Capital · 05 Cash Flow & Liquidity

Consolidated Group facts, so these pages carry a period slicer only: the balance sheet, cash
flow, working capital and covenant marts have no entity grain, and a unit slicer beside them
would be a control that controls nothing (`P6B-24`). Balances and cash are month-end trends
over **closed months** — the marts carry the last close forward, and the visual filter, not
the measure, keeps the trend honest.

### 06 EBITDA & Variance Bridge

Statutory, management-adjusted and covenant EBITDA on three tiles, kept apart; the statutory
→ add-backs → adjusted bridge with the add-back step in copper; Adjusted EBITDA by month on
the four governed scenarios; and the definitions in prose.

### 07 Debt & Covenants

Debt and the covenant test on tiles, the status tile reading `[Covenant Status]` and nothing
else — **Indicative** between test dates, a verdict only at a fiscal year end (`P6B-11`). The
leverage trend against the dashed copper limit, the contractual test dates (every one
Compliant), and the instrument register.

### 08 Workforce & CapEx

The workforce and capital measures are date-range measures with no period-basis switch, so
the page has no basis slicer and says what its ranges are: tiles are the month selected;
hires, exits and FTE by month, spend by asset class and the largest programmes are FY2026 to
the reporting close. The project table is keyed on the corrected unique `project_id`
(ADR-0026; `P6B-12`, 1,846 projects, 0 duplicates in engine, dimension and mart alike).

### 09 Consolidation & Controls

The five layers and the two views they make; what each layer contributes to EBITDA and net
income for FY2026 from the governed `[Layer EBITDA]` / `[Layer Net Income]`; entries by
layer and year from `[Layer Entries]`; the control environment of every phase and the
reconciliations across artefacts, **read from the registers when the report is generated**
and checked against them by `P6B-13` (the page shows 68 for Phase 6A because
`phase06a_control_results.csv` has 68 rows; the page code contains no such literal).

### 10 Lineage & Technical

The chain from the three ERP extracts to this page as seven stations, the build identifiers
and digests (the report's own build id is computed at generation time — a manifest written
after generation could only hold the previous project's digest), the model's validation
facts, and the ten questions. No slicer.

## 3. What each page does not pretend

* The Executive Overview's cash, net debt, leverage and headroom are Group figures; the tiles
  say so, and a unit selection leaves them unchanged by design.
* The Layer bridge is annual and carries no reporting-close cutoff; its FY2026 total (29.2m)
  includes the source's post-close months and is not the year-to-date statutory figure
  (28.1m). The chart's subtitle says so; see the phase record for the owner question.
* DSO, DIO, DPO, cash conversion cycle, revolver drawn/available and principal by
  instrument are deferred by owner decision (`P6-COV-02`) and appear nowhere (`P6B-14`).
* Hires and exits are counts for the month; in August 2026 the source has none.

## 4. Slicers and interactions

| key | column | default | synced | on |
|---|---|---|---|---|
| `sl_period` | `Date[month_label_long]` | Aug 2026 | yes | 01–08 |
| `sl_basis` | `Period Basis[basis_name]` (tiles) | Year to date | yes | 01, 02, 03, 06 |
| `sl_rbasis` | `Reporting Basis[basis_name]` | Statutory | yes | 01, 02, 03, 06 |
| `sl_bu` · `sl_entity` | `Business Unit[bu_name]` · `Entity[entity_name]` | all | yes | 01, 02, 03, 06, 08 |
| `sl_comparison` | `Comparison[comparison_name]` (tiles) | Actual vs Budget | yes | 02 |

No slicer exposes a version: the derived prior-year version `PY_DERIVED` is the measure's
choice and appears in no filter, no slicer and no projection (`P6B-09`). Twenty-nine
`NoFilter` edges, each with its reason in `pages.py`.

## 5. The object inventory

**655 visuals** (the Group-level pages lost their inert slicers; the Controls page gained this
phase's register row), classified by
`layout.classify` and written to `data/phase06b_object_inventory.json` on every run:

| kind | count | what it is |
|---|---|---|
| analytical | 28 | charts, matrices, tables — the objects a reader reads |
| kpi | 160 | card values and the tile labels, captions and favourability words that belong to them |
| text | 224 | titles, subtitles, section headers, notes, the register rows on pages 09 and 10 |
| shape | 116 | grounds, marks and hairline rules |
| navigation | 100 | ten rail buttons on each of ten pages |
| slicer | 27 | |

The density gate is on analytical objects (`P6B-19`: at most 6 per page; the Executive
Overview has 5). Pages 09 and 10 are register pages and carry most of the text objects by
design; a table visual cannot colour a PASS green per row, so each cell is a textbox.

## 6. Native evidence

`native_qa.py` opens the project through Desktop's own Open dialog, refreshes every
partition, collapses the panes, and then reads what Desktop rendered:

* the accessible name of every card (`Revenue 279.0.`) — re-evaluated by `P6B-25` in each
  tile's own scope through the engine and compared as rendered text;
* the error text of any visual that failed (none, on every page, `P6B-20`);
* the selected page tab after each of the ten rail buttons (`P6B-21`);
* the cards after Industrial Services is chosen in the unit slicer, and after it is cleared
  (`P6B-22`);
* the pixel where the Actual revenue line ends against the position of the reporting close
  on the rendered chart (`P6B-23`).

The record carries the report build id (the declarations) and the model's definition digest
it was taken on and is accepted only while both are the ones on disk; the project digest is
recorded too, but the Controls page's register text changes when the pass itself is written
into the register, so it is not the binding. Screenshots: [`assets/phase-06b/final/`](assets/phase-06b/MANIFEST.md).
