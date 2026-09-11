# Power BI controls — semantic model and report

    python -m src.powerbi.run --native      generate, deploy, control the model and the report
    python -m src.powerbi.faults            break the model sixteen ways and prove each is caught
    python -m src.powerbi.report.faults     break the report twelve ways and prove each is caught

**Semantic model: 68 controls, 16 fault fixtures. Report: 43 controls, 12 fault fixtures. Phase 6B.1: 12 controls, 3 fixtures**
([§ the report on the model](#the-report-on-the-model-p6b)). The governing principle is Phase
4C's, widened one more time:

> Different artefacts expressing the same financial measure must reconcile to one authoritative
> definition — **and Power BI is another artefact.**

---

## Why the DAX has to be real

A control that re-implemented each measure in SQL and compared the two would be comparing two
things written by the same hand on the same afternoon. It would agree, and it would prove
nothing.

So `P6-XAR` executes the model's **own measures** against Analysis Services and compares the
result with SQL over the governed marts. At least one side is always independent, and the side
that is supposed to represent Power BI is Power BI.

That decision is not theoretical. Executing the model found two defects that no amount of
reading the TMDL would have shown:

| found by running it | what it was |
|---|---|
| the engine refusing to load | a relationship on `Financial Detail[cost_centre_key]` — a column that does not exist on the mart, and a second one from Headcount to a Cost Centre it has no key for at all |
| `Revenue` = 557,961,779.56 against a mart holding 278,980,889.78 | every statement measure summed **both** reporting bases and reported exactly twice the truth |
| four measures erroring | a measure reference used as a boolean table filter (three times) and `MIN` over a Boolean column |

Text always parses. A model reviewed only as text is a model nobody has run.

When the engine is unavailable, the DAX families report `NOT_EXECUTED` and say why. They never
fall back to a SQL re-implementation and call the answer a Power BI value.

---

## The five families

| family | n | asserts |
|---|---|---|
| `P6-SEM` | 15 | the model is structurally sound and its metadata is present |
| `P6-XAR` | 19 | Power BI reconciles to the governed marts |
| `P6-XLS` | 8 | Power BI reconciles to the Excel workbook |
| `P6-POL` | 7 | the reporting policies hold in DAX |
| `P6-PBIP` | 4 | the project on disk is one Power BI Desktop will open, and it is the same model the engine runs |
| `P6-PATH` | 4 | every reportable dimension reaches every fact it filters by exactly one active path, and the filter demonstrably arrives |
| `P6-PCT` | 2 | non-additive percentages are not added: `[Variance %]` reconciles at every grain, comparison and basis |
| `P6-FMT` | 6 | formats are governed, balanced, class-correct, rendered correctly by the engine, and not overridden or double-scaled by the report |
| `P6-COV` | 2 | every financial concept the report names maps to a governed measure or is deferred on record |
| `P6-XAR-20` | 1 | the account-grain amount reconciles to the statement line |

The fifth family was added in Phase 6A.2, after the first four had all passed on a project
that Desktop refused to open.

### `P6-SEM` — structure

Dimension keys unique over the published population; every relationship resolving with no
orphan and therefore no blank member; **declared cardinality matching the data**, because
declaring many-to-one does not make the data many-to-one and Power BI silently promotes a broken
one to many-to-many; no two tables joined by more than one active path; every inactive
relationship carrying a written reason; descriptions on every table and measure; the five
required elements on every high-risk measure; display folders; format strings; statement
captions sorting by governed order rather than alphabetically; no technical key left visible;
the model loading in the engine; **all 89 measures parsing and evaluating**.

### `P6-XAR` — Power BI against the marts

Revenue, Gross Profit, Statutory EBITDA, Adjusted EBITDA, EBIT, Net Income, Cash, Total Assets,
Total Equity, Operating Cash Flow, Closing Cash, Gross Debt, Covenant Net Debt, Covenant EBITDA,
Covenant Net Leverage, Closing FTE, CapEx, and the count of capital projects.

`P6-XAR-19` goes one step further upstream and recomputes revenue from `vw_statutory_fact` —
the consolidated fact, not the mart. A mart agreeing with Power BI proves the model reads the
mart; this proves the mart it reads still agrees with the ledger.

Tolerance: `0.05` on money, `0.0005` on a leverage multiple.

### `P6-XLS` — Power BI against Excel

Through the workbook's own committed QA evidence (`data/phase05_workbook_qa.csv`), so neither
side is a fresh calculation made to satisfy the control. Executive summary lines, the P&L,
closing cash and net leverage.

### `P6-POL` — the policies

| control | asserts |
|---|---|
| `P6-POL-01` | Actual is **BLANK** after the reporting close, never zero |
| `P6-POL-02` | statutory, adjusted and covenant EBITDA are three separate definitions |
| `P6-POL-03` | a month the agreement does not test is labelled **Indicative** |
| `P6-POL-04` | Prior Year resolves to the governed `PY_DERIVED` version |
| `P6-POL-05` | no fact row falls to a blank Scenario member |
| `P6-POL-06` | statutory and management measures pin the basis they are named for |
| `P6-POL-07` | the current forecast is the version the master marks as default |

`P6-POL-06` is checked on the **definition**, read back out of the engine, not on the values —
and the reason is worth recording. In this baseline layer 4 posts no legs and both approved
management adjustments carry `0.00`, so the two bases hold identical figures everywhere. A
measure secretly reading the wrong basis would agree with every number in the platform. When
the data cannot tell two things apart, the control has to look at what the model says rather
than at what it returns.

---

### `P6-PBIP` — the native project

**A semantic model can be valid in the engine and invalid as a project.** The engine has no
reserved table names and TMSL carries no doc comments; the TMDL parser does not run DAX. Phase
6A's suite was pointed entirely at the engine, and the project it validated did not open
(P6B-D-01, P6B-D-02). This family reads the generated text the way the parser does, and then
stops reading and asks Desktop.

| control | asserts | how |
|---|---|---|
| `P6-PBIP-01` | a `///` doc comment sits only above an object that has a `Description` — table, column, measure, hierarchy, partition, expression, model — never a relationship | parses every generated `.tmdl` |
| `P6-PBIP-02` | no table name in Desktop's reserved list (`Measures`, confirmed against Desktop 2.157 rather than assumed) | parses every `table` declaration |
| `P6-PBIP-03` | **Power BI Desktop opens the generated `.pbip` and loads it** | `desktop.py` drives Desktop's own File > Open dialog, reads back the loaded project's title or the refusal dialog's text, then runs Desktop's own refresh and requires every partition to load |
| `P6-PBIP-04` | the project text, the TMSL-deployed engine and Desktop's own session database agree on tables, measures, relationships and active relationships | counts in all three forms; 28 / 89 / 36 / 31 |

`P6-PBIP-03` is **blocking**, and it is the only control that takes the keyboard. It waits for
the machine to have been idle for fifteen seconds before it starts and reports `NOT_EXECUTED`
with the reason if it never is, because an untested project is not a broken one and a
control that types over someone's work is worse than one that waits. It is requested by the
phase run and by the two PBIP fixtures, not by every control invocation — the fault suite runs
the controls a dozen times, and a Desktop round trip is twenty seconds each.

The screenshot it takes is rendered from Desktop's own window handle (`PrintWindow`), never
grabbed from the screen, so it cannot contain whatever happened to be in front.

### The Phase 6A.3 families — what the report found that the engine did not

The Phase 6B report was the first thing to *ask* the model a business-unit question and the
first thing to *look at* a percentage above entity grain. It found a dimension that filtered
nothing and a percentage that summed. Both had passed every control: `P6-SEM-04` proved no
table had two active paths and never asked whether one had none; every reconciliation
compared dollars at group grain and never a percentage at any grain.

`P6-PATH` walks the live engine's relationship graph (declarations when the engine is not
live) from each dimension in `config.EXPECTED_PATHS` to each fact it must filter, then
proves the filter arrives: a member the fact has rows for, `COUNTROWS` with and without it.
`P6-PCT` compares `[Variance %]` with the ratio of the additive components summed in SQL over
`mart_variance` at group, unit, entity, line and entity + line, for all four comparisons and
all three period bases. `P6-FMT` renders five representative values with the format the
Revenue measure actually carries and requires `5.6`, `(5.6)`, `–`, `279.0`, `(0.9)`, then
reads the generated report for projection overrides and stacked display units. `P6-COV`
holds the concept map: every brief item is a governed measure or a recorded deferral.

## Fault fixtures

Each breaks the **model** — a measure, a relationship, a published dimension — deploys the
damaged model to the real engine, runs the real controls, and asserts the control named for it
in advance is the one that fails. A fixture caught by *some other* control is reported as a
miss, because "something went red" and "the right thing went red" are different claims.

| fixture | what it breaks | caught by |
|---|---|---|
| `F6-XAR-01` | Revenue omits a valid account family | `P6-XAR-01` |
| `F6-XAR-02` | EBITDA sweeps in the year-end close — **P4-D-02 attempted again in DAX** | `P6-XAR-03` |
| `F6-XAR-03` | future Actual returns zero instead of blank | `P6-POL-01` |
| `F6-XAR-04` | Covenant EBITDA aliases Adjusted EBITDA | `P6-POL-02` |
| `F6-XAR-05` | statutory reporting reads the management basis | `P6-POL-06` |
| `F6-XAR-06` | cash differs from the cash flow's closing cash | `P6-XAR-11` |
| `F6-XAR-07` | a superseded forecast presented as current | `P6-POL-07` |
| `F6-XAR-08` | a required balance sheet caption missing | `P6-XAR-07` |
| `F6-XAR-09` | `PY_DERIVED` removed from the version dimension — **P7-D-01 in the semantic layer** | `P6-POL-04` |
| `F6-XAR-10` | Capital Project reverts to the colliding pre-ADR-0026 key — **P6-D-01** | `P6-SEM-01` |
| `F6-PBIP-01` | relationship rationale emitted as a `///` doc comment — **P6B-D-01** | `P6-PBIP-01` |
| `F6-PBIP-02` | the measures host named the reserved `Measures` — **P6B-D-02** | `P6-PBIP-02` |
| `F6A3-01` | the `Entity → Business Unit` relationship removed — **P6B-D-05** | `P6-PATH-01` |
| `F6A3-02` | `[Variance %]` additive again, stored percentages summed — **P6B-D-04** | `P6-PCT-01` |
| `F6A3-03` | the Excel-style money format back on every money measure — **P6B-D-03** | `P6-FMT-04` |
| `F6A3-04` | a report concept with no governed measure behind it | `P6-COV-01` |

**16/16 detected.** Every fixture restores the model and the suite redeploys clean.

The two PBIP fixtures are different in kind from the ten before them. They break the **project
on disk**, not the model: each regenerates the project into a disposable directory with the
Phase 6A emitter's defect put back, deploys it over TMSL — and the engine takes it, which the
harness records as *"engine accepted the model over TMSL"* — then the project controls catch it
and Desktop, asked, refuses it. That row is the whole lesson of Phase 6A.2 in one line.

`F6-XAR-10` is worth singling out: with a duplicate dimension key, Analysis Services **refuses
to load the model at all** rather than quietly promoting the relationship to many-to-many. The
harness records that refusal alongside the control failure, because a model the engine will not
load is itself a detection and the most emphatic kind available.

### What the fixtures taught the harness

Three fixtures reported a miss on their first run while proving nothing: they created damaged
tables in DuckDB, but the model's partitions read **Parquet**, so the deployment failed, the
clean model stayed loaded, and the controls correctly found nothing wrong with it. The harness
now publishes damaged sources to Parquet and treats a failed deployment as its own outcome
rather than as a miss.

---

## The report on the model (`P6B`)

    python -m src.powerbi.report.controls

The semantic families prove the model. These prove the **report on top of it**: that every
number a page shows is a governed measure in a stated scope, that the scope is the one the
page claims, and that nothing on a page was typed, computed locally, scaled twice or dressed
up as a verdict the agreement never gave. Three kinds of evidence, and the register says which
each control used: **static** (the generated PBIR files, read as JSON — what Desktop opens),
**live** (the model's own measures evaluated by the engine in the scope a visual declares),
and **native** (the last pass through Power BI Desktop, accepted only while the report
declarations and the model definition it was taken on are the ones on disk).

| control | evidence | asserts |
|---|---|---|
| `P6B-01` | static | no financial amount typed: no decimal, percentage or ratio in any textbox on the eight financial pages; every card binds a measure |
| `P6B-02` | static | every value on every visual is an explicit governed measure — no aggregation, no arithmetic, no fact column in a value role, no unknown measure |
| `P6B-03` | static | the headline KPIs are the four governed primaries (Revenue, Management Adjusted EBITDA, Closing Cash, Covenant Net Leverage); every tile a measure |
| `P6B-04` | static | the income statement is the governed line hierarchy with unit and entity beneath, and its values are the five variance measures |
| `P6B-05` | live | selecting a unit narrows Revenue, Adjusted EBITDA and FTE in the Executive Overview's own scope through the slicer's column, and the units sum to the Group |
| `P6B-06` | static | every percentage or variance shown is the governed measure; the report carries no ratio of its own |
| `P6B-07` | static | no visual scoped to the Actual scenario binds a fact column — the cutoff cannot be bypassed |
| `P6B-08` | static + live | every month-end trend on a carried-forward balance is scoped to closed months, and every Actual measure the report uses is blank for the four months after the close |
| `P6B-09` | static | no version on any page: `PY_DERIVED` and `version_code` appear in no filter, slicer or projection |
| `P6B-10` | live | the forecast on the page equals the mart for the version `ref_default_version` marks current |
| `P6B-11` · `-11L` | static · live | the status tile binds `[Covenant Status]` alone, the test table is filtered to period 12, no verdict is typed; the engine reads *Indicative* at the close and the mart's verdict at the last test date |
| `P6B-12` · `-12L` | static · live | the project table is keyed on `project_id`; engine, dimension and mart agree on 1,846 distinct projects with 0 duplicates |
| `P6B-13` | static | the control counts on page 09 equal the registers' row counts, and the page code holds no control-count literal |
| `P6B-14` | static | DSO, DIO, DPO, CCC and the revolver concepts are absent, and deferred on record |
| `P6B-15` | static | no display unit other than None on a scaled money measure, no projection format |
| `P6B-16` | static | every `NoFilter` interaction has a reason in the page declaration (29 edges) |
| `P6B-17` | static | slicers synced by key, defaulted to the reporting close, unit paired with entity |
| `P6B-18` | static | one navigation button per page on every page, each to a page that exists |
| `P6B-19` | static | every object on the canvas, no two analytical objects overlapping, no page above the density gate of 6 |
| `P6B-24` | static | no slicer that moves nothing on its page (through the measures' tables and the active one-to-many paths) |
| `P6B-26` · `-27` | static | every colour a named palette colour; every font and size on the type scale |
| `P6B-20` | native | the last Desktop pass rendered every page with zero visual errors |
| `P6B-21` | native | every rail button landed on its page |
| `P6B-22` | native | choosing Industrial Services narrowed the Executive Overview |
| `P6B-23` | native | the rendered Actual revenue line ends at the reporting close |
| `P6B-25` | native + live | every card Desktop rendered on the Executive Overview equals the engine's value in the tile's own scope, compared as rendered text |
| `P6B-30…42` | live | thirteen three-way reconciliations: Revenue, Gross Profit, Statutory EBITDA, Adjusted EBITDA, EBIT, Net Income, Cash, Net Debt, Covenant EBITDA, Covenant Leverage, Covenant Headroom, FTE, CapEx — the visual's own scope evaluated in the engine against the semantic controls' mart SQL |

**Why three routes.** `P6-XAR` already reconciles the engine to the marts at group grain in
a filter the control writes. `P6B-30…42` reconcile in the filter the *page* writes — the
visual's filters plus the slicer defaults, minus the slicers the page switched off — so a
scope mistake on a page (a card reading the wrong basis, an outlook that summed twelve
full-year rows) fails here even though the measure itself is right.

### Report fault fixtures

Each puts one report-level fault into a scratch copy of the generated report and asks
whether the control named for it notices. A fixture caught only by another control is a miss.

| fixture | what it breaks | caught by |
|---|---|---|
| `F6B-01` | the Revenue card replaced by the number typed as text | `P6B-01` |
| `F6B-02` | a chart series that is *Sum of amount_usd*, not a measure | `P6B-02` |
| `F6B-03` | account detail reading the raw fact column under an Actual filter — post-close rows would show | `P6B-07` |
| `F6B-04` | the covenant status tile replaced by the word *Breach*, typed | `P6B-11` |
| `F6B-05` | the project table on the pre-correction project key | `P6B-12` |
| `F6B-06` | the Phase 6A control count typed as the stale 53 | `P6B-13` |
| `F6B-07` | the outlook's Var % computed in the visual as Variance ÷ Comparator | `P6B-06` |
| `F6B-08` | a million display unit on a card whose measure already scales | `P6B-15` |
| `F6B-09` | a rail button to a page that does not exist | `P6B-18` |
| `F6B-10` | a thousands display unit on a money chart's axis | `P6B-15` |
| `F6B-11` | a `NoFilter` interaction with its reason erased | `P6B-16` |
| `F6B-12` | unit and entity slicers on the Group-level cash flow page | `P6B-24` |

**12/12 detected.** The first ten mutate the generated files, the last two the declarations;
every fixture works on its own copy and the committed report is never touched.

---

## Phase 6B.1 (`P6B1`)

    python -m src.powerbi.controls_b1
    python -m src.powerbi.faults_b1

The two corrections the owner held Phase 6B for, each with the control that keeps it
corrected. The family keeps its own register (`data/phase06b1_control_results.csv`) so the
Phase 6A register the frozen workbook reads stays at 68 rows.

| control | evidence | asserts |
|---|---|---|
| `P6B1-HS-01` | static | every sorted column in the model maps one value to exactly one sort key, and back — 14 sort declarations; found `Scenario[scenario_name]` and `Balance Sheet[caption]` at the wrong grain the first time it ran |
| `P6B1-HS-02` | static | the statement hierarchy's keys are at caption grain, level-1 in the chart's order, level-2 contiguous under its level-1, and neither alphabetical; the balance sheet leads with Current Assets, the income statement with Revenue |
| `P6B1-HS-03` | live | the engine groups each level-2 caption once (0 duplicates), resolves 175 accounts beneath their captions, and puts *Cash and cash equivalents* first |
| `P6B1-SC-01` | static | the consolidation bridge and the headline it reconciles to share the period and basis slicers, no interaction is switched off between them, the bridge pins no year of its own, and its title is the governed `[Consolidation Bridge Title]` |
| `P6B1-BR-01` | static | the month-grain bridge sums to `mart_consolidation_bridge` for every layer and fiscal year (EBITDA, net income, entries) |
| `P6B1-BR-02…07` | live | the statutory layers' EBITDA and net income sum to `[Statutory EBITDA]` and `[Net Income]` on MTD, YTD and FY at the close, within the cent tolerance |
| `P6B1-BR-08` | live | the bridge is blank after the reporting close on every basis |

| fixture | what it breaks | caught by |
|---|---|---|
| `F6B1-01` | *Accrued liabilities* given two level-2 sort keys in the published Account dimension — P6B-D-06 put back | `P6B1-HS-01` |
| `F6B1-02` | the bridge switched off from the period slicer: annual again, beside a year-to-date headline | `P6B1-SC-01` |
| `F6B1-03` | `[Layer EBITDA]` reverted to a plain sum of the bridge fact, blind to the basis and the close | `P6B1-BR-03` |

**3/3 detected.** The engine, asked to load the dimension with the duplicated key, took it
without complaint — which is exactly why the control exists.

---

## Relationship to the Phase 5.1 framework

The key and grain framework (`src/integrity/`) covers the same objects one layer down: it proves
the *data* has the keys the model declares. The twelve semantic dimensions this phase publishes
are declared there too — `P7-REG-01` flagged all twelve the moment they appeared, which is what
it is for. **290 integrity controls, 18 fixtures**, all clean.

The division is deliberate. `src/integrity` asks whether the warehouse keys are real;
`src/powerbi` asks whether the model built on them reports the right numbers.
