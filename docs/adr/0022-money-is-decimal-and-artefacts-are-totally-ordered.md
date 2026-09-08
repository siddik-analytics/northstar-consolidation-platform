# ADR-0022: Money is DECIMAL, and every committed artefact is written in a total order

- **Status:** Accepted
- **Date:** 2026-09-07
- **Phase:** 3
- **Related:** ADR-0001 (DuckDB), ADR-0011 (anchor-first deterministic modelling),
  ADR-0019 (ingestion layers)

## Context

Phase 3 claimed a deterministic build. The claim was tested by comparing row counts, which
is not the same thing, and when two consecutive runs over the identical frozen source layer
were finally compared byte for byte, three artefacts differed.

Two independent causes, and only one of them is a build problem.

**Row order.** Several artefacts were written with `COPY table TO 'file.parquet'` and no
`ORDER BY`. DuckDB scans in parallel and emits rows in whatever order the threads produce
them, so identical data serialises to different bytes. Two aggregates compounded it:
`list(erp_system)` collected values in scan order, and `any_value()` picked an example row
arbitrarily, so an exception file could name a different example line on every run.

**Floating-point addition.** `signed_local_amount` was a `DOUBLE`. Floating-point addition
is not associative: `(a + b) + c` and `a + (b + c)` can differ in the last bit. A parallel
`SUM` combines its partial results in whatever order the threads finish in, so the same
ledger can total to a different value from one run to the next. The differences are tiny —
and a reconciliation quoted to six decimal places is quite capable of printing them.

The second is the more serious finding, because it is not really about reproducibility. A
general ledger is a set of exact amounts in the smallest unit of its currency. Representing
one as a binary float means `0.10 + 0.20 ≠ 0.30`, and every total carries an error that
grows with the number of rows. It happens to be small here. It is still the wrong type.

## Decision

**Money is `DECIMAL(18,2)`, from the standardised layer onward.** The cast is applied where
the canonical debit-positive sign is applied — the point at which an amount stops being one
ERP's opinion and becomes the platform's — so every later layer inherits it. DuckDB's decimal
sum is exact integer arithmetic and independent of the order the rows arrive in.

This is lossless here and must be verified to stay so: every source amount is exact to the
cent, asserted by test across all 1,080,782 lines. `DECIMAL(18,2)` holds up to 10^16 currency
units, which is nine orders of magnitude above the largest posting in the group.

The parsed layer keeps `DOUBLE`, because it holds what the file said, before the platform
has committed to anything.

**Where a rate must be applied, the product is rounded to the cent and held as `DECIMAL`
before it is summed** — through a single named `usd()` macro, so no view can quietly
translate on a different rule. Phase 4's translation engine inherits the same requirement.

**Every committed artefact is written in a total order.** The journal-line fact orders by its
lineage (`erp_system, source_file, source_row_ordinal`); everything else is small enough to
order by all of its columns. `list()` aggregates are sorted; example columns use `min()`,
never `any_value()`. A static test asserts that no `COPY ... TO` in the pipeline lacks an
`ORDER BY`.

**Reproducibility is measured, not claimed.** The evidence is byte-level: two consecutive
full runs must produce identical checksums for every artefact in the manifest. A test that
compares row counts does not test this.

## Consequences

No reported figure changed. The group income statement, entity external revenue and all
twelve business-unit gross margins still reconcile to the Phase 2 targets at exactly
0.000000, because the drift was always in the last bit of a double.

Aggregation is marginally slower and the ordering adds a sort to artefacts of at most a few
tens of thousands of rows. Neither is measurable against the parse and mapping stages.

Later phases inherit the constraint. An elimination, a translation or an NCI allocation that
introduces a `DOUBLE` money column reintroduces both problems at once, and the type test in
`tests/test_phase03_pipeline.py` is written against the conformed facts so it will catch a
regression there.

Division still yields a float — a margin percentage, a ratio, an amount in millions. That is
correct: those are measures, not money. What must be exact is the sum of the ledger, and the
division happens once, after it.

## Alternatives rejected

**Round the outputs to fewer decimal places and call it deterministic.** Hides the defect
instead of fixing it, and picks the tolerance to fit the error rather than the business.

**Force single-threaded aggregation.** Would make the double sums repeatable without making
them correct, and would give up DuckDB's main advantage.

**Integer cents.** Exact and fast, but every query would have to remember the scale, and a
forgotten division by 100 is a silent hundredfold error — the same class of defect as the
malformed-amount fault this phase had to add a control for. `DECIMAL` carries its own scale.
