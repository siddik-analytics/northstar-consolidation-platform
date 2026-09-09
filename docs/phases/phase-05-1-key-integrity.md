# Phase 5.1 — upstream dimensional-integrity correction

**Status:** complete, awaiting rebaseline review
**Baseline corrected:** `026bf43` (Phase 5, approved)
**Discovered during:** Phase 6A, Power BI semantic model
**Decision:** Option A — fix the source generator
**ADR:** [ADR-0026](../adr/0026-a-declared-key-is-a-contract.md)

---

## 1. What was wrong

Building the Power BI `Capital Project` dimension required a unique key. `project_id` was not
one.

| | rows | distinct `project_id` |
|---|---|---|
| `data/reference/capex_projects.csv` | 1,846 | 395 |
| `fact_capex_project` | 1,846 | 395 |
| `ref_fixed_asset` | 1,846 | 395 |
| `mart_capex` | 1,846 | 395 |

```
CP-200-202505-01  BUILDING   Buildings and improvements programme       44,908.63
CP-200-202505-01  IT         Computer hardware and software programme   16,840.74
CP-200-202505-01  LEASEHOLD  Leasehold improvements programme           14,969.54
CP-200-202505-01  PLANT      Machinery and equipment programme          86,074.88
CP-200-202505-01  VEHICLE    Vehicles programme                         24,325.51
```

Five different capital programmes, one identifier.

### Root cause

`src/generation/datasets.py`. The sequence number came from the inner loop that splits **one
asset class** into parts, while the outer loop walked the asset classes — so it restarted at
`-01` for every class in the same entity-month.

```python
for acct, amt in additions.items():                          # asset class
    for i, part in enumerate(allocate_exact(amt, ...)):      # split within that class
        pid = f"CP-{entity[-3:]}-{em.period_key}-{i + 1:02d}"   # i restarts per class
```

### Why nothing caught it

**Every join still worked.** `ref_fixed_asset` joined `fact_capex_project` and returned rows —
five times too many, and no control compared the row count before the join with the row count
after it.

The only checks in range were `P5-OPS-03` (`project_id IS NOT NULL`, which a colliding key
passes) and `P5-GRN-01`/`P5-GRN-02`, which covered the two financial marts and no operational
mart at all. The deeper gap was that the platform declared keys without ever proving them.

---

## 2. The corrected identifier

```
CP-{entity}-{period}-{asset_class}-{sequence}     e.g. CP-200-202505-PLANT-01
```

Deterministic, human-readable, asset class explicit, sequence scoped within entity + period +
class. No UUID, no downstream surrogate, no hash.

```python
for acct, (cls, name, life) in ASSET_CLASSES.items():        # declared order, not derived
    amt = additions[acct]
    ...
    pid = f"CP-{entity[-3:]}-{em.period_key}-{cls}-{i + 1:02d}"
```

Two deliberate properties:

* **Asset classes are walked in `ASSET_CLASSES` declaration order**, not in the order a derived
  dict happens to yield. The per-entity generator is consumed in loop order, so the sequence of
  random draws — and therefore the economics — is a function of that order. Iterating the
  declared constant removes the dependence on an incidental dict without perturbing a single
  draw.
* **Only the identifier string changed.** No draw, no allocation, no rounding.

### Result

| | before | after |
|---|---|---|
| `capex_projects.csv` rows / distinct ids | 1,846 / **395** | 1,846 / **1,846** |
| `fixed_assets.csv` rows / distinct `asset_id` | 1,846 / 1,846 | 1,846 / 1,846 |
| `fixed_assets.csv` distinct `project_id` | **395** | **1,846** |
| orphan fixed assets | 0 | 0 |
| max rows per `project_id` | **5** | **1** |

---

## 3. Traceability restored

```
Capital Project ──► CapEx fact ──► Fixed Asset
```

| control | result |
|---|---|
| `P7-CPX-01` every project row carries its own identifier | 1,846 rows / 1,846 ids |
| `P7-CPX-02` every fixed asset resolves to a project | 0 orphans |
| `P7-CPX-03` no identifier resolves to two project definitions | 0 |
| `P7-CPX-04` asset agrees with project on asset class | 0 disagreements |
| `P7-CPX-05` asset agrees with project on owning entity | 0 disagreements |
| `P7-CPX-06` asset acquired in its project's period | 0 disagreements |
| `P7-CPX-07` asset cost reconciles to project spend, project by project | `0.00` |
| `P7-CPX-08` every project created at least one asset | 0 unbuilt |
| `P7-CPX-09` the corrected key reaches the reporting mart | 1,846 / 1,846 |

The join no longer fans out: 1,846 assets joined to projects return 1,846 rows.

---

## 4. The framework

Two files. The split is the point.

| | |
|---|---|
| `src/integrity/registry.py` | **What is true** — every declared key, grain and foreign key, with its authority and owner. Data, not code. |
| `src/integrity/controls.py` | **One engine that proves all of it.** No bespoke checks. |

**61 keyed objects declared** — 17 dimensions, 20 references, 9 facts, 15 marts — covering the
whole chain from the source subledgers to the marts, because P6-D-01 existed in the source and
reached Power BI intact.

Every key was established against the real population rather than assumed from the column
names. Six needed a column the obvious guess omitted, which is the same class of mistake the
defect was:

| object | what the obvious key missed |
|---|---|
| `dim_date` | `accounting_period` — adjustment periods 13–16 share a `period_key` |
| `fact_trial_balance` | `special_period_type` |
| `fact_layer1_usd` | `translation_basis` — average and closing are different rows |
| `fact_financials` | `process`, `journal_character` |
| `fact_revenue_detail` | `group_account` |
| `ref_fx_rate` | `rate_set`, `rate_type` |

### Results

| family | controls | passed |
|---|---|---|
| `P7-REG` registry is complete and honest | 4 | 4 |
| `P7-KEY` every declared key unique over its population | 61 | 61 |
| `P7-NUL` no null in an unpermitted key column | 122 | 122 |
| `P7-REF` every declared foreign key resolves | 33 | 32 + 1 finding |
| `P7-CPX` the capital project chain | 9 | 9 |
| **total** | **229** | **228, 0 blocking failures, 1 open finding** |

`P7-REG-01` is the one that matters: it fails when a keyed table exists that the registry does
not declare. Without it the framework reports green over the objects it happens to know about
— which is exactly where the platform already was.

### Nulls in a key

Four facts legitimately carry a null in a key column: a non-intercompany line has no partner, a
consolidation entry has no cost centre, an ordinary posting has no special period type, layer 1
is not the output of a process. That is NULL meaning *there is none*, not *unknown*. The
permission is **per column with a reason**, and `P7-NUL-<object>-declared` fails a permission
with no reason or a reason with no permission.

### Fault fixtures

| fixture | must be caught by | result |
|---|---|---|
| `F7-KEY-01` two projects share one identifier — **P6-D-01 recreated** | `P7-CPX-01` | DETECTED |
| `F7-KEY-02` a dimension holds two rows for one member | `P7-KEY-dim_entity` | DETECTED |
| `F7-KEY-03` a mart duplicates a row at its declared grain | `P7-KEY-mart_capex` | DETECTED |
| `F7-NUL-01` a declared key column is null | `P7-NUL-fact_capex_project` | DETECTED |
| `F7-REF-01` an asset references a project that does not exist | `P7-CPX-02` | DETECTED |
| `F7-REG-01` a keyed table the registry does not declare | `P7-REG-01` | DETECTED |
| `F7-CPX-01` asset contradicts project on asset class | `P7-CPX-04` | DETECTED |
| `F7-CPX-02` asset contradicts project on owning entity | `P7-CPX-05` | DETECTED |
| `F7-CPX-03` asset cost no longer reconciles | `P7-CPX-07` | DETECTED |

**9/9 detected by their intended control.** A fixture caught by some *other* control is
reported as a miss — "something went red" is not "the right thing went red". Each runs inside a
rolled-back transaction; the warehouse was verified unchanged afterwards.

---

## 5. Open finding P7-D-01 — reported, not fixed

The framework found a second gap on its first run.

`PY_DERIVED` is used as a version code by **12,516 rows** of `mart_financial_ytd` and by the
prior-year comparator rows of `mart_variance`, but no such row exists in `dim_version` or
`dim_report_scenario` — even though `PY` *is* a first-class scenario in `dim_scenario`. Prior
year is derived in the mart by shifting Actual twelve months and stored nowhere
(`src/marts/build.py:158`); `ref_default_version` unions the PY default in by hand, which is
the design already working around the gap.

It is quarantined at its exact population under
[ADR-0021](../adr/0021-source-findings-are-baselined-not-downgraded.md): the control reports
`SOURCE_FINDING` at exactly 12,516 orphans and **FAILS** at any other number, so a new defect
of the same shape cannot hide inside a known one, and a silent upstream fix does not pass
unnoticed either.

**Not fixed here.** The fix belongs to the Phase 5 scenario architecture — a derived version
needs a row in the version master, or the mart should not put PY in a column called
`version_code` — and that is a design decision, not an identifier correction. It needs an owner
decision.

---

## 6. Zero economic drift

`tools/financial_invariance.py`, sixteen grains, full outer joined on the business key.

| comparison | rows | only before | only after | max abs diff |
|---|---|---|---|---|
| `journal_by_month_entity_account` | 1,256 | 0 | 0 | 0.000000 |
| `financials_by_month_entity_account` | 39,492 | 0 | 0 | 0.000000 |
| `mart_measure_grain` | 44,184 | 0 | 0 | 0.000000 |
| `mart_account_grain` | 133,558 | 0 | 0 | 0.000000 |
| `mart_variance` | 50,652 | 0 | 0 | 0.000000 |
| `mart_balance_sheet` | 1,296 | 0 | 0 | 0.000000 |
| `mart_cash_flow` | 48 | 0 | 0 | 0.000000 |
| `mart_covenants` | 33 | 0 | 0 | 0.000000 |
| `mart_working_capital` | 48 | 0 | 0 | 0.000000 |
| `mart_debt` | 595 | 0 | 0 | 0.000000 |
| `mart_headcount` | 22,215 | 0 | 0 | 0.000000 |
| `mart_fx` | 176 | 0 | 0 | 0.000000 |
| `mart_layer_bridge` | 20 | 0 | 0 | 0.000000 |
| `capex_by_entity_month_class` | 1,836 | 0 | 0 | 0.000000 |
| `capex_source_by_entity_month_class` | 1,836 | 0 | 0 | 0.000000 |
| `fixed_assets_by_entity_class` | 51 | 0 | 0 | 0.000000 |

**ZERO ECONOMIC DRIFT** — 297,296 rows, every monetary difference `0.00`, and no row appearing
or disappearing on either side.

Capex is compared on entity, month and asset class — its economic grain — and never on
`project_id`, because joining on the thing that changed would compare nothing. The row count is
carried as a compared *value*, so a correction that split or merged projects would fail there
rather than pass on totals.

Independently recomputed, not carried forward:

| | before | after |
|---|---|---|
| source CapEx `spend_local` | 71,937,380.13 | **71,937,380.13** |
| fixed-asset `cost_local` | 71,937,380.13 | **71,937,380.13** |
| mart CapEx `spend_usd` | 70,919,722.37 | **70,919,722.37** |

---

## 7. Full regression

| suite | result |
|---|---|
| Phase 2 source controls | **80/80 passed** |
| Phase 2 fault fixtures | **10/10 detected** |
| Phase 3 ingestion controls | **62/62 passed**, 0 source findings |
| Phase 3 fault fixtures | **10/10 handled as intended** (F02 deferred to the Phase 4 hard gate) |
| Phase 4 consolidation controls | **72/72 passed**, 0 source findings |
| Phase 4 fault fixtures | **23/23 handled as intended** |
| Phase 5 mart controls | **36/36 passed** |
| Excel reconciliation | **17/17 agree with the marts** |
| Excel layout QA | 0 blocking, 0 warnings; 16 sheets rendered |
| Key and grain controls | **228/229**, 0 blocking, 1 open finding |
| Key fault fixtures | **9/9 detected** |
| `pytest` | **469 passed** |

---

## 8. What changed, and what only looks like it changed

### Content changed

| artefact | what changed |
|---|---|
| `data/reference/capex_projects.csv` | 1,846 `project_id` values |
| `data/reference/fixed_assets.csv` | 1,846 `project_id` values, and `asset_description` (it embeds the id) |
| `fact_capex_project`, `ref_fixed_asset`, `mart_capex` | the same identifiers, carried through |
| workbook sheet `_capex` (hidden data sheet) | 1,846 identifier strings |
| `src/generation/datasets.py` | the generator fix |

### Only the build metadata changed

| | before | after |
|---|---|---|
| source layer digest | `fd7afb8f…` | `8013298c…` |
| Phase 3 build id | `4e860643143938e8` | `6e0c519360d3669b` |
| Phase 4 build id | `78e406e139662392` | `a99d9fba5694ad7d` |
| Phase 5 mart build id | `2caac83888d04d3f` | `24b65b7f05f7697d` |
| workbook build digest | `ee8bf988…` | `0defa626…` |

Every manifest hash moved because it incorporates the source digest. That is the mechanism
working, not evidence of drift.

### The workbook, cell by cell

`tools/workbook_diff.py`, 42 sheets, 615,262 valued cells:

```
NUMERIC differences    : 0
text differences       : 1852
cells added / removed  : 0 / 0

  _capex                         1846      the project identifiers
  00 Cover                          3      source digest, consolidation and mart build ids
  15 Data & Technical               3      the same three lineage stamps

VERDICT: NO NUMERIC CHANGE
```

No **visible** sheet changed at all. `project_id` is selected for the *Largest projects* table
but never written — that table shows the project name, business unit, asset class and amounts
(`src/excel/sheets3.py:188`) — so the identifiers live only on the hidden `_capex` data sheet.

---

## 9. Determinism

The full chain was built twice from a clean generation. Every identifier reproduced:

| | run 1 | run 2 |
|---|---|---|
| `capex_projects.csv` digest | `aeadd5a6720bb205` | `aeadd5a6720bb205` |
| source dataset digest | `8013298c3fee35ef…` | `8013298c3fee35ef…` |
| Phase 4 build id | `a99d9fba5694ad7d` | `a99d9fba5694ad7d` |
| Phase 5 mart build id | `24b65b7f05f7697d` | `24b65b7f05f7697d` |
| workbook build digest | `0defa62662371119` | `0defa62662371119` |

---

## 10. Scope discipline

Not done, deliberately:

* No surrogate key in Power BI, no `asset_class` concatenation in the mart, no dropped
  dimension. The generator is the authority and it was corrected there.
* No accounting logic touched. No FX, IC, PPA, NCI, PUP, CTA or statement code changed.
* Phase 6A **not resumed**. The WIP is preserved on `wip/phase-06a-semantic-model` at `ca72922`
  and must be rebased onto this baseline before it continues — its `Capital Project` and
  `CapEx` declarations still assume the defective key.
* P7-D-01 reported, not fixed.

---

## 11. The lesson

> **A declared key is a contract, not a naming convention. Its uniqueness must be proved over
> its authoritative population.**

`project_id` was documented as a key, named like a key and joined on like a key for four
phases, 250 controls and 42 fault fixtures. It was found by a modelling tool asking the one
question nobody had thought to ask.

The framework exists so that question is now asked of every key, on every build, by default.
