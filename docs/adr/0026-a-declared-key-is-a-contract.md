# ADR-0026 — a declared key is a contract, not a naming convention

**Status:** accepted, upstream correction discovered during Phase 6A
**Supersedes:** the `project_id` format in `docs/source-data-dictionary.md` as generated from
Phase 2 through the Phase 5 baseline `026bf43`
**Related:** [ADR-0008](0008-revenue-detail-separate-fact.md),
[ADR-0021](0021-source-findings-are-baselined-not-downgraded.md),
[ADR-0022](0022-money-is-decimal-and-artefacts-are-totally-ordered.md), defect P6-D-01

## Context

Building the Power BI semantic model needed a `Capital Project` dimension. A dimension needs a
unique key. `project_id` was not one:

| | rows | distinct `project_id` |
|---|---|---|
| `data/reference/capex_projects.csv` | 1,846 | 395 |
| `fact_capex_project` | 1,846 | 395 |
| `ref_fixed_asset` | 1,846 | 395 |
| `mart_capex` | 1,846 | 395 |

Five different capital programmes in one entity-month shared one identifier:

```
CP-200-202505-01  BUILDING   Buildings and improvements programme       44,908.63
CP-200-202505-01  IT         Computer hardware and software programme   16,840.74
CP-200-202505-01  LEASEHOLD  Leasehold improvements programme           14,969.54
CP-200-202505-01  PLANT      Machinery and equipment programme          86,074.88
CP-200-202505-01  VEHICLE    Vehicles programme                         24,325.51
```

The generator built the identifier from a sequence taken from the inner loop that splits **one
asset class** into parts, while the outer loop walked the asset classes. The sequence restarted
at `-01` for every class.

Nothing caught it. Not the 80 source controls, not the 62 ingestion controls, not the 72
consolidation controls, not the 36 mart controls. `P5-OPS-03` checked `project_id IS NOT NULL`,
which a colliding key passes comfortably. The two grain controls that existed, `P5-GRN-01` and
`P5-GRN-02`, covered `mart_financial_monthly` and `mart_financial_ytd` and nothing else.

The defect was invisible for a specific and uncomfortable reason: **every join still worked.**
`ref_fixed_asset` joined to `fact_capex_project` and returned rows. It just returned five times
too many, and no control compared the row count before the join with the row count after it.

No financial figure was affected. Source spend and fixed-asset cost both totalled
71,937,380.13 before and after; the correction moved nothing.

## Decision

**1. The identifier carries the grain that makes a project distinct.**

```
CP-{entity}-{period}-{asset_class}-{sequence}
```

Deterministic, human-readable, with the asset class explicit and the sequence scoped within
entity, period and class. Asset classes are walked in `ASSET_CLASSES` declaration order rather
than in whatever order a derived dict yields, because the per-entity generator is consumed in
loop order and the sequence of draws — and therefore the economics — is a function of it.

**2. A declared key is a contract, and its uniqueness is proved over its authoritative
population.**

Not asserted in a docstring, not implied by a name ending in `_id`. Proved, by a control, over
every row, every build. `src/integrity/registry.py` states the contract for all 61 keyed
objects in the platform and `src/integrity/controls.py` proves every one of them with a single
generic engine — 229 controls, no bespoke check anywhere, because a bespoke check is a check
somebody has to remember to write and the whole defect is that nobody did.

**3. The registry may not go stale.** `P7-REG-01` fails when a keyed table exists that the
registry does not declare. Without it the framework would report green over the objects it
happens to know about, which is the position the platform was already in.

**4. A key column may be null only where the registry names the column and says why.** Four
facts legitimately carry nulls in a key column — a non-intercompany line has no partner, a
consolidation entry has no cost centre, an ordinary posting has no special period type, layer 1
is not the output of a process. That is NULL meaning *there is none*, not NULL meaning
*unknown*, and the permission is per column with a reason attached, because "some key column
somewhere may be null" is not a contract anyone can check.

## Consequences

The source layer was regenerated and every downstream layer rebuilt. Source digest moves from
`fd7afb8f…` to `8013298c…`, and the Phase 3, 4 and 5 build ids move with it. The identifier
strings change in four artefacts and on one hidden workbook sheet.

**No money moves.** 295,000 rows compared across sixteen grains — the journal, the consolidated
fact, both financial marts, variance, balance sheet, cash flow, covenants, working capital,
debt, headcount, FX, the layer bridge, capex at its economic grain and the fixed-asset register
— maximum absolute difference `0.00`, no row appearing or disappearing on either side. The
workbook: 615,262 valued cells across 42 sheets, **zero** numeric differences.

The framework found a second, unrelated gap on its first run. `PY_DERIVED` is used as a version
code by 12,516 rows of `mart_financial_ytd` and by the prior-year comparator rows of
`mart_variance`, but no such row exists in `dim_version` or `dim_report_scenario`, even though
`PY` is a first-class scenario in `dim_scenario`. It is recorded as open finding **P7-D-01**,
quarantined at its exact population under [ADR-0021](0021-source-findings-are-baselined-not-downgraded.md)
so a new defect of the same shape cannot hide inside it, and reported rather than fixed: the
fix belongs to the Phase 5 scenario architecture, not to an identifier correction.

## The thing worth remembering

A key that is never tested is a naming convention with ambitions. This one survived four
phases, 250 controls and 42 fault fixtures, and was found by a modelling tool asking the only
question nobody had thought to ask: *is this actually unique?*

The framework exists so that question is now asked of every key, on every build, by default.
