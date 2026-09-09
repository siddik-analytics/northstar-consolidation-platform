# ADR-0027 — a derived version is still a governed version

**Status:** accepted, Phase 5.1
**Supersedes:** the implicit handling of Prior Year as a scenario without a version, from
Phase 5 through the baseline `dd46611`
**Related:** [ADR-0004](0004-prior-year-derived-not-stored.md),
[ADR-0021](0021-source-findings-are-baselined-not-downgraded.md),
[ADR-0026](0026-a-declared-key-is-a-contract.md), defect P7-D-01

## Context

The key and grain framework built for [ADR-0026](0026-a-declared-key-is-a-contract.md) found
this on its first run.

`PY_DERIVED` was used as a version code by **12,516 rows** of `mart_financial_ytd` and by every
prior-year comparator in `mart_variance`. It existed in no version master. Not in
`dim_version`, not in `dim_report_scenario` — even though `PY` *was* a first-class scenario in
`dim_scenario`, typed `DERIVED`, with `parent_code = ACT`.

The reasoning that produced it is entirely sound as far as it goes.
[ADR-0004](0004-prior-year-derived-not-stored.md) says prior year is derived from Actual by a
twelve-month offset and stored nowhere, so it cannot drift from the Actual it is a view of. The
mart derives it inline:

```sql
prior AS (
    SELECT basis, 'PY' AS scenario_code, 'PY_DERIVED' AS version_code, ...
           period_key + 100 AS period_key, ...
    FROM actual WHERE scenario_code = 'ACT'
)
```

What followed did not follow. Because the *data* is not stored, the *identity* was never
registered — and those are different questions. `dim_report_scenario` admitted a version only
if rows existed carrying its code, which is a reasonable test for a stored version and the
wrong test for a derived one. So Prior Year was excluded from the dimension that governs what a
report may offer, while remaining the comparator in one of the four approved comparisons.

The workaround was already in the code, which is usually the clearest signal that something is
wrong:

```sql
CREATE OR REPLACE TABLE ref_default_version AS
SELECT scenario_code, version_code FROM dim_report_scenario WHERE is_default
UNION ALL SELECT 'PY', 'PY_DERIVED'          -- because there is no row to be the default of
```

Two definitions of what a valid version is, one of them assembled by hand.

## Decision

**1. `PY_DERIVED` is a governed derived version in the authoritative master.**

One row in `config/dimensions/scenario_version.csv`, in the existing schema, no invented
columns:

| attribute | value |
|---|---|
| `code` | `PY_DERIVED` |
| `name` | `Prior Year (Derived)` |
| `parent_code` | `PY` |
| `scenario_type` | `DERIVED` — the version type, and the policy hook |
| `fx_rate_set` | `ACTUAL` — Prior Year *is* Actual, at actual rates |
| `fiscal_year` | *(none)* — it spans years, like Actual |
| `is_default` | `TRUE` — the one PY version is the PY default |
| `is_locked` | `TRUE` — a derived figure is not editable |
| `is_reserved` | `FALSE` |
| `approved_by` | *(none)* — approval is inherited from the Actual it derives from |

**2. The distinction is preserved, not blurred.** `PY` is the comparison scenario; `PY_DERIVED`
is the governed version that scenario uses. It is not source-loaded, not a submission, not a
budget or forecast version, and not independently editable. It is deterministically derived
from approved Actual at *t − 12*, and `P7-VER-07`, `P7-VER-08` and `P7-VER-10` prove each of
those three things rather than asserting them in a comment.

**3. "Populated" means something different for a derived version.** A stored version is
populated when rows carry its code. A derived version is populated when *the version it derives
from* is. `dim_scenario` now carries `derived_from_scenario_code` — which was already in the
master as `parent_code` and was simply being dropped by the loader — so a derivation can name
its source and `dim_report_scenario` can ask the right question.

**4. One authority for version membership.** The `UNION ALL` is gone.
`ref_default_version` is now `SELECT scenario_code, version_code FROM dim_report_scenario WHERE
is_default` and nothing else. `P7-VER-05` fails if a default ever appears outside the governed
master again.

**The rule, stated generally:**

> **Deriving a figure is not a reason to leave its identity ungoverned.** Where the number comes
> from and whether the thing has a governed identity are separate questions, and answering the
> first does not answer the second.

## Consequences

Fourteen permanent controls (`P7-VER-01` … `P7-VER-14`) covering referential integrity over
every version-bearing column, scenario/version compatibility, default uniqueness, the
derived-version policy, reserved-scenario containment and blank members. Nine fault fixtures
(`F7-VER-01` … `F7-VER-09`), each caught by the control named for it in advance; `F7-VER-01`
recreates P7-D-01 by deleting the version that mart rows still join on.

The framework finishes at **249/249, zero quarantined references**. The ADR-0021 acceptance
that held P7-D-01 at exactly 12,516 orphans is retired rather than relaxed.

**No money moved.** Eighteen grains compared, 325,000 rows, maximum absolute difference `0.00`,
including two comparisons isolating Prior Year specifically: `prior_year_measure_grain` (12,516
rows) and `prior_year_comparison` (15,540 rows), and variance in dollars *and* per cent. The
workbook: 615,270 valued cells, **zero** numeric differences; the only content change is one
row appearing on the hidden `_scen` lookup sheet, which is the governed version arriving where
it belongs.

One test had to change. `test_scenario_and_version_definitions_are_consistent` asserted *no
version may belong to PY*, which encoded the conflation this ADR corrects. It now asserts the
stronger thing: PY has exactly one version, that version is typed `DERIVED`, locked, default
and unreserved — and no PY row is stored anywhere.

## The thing worth remembering

The framework built for one defect found the next one within a day of existing, in a different
dimension, with a different cause and the same shape: an identifier in use that resolved to
nothing, invisible because every query it appeared in still returned rows.

That is what a control family is for. It is also a reminder that a workaround in the code —
here, a hand-written `UNION ALL` with a comment explaining itself — is usually a defect that
somebody has already noticed and routed around.
