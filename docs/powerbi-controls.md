# Power BI semantic controls

    python -m src.powerbi.run       generate, deploy, control
    python -m src.powerbi.faults    break it twelve ways and prove each is caught

**53 controls, 12 fault fixtures.** The governing principle is Phase 4C's, widened one more
time:

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

**12/12 detected.** Every fixture restores the model and the suite redeploys clean.

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

## Relationship to the Phase 5.1 framework

The key and grain framework (`src/integrity/`) covers the same objects one layer down: it proves
the *data* has the keys the model declares. The twelve semantic dimensions this phase publishes
are declared there too — `P7-REG-01` flagged all twelve the moment they appeared, which is what
it is for. **290 integrity controls, 18 fixtures**, all clean.

The division is deliberate. `src/integrity` asks whether the warehouse keys are real;
`src/powerbi` asks whether the model built on them reports the right numbers.
