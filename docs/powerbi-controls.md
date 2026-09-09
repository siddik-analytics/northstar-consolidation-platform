# Power BI semantic controls

    python -m src.powerbi.run       generate, deploy, control
    python -m src.powerbi.faults    break it ten ways and prove each is caught

**49 controls, 10 fault fixtures.** The governing principle is Phase 4C's, widened one more
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

## The four families

| family | n | asserts |
|---|---|---|
| `P6-SEM` | 15 | the model is structurally sound and its metadata is present |
| `P6-XAR` | 19 | Power BI reconciles to the governed marts |
| `P6-XLS` | 8 | Power BI reconciles to the Excel workbook |
| `P6-POL` | 7 | the reporting policies hold in DAX |

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

**10/10 detected.** Every fixture restores the model and the suite redeploys clean.

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
