# ADR-0004 — Prior Year derived by date offset, not stored as a scenario

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1

## Context

The brief lists four scenarios: Actual, Budget, Forecast and Prior Year. The first three are
distinct sets of data. Prior Year is not — it is last year's Actual, viewed alongside this
year's.

## Decision

**Prior Year is derived**, by a twelve-month date offset over the Actual scenario, and
implemented as an item in the Power BI `Scenario Comparison` calculation group. It is present
in `dim_scenario` as `PY` with `scenario_type = 'DERIVED'` so that it appears to users as a
first-class scenario, but **no rows are stored against it**.

`dim_date.prior_year_date_key` is materialised to make the offset a join rather than a
calculation.

## Alternatives considered

**Store Prior Year as its own scenario.** Simple to query and the naive reading of the brief.
It duplicates every actual row, doubling the largest partition of the fact table for no new
information. Worse, it creates a **restatement hazard**: correct a prior period and the stored
prior-year copy silently diverges from the actual it is supposed to represent. Two versions of
the same truth, one of which is stale, is exactly the problem this engagement exists to
eliminate. Rejected.

**Handle it purely in DAX with `SAMEPERIODLASTYEAR`, with no scenario member.** Technically
sufficient, but users expect to see Prior Year in a scenario selector next to Budget and
Forecast. Presenting it as a scenario member while deriving the data gives both.

## Consequences

**Positive.** No duplication. A prior-period correction propagates automatically to every
prior-year comparison. Storage and refresh cost unchanged.

**Negative.** Requires the Actual scenario to hold a full extra year of history to support
prior-year comparison at the start of the series — hence actuals from January 2023, giving
FY2024 onwards a complete comparative.

**Verification.** `CTL-SCN-05` asserts that the derived prior year equals the Actual scenario
for the corresponding prior-year period, proving the two approaches are equivalent.
