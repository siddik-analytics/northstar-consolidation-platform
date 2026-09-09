# Phase 6A — Power BI semantic model

**Status:** complete, awaiting semantic model review
**Baseline:** `192b1a5` (Phase 5.1, approved)
**WIP recovered from:** `ca72922` on `wip/phase-06a-semantic-model`
**Docs:** [semantic model](../powerbi-semantic-model.md) · [measures](../powerbi-measures.md) ·
[controls](../powerbi-controls.md)

---

## 1. The governance story

Phase 6A was attempted three times. Twice it stopped, and both times for the same reason: **an
identifier in use that resolved to nothing.**

| | defect | what it was | resolution |
|---|---|---|---|
| first attempt | **P6-D-01** | `project_id` identified 1,846 capital projects with 395 values. A `Capital Project` dimension needs a unique key, so it could not be built | escalated, not worked around. Corrected at the generator ([ADR-0026](../adr/0026-a-declared-key-is-a-contract.md)) |
| second attempt | **P7-D-01** | `PY_DERIVED` was the version code on 12,516 mart rows and existed in no version master. It would have arrived as a blank Scenario member | escalated. `PY_DERIVED` made a governed derived version ([ADR-0027](../adr/0027-a-derived-version-is-still-a-governed-version.md)) |

Neither was compensated for in DAX. A surrogate key would have hidden the first; a hard-coded
`"PY_DERIVED"` string would have hidden the second. Both would have produced a working report
over a broken contract, and the contract is the thing that has to be right.

The framework built to close the first found the second within a day of existing.

---

## 2. Rebase

`wip/phase-06a-semantic-model` rebased from `026bf43` onto `192b1a5`. **Zero conflicts** — the
WIP touched only new paths, so nothing about it was a design decision. Historical WIP commit
preserved rather than squashed.

---

## 3. What the WIP was worth

Audited against the specification, not accepted for existing.

| | |
|---|---|
| **Retained** | the config/measures/model split; the TMDL generator; the star schema shape; the disconnected `Period Basis` and the reasoning that rejected a calculation group; the five inactive business-unit relationships; ~80 of the measures |
| **Revised** | Capital Project (key now valid); Scenario (now carries `PY_DERIVED`, version type, and a Scenario→Version hierarchy); every statement measure (basis filter, cutoff guard); variance (now honours the period basis); Balance Sheet and Measure Line (sort-by, hierarchies); nine measure descriptions |
| **Discarded** | the `Headcount → Cost Centre` relationship — `mart_headcount` carries no cost centre at all, so the join could never have resolved |
| **Added** | `deploy.py`, `dax.py`, `controls.py`, `faults.py`, `run.py`; the Job Family dimension; 7 measures; 49 controls; 10 fixtures |
| **Regenerated** | every semantic Parquet, the whole PBIP/TMDL project, the manifest. Nothing generated before the rebaseline was reused |

---

## 4. The model

**28 tables · 89 measures · 31 active + 5 inactive relationships · 256,983 rows.**

14 dimensions (Date, Entity, Business Unit, Account, Cost Centre, Consolidation Layer,
Reporting Basis, Currency, Scenario, Measure Line, Comparison, Capital Project, Debt Instrument,
Job Family), 12 facts, plus `Period Basis` (disconnected) and a measures-only table.

Measures by folder: model context 5, income statement 17, scenario 10, variance 6, balance
sheet 15, cash flow 9, debt and covenants 10, workforce 7, capital expenditure 7, foreign
exchange 3.

**No calculation groups.** Rejected on inspection: a calculation group rewrites *filter
context*, and the three period columns are stored results rather than filters of one another.

**One calculated column** — `Financial Detail[cost_centre_key]`, the composite `entity|code`.
Power BI relates on a single column; a cost centre code is only unique within its entity.

---

## 5. Native validation — what was actually done

Power BI Desktop 2.157.1354.0 is installed as a Store package. **It will not open a PBIP project
from the command line on this machine**: `.pbip` has no file association, the Store-app launch
does not forward the file argument, and the setting that would enable it is not reachable
without guessing at an undocumented location. Desktop opened, but on a blank report.

The Analysis Services instance Desktop runs behind itself **does** accept TMSL over XMLA — which
is how external tabular tools have always driven it. So the model is emitted as TMSL from the
same declarations that produce the TMDL, deployed to that instance, refreshed, and queried
there.

That is real native validation, and it is stated precisely: the **engine** is Power BI's own,
the model is the one the PBIP describes, the DAX is the model's own. What was *not* done is
opening the `.pbip` in the Desktop UI. No screenshot, no visual, no report page.

### What running it found

| | |
|---|---|
| engine refused to load | `Financial Detail[cost_centre_key]` — a relationship on a column that does not exist; and `Headcount → Cost Centre`, a join to a dimension that fact has no key for |
| `Revenue` = 557,961,779.56 vs a mart holding 278,980,889.78 | **every** statement measure summed both reporting bases |
| 4 measures errored | a measure reference used as a boolean table filter (×3), and `MIN` over a Boolean column |

None of these is visible in TMDL. Text always parses.

---

## 6. Capital Project

| | |
|---|---|
| dimension rows | **1,846** |
| distinct `project_id` | **1,846** |
| key | the corrected business key `CP-{entity}-{period}-{asset_class}-{sequence}` |
| surrogate | **none** — one here would hide exactly what the correction fixed |
| `mart_capex` orphans | 0 |

`F6-XAR-10` rebuilds the dimension at the pre-correction grain; Analysis Services refuses to
load the model.

---

## 7. Scenario and version

Six reportable versions, `PY_DERIVED` among them. **Zero blank members**: every one of the
12,516 prior-year mart rows resolves. `[Prior Year Version]` reads `PY_DERIVED` from the
dimension rather than from a string in DAX, and the current forecast is read from the governed
default flag — `P6-POL-07` proves the model's answer equals the master's. Downside remains
reserved and absent.

---

## 8. Statements, variance and policy

**P&L hierarchy** complete and ordered by `sort_order`, never alphabetically: Revenue → Cost of
sales → Gross profit → Operating expenses → EBITDA → Add-backs → Adjusted EBITDA → D&A → EBIT →
Net finance → Tax → Net income → NCI → Attributable to parent. Balance sheet captions sort by
their governed order under an `account_class → caption` hierarchy.

**Variance** — four comparisons × MTD/YTD/FY × dollars, per cent and favourability, from **six
measures** reading the precomputed `mart_variance`, not from dozens of near-identical ones.
Favourability comes from the measure's own `favourable_direction`: revenue above plan is
favourable, operating expense above plan is not. `Variance %` reads the *stored* percentage on a
single line so Power BI and Excel cannot disagree, and recomputes only where a stored percentage
could not legitimately be summed.

**Actual cutoff** — the mart publishes ACTUAL rows for the whole fiscal year and the four after
the close carry `0.00`. Every statement measure blanks when the context resolves to Actual alone
past the close; a mixed Actual-and-Forecast trend is left alone.

**Three EBITDA definitions** kept separate in source, description and lineage. Adjusted and
Covenant EBITDA are equal in this baseline — the sponsor fee runs below its cap and the covenant
FX add-back has no population — which is an outcome, not a definition.

**Covenants** — rolling twelve-month EBITDA, and `Covenant Status` returns **Indicative** on any
month the agreement does not test.

---

## 9. Statutory versus management — a limitation worth stating

Layer 4 posts **no legs at all** in `fact_financials`, and both approved management adjustments
carry `0.00`. The two bases therefore hold **identical figures everywhere** in the marts, at
every grain.

This is not a defect discovered here: it is the state of the approved baseline, and Phase 4's
`F4-MGT-LEAK` fixture proves the separation works by injecting a live adjustment. But it has a
direct consequence for this phase — a measure secretly reading the wrong basis would agree with
every number in the platform, so `P6-POL-06` reads the deployed DAX back out of the engine and
checks what it filters rather than what it returns.

Recorded as a limitation, not escalated.

---

## 10. Controls and fixtures

| family | n | result |
|---|---|---|
| `P6-SEM` structure | 15 | 15 pass |
| `P6-XAR` Power BI ↔ marts | 19 | 19 pass |
| `P6-XLS` Power BI ↔ Excel | 8 | 8 pass |
| `P6-POL` policy | 7 | 7 pass |
| **total** | **49** | **49 pass, 0 not executed, 0 blocking failures** |

**10/10 fault fixtures detected by their intended control.**

Four fixtures initially reported a miss. Each was a real finding: two needed a control that did
not yet exist (`P6-POL-06`, `P6-POL-07`), one had the wrong expectation, and three exposed a
flaw in the harness itself — damaged tables were created in DuckDB while the partitions read
Parquet, so the deployment silently failed and the clean model stayed loaded. The harness now
publishes damaged sources properly and treats a failed deployment as its own outcome.

---

## 11. Reconciliation evidence

Power BI ↔ marts, real DAX against independent SQL, at the August 2026 close:

| measure | Power BI | mart |
|---|---|---|
| Revenue | 278,980,889.78 | 278,980,889.78 |
| Gross Profit | 75,980,813.59 | 75,980,813.59 |
| Statutory EBITDA | 28,100,907.83 | 28,100,907.83 |
| Management Adjusted EBITDA | 31,911,102.90 | 31,911,102.90 |
| EBIT | 15,473,409.60 | 15,473,409.60 |
| Net Income | (939,022.82) | (939,022.82) |
| Total Assets | 465,523,771.19 | 465,523,771.19 |
| Closing Cash | 14,579,689.06 | 14,579,689.06 |
| Covenant EBITDA | 57,842,615.47 | 57,842,615.47 |
| Covenant Net Leverage | 4.214182 | 4.214182 |

All 19 within `0.05` (money) / `0.0005` (turns). `P6-XAR-19` recomputes revenue from
`vw_statutory_fact` — the ledger, not the mart — and agrees.

Power BI ↔ Excel: 8 of 8, through the workbook's committed QA evidence.

---

## 12. Performance

| | |
|---|---|
| tables / rows | 28 / 256,983 |
| measures | 89 |
| relationships | 31 active + 5 inactive |
| project generation | **0.14 s** |
| TMSL deploy + full refresh | **4.7 s** |
| control suite (49, incl. 89 DAX evaluations) | **2.8 s** |
| all 89 measures evaluated | 1.97 s (**22 ms each**) |

Highest-cardinality columns are measure values on the two large facts — unavoidable, they are
the facts. No high-cardinality text column, no redundant calculated column, no table that
recreates a mart. Nothing warranted optimisation that would have obscured the finance logic.

---

## 13. Reproducibility

Two clean generations produced an identical project digest **`c04c498f4469329c`** across every
`.tmdl`, `.pbip`, `.pbism` and `.pbir` file. Lineage tags are UUID5 digests of object names
rather than random GUIDs, which is what makes that possible.

The TMSL deployment carries a server-assigned modification timestamp that is not part of the
project and is not compared.

---

## 14. Full regression

| suite | result |
|---|---|
| Phase 2 source controls | **80/80** |
| Phase 3 ingestion controls | **62/62**, 0 source findings |
| Phase 4 consolidation controls | **72/72**, 0 source findings |
| Phase 5 mart controls | **36/36** |
| Phase 5.1 key, grain and version controls | **290/290**, 0 findings |
| Phase 5.1 fixtures | **18/18** |
| Phase 6A semantic controls | **49/49**, 0 not executed |
| Phase 6A fixtures | **10/10** |
| `pytest` | **510 passed** |

Upstream untouched: no change to `src/generation`, `src/pipeline`, `src/consol`, `src/marts`,
`src/excel`, `config/`, or any published mart. Source digest, Phase 3/4/5 build ids and the
workbook digest all unchanged from `192b1a5`.

The integrity suite grew from 249 to 290 because the twelve semantic dimensions this phase
publishes are now declared in the registry — `P7-REG-01` flagged all twelve the moment they
appeared.

---

## 15. Limitations

1. **The PBIP was not opened in the Desktop UI.** Validation was via TMSL deployment to
   Desktop's own Analysis Services instance. Real engine, real model, real DAX — but not the
   Desktop file-open path, and no visual was rendered.
2. **Statutory and management are indistinguishable in this data** (§9), so the basis
   separation is proved on the definition rather than on the values.
3. **CapEx has no Budget or Forecast scenario upstream.** The subledger carries an approved
   amount per project and no scenario dimension, so `CapEx Variance` measures spend against
   approval. No Budget CapEx measure is offered, because offering one would mean inventing the
   data behind it.
4. **No report pages.** Phase 6A is the semantic layer; the technical validation page is empty
   by design.
5. **`P6-D-02` — the build ids are checkout-dependent, and it is open.** Rebasing this branch
   re-checked-out several declared build inputs and changed their line endings, which changed
   the recomputed build ids even though every byte of content was identical. The form that
   reproduces each committed id is a per-file mixture of CRLF and LF, which is the problem
   stated plainly: the ids depend on which files were last authored on Windows.

   The working tree was restored to those forms, so the approved baseline verifies here and all
   510 tests pass — but a fresh clone will fail the two reproducibility tests while every
   financial value stays identical. The fix is one line per module and it moves the Phase 3, 4
   and 5 build ids, which this phase was told not to do. Reported rather than done; see
   [the defect register](../defect-register.md).

---

## 16. Recommended Phase 6B scope

The model is ready to report from. What it is not yet is a report.

1. **Executive summary** — the group in one screen: revenue and adjusted EBITDA against plan,
   the covenant position with its Indicative/test-date distinction visible, cash and liquidity.
2. **P&L** with the governed hierarchy, period-basis slicer, and account-aware favourability
   colouring — the rules are all in the model already.
3. **Business unit and entity performance**, using the Entity → Business Unit path.
4. **Balance sheet and cash flow**, on the caption hierarchies.
5. **Debt and covenants**, with test dates distinguished from indicative months.
6. **Workforce and capital**, using Job Family and Capital Project.
7. **Lineage page** — build ids, control results and the reconciliation evidence, so a reader
   can see what proves the numbers.

Two things to carry in: the visual review discipline that found eleven defects in Phase 5, and
the rule that a report page adds no definition the model does not already hold.
