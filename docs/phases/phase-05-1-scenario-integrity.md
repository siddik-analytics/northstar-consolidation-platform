# Phase 5.1 — scenario dimension integrity

**Status:** complete, awaiting rebaseline review
**Corrects:** `dd46611` (Phase 5.1 key integrity, approved)
**Discovered by:** the key and grain framework, on its first run
**Decision:** add `PY_DERIVED` as an explicit governed derived version
**ADR:** [ADR-0027](../adr/0027-a-derived-version-is-still-a-governed-version.md), extending
[ADR-0004](../adr/0004-prior-year-derived-not-stored.md)

---

## 1. What was wrong

`PY_DERIVED` was used as a version code by **12,516 rows** of `mart_financial_ytd` and by every
prior-year comparator in `mart_variance`. It existed in no version master — not `dim_version`,
not `dim_report_scenario` — even though `PY` *was* a first-class scenario in `dim_scenario`,
typed `DERIVED`, with `parent_code = ACT`.

The reasoning that produced it is sound as far as it goes.
[ADR-0004](../adr/0004-prior-year-derived-not-stored.md) says Prior Year is derived from Actual
by a twelve-month offset and stored nowhere, so it cannot drift from the Actual it is a view of.

What followed did not follow. Because the *data* is not stored, the *identity* was never
registered — and those are different questions. `dim_report_scenario` admitted a version only if
rows existed carrying its code, which is a reasonable test for a stored version and the wrong
test for a derived one.

The workaround was already in the code, which is usually the clearest signal:

```sql
CREATE OR REPLACE TABLE ref_default_version AS
SELECT scenario_code, version_code FROM dim_report_scenario WHERE is_default
UNION ALL SELECT 'PY', 'PY_DERIVED'          -- no row to be the default of
```

Two definitions of what a valid version is, one assembled by hand.

---

## 2. The master-data definition

One row in `config/dimensions/scenario_version.csv`, in the existing schema. No invented
columns — the master already had everything needed, including `scenario_type` to carry the
version type and `is_locked` to carry non-editability.

```
version,PY_DERIVED,Prior Year (Derived),PY,,DERIVED,ACTUAL,,,TRUE,TRUE,,,FALSE,45,"..."
```

| attribute | value | why |
|---|---|---|
| `code` | `PY_DERIVED` | the code 12,516 rows already join on |
| `name` | `Prior Year (Derived)` | says what it is, in the list a reader sees |
| `parent_code` | `PY` | the comparison scenario it serves |
| `scenario_type` | `DERIVED` | the version type, and the hook every policy control reads |
| `fx_rate_set` | `ACTUAL` | Prior Year *is* Actual, at actual rates |
| `fiscal_year` | *(none)* | it spans years, like `ACTUAL` |
| `actual_months` / `forecast_months` | *(none)* | not a submission with a split |
| `is_default` | `TRUE` | the one PY version is the PY default |
| `is_locked` | `TRUE` | a derived figure is not editable |
| `is_reserved` | `FALSE` | it is reportable |
| `approved_by` / `approved_date` | *(none)* | approval is inherited from the Actual it derives from |
| `sort_order` | `45` | immediately after the `PY` scenario at 40 |

`dim_scenario` also now exposes `derived_from_scenario_code` — the master's own `parent_code`
on a scenario row, which the loader had been dropping. A derivation must be able to name its
source, or the platform cannot tell *PY comes from Actual* from *PY comes from nowhere*.

### The semantic distinction, preserved

| | |
|---|---|
| `PY` | the comparison / reporting **scenario** |
| `PY_DERIVED` | the governed derived **version** that scenario uses |

`PY_DERIVED` is **not** source-loaded, **not** a forecast submission, **not** a budget version,
**not** independently editable. It is deterministically derived from approved Actual at
*t − 12*. Each of those is proved by a control, not asserted in a comment.

---

## 3. The workaround removed

```sql
CREATE OR REPLACE TABLE ref_default_version AS
SELECT scenario_code, version_code FROM dim_report_scenario WHERE is_default
```

The `UNION ALL` is gone. There is one authoritative source for version membership, and
`P7-VER-05` fails if a default ever appears outside it again. A regression test reads the SQL
(comments stripped) and fails if `UNION` or a hand-written version code returns.

`dim_report_scenario` now also asks the right population question:

```sql
CASE WHEN v.scenario_type = 'DERIVED'
     -- the scenario it derives from has a populated default version
     THEN EXISTS (SELECT 1 FROM dim_version sv
                  JOIN fact_financials f ON f.version_code = sv.version_code
                  WHERE sv.scenario_code = s.derived_from_scenario_code AND sv.is_default)
     ELSE EXISTS (... rows carrying this version's own code ...)
END
```

---

## 4. Scenario / version architecture after the correction

| scenario | type | reserved | default version | version type | locked |
|---|---|---|---|---|---|
| `ACT` | ACTUAL | no | `ACTUAL` | ACTUAL | no |
| `BUD` | BUDGET | no | `BUD_FY26_V1` | BUDGET | yes |
| `FC` | FORECAST | no | `FC_FY26_08` | FORECAST | no |
| `PY` | DERIVED | no | **`PY_DERIVED`** | **DERIVED** | **yes** |
| `DS` | DOWNSIDE | **yes** | — | — | — |

`dim_report_scenario` holds six versions (was five). `ref_default_version` holds the same four
rows it always did — now all four from one authority.

```
ACT ──derives──► PY          PY_DERIVED = ACTUAL at t-12, never stored
```

---

## 5. Before / after unresolved references

| column | before | after |
|---|---|---|
| `mart_financial_ytd.version_code` → `dim_version` | **12,516** | **0** |
| `mart_financial_ytd.version_code` → `dim_report_scenario` | **12,516** | **0** |
| `mart_financial_monthly.version_code` → `dim_version` | 12,516 | **0** |
| `mart_variance.comparator_version` → `dim_version` | 12,516 | **0** |
| `mart_variance.base_version` → `dim_version` | 0 | 0 |
| `ref_default_version.version_code` → `dim_version` | 1 (the hand-written row) | **0** |
| `fact_plan`, `fact_financials`, `fact_trial_balance`, `fact_consol_journal` | 0 | 0 |

Eleven version-bearing columns, all resolving. Zero blank members possible.

---

## 6. Key and grain framework

| family | controls | result |
|---|---|---|
| `P7-REG` | 4 | 4 pass |
| `P7-KEY` | 61 | 61 pass |
| `P7-NUL` | 122 | 122 pass |
| `P7-REF` | 39 | 39 pass |
| `P7-CPX` | 9 | 9 pass |
| `P7-VER` | 14 | 14 pass |
| **total** | **249** | **249 pass, 0 blocking failures, 0 open findings** |

**Zero quarantined version references.** The ADR-0021 acceptance that held P7-D-01 at exactly
12,516 orphans is retired, not relaxed. `P7-REF` grew from 33 to 39 because six version
foreign keys are now declared rather than assumed.

---

## 7. New controls

| control | asserts |
|---|---|
| `P7-VER-01` | every version code in every fact and mart resolves — iterated from the eleven version-bearing columns, so a fact nobody thought about fails rather than being silently out of scope |
| `P7-VER-02` | a version's type is the type its scenario declares, not merely a scenario that exists |
| `P7-VER-03` | a reporting row's scenario matches its version's scenario |
| `P7-VER-04` | each reportable scenario has exactly one default version |
| `P7-VER-05` | no default version exists outside the governed master |
| `P7-VER-06` | Prior Year is a governed derived version — the P7-D-01 condition as membership |
| `P7-VER-07` | a derived version carries no source-loaded rows |
| `P7-VER-08` | a derived version is locked against editing |
| `P7-VER-09` | a derived version names the scenario it derives from, and it exists |
| `P7-VER-10` | Prior Year equals Actual twelve months earlier, to the cent |
| `P7-VER-11` | every Actual month has its prior-year row a year later |
| `P7-VER-12` | no reserved scenario or version is reportable |
| `P7-VER-13` | no reserved version carries reporting data |
| `P7-VER-14` | every reportable version and scenario is named |

`P7-VER-10` and `P7-VER-11` are a pair worth noting. One proves every Prior Year row is the
right Actual; the other proves no Actual month is *missing* its Prior Year. A control iterating
Prior Year can only find rows that are wrong — a row the derivation never built is invisible to
it. That is the Phase 4A lesson about control populations, applied here.

---

## 8. New fixtures

| fixture | breaks | must be caught by | result |
|---|---|---|---|
| `F7-VER-01` | a version code in use removed from the master — **P7-D-01 recreated** | `P7-VER-01` | DETECTED |
| `F7-VER-02` | a derived version filed under the wrong scenario | `P7-VER-02` | DETECTED |
| `F7-VER-03` | two forecast versions both marked as the current default | `P7-VER-04` | DETECTED |
| `F7-VER-04` | a derived version unlocked, so a derived figure becomes editable | `P7-VER-08` | DETECTED |
| `F7-VER-05` | a derived version source-loaded as stored data | `P7-VER-07` | DETECTED |
| `F7-VER-06` | a default version outside the governed master | `P7-VER-05` | DETECTED |
| `F7-VER-07` | a reserved scenario made reportable by being configured | `P7-VER-12` | DETECTED |
| `F7-VER-08` | Prior Year drifting from the Actual it is a view of | `P7-VER-10` | DETECTED |
| `F7-VER-09` | a derived version that does not say what it derives from | `P7-VER-09` | DETECTED |

**18/18 fixtures detected by their intended control** (9 key, 9 version). Each runs inside a
rolled-back transaction.

---

## 9. Monetary invariance

Eighteen grains, full outer joined on the business key, **325,352 rows**, every difference
`0.00`, no row appearing or disappearing:

| comparison | rows | max abs diff |
|---|---|---|
| `journal_by_month_entity_account` | 1,256 | 0.000000 |
| `financials_by_month_entity_account` | 39,492 | 0.000000 |
| `mart_measure_grain` (Actual, Budget, Forecast, PY) | 44,184 | 0.000000 |
| `mart_account_grain` | 133,558 | 0.000000 |
| `mart_variance` (MTD/YTD/FY, $ **and %**) | 50,652 | 0.000000 |
| **`prior_year_measure_grain`** | **12,516** | **0.000000** |
| **`prior_year_comparison`** (ACT_VS_PY, $ and %) | **15,540** | **0.000000** |
| `mart_balance_sheet` | 1,296 | 0.000000 |
| `mart_cash_flow` | 48 | 0.000000 |
| `mart_covenants` | 33 | 0.000000 |
| `mart_working_capital` | 48 | 0.000000 |
| `mart_debt` | 595 | 0.000000 |
| `mart_headcount` | 22,215 | 0.000000 |
| `mart_fx` | 176 | 0.000000 |
| `mart_layer_bridge` | 20 | 0.000000 |
| `capex_by_entity_month_class` | 1,836 | 0.000000 |
| `capex_source_by_entity_month_class` | 1,836 | 0.000000 |
| `fixed_assets_by_entity_class` | 51 | 0.000000 |

**ZERO ECONOMIC DRIFT.** Two comparisons were added for this correction specifically —
Prior Year at measure grain, and the ACT_VS_PY comparison including variance per cent — so
"PY is unchanged" is a measured statement rather than an inference from a total that happens
to include it.

---

## 10. Full regression

| suite | result |
|---|---|
| Phase 2 source controls | **80/80** |
| Phase 2 fault fixtures | **10/10** |
| Phase 3 ingestion controls | **62/62**, 0 source findings |
| Phase 3 fault fixtures | **10/10 as intended** |
| Phase 4 consolidation controls | **72/72**, 0 source findings |
| Phase 4 fault fixtures (incl. XAR) | **23/23 as intended** |
| Phase 5 mart controls | **36/36** |
| Excel reconciliation | **17/17 agree with the marts** |
| Excel layout QA | 0 blocking, 0 warnings; 16 sheets rendered |
| Key, grain and version controls | **249/249**, 0 findings |
| Key and version fixtures | **18/18 detected** |
| `pytest` | **486 passed** |

---

## 11. Workbook

Rebuilt and re-QA'd. Not redesigned.

```
sheets compared        : 42
cells with a value     : 615,270
NUMERIC differences    : 0
text differences       : 4          two build ids, on Cover and Data & Technical
cells added / removed  : 8 / 0      one row on the hidden `_scen` lookup sheet
VERDICT: NO NUMERIC CHANGE
```

The 8 added cells are `PY_DERIVED` arriving on the hidden `_scen` data sheet — the governed
version appearing where it belongs. **No visible sheet changed at all.** The workbook reads
named versions from `dim_report_scenario` (`src/excel/build.py:581`) rather than rendering an
exhaustive list, so no visible table is now incomplete.

---

## 12. Digest changes, and why

| | before | after | |
|---|---|---|---|
| source layer digest | `8013298c…` | `8013298c…` | **unchanged** |
| Phase 3 build id | `6e0c519360d3669b` | `6e0c519360d3669b` | **unchanged** |
| Phase 3 manifest artefacts | — | 2 checksums moved | `dim_scenario.parquet`, `dim_version.parquet` |
| Phase 4 build id | `a99d9fba5694ad7d` | `fcfa135a222f58ba` | moved |
| Phase 5 mart build id | `24b65b7f05f7697d` | `50d85b385b7a2a41` | moved |
| workbook build digest | `0defa626…` | `0a26d398…` | moved |

The chain, precisely:

* **The source layer did not move.** This correction is master data and reporting
  configuration, not generated source, and the generator was not touched.
* **The Phase 3 build id did not move either.** It is a digest of Phase 3's own declared
  inputs — the source digest and the pipeline's configuration — and the scenario master is not
  among them.
* **Two artefact checksums inside the Phase 3 manifest did move**, and they are exactly the two
  that should: `dim_scenario.parquet` gained the `derived_from_scenario_code` column, and
  `dim_version.parquet` gained the `PY_DERIVED` row. Content changed, so the content hash
  changed.
* **The Phase 4 build id moved because it hashes the Phase 3 manifest file**
  (`src/consol/run.py`, `BUILD_INPUTS`), and those two checksums are in it. Phase 5 and the
  workbook then move because each incorporates the manifest above it.

So a change to a published dimension is carried downstream by its content hash rather than by
the build id of the phase that published it. That is the mechanism working as designed, and it
is why the invariance proof — not the digest — is what says whether a number moved.

---

## 13. Determinism

Two full builds of the corrected chain from clean generation produced identical ids
throughout: source `8013298c3fee35ef…`, Phase 3 `6e0c519360d3669b`, Phase 4
`fcfa135a222f58ba`, Phase 5 `50d85b385b7a2a41`, workbook `0a26d3980bd463e5`.

---

## 14. Documentation

New: [ADR-0027](../adr/0027-a-derived-version-is-still-a-governed-version.md), this report.
[ADR-0004](../adr/0004-prior-year-derived-not-stored.md) carries an *extended by* note — its
decision that Prior Year is derived and never stored stands unchanged. Updated: the ADR index,
`data-contract.md` (the version dimension and the derived-version rule), `reporting-marts.md`
(a new scenario and version section), `reporting-controls.md`, `key-and-grain-framework.md`
(six families, 249 controls, 18 fixtures, P7-D-01 closed), `control-framework.md`,
`reproducibility.md`, `roadmap.md`, `README.md`.

One test changed. `test_scenario_and_version_definitions_are_consistent` asserted *no version
may belong to PY*, which encoded the conflation this corrects. It now asserts the stronger
thing: PY has exactly one version, typed `DERIVED`, locked, default and unreserved — and no PY
row is stored anywhere.

---

## 15. Scope discipline

Not done, deliberately:

* Prior Year not removed from the reporting architecture.
* No blank member left for Power BI to absorb.
* No second source dataset materialised to satisfy the dimension — the version row governs
  identity, the amount stays derived from Actual.
* No accounting logic touched.
* Workbook not redesigned.
* Phase 6A **not resumed**. WIP preserved at `ca72922` on `wip/phase-06a-semantic-model`.

---

## 16. The lesson

> **Deriving a figure is not a reason to leave its identity ungoverned.** Where a number comes
> from and whether the thing has a governed identity are separate questions, and answering the
> first does not answer the second.

The framework built for P6-D-01 found P7-D-01 within a day of existing — a different dimension,
a different cause, the same shape: an identifier in use that resolved to nothing, invisible
because every query it appeared in still returned rows.

A workaround in the code, with a comment explaining itself, is usually a defect somebody has
already noticed and routed around.
