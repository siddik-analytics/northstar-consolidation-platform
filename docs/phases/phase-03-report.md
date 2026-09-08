# Phase 3 Report — Ingestion, Staging & COA Harmonisation

**Status:** Complete · **Date:** 2026-09-07 · **Next gate:** owner review

Three deliberately heterogeneous ERP source systems ingested, normalised and harmonised into
one controlled finance data model, **without altering a byte of the approved source data**.

No consolidation was performed: no elimination, no investment elimination, no NCI entry, no
FX translation, no CTA posting, no unrealised profit elimination, no management adjustment,
no consolidated statement, no Excel and no Power BI. Everything produced is layer 1.

---

## 1. Summary

| | |
|---|---|
| Source files ingested | **507 of 507** |
| Journal lines through the pipeline | **1,080,782** |
| Mapping agreement, lines the source classified | **100.000000%** (1,013,640 of 1,013,640) |
| Mapping agreement, all lines | 99.984641% (1,080,616 of 1,080,782) |
| Unmapped · ambiguous · invalid dimension | **0 · 0 · 0** |
| Gross margin by business unit vs the anchor | **exact**, all 12 business-unit-years |
| Group revenue, cost of sales, opex vs the source-layer target | **0.000000%** deviation, all 3 years |
| Controls | **54 of 61 pass, 0 blocking pipeline failures** |
| Source findings | **7 controls, across 4 defects in the frozen Phase 2 layer** |
| Tests | 317 → **367** |
| Runtime | **~110 s** for the full pipeline, **2.4 s** for the 61 controls |
| Deterministic rebuild | ✅ identical artefact checksums |
| Phase 2 source layer | ✅ **unchanged**, digest `34adb63e…` |

**Four defects were found in the frozen source layer.** Following the Phase 3 brief, none
was patched. Each is documented in §12 with its cause, its population, its amount, its effect
and a proposed correction, and each is escalated as an open item for the owner.

---

## 2. Pipeline architecture

Five layers, named after what has happened to the data rather than where it sits (ADR-0019).

```
data/raw/{aurora,sable,kestrel}/*.csv            507 files · 1,080,782 lines · frozen
        │  adapters.py        one adapter per source system, no generic parser
        ▼
parsed_aurora · parsed_sable · parsed_kestrel     typed, every native column verbatim
        │  standardise.py     sign · period · dimensions · attributes
        ▼
stg_standardised                                  one canonical journal-line model
        │  harmonise.py       127 effective-dated rules, config-driven
        ▼
stg_mapped_enriched                               + group account, rule id, status
        │  conform.py · dimensions.py · subledgers.py
        ▼
fact_journal_line · fact_trial_balance · 12 dimensions · 12 reference tables · 5 views
```

Engine: **DuckDB SQL end to end**. There is no row-by-row Python in the transformation path.
The warehouse is `data/20_warehouse/northstar.duckdb`; each layer is also materialised as
Parquet under `data/10_staging/`.

Commands:

```bash
python -m src.pipeline.run          # full pipeline, then controls
python -m src.pipeline.controls     # controls alone, against the built warehouse
python -m src.pipeline.faults       # every fault fixture through the real pipeline
```

Design detail: [`docs/ingestion-design.md`](../ingestion-design.md).

---

## 3. ERP parser results

No generic parser. Three adapters, each stating its own system's conventions as data.

| | Aurora | Sable | Kestrel |
|---|---|---|---|
| Encoding | UTF-8 | UTF-8 | **Windows-1252** |
| Delimiter | `,` | `,` | `;` |
| Dates | ISO | US `MM/DD/YYYY` | German `DD.MM.YYYY` |
| Amounts | one signed amount | **natural sign**, US thousands separators | separate **SOLL / HABEN**, German notation |
| Account key | 4 digits, text | 5 digits, text | **8 chars, zero-padded, text** |
| Fiscal year | **absent** — from the posting date | native | native |
| Cost centre | **absent** — resolved from entity + department | **absent** — resolved from the dimension string | native `KOSTL` |
| Periods | 1–12 | 1–12 | **1–16** |
| Files · lines | 220 · 525,338 | 132 · 370,906 | 155 · 184,538 |
| Parse failures | **0** | **0** | **0** |

Three things had to be got right and are each proved by a control:

- **Sable's sign** exists only once the account's normal balance is known. It is taken from
  the **approved chart**, not from the extract's own `NORMALBALANCE` column — and the two are
  then compared. They agree on all 370,906 rows.
- **Kestrel's account keys** keep their leading zeros as text everywhere; none is coerced to a
  number at any stage (`P3-ING-07`). `00012000` narrowed to `12000` would join to nothing and
  no total would notice.
- **Both source-translated columns** — Aurora's deliberately stale `AMOUNT_USD_SYSTEM` and
  Kestrel's legacy `DMBTR_KONZERN_EUR` — are carried on the journal-line fact for lineage and
  appear on **no aggregate** (`P3-ING-12`, CTL-FX-06).

Kestrel's four special periods are classified rather than numbered: 542 statutory-close, 30
audit, 40 tax and 16 group-reporting postings, all reporting in management period 12
(`P3-ING-10`, `P3-ING-11`).

---

## 4. Row counts by stage

| Stage | Table | Rows |
|---|---|---|
| parsed | `parsed_aurora` | 525,338 |
| | `parsed_sable` | 370,906 |
| | `parsed_kestrel` | 184,538 |
| standardised | `stg_standardised` | **1,080,782** |
| mapped | `stg_mapped_enriched` | **1,080,782** |
| conformed | `fact_journal_line` | **1,080,782** |
| | `fact_trial_balance` | 42,081 |
| | 12 conformed dimensions | 872 |
| | `fact_plan` | 26,124 |
| | `fact_revenue_detail` | 50,045 |
| | `fact_headcount` | 20,349 |
| | `fact_capex_project` | 1,846 |
| | 12 reference tables | 5,487 |
| | `stg_group_adjustment` | **0 by design** |
| exceptions | `mapping_exceptions.csv` | **0** |

Every data row in every file reaches the parsed layer, counted independently against the
files themselves (`P3-ING-02`).

Mapping outcomes:

| Status | Lines |
|---|---|
| `MAPPED_DIRECT` | 995,241 |
| `MAPPED_SPLIT` | 46,119 |
| `MAPPED_SPLIT_DEFAULT` | 38,809 |
| `MAPPED_DERIVED` | 613 |
| everything else | **0** |

---

## 5. The mapping engine

The core deliverable. See [`docs/mapping-engine.md`](../mapping-engine.md) and ADR-0020.

The approved source charts carry the account-level mapping and a **prose** `mapping_rule`
column that a pipeline cannot execute. Phase 3 makes the conditional logic executable
configuration rather than code: `config/mapping/mapping_rules.csv`, **127 effective-dated
rules** covering 53 conditional accounts, in a language with an allow-list.

```
condition := clause { ' AND ' clause }
clause    := 'TRUE' | field op literal | field IN (...) | field NOT IN (...)
           | field IS NULL | field IS NOT NULL
```

A field must be a declared context field or a declared line attribute; anything else is
rejected when the rule set loads and the build stops. Conditions are **parsed and re-emitted**
as SQL rather than interpolated, so a literal cannot carry a predicate.

Four properties are enforced, not hoped for:

- **Nothing defaults silently.** A split's default is a declared rule with a rule id, not an
  `else` in code, and `P3-MAP-06` fails the build if a conditional account has none.
- **An ambiguity is an exception.** Two matching non-default branches make the line
  `AMBIGUOUS` and block the close. Resolving by priority would make two overlapping rules look
  like one working rule until somebody checked.
- **Every line ends with exactly one of ten declared statuses.**
- **Blocking statuses produce an investigation file** with the ERP, entity, account,
  attributes carried, candidate rules, the reason none resolved it and the amount affected.

Performance came from shape rather than tuning: the ledger joins to the rule set on
(ERP, source account) and one `CASE` over the rule id evaluates every condition, so a line
only evaluates the handful of branches belonging to its own account — one pass over 1.08m
rows.

### The German total-cost-method reclassification

Kestrel reports on the *Gesamtkostenverfahren*, where `00081000 Bestandsveraenderung` and
`00081200 Aktivierte Eigenleistungen` sit **above** the revenue line inside *Gesamtleistung*.
Under the group's cost-of-sales presentation they belong **inside cost of sales**.

What reverses is the **caption, not the number**. A credit stays a credit; it stops adding to
*Gesamtleistung* and starts reducing cost of sales, which in a debit-positive model happens
by landing on a cost-of-sales account. Consequently the mapped trial balance still sums to
zero, net income is unchanged, gross margin becomes economically correct, and the source
presentation stays visible on the line — `00081000`, its German name, `is_presentation_reclass`
and `presentation_reclass_type = 'GKV_TO_UKV'`. 613 postings, all landing in cost of sales,
none left in revenue (`P3-MAP-10`, `P3-MAP-11`, CTL-MAP-08).

---

## 6. Mapping acceptance — the hard gate

Phase 2 recorded, per line, the group account a Phase 3 mapping is expected to produce. That
file is an **oracle**: `reconcile.py` reads it to grade the engine and no transformation stage
may. `test_the_manifest_is_an_oracle_and_never_an_input` inspects the stage modules and
asserts the separation, because a perfect score against a file the engine can read means
nothing.

| Population | Lines | Exact matches | Mismatches | Agreement |
|---|---|---|---|---|
| **Classifiable at source** | 1,013,640 | 1,013,640 | 0 | **100.000000%** |
| Not classifiable at source | 67,142 | 66,976 | 166 | 99.752763% |
| **All lines** | **1,080,782** | **1,080,616** | **166** | **99.984641%** |

| | |
|---|---|
| Unmapped | **0** |
| Ambiguous | **0** |
| Invalid dimension | **0** |
| Out of effect | **0** |

A line is *classifiable at source* when its account maps unconditionally, or when the posting
declares at least one of the attributes its account's rule set reads.

**The 100.00% threshold is met on every line the source system classified, and is not met
across all lines.** All 166 disagreements sit in the unclassifiable population, every one of
them caused by source defect **P2-D-01** (§12.1): three journal types are written without the
line attributes the approved mapping contract requires, so the split cannot be derived from
the data. Not one disagreeing line carries a usable attribute — verified directly. The
threshold was not reduced; the shortfall is attributed, quantified and escalated.

Detail: `data/phase03_mapping_acceptance.csv`.

---

## 7. Mapped financial reconciliation

Layer 1 only. Both legs of every intercompany transaction present, nothing eliminated. The
USD figures apply the approved monthly average rates (income statement) and closing rates
(balance sheet) **for comparison only**: no CTA is computed, nothing is posted, and no
translated fact is stored. Full detail in
[`docs/source-to-group-reconciliation.md`](../source-to-group-reconciliation.md) and
`data/phase03_reconciliation.csv`.

### Group income statement, against the Phase 2 source-layer targets

| USD m | FY2023 | FY2024 | FY2025 |
|---|---|---|---|
| Revenue — mapped / target | 365.780 / 365.780 | 415.774 / 415.774 | 462.635 / 462.635 |
| Cost of sales — mapped / target | 265.560 / 265.560 | 300.726 / 300.726 | 332.555 / 332.555 |
| Operating expense — mapped / target | 70.980 / 70.980 | 76.074 / 76.074 | 78.735 / 78.735 |
| **Deviation** | **0.000000%** | **0.000000%** | **0.000000%** |

Tolerance 0.5%, unchanged from Phase 2 and not relaxed. It was not needed.

### Gross margin by business unit — the control that matters

A mapping can be wrong and still balance: move production payroll into SG&A and every trial
balance still sums to zero while the margin moves three points. This is the reconciliation
that finds it, and fault fixture F08 tests exactly that scenario.

| BU | FY2023 mapped / anchor | FY2024 | FY2025 |
|---|---|---|---|
| Flow Control | 32.500% / 32.500% | 33.400% / 33.400% | 34.000% / 34.000% |
| Industrial Services | 21.000% / 21.000% | 21.600% / 21.600% | 22.000% / 22.000% |
| Engineered Systems | 18.500% / 18.500% | 18.000% / 18.000% | 19.000% / 19.000% |
| Aftermarket | 42.000% / 42.000% | 42.500% / 42.500% | 43.000% / 43.000% |

**Twelve business-unit-years, exact.** Revenue and gross profit by BU also reproduce the
anchor exactly, and external revenue by entity reproduces `anchor_by_entity.csv` with a worst
variance of **0.000000 USD m** across eleven entities × three years.

### Balance sheet, at closing rates

Two comparisons, because they answer different questions: `mapped` is what the pipeline
produced, `oracle` is the same balance built from the group account Phase 2 said each line
should carry.

| FY2025, USD m | mapped | oracle | mapping variance | target | vs target |
|---|---|---|---|---|---|
| cash | 22.000 | 22.000 | 0.000 | 22.000 | (0.000) |
| trade receivables | 65.479 | 65.479 | 0.000 | 65.484 | (0.006) |
| inventory | 40.803 | 40.803 | 0.000 | 40.803 | (0.000) |
| property, plant and equipment | 95.200 | 95.200 | 0.000 | 95.200 | 0.000 |
| trade payables | 40.103 | 40.103 | 0.000 | 40.103 | 0.000 |
| revolving credit facility | 19.518 | 19.518 | 0.000 | 19.518 | 0.000 |
| term loan, gross | 226.600 | 226.600 | 0.000 | 226.600 | 0.000 |
| **contract assets** | 6.567 | 8.901 | **(2.334)** | 8.901 | (2.334) |
| **prepayments** | 10.576 | 8.242 | **2.334** | 8.242 | 2.334 |
| accrued liabilities | 22.792 | 22.792 | **0.000** | 22.666 | 0.126 |
| income taxes payable | 2.347 | 2.347 | **0.000** | 2.473 | (0.126) |

The only caption pair where the pipeline differs from the oracle is contract assets and
prepayments — source defect **P2-D-01**. Accrued liabilities and income taxes payable agree
with the oracle **exactly**; that variance is between the source data and the anchor — source
defect **P2-D-04**. Every other caption reconciles exactly.

### Revenue detail to the general ledger

ADR-0008 keeps customer and product detail in its own fact at a finer grain, and the point of
that decision is that the two tie. Customer and product measures are **not** pushed into the
journal-line fact.

Reconciled at entity × period, 507 combinations. **Worst variance: 0.00 local.**

### Trial balances

| Proof | Worst | Threshold |
|---|---|---|
| native trial balance closes in each ERP's own convention | 0.0000 | 0.02 |
| still closes after sign normalisation | 0.0000 | 0.02 |
| still closes after mapping | 0.0000 | 0.02 |
| mapping changed no amount, line for line | 0.000000 | 0.005 |
| `fact_trial_balance` ties to `fact_journal_line` | 0.0000 | 0.02 |

---

## 8. Controls

**61 Phase 3 controls**, all reading the built warehouse rather than the pipeline's memory.
Written to `data/phase03_control_results.csv`.

| Family | Controls | What it covers |
|---|---|---|
| `P3-ING` | 13 | files, row counts, encodings, locales, dates, account-key typing, lineage grain and density, special periods, the forbidden translated columns, per-ERP numeric grammar |
| `P3-TB` | 6 | the trial balance survives each conversion; statistical accounts excluded; no class inverted |
| `P3-MAP` | 13 | nothing unresolved, nothing ambiguous, effective dates, one default per conditional account, live targets, no orphan account, coverage of value, the German reclassification, the acceptance oracle |
| `P3-DIM` | 10 | every key resolves; no duplicate natural keys; Kestrel's native cost centre agrees with the resolution; intercompany partner validity; affiliate interest separated; FX rate completeness |
| `P3-REC` | 11 | source → standardised → mapped amount preservation, the group income statement, the balance sheet, revenue detail, business-unit margin, entity revenue, the trial balance fact, planning completeness |
| `P3-BR` | 3 | business sense: direct labour present, payroll splits plausibly, no source-layer CTA or reserve |
| `P3-CMP` | 3 | period completeness, no posting before an effective date, group-account coverage |
| `P3-ADJ` | 2 | Phase 3 posts no group adjustment and produces layer 1 only |

**Result: 54 pass, 0 blocking pipeline failures, 7 source findings.**

A control outcome is one of three things, and collapsing them would hide the one that
matters:

| Status | Meaning |
|---|---|
| `PASS` | the control holds |
| `FAIL` | **the pipeline is wrong.** A blocking failure stops the build. There are none |
| `SOURCE_FINDING` | the control does not hold, and the cause is a defect in the frozen source layer that Phase 3 is not permitted to patch. Reported with its population, its amount and its defect reference |

A source finding is never downgraded to a pass and never absorbed. The seven are listed in
§12 with the four defects they belong to.

A source finding is also not a licence to stop looking. Each is registered in
`config/controls/source_exception_register.csv` **at the population it was accepted at**, and
the control compares against that baseline: nil is a `PASS`, the accepted population is a
`SOURCE_FINDING`, and anything else — more lines or fewer — is a `FAIL`. Without that, a new
break of the same shape as an accepted one would hide inside the known population and no
control would ever move. Each entry carries the phase by which the defect is expected to be
corrected, so an exception cannot silently become permanent.

Two new design controls were added to the register (86 total, 71 blocking):
`CTL-DQ-11` source lineage complete and unique, `CTL-MAP-09` mapping rule set integrity.

---

## 9. Fault fixtures through the real pipeline

The ten approved Phase 2 fault fixtures were each run through **the actual pipeline** — a
complete source tree with that fault's file substituted, parsed, normalised, harmonised,
conformed and then controlled. The fixture generator was not tested against itself.

| Fault | What it is | Phase 2's intended control | Phase 3 family | Fired | Outcome |
|---|---|---|---|---|---|
| `F01` | Unmapped source account | `CTL-MAP-01` | `P3-MAP` | `P3-MAP-01`, `P3-MAP-03`, `P3-MAP-04`, `P3-MAP-08` | **DETECTED** |
| `F02` | Intercompany amount mismatch | `CTL-IC-01` | — | — | deferred to Phase 4 |
| `F03` | Missing FX rate | `CTL-FX-01` | `P3-DIM` | `P3-DIM-10` | **DETECTED** |
| `F04` | Duplicate journal identifier | `CTL-DQ-03` | `P3-ING` | `P3-ING-02`, `P3-ING-08` | **DETECTED** |
| `F05` | Invalid cost centre | `CTL-DQ-08` | `P3-DIM` | `P3-DIM-02` | **DETECTED** |
| `F06` | Malformed localised amount | `CTL-DQ-09` | `P3-ING` | `P3-ING-13` | **DETECTED** |
| `F07` | Posting date outside its period | `CTL-DQ-06` | `P3-ING` | `P3-ING-06` | **DETECTED** |
| `F08` | Payroll misclassified across the gross margin line | `CTL-MAP-04` | `P3-REC` | `P3-REC-06` | **DETECTED** |
| `F09` | Unbalanced journal | `CTL-TB-01` | `P3-TB` | `P3-TB-01`, `P3-TB-02`, `P3-TB-03` | **DETECTED** |
| `F10` | Posting before the consolidation effective date | `CTL-CON-02` | `P3-CMP` | `P3-CMP-02` | **DETECTED** |

**9 of 10 faults are detected in Phase 3 by the control family that is supposed to catch
them; the tenth belongs to a later phase. 10 of 10 handled as intended, and none detected
only by accident.**

Results: `data/phase03_fault_results.csv`.

Two notes on how this is scored. A fault is **detected** only when a control in the family
that is *supposed* to catch it fires; a fault found only by an unrelated control would be a
control-design defect, not a success. And a fault frequently breaks several controls at once —
an unmapped account also breaks the mapped trial balance, because the line has no group
account to sit in. That cascade is expected and is reported alongside the intended detection
rather than counted as one.

Three of the ten were not handled as intended on the first sweep, and all three were **control
design** defects rather than fixture failures. F06's malformed German amount was found only by
the trial balance breaking three layers downstream; F08 was not found at all. F02 was flagged
by a parse error from a concurrent run rather than by anything real. Each was fixed at the
control — a new numeric-grammar control at ingestion, a gross-margin tolerance tightened to
one basis point, and a fault harness that no longer writes over the clean baseline (§13.4–13.6
and §13a). The sweep above is the re-run.

**F02 is not a gap.** An intercompany amount mismatch between two entities cannot be seen
until the pair is matched, and pair matching is the Phase 4 elimination engine. Both trial
balances still close, both postings map correctly, and every Phase 3 control is *right* to
pass. Reporting it as detected here would mean a Phase 3 control had fired for a reason it
does not own.

---

## 10. Performance

| Stage | Seconds |
|---|---|
| parsed | 22.5 |
| dimensions | 0.2 |
| standardised | 21.3 |
| mapped | 42.9 |
| subledgers | 2.9 |
| conformed | 9.1 |
| reconciliation and acceptance | 10.7 |
| **total** | **≈110 s** |

1,080,782 journal lines, 507 files, three encodings, on a laptop. Two consecutive runs, within
a second of each other. The 61 controls run separately against the built warehouse and take
about **2.4 s**.

No row-by-row Python in the transformation path, no repeated full-file scans, no CSV
round-tripping between stages — Parquet between layers and DuckDB throughout.

These figures are roughly double an earlier measurement of the same pipeline, taken before
the determinism work. Most of that is the machine rather than the code: the parse stage also
doubled, and nothing in it changed. The decimal arithmetic and the artefact sorts are not
free, but they are not the explanation either, and they are not negotiable — a build that
totals a ledger differently depending on thread scheduling is not a build worth having
quickly.

---

## 11. Determinism and reproducibility

A clean clone runs:

```bash
python src/anchors/build_anchors.py     # anchors
python -m src.generation.build          # the frozen source layer
python -m src.pipeline.run              # ingest → conform → controls
python -m pytest tests -q
```

The build id is the SHA-256 of the Phase 2 dataset digest plus the mapping configuration, the
four charts and the entity master — **not a timestamp**. A clock value in a committed manifest
leaves the working tree dirty after every run and destroys the reproducibility it was meant to
record. Wall-clock duration is printed and never written.

| Evidence | Result |
|---|---|
| Build id | `327f6075487158cc` |
| Frozen source layer digest | `34adb63e872ccd3f02318e9336739772f069c1c8add1f2b8c1217ae46e307b80` |
| Artefacts checksummed in the manifest | 25 |
| Consecutive pipeline runs | **three**, identical checksums across every one of the 25 artefacts |
| Money arithmetic | `DECIMAL(18,2)`, exact and order-independent, from the standardised layer onward |
| Working tree after a full rebuild | **clean** |

---

## 12. Defects found in the frozen source layer

Phase 3 revealed four defects in the Phase 2 source data. Per the Phase 3 brief, **none was
patched** and no Phase 2 generation module was changed —
`test_no_phase_2_generator_module_was_changed_by_phase_3` asserts that against git.

Each is stated below with what it is, why it is a source-layer defect rather than a pipeline
one, what it affects, and a proposed correction.

### P2-D-01 — Opening-balance, year-end-close and special-period journals carry no line attributes

**What it is.** `src/generation/journals.py` writes three journal types without the line
attributes the approved mapping contract requires. In `year_end_close` and
`special_period_adjustments` the required attributes are *fetched from the source map and then
discarded* (`src, req = resolved` / `src, _req = resolved`, with `""` written to the attribute
field); `opening_balance` does the same.

**Why it is a source-layer defect.** The approved mapping contract states, per source account,
which line attribute a conditional split must read. A posting to a conditional account that
carries none of them cannot be classified from the data it contains. The mapping engine
behaves correctly — it resolves to the account's declared default branch — but the source
extract does not contain the information the contract says it will.

**Affected.** 166 lines across 3 ERPs and 16 source accounts:

| Journal type | Lines | Entities | Absolute amount, local |
|---|---|---|---|
| `YEAR_END_CLOSE` | 158 | 12 | 67,888,396 |
| `AUDIT_ADJUSTMENT` (Kestrel period 14) | 5 | 4 | 9,273 |
| `OPENING_BALANCE` | 3 | 3 | 1,891,449 |

**Effect.** It is the sole cause of the mapping shortfall from 100.000000% to 99.984641%, and
it is **material to the balance sheet**: seven Kestrel postings to `00017000 Aktive
Rechnungsabgrenzung` carry no `accrual_type`, so **$2.33m — 26% of the caption — sits in
prepayments instead of contract assets**, and contract assets are driven to a credit balance
at the Kestrel entities. The year-end-close lines have no effect on any reported figure,
because the close is excluded from every result measure by design.

**Proposed correction.** In `journals.py`, write `req` to the line-attribute field in
`opening_balance`, `year_end_close` and `special_period_adjustments`, exactly as `post()`
already does. The attributes are already resolved in each of the three methods and are
currently discarded. Regenerate, and re-run the Phase 2 controls and the Phase 3 acceptance.

**Controls reporting it:** `P3-MAP-04`, `P3-MAP-13`, `P3-REC-03`, `P3-TB-06`.

### P2-D-02 — A posting's declared classification contradicts the cost centre it was posted to

**What it is.** `journals.py::_cost_centre` selects a cost centre from `ACCOUNT_DEPTS` for the
group account, and only *then* applies the split's required function to the line attribute.
For `dept_function` it re-picks the department only if a matching one exists within
`ACCOUNT_DEPTS` at that entity; for `cost_center_function` it does not re-pick at all; for
`dept_code` there is no handling. The line therefore declares one classification and sits in a
cost centre carrying another.

**Why it is a source-layer defect.** The whole basis of the material mapping problem
(ADR-0007, CTL-MAP-04) is that the **department or cost-centre segment** carries the
information the account code cannot. A German entity's split of `00091600 Leiharbeit` between
cost of sales and operating expenses comes from KOSTL. A free-text assignment field that
contradicts KOSTL would be a finding in any real implementation.

**Affected.** 5,710 lines, 0.53% of the ledger:

| ERP | Lines | Absolute amount, local |
|---|---|---|
| Kestrel | 4,419 | 44,403,103 |
| Sable | 1,291 | 6,696,513 |

Thirteen distinct combinations, all of one shape: a posting declaring `PRODUCTION`, `FIELD` or
`INDIRECT_OPS` while sitting in an `SGA`, `PROJECT` or `INDIRECT_OPS` cost centre.

**Effect.** None on any reported figure. The mapping contract names the line attribute as
authoritative, the engine resolves attribute-first, and the mapped result reproduces the
oracle exactly for all of these lines. What is lost is corroboration: the cost-centre
dimension does not independently confirm the classification, so a reviewer cannot check the
gross margin split from the dimension alone.

**Proposed correction.** In `_cost_centre`, honour all three required attributes when
selecting the cost centre — extend the `dept_function` search beyond `ACCOUNT_DEPTS` to any
department at the entity carrying the required function, apply the same search for
`cost_center_function`, and select the named department for `dept_code`. Where an entity
genuinely has no department of the required function, the split itself should be reconsidered
rather than the label applied anyway.

**Control reporting it:** `P3-MAP-12`.

### P2-D-03 — Intercompany postings do not consistently carry the counterparty

**What it is.** The invoice leg of every intercompany flow carries its partner. The **cash
settlement leg** does not, because `journals.py` stage 3 posts settlements with `partner=""`.
The group treasury current account (`125100` / `225100`) and the intercompany loan accounts
(`175100` / `235100`) carry **no partner on any line**, although their counterparty is always
Topco by construction.

**Why it is a source-layer defect.** `CTL-IC-04` — a Phase 3 blocking control approved in
Phase 1 — requires every posting to an intercompany account to carry a valid partner. In a
real ERP, clearing an intercompany receivable references the specific counterparty; that is
how the balance is attributable.

**Affected.** 5,248 postings:

| Account group | Lines |
|---|---|
| Intercompany trade current account (`120500`, `210500`) | 4,628 |
| Group treasury current account (`125100`, `225100`) | 375 |
| Intercompany loans (`175100`, `235100`) | 243 |
| Other | 2 |

**Effect. Material for Phase 4.** At 31 December 2025 the intercompany receivable and payable
position is **(24.284)m local in total, of which only (8.913)m — 37% — is attributable to an
entity pair**. The intercompany *result* elimination will work, because the invoice legs carry
partners; the intercompany **balance sheet** elimination by pair will not. Phase 2's own
`P2-IC-01` did not catch this because it filters to lines that already have a partner.

**Proposed correction.** In `journals.py`, carry the partner onto the settlement leg of every
intercompany balance (the settlement is generated from the same movement as the invoice, so
the counterparty is known), and set the partner to `NIG-100` on every treasury current account
and intercompany loan posting. Then tighten `P2-IC-01` so it tests the whole intercompany
population rather than the subset that already has a partner.

**Control reporting it:** `P3-DIM-08`.

### P2-D-04 — Kestrel special period 15 crosses an anchored balance sheet caption

**What it is.** The period-15 tax true-up reallocates between corporate income tax and trade
tax on the balance sheet, moving an amount from `218100 Income taxes payable` to
`219100 Other taxes payable`. Those two accounts belong to **different anchored captions**:
`tax_payable` and `accrued` respectively.

**Why it is a source-layer defect.** The Phase 2.1 report states that special periods 14–16
"reclassify within one anchored caption, so the year's result and every anchored subtotal are
unchanged", and control `P2-FMT-09` tests it — but only for the **result**, not for balance
sheet captions.

**Affected.** $0.028m, $0.039m and $0.126m in FY2023, FY2024 and FY2025 — 0.56% of income taxes
payable and 5.1% of the caption at FY2025.

**Effect.** Two balance sheet captions deviate from the source-layer target by that amount.
The mapping is not involved: the pipeline and the oracle agree exactly.

**Proposed correction.** Either replace the `218100 → 219100` leg of the period-15 adjustment
with one that stays inside the tax-payable caption, or accept it and extend `P2-FMT-09` to
test anchored balance sheet captions as well as the result, restating the two caption anchors
accordingly. The first is simpler and preserves the stated design intent.

**Control reporting it:** `P3-REC-11`.

---

## 13. Defects found and fixed inside Phase 3

Seven. Three were found by the acceptance oracle during development; three were found by
running the fault fixtures through the real pipeline, and every one of those three is a
**control-design** defect — the fault was caught by the wrong control, or not at all. The
brief is explicit that this is a failure to be fixed rather than a result to be reported, and
each fix tightens a control the clean baseline already satisfies. **No threshold was loosened
and no control was weakened to make the sweep pass.** The seventh was found by the determinism
proof itself.

1. **A rule field resolved to the wrong source.** `dept_code` was resolved from the posted
   department segment only. Where a posting declares its own `dept_code`, the declared value
   is the source system's statement about the line and must take precedence. 186 Sable lines
   were mapping to consulting fees instead of the integration-programme add-back.
2. **A split rule authored from an incomplete narrative.** Kestrel `00089000` was authored as
   `partner_bu = 'IS' → service revenue`, following the chart narrative. IC-SV-03 recharges
   Tyneside services to an Engineered Systems partner, which that rule sends to product
   revenue. Expressed the other way round — `partner_bu IN ('FC','AM') → product`, else
   service — the rule matches the intercompany matrix. 26 lines.
3. **A sign control testing the wrong quantity.** The account-class sign test was written
   against each year's *movement*, which is legitimately either way round for a balance sheet
   account. It now tests the closing **balance** for balance sheet accounts and the year's
   total for income statement accounts, with contra and genuinely bidirectional accounts named
   and excluded rather than inferred.
4. **No control could see a malformed localised amount.** Fault F06 rewrites a German
   `13.068,03` as `13.068.03`. That is not null, not blank and not non-numeric — DuckDB reads
   it as 1,306,803, a hundredfold overstatement that then balances, because the fault rewrites
   both legs. The completeness and null controls are structurally incapable of seeing it. A
   new control `P3-ING-13` now validates every raw amount string against a **per-ERP numeric
   grammar** before it is ever cast: Aurora and Sable US grouping, Kestrel German grouping,
   each as an anchored regular expression. The clean data has zero non-conforming amounts, so
   the control is at its natural threshold and not a tuned one. F06 now fails it at ingestion,
   which is where the defect actually is. The design register was underspecified in the same
   way — `CTL-DQ-09` asked only for zero nulls — and its acceptance criterion was amended to
   require grammar conformance before the cast.
5. **The gross-margin control was too loose to see a plausible misclassification.** Fault F08
   re-tags eight payroll postings from a production department to an SGA one *consistently* —
   attributes and cost centre agree — so nothing about the line looks wrong. It moves group
   gross margin by 0.047104pp, and `P3-REC-06` was set at 0.05pp. The threshold was the
   defect: the clean pipeline reproduces every business unit's margin at **exactly**
   0.000000pp, because the mapping is deterministic and the target is the source itself, so
   any tolerance above zero is slack with nothing to absorb. It is now 0.01pp — one basis
   point, a factor of five below the fault it must catch and many orders of magnitude above
   float noise. It is named `TOL_MARGIN` in `controls.py` rather than written inline, so a
   test can assert it has not drifted back up. F08 fails it.
6. **A known source finding could hide a new defect.** The three-way status was right, but a
   `SOURCE_FINDING` was decided on the shape of the break, not its size — so a *new* break of
   a known shape would have been absorbed into an existing finding and never surfaced. The
   source exception register (§8) now fixes each accepted finding at its population, and the
   control fails on any deviation in either direction.
7. **The build was not actually reproducible, and money was a float.** Two consecutive runs
   of the same pipeline over the same frozen input produced different bytes in three
   artefacts. Two causes, both worth stating plainly because the second is an accounting
   defect and not merely a build one.

   *Order.* Several artefacts were written with no `ORDER BY`. DuckDB's parallel scan is free
   to emit rows in a different sequence on an identical input, so the Parquet differed while
   the data did not. Every committed artefact now has a total order — the journal-line fact
   by its lineage, everything else by all of its columns — the two `list()` aggregates are
   sorted, and the example columns in the exception and acceptance files use `min()` rather
   than `any_value()`, so no run can name a different example line than the last.

   *Arithmetic.* `signed_local_amount` was a `DOUBLE`. A parallel `SUM` over doubles adds its
   partial results in whatever order the threads finish in, and floating-point addition is
   not associative — so the same ledger could total to a different last bit from one run to
   the next. On a reconciliation quoted to six decimals that is enough to move a printed
   figure, and it is the wrong representation for money regardless. Every source amount is
   exact to the cent (verified: zero values beyond two decimal places across all 1,080,782
   lines), so money is now `DECIMAL(18,2)` from the standardised layer onward, where the
   canonical sign is applied. DuckDB's decimal sum is exact integer arithmetic and
   independent of order. The USD comparison views round to the cent through a single named
   `usd()` macro for the same reason.

   No reported figure changed: the group income statement, entity revenue and all twelve
   business-unit margins still reconcile at exactly 0.000000. Three consecutive full runs now
   produce byte-identical output across all 25 artefacts.

---

## 13a. Self-audit

Reviewed as if another firm were about to audit the implementation.

| Reviewed | Finding |
|---|---|
| Sign conventions | stated once in `config.py`, recovered per system, proved by `P3-TB-01` to `P3-TB-06`. Debit less credit reconstructs the signed amount exactly on all 1.08m lines; Kestrel's native SOLL and HABEN agree with the derived pair to 0.00 |
| Mapping correctness | 100.000000% against the oracle on every classifiable line; the shortfall is attributed to a named source defect, not absorbed |
| Source lineage | complete on every row; grain enforced; ordinals dense 1..N per file |
| Effective dates | zero postings outside their mapping's effective window |
| Duplicated or overlapping rules | rule ids unique; no line matches more than one non-default branch; no two rules share a priority within an account |
| Mapping defaults | every conditional account declares one explicitly; none is an `else` in code |
| Special periods | four types classified, all reporting in December, none reaching a management view |
| German presentation reclass | 613 postings, all in cost of sales, none left in revenue, amount unchanged, flagged and traceable |
| Scenario leakage | the GL fact carries `ACT`/`ACTUAL` only; the reserved Downside has no rows; Prior Year is not materialised |
| Account-key typing | Kestrel's eight-character keys are text everywhere, none coerced; no adapter casts an account key to a number |
| Stale source currency fields | present on the detail for lineage, absent from every aggregate |
| Rounding | the journal-line fact rounds nothing; only the trial balance aggregate rounds, and it ties to the detail at 0.0000 |
| Mapping-induced imbalance | mapping moves no amount, line for line, at 0.000000 |
| Loss of source detail | 266 of 392 source accounts post; every native column is preserved in the parsed layer; the customer reference stays on the line without its measures |
| Performance | ~110 s for 1.08m lines, no row-by-row Python in the transformation path |
| Determinism | build id is a function of its inputs; no clock value in any committed artefact; three consecutive runs produce identical checksums across all 25 artefacts. This did **not** hold on first inspection and was fixed (§13.7) |
| Money representation | `DECIMAL(18,2)` from the standardised layer onward, so no total depends on thread scheduling. Verified lossless: zero source amounts carry more than two decimal places |
| Control design | the three faults the sweep did not route to their intended control family were treated as control defects and fixed at the control, not at the fixture (§13.4–13.6) |

Four defects in Phase 3's own work were found by this review and fixed: the account-class
sign control was testing a movement where it should have tested a balance (§13.3); a fault run
was overwriting the clean baseline's staging artefacts — the fault harness now runs the real
stages with artefact writing switched off, so a fault variant cannot contaminate the baseline;
two concurrent pipeline processes writing the same staging Parquet produced a spurious parse
failure, which is why the harness serialises its variants; and the build was not reproducible
because artefacts had no total order and money was held as a float (§13.7).

The last one is the one worth dwelling on. Determinism was **claimed** in the design and
asserted by a test that compared row counts. It was never actually measured byte for byte
until this review, and when it was, it did not hold.

---

## 14. Files created and changed

**New — code (12):** `src/pipeline/` — `config.py`, `adapters.py`, `dimensions.py`,
`standardise.py`, `rules.py`, `harmonise.py`, `subledgers.py`, `conform.py`, `reconcile.py`,
`controls.py`, `faults.py`, `run.py`, plus `__init__.py`.

**New — configuration (2):** `config/mapping/mapping_rules.csv`, 127 effective-dated rules;
`config/controls/source_exception_register.csv`, the seven accepted source findings with the
population each was accepted at.

**New — documentation (8):** `docs/ingestion-design.md`, `docs/mapping-engine.md`,
`docs/staging-data-dictionary.md`, `docs/source-to-group-reconciliation.md`,
`docs/adr/0019-five-layer-ingestion-with-line-level-lineage.md`,
`docs/adr/0020-mapping-rules-as-an-executable-configuration-language.md`,
`docs/adr/0021-source-findings-are-baselined-not-downgraded.md`,
`docs/adr/0022-money-is-decimal-and-artefacts-are-totally-ordered.md`, and this report.

**New — tests (1):** `tests/test_phase03_pipeline.py`, 50 tests.

**New — committed evidence (5):** `data/phase03_manifest.json`,
`data/phase03_control_results.csv`, `data/phase03_reconciliation.csv`,
`data/phase03_mapping_acceptance.csv`, `data/phase03_fault_results.csv`.

**Amended — configuration (1):** `config/controls/control_register.csv` (+CTL-DQ-11,
+CTL-MAP-09).

**Amended — documentation (5):** `docs/control-framework.md`, `docs/data-contract.md`,
`docs/adr/README.md`, `docs/phases/roadmap.md`, `README.md`.

**Amended — build (1):** `Makefile`.

**Unchanged:** every Phase 2 generation module, every anchor, every source chart, every
extract. `src/generation/` is byte-identical to commit `20355b2`.

---

## 15. Limitations and open questions

1. **Four source defects are open** (§12). P2-D-01 and P2-D-03 have consequences that
   propagate: P2-D-01 misstates two balance sheet captions by $2.33m, and P2-D-03 leaves 63%
   of the intercompany balance position unattributable to an entity pair, which Phase 4's
   balance sheet elimination will need. Both need an owner decision before Phase 4 begins.
2. **The mapping gate is met on classifiable lines and not across all lines** (§6). It cannot
   be met across all lines while P2-D-01 stands, because the data does not contain what the
   rule needs. The threshold was not reduced.
3. **`ref_cta_expectation` is loaded as a control input only.** It is the expectation Phase 5's
   translation engine will be tested against (CTL-FX-12) and must never be joined into a
   reporting measure. Nothing enforces that beyond the documented intent and its absence from
   every fact.
4. **`stg_group_adjustment` is empty and untested in anger.** Its schema is declared and
   `P3-ADJ-01` proves Phase 3 writes nothing to it, but no entry has ever passed through it.
5. **Two rule branches never fire on the current data** — Sable `40900` reimbursables and
   Kestrel `00081200` own work capitalised. They are authored from the approved charts and are
   correct; they are simply unexercised, and `rpt_group_account_coverage` reports 23 group
   accounts as `MAPPED_BUT_UNUSED` for the same reason.
6. **The validation views translate at approved rates for comparison only.** They are views,
   not facts, and produce no CTA — but they are the first place in the platform where a rate is
   applied to a ledger amount, and Phase 4 must not mistake them for a translation engine.

---

## 16. Recommended Phase 4 scope

Ordered by dependency.

1. **Resolve the four source defects first.** P2-D-01 and P2-D-03 in particular: Phase 4's
   intercompany balance sheet elimination needs the counterparty on the settlement legs, and
   two balance sheet captions are currently misstated. A Phase 2.3 correction pass regenerating
   the source layer and re-running Phase 3 is the cheapest point at which to fix them.
2. **FX translation and the CTA.** Monthly average for the income statement, closing rate for
   the balance sheet, historical rates for equity from `ref_fx_rate_historical` (FX-P03), and
   CTA computed to layer 5. It is tested against `ref_cta_expectation` — the per-entity,
   per-month expectation Phase 2.2 derived from source balances before any engine existed
   (CTL-FX-04, CTL-FX-12, ADR-0017). CTA must never be entered as a plug, and `P3-BR-03` has
   already proved there is no source-layer reserve for it to hide in.
3. **Intercompany elimination by entity pair**, layer 2, using `dim_intercompany_partner` and
   the conformed ledger. Blocked on P2-D-03 for the balance sheet legs.
4. **Investment elimination** across the full ownership tree, from `ref_investment_register`
   and `ref_investment_rollforward`, layer 3.
5. **Purchase price allocation and acquired intangible amortisation**, layer 3 — the goodwill,
   intangibles and PPA deferred tax that `rpt_group_account_coverage` currently reports as
   `CREATED_BY_CONSOLIDATION`.
6. **NCI allocation** — income, equity and the NCI share of CTA — from `ref_ownership`,
   layer 3.
7. **Unrealised profit in inventory**, from `ref_ic_inventory_holding`'s FIFO layers, layer 3.
8. **The management adjustment layer**, layer 4, with the adjustment metadata `CTL-CON-07`
   requires. `stg_group_adjustment` is the staging table it should be raised through.
9. **Cash flow derived from balance sheet movements** (ADR-0006).

Phase 4 should not touch `src/pipeline/` other than to consume its output, and should not
change the source layer.

---

**Phase 3 is complete.** The three source systems ingest, normalise and harmonise into one
finance data model with full line-level lineage, a configuration-driven mapping engine that
reproduces the acceptance oracle exactly on every line the source classified, and no
consolidation performed. Four defects in the frozen source layer are reported, quantified and
escalated rather than patched.
