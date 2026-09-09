# The Power BI semantic model

    python -m src.powerbi.run          generate the project, deploy it, run the controls
    python -m src.powerbi.faults       break it ten ways and prove each is caught

A governed star schema over the Phase 5 reporting marts. **28 tables, 89 measures, 31 active
relationships and 5 deliberately inactive ones**, generated from two Python declarations and
validated by executing real DAX against a real Analysis Services engine.

Nothing in it decides an accounting question. Every consolidation rule — layers, FX, CTA,
intercompany, PPA, NCI, unrealised profit, the add-back policy, the covenant bridge — is settled
upstream and arrives on the mart row.

---

## How it is built

| | |
|---|---|
| `src/powerbi/config.py` | tables, keys, relationships, hierarchies, the semantic dimension queries |
| `src/powerbi/measures.py` | every measure, its format, folder and description |
| `src/powerbi/model.py` | emits the **PBIP / TMDL** project — what a person opens, what git reviews |
| `src/powerbi/deploy.py` | emits **TMSL** and deploys to a live engine — what proves it works |
| `src/powerbi/dax.py` | executes DAX against that engine |
| `src/powerbi/controls.py` | 49 semantic and reconciliation controls |
| `src/powerbi/faults.py` | 10 fixtures, each caught by a named control |

Both output forms come from one declaration, which is why they cannot disagree.

### Why generate two forms

TMDL is text, and text always parses. Only an engine will tell you that a relationship names a
column which does not exist, or that every statement measure has been quietly summing two
reporting bases. **Both of those were in this model until it was deployed.** A semantic model
reviewed only as text is a semantic model nobody has run.

---

## The star

Fourteen dimensions, twelve facts, plus a disconnected `Period Basis` and a measures-only table.

```
                    Date ── Entity ── Business Unit
                      │       │
   Reporting Basis ───┼───────┼─── Scenario ── (Scenario → Version hierarchy)
                      │       │
   Measure Line ──── FACTS ───┼─── Cost Centre ── Account
                      │       │
   Comparison ────────┘       └─── Capital Project · Debt Instrument · Job Family
                                   Consolidation Layer · Currency
```

| dimension | rows | key | note |
|---|---|---|---|
| Date | 48 | `period_key` | one calendar for the whole model |
| Entity | 15 | `entity_code` | includes the three elimination entities |
| Business Unit | 5 | `bu_code` | reached **through Entity**, never directly |
| Account | 175 | `group_account` | the group chart, with its statement attributes |
| Cost Centre | 162 | `cost_centre_key` | composite `entity|code` — codes repeat across entities |
| Consolidation Layer | 5 | `layer_id` | and its statutory / management membership |
| Reporting Basis | 2 | `basis` | statutory or management |
| Currency | 4 | `currency_code` | presentation currency is USD |
| Scenario | 6 | `version_code` | scenario **and** version, with a hierarchy |
| Measure Line | 14 | `measure_code` | the P&L hierarchy in presentation order |
| Comparison | 4 | `comparison_code` | the four approved comparisons |
| Capital Project | **1,846** | `project_id` | **1,846 unique** — see below |
| Debt Instrument | 14 | `instrument_id` | carries the covenant flag |
| Job Family | 12 | `job_family_code` | the one workforce attribute with no other home |

Facts: Financials (44,184), Financial Detail (133,558), Variance (50,652), Balance Sheet
(1,296), Cash Flow (48), Working Capital (48), Covenants (33), Debt (595), Headcount (22,215),
CapEx (1,846), FX (176), Layer Bridge (20). **256,983 rows.**

### Deliberate absences

**No Department dimension.** Headcount reaches department through Cost Centre already; a direct
relationship as well would give one business concept two filter paths.

**No Asset Class dimension.** Asset class is a property of a capital project, and a second table
for it would be the same concept twice.

**No calculation group.** Considered and rejected on inspection rather than on principle: a
calculation group rewrites a measure's *filter context*, and the three period columns are not
filters of one another — they are three stored results, and switching between them needs a
column reference to change. Forcing it produces something a reviewer cannot read. A disconnected
`Period Basis` table read by `SWITCH` does the same job in the open.

**One calculated column**, on Financial Detail: `cost_centre_key`. Power BI relates on a single
column and a cost centre is identified by entity and code together, so the composite has to be
formed somewhere. It is formed in the model rather than added to a frozen Phase 5 mart, and it
is concatenation of two governed keys with no business logic in it.

### The five inactive relationships

Every fact carries `bu_code` and every one of those paths is **inactive**, because a fact
already reaches Business Unit through Entity and an entity belongs to exactly one unit. A second
active path would make every segment total ambiguous with no way to tell which route a visual
used. They are kept rather than deleted because the columns are genuinely on the marts and a
future report may want `USERELATIONSHIP`. Each carries its own written reason; `P6-SEM-05`
fails a reason shorter than a sentence.

---

## Capital Project, and why it is a dimension at all

This dimension is the reason Phase 6A stopped twice.

`project_id` identified **1,846 capital projects with 395 values**: the sequence restarted
inside each asset class, so every class in an entity-month reissued `-01`. A dimension needs a
unique key, so the model could not be built — and rather than introduce a surrogate to paper
over it, the defect was escalated (**P6-D-01**) and corrected at the generator
([ADR-0026](adr/0026-a-declared-key-is-a-contract.md)).

The dimension is keyed on the corrected **business** key, `CP-{entity}-{period}-{asset_class}-{sequence}`.
No surrogate, no composite, no downstream workaround — introducing one would have hidden exactly
the thing the correction fixed. Fixture `F6-XAR-10` rebuilds the dimension at the old grain, and
Analysis Services refuses to load the model at all.

---

## Scenario and version

One dimension, keyed on version, with a `Scenario → Version` hierarchy. A version belongs to
exactly one scenario, so these are two levels of one thing rather than two dimensions;
splitting them would snowflake the model and give every fact two paths to the same concept.

| scenario | default version | |
|---|---|---|
| Actual | `ACTUAL` | blank after the close — see below |
| Budget | `BUD_FY26_V1` | locked on board approval |
| Forecast | `FC_FY26_08` | three retained, one current |
| Prior Year | **`PY_DERIVED`** | governed derived version (ADR-0027) |
| Downside | — | reserved, absent by construction |

`PY_DERIVED` is the second defect this phase found upstream: it was the version code on 12,516
mart rows and existed in no version master, so it would have arrived here as a **blank member**.
`P6-POL-04` proves `[Prior Year Version]` reads `PY_DERIVED` from the dimension rather than from
a string in DAX, and `F6-XAR-09` removes it to prove the control fires.

The current forecast is read from the governed default flag, never named in DAX. `P6-POL-07`
proves the model's answer equals the master's, and `F6-XAR-07` pins a superseded forecast to
prove it catches one.

---

## The Actual cutoff

`mart_financial_ytd` publishes ACTUAL rows for every month of FY2026 including the four after
the August close, and **they carry `0.00`**. A naive `SUM` therefore returns zero for September
— which says the group earned nothing, when the truth is the month has not happened.

Every statement measure carries a guard that returns `BLANK()` when the filter context resolves
to Actual *alone* and the latest period is past the close. A mixed selection showing Actual and
Forecast together is showing the forecast on purpose and is left alone. `P6-POL-01` tests it at
the month where it bites; `F6-XAR-03` removes the guard to prove the control fires.

---

## Statutory versus management

Both bases are published as separate rows on the same mart. A measure that does not state which
one it wants **sums both and reports exactly twice the truth** — which is what every statement
measure did until the model was deployed and `Revenue` came back at 557,961,779.56 against a
mart holding 278,980,889.78.

Most lines follow the `Reporting Basis` selection and default to statutory. `Statutory EBITDA`
and `Management Adjusted EBITDA` are pinned to their basis.

**This one cannot be proved from the values.** In the approved baseline layer 4 posts no legs
at all and both approved management adjustments carry `0.00`, so the two bases hold identical
figures everywhere — a measure secretly reading the wrong basis would agree with every number
in the platform. `P6-POL-06` therefore reads the deployed DAX back out of the engine and checks
what it actually filters. The separation is real architecture, proved by Phase 4's `F4-MGT-LEAK`
fixture injecting a live adjustment; it simply is not exercised by this dataset.

---

## Three EBITDA definitions

| measure | source | basis |
|---|---|---|
| `Statutory EBITDA` | `mart_financial_ytd`, line `EBITDA` | pinned STATUTORY |
| `Management Adjusted EBITDA` | `mart_financial_ytd`, line `ADJ_EBITDA` | pinned MANAGEMENT |
| `Covenant EBITDA` | `mart_covenants`, the rolling twelve-month bridge | the agreement's |

Adjusted and Covenant EBITDA are **equal in the current baseline** — the sponsor fee runs below
its cap and the covenant FX add-back has no population. That is an outcome, not a definition,
and the two remain separate measures with separate sources, descriptions and lineage.
`F6-XAR-04` aliases one to the other and `P6-POL-02` fails.

---

## Covenants

The Phase 5 correction is preserved. Leverage is computed on a **rolling twelve-month** covenant
EBITDA, because dividing a full net debt balance by a part-year EBITDA reports a breach that
does not exist — 7.38x against a 4.50x limit, which is what the Phase 5 visual review caught.

`Covenant Status` distinguishes what the agreement actually tests: fiscal year ends
(CA-009..012) return **Compliant** or **Breach**; every other month returns **Indicative**.
`P6-POL-03` asserts both halves.

---

## Validation

Power BI Desktop 2.157.1354.0 will not open a PBIP project from the command line on this
machine — `.pbip` has no file association and the Store build does not forward the argument. The
Analysis Services instance Desktop runs behind itself **does** accept TMSL over XMLA, which is
how external tabular tools have always driven it, so the model is deployed there and queried
there.

That is real native validation: the real engine, the real model, the real DAX. All 89 measures
parse and evaluate; 19 reconciliations against the marts and 8 against the Excel workbook pass;
10 fault fixtures are each caught by the control named for them in advance.

See [`powerbi-controls.md`](powerbi-controls.md) for the suite and
[`powerbi-measures.md`](powerbi-measures.md) for the measures.
