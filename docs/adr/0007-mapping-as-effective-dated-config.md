# ADR-0007 — Chart-of-accounts mapping as effective-dated configuration

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1

## Context

391 source accounts across three ERPs map into 181 group accounts. The mapping is not
uniformly one-to-one: some are many-to-one, and several are one-to-many resolved by a second
attribute — most importantly the payroll accounts, where the department decides whether a cost
sits above or below gross margin.

Mappings also change over time. Accounts are added, businesses are acquired, and the group
chart evolves.

## Decision

Mappings are **data**: effective-dated rows in `config/coa/source_coa_*.csv`, loaded into
`dim_source_account`.

```
erp_system + source_account + effective_from  →  group_account + mapping_type + mapping_rule
```

Four mapping types: `DIRECT` (1:1), `MERGE` (n:1), `SPLIT` (1:n resolved by another line
attribute), `DERIVED` (needs a transformation such as a sign reversal).

Mappings are **never edited retrospectively**. A change creates a new effective-dated row.

## Alternatives considered

**Hard-coded `CASE` expressions in the transformation SQL.** Fast to write for the first fifty
accounts. Becomes unreviewable at 391, cannot be diffed meaningfully, cannot be
effective-dated, and requires a developer for a change that a controller should own. Rejected.

**A mapping table in the database, edited directly.** Removes the developer from the loop but
loses version control, review, and the ability to reproduce a closed period exactly. Rejected —
the file-based approach gives change history and pull-request review for free.

**Overwrite mappings in place when they change.** Simplest. Silently restates closed periods:
re-running FY2024 after a mapping change produces different numbers with no record of why.
Rejected; `CTL-MAP-07` blocks it.

## Consequences

**Positive.** Mapping changes are pull requests with a diff and a reviewer. A closed period
always re-computes to the same answer. `tests/test_config_integrity.py` validates every mapping
in CI — a mapping to a non-existent or statistical group account cannot be merged. The mapping
file doubles as documentation of *why* each mapping exists, in its `notes` column.

**Negative.** Conditional splits need a rule evaluator in the transformation layer rather than
a simple join. The `mapping_rule` grammar is deliberately narrow — equality and set membership
over a fixed set of line attributes — because a general expression language in configuration
becomes code that nobody tests.

**Critical constraint.** A `SPLIT` that fails to resolve must **fail**, not default.
`CTL-MAP-04` blocks the load. Defaulting an unresolved payroll line to SG&A would move cost
across the gross margin line silently, and every balancing control would still pass.

**Never default an unmapped account into "other expenses".** Unmapped accounts go to suspense
and block the close (`CTL-MAP-01`). A plausible-looking wrong number is worse than a failure,
because a failure gets fixed.
