# Declared keys and declared grains

    python -m src.integrity.controls    # prove every declared key and grain
    python -m src.integrity.faults      # break each one on purpose and prove it is caught

A key that is never tested is a naming convention with ambitions. `project_id` was named like a
key, joined on like a key and documented as a key, and it identified 1,846 capital projects
with 395 values (defect **P6-D-01**, [ADR-0026](adr/0026-a-declared-key-is-a-contract.md)). It
survived four phases and 250 controls because every join it took part in still returned rows —
just five times too many.

This framework exists so that the question *is this actually unique?* is asked of every key, on
every build, without anyone having to remember.

## How it is built

Two files, and the split between them is the point.

| | |
|---|---|
| `src/integrity/registry.py` | **What is true.** Every declared key, grain and foreign key in the platform, with its authority and its owner. Data, not code. |
| `src/integrity/controls.py` | **One engine that proves all of it.** No object has a bespoke check, because a bespoke check is a check somebody has to remember to write. |

A new table is covered by adding six lines of declaration. Nothing is added to the engine.

## The registry

Each entry declares the columns that must jointly identify a row, whether any of them may be
null and why, the authority for the object's content, and the phase that owns it.

```python
Declared("fact_capex_project", "FACT", ("project_id",), FORBIDDEN,
         "data/reference/capex_projects.csv", "Phase 2",
         note="THE P6-D-01 CONTRACT. project_id alone identifies a capital project...")
```

**61 keyed objects** are declared — 17 dimensions, 20 references, 9 facts and 15 marts — with
**39 foreign keys** between them. Every key was established against the real population rather
than assumed from the column names, and several needed a column the obvious guess omitted,
which is the same class of mistake P6-D-01 was:

| object | the column the obvious key missed | why |
|---|---|---|
| `dim_date` | `accounting_period` | the calendar carries adjustment periods 13–16, which share a `period_key` with the December they adjust |
| `fact_trial_balance` | `special_period_type` | an ordinary December posting and a period-13 adjustment are different rows at the same `period_key` |
| `fact_layer1_usd` | `translation_basis` | the same balance appears translated at the average and at the closing rate |
| `fact_financials` | `process`, `journal_character` | one account in one month is legitimately touched by several processes within a layer, and a year-end close leg has to be distinguishable from an ordinary one |
| `fact_revenue_detail` | `group_account` | one customer-product line can hit both a product and a service revenue account in a month |
| `ref_fx_rate` | `rate_set`, `rate_type` | budget and actual rate sets coexist, as do average and closing |

## Nulls in a key

Four facts legitimately carry a null in a key column. A line with no intercompany counterparty
has no partner; a consolidation entry is posted at entity level and has no cost centre; layer 1
is the translated ledger rather than the output of a process. That is NULL meaning **there is
none**, not NULL meaning **unknown**, and the two are different things. (The Phase 4C policy —
*a no-population additive component contributes zero, never NULL* — governs measures, and says
nothing about attributes.)

The permission is **per column and carries a reason**, because "some key column somewhere may be
null" is not a contract anyone can check. `P7-NUL-<object>` tests only the columns outside the
declared set, and `P7-NUL-<object>-declared` fails a permission with no reason or a reason with
no permission. Uniqueness over such a key is proved with NULL treated as a value, which is the
semantics every join in the platform already relies on.

## The six families

| family | controls | asserts |
|---|---|---|
| `P7-REG` | 4 | the registry is complete, resolves, and its waivers carry reasons |
| `P7-KEY` | 61 | every declared key is unique over its whole population |
| `P7-NUL` | 122 | no null in an unpermitted key column, and every permission is declared |
| `P7-REF` | 39 | every declared foreign key resolves |
| `P7-CPX` | 9 | the capital-project chain, end to end |
| `P7-VER` | 14 | scenario and version governance, including the derived-version policy |

**249 controls, 249 pass, nothing quarantined.**

Control ids carry the object name rather than a sequence number — `P7-KEY-mart_capex`, not
`P7-KEY-12` — so a failure says what broke without a lookup, and inserting a registry entry
does not renumber the suite.

### `P7-REG-01` is the one that matters

It fails when a keyed table exists in the warehouse that the registry does not declare. Without
it, the framework reports green over the objects it happens to know about — which is precisely
the position the platform was already in when the defect was found. A registry that can quietly
fall behind the warehouse is documentation, and documentation does not catch defects.

## The capital-project chain

`P6-D-01`'s real damage was that a fixed asset could not name the project that bought it.
`P7-CPX` proves the chain link by link, on the attributes that have to agree and then on the
money:

```
Capital Project ──► CapEx fact ──► Fixed Asset
```

| control | asserts |
|---|---|
| `P7-CPX-01` | every capital project row carries its own identifier — 1,846 rows, 1,846 ids |
| `P7-CPX-02` | every fixed asset resolves to a capital project |
| `P7-CPX-03` | no identifier resolves to two different project definitions |
| `P7-CPX-04` | an asset agrees with its project on asset class |
| `P7-CPX-05` | an asset agrees with its project on owning entity |
| `P7-CPX-06` | an asset is acquired in its project's period |
| `P7-CPX-07` | asset cost reconciles to project spend, project by project, to `0.00` |
| `P7-CPX-08` | every project created at least one asset |
| `P7-CPX-09` | the corrected key reaches the reporting mart intact |

Uniqueness alone would not have been enough. An identifier can be unique and still describe the
wrong thing, so each link is tested on the attributes that must agree — and then on the money,
because identifier integrity is only worth having if the amounts follow the identifier.

## Fault fixtures

Eighteen, each breaking one thing and naming in advance the control that must catch it. A
fixture caught by *some other* control is reported as a miss: "something went red" is not "the
right thing went red". Each runs inside a transaction that is rolled back.

| fixture | what it breaks | must be caught by |
|---|---|---|
| `F7-KEY-01` | **two capital projects share one identifier — P6-D-01 recreated** | `P7-CPX-01` |
| `F7-KEY-02` | a dimension holds two rows for one member | `P7-KEY-dim_entity` |
| `F7-KEY-03` | a mart duplicates a row at its declared grain | `P7-KEY-mart_capex` |
| `F7-NUL-01` | a declared key column is null | `P7-NUL-fact_capex_project` |
| `F7-REF-01` | a fixed asset references a project that does not exist | `P7-CPX-02` |
| `F7-REG-01` | a keyed table exists that the registry does not declare | `P7-REG-01` |
| `F7-CPX-01` | an asset contradicts its project on asset class | `P7-CPX-04` |
| `F7-CPX-02` | an asset contradicts its project on owning entity | `P7-CPX-05` |
| `F7-CPX-03` | asset cost no longer reconciles to project spend | `P7-CPX-07` |
| `F7-VER-01` | **a version code in use is removed from the master — P7-D-01 recreated** | `P7-VER-01` |
| `F7-VER-02` | a derived version is filed under the wrong scenario | `P7-VER-02` |
| `F7-VER-03` | two forecast versions are both marked as the current default | `P7-VER-04` |
| `F7-VER-04` | a derived version is unlocked, so a derived figure becomes editable | `P7-VER-08` |
| `F7-VER-05` | a derived version is source-loaded as stored data | `P7-VER-07` |
| `F7-VER-06` | a default version exists outside the governed master | `P7-VER-05` |
| `F7-VER-07` | a reserved scenario becomes reportable because it is configured | `P7-VER-12` |
| `F7-VER-08` | Prior Year drifts from the Actual it is a view of | `P7-VER-10` |
| `F7-VER-09` | a derived version does not say what it derives from | `P7-VER-09` |

**18/18 detected by their intended control.**

Two of them are worth keeping for what they recreate. `F7-KEY-01` restores the warehouse
exactly as it stood at the approved Phase 5 baseline `026bf43`; `F7-VER-01` restores it as it
stood at `dd46611`. Every control in the platform passed in both states.

## Scenario and version governance

The framework found its second defect on its first run, in a different dimension with a
different cause and exactly the same shape: an identifier in use that resolved to nothing.

`PY_DERIVED` was used as a version code by 12,516 rows of `mart_financial_ytd` and by every
prior-year comparator in `mart_variance`, and existed in no version master — though `PY` *was* a
first-class scenario. Prior Year is derived from Actual at *t − 12* and stored nowhere
(ADR-0004), so its data has no rows; the mistake was concluding that its **identity** therefore
needed no row either. `ref_default_version` unioned the PY default in by hand, which is the
design already working around the gap.

**Defect P7-D-01, closed under [ADR-0027](adr/0027-a-derived-version-is-still-a-governed-version.md).**
Prior Year now has a governed derived version in the master; the hand-written union is gone;
`ref_default_version` derives from the governed dimension alone. The ADR-0021 acceptance that
held the finding at exactly 12,516 orphans is retired, not relaxed.

> **Deriving a figure is not a reason to leave its identity ungoverned.** Where a number comes
> from and whether the thing has a governed identity are separate questions.

| control | asserts |
|---|---|
| `P7-VER-01` | every version code in every fact and mart resolves — iterated from the eleven version-bearing columns, so a fact nobody thought about fails rather than being out of scope |
| `P7-VER-02` | a version's type is the type its scenario declares, not merely a scenario that exists |
| `P7-VER-03` | a reporting row's scenario matches its version's scenario |
| `P7-VER-04` | each reportable scenario has exactly one default version |
| `P7-VER-05` | no default version exists outside the governed master |
| `P7-VER-06` | Prior Year is a governed derived version — the P7-D-01 condition, as membership |
| `P7-VER-07` | a derived version carries no source-loaded rows |
| `P7-VER-08` | a derived version is locked against editing |
| `P7-VER-09` | a derived version names the scenario it derives from, and it exists |
| `P7-VER-10` | Prior Year equals Actual twelve months earlier, to the cent |
| `P7-VER-11` | every Actual month has its prior-year row a year later — iterated from Actual, because a PY row the derivation failed to build is invisible from PY |
| `P7-VER-12` | no reserved scenario or version is reportable |
| `P7-VER-13` | no reserved version carries reporting data |
| `P7-VER-14` | every reportable version and scenario is named, so no blank member is possible |

Note `P7-VER-10` and `P7-VER-11` together. One proves every Prior Year row is the right Actual;
the other proves no Actual month is missing its Prior Year. A control iterating Prior Year can
only find rows that are wrong — a row the derivation never built is invisible to it. That is
the Phase 4A lesson about control populations, applied here.

## Proving a rebuild changed no money

    python tools/financial_invariance.py --snapshot data/95_invariance/before
    ... rebuild ...
    python tools/financial_invariance.py --snapshot data/95_invariance/after
    python tools/financial_invariance.py --compare data/95_invariance/before data/95_invariance/after

A digest moving is not evidence of drift, and a digest holding is not evidence against it. Both
say something about build ids. What settles the question is a value-level comparison at the
grain the business reads, joined on the business key, with a required difference of exactly
zero — sixteen grains, full outer joined, so a row that appears, disappears or moves grain
fails in its own right rather than hiding inside a matching total.

Identifier columns are deliberately excluded from what is compared. Capex is compared on entity,
month and asset class — the economic grain of a capital project — and never on `project_id`,
since joining on the thing that changed would compare nothing. The row count is carried as a
compared *value*, so a correction that split or merged projects would fail there rather than
pass on totals alone.

`tools/workbook_diff.py` does the same job for the workbook: every cell of every sheet, cached
values, split into numeric differences (which would be drift) and text differences (which are
identifiers and build stamps).
