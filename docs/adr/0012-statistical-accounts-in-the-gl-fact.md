# ADR-0012 — Statistical accounts in the GL fact, outside the trial balance

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1

## Context

Management reporting needs non-financial measures alongside financial ones: headcount,
billable hours, available hours, units shipped, bookings, backlog, occupied square footage.
Revenue per FTE, utilisation and EBITDA per head are standard board metrics, and each one
requires a financial and a non-financial measure to share entity, cost centre, period and
scenario context.

## Decision

Non-financial measures are held as **statistical accounts in the `9xxxxx` block of the group
chart**, stored in `fact_financials` alongside financial data, with:

- `is_statistical = TRUE`
- `include_in_tb_balance = FALSE`
- `fx_method = 'NONE'`
- the value in the `quantity` column; `amount_usd` is null

They are **excluded from every debits-equals-credits test** (`CTL-TB-04`) and are never
translated (`FX-P08`).

## Alternatives considered

**Separate fact tables for each non-financial measure.** Architecturally tidier — headcount is
genuinely not a general ledger balance. It requires a separate conformed-dimension join for
every cross-measure calculation and multiplies the number of facts a report author must
understand. Rejected for the general case, but *not* universally: `fact_headcount` and
`fact_capex` exist as detailed facts because they carry movement structure (hires, leavers,
transfers; additions, disposals, depreciation) that does not fit a single account balance. The
statistical accounts hold the **summary** measures, and `CTL-REC-03` and `CTL-REC-04` reconcile
the two.

**Keep them only in the detailed facts and never in the GL fact.** Means every per-FTE or
per-hour metric crosses two facts. Workable in DAX but slower, and it makes a simple
statistical measure unavailable at the same drill path as the financials. Rejected.

**Include them in the trial balance with an offsetting entry.** Some ERPs do this. It makes
headcount a "balance" that must be balanced by something meaningless. Rejected as accounting
theatre.

## Consequences

**Positive.** Revenue per FTE is a ratio of two measures in one fact with identical
dimensionality — no cross-fact join, no relationship ambiguity. Non-financial measures inherit
scenario and version handling for free, so budgeted headcount and forecast headcount work
exactly like budgeted revenue.

**Negative.** Every balancing control must filter on `include_in_tb_balance`. This is easy to
forget when writing a new control, so it is asserted structurally:
`tests/test_config_integrity.py::test_statistical_accounts_are_excluded_from_the_trial_balance`
verifies that no statistical account is ever marked for trial balance inclusion, and no
financial account is ever excluded.

**Why this matters more than it looks.** If statistical accounts were included in the trial
balance test, `CTL-TB-01` — the most fundamental control in the platform — would fail every
single month. A control that always fails is a control that people learn to ignore, and once
they ignore it, it protects nothing.
