# ADR-0005 — Monthly-average FX for P&L, closing-rate balance sheet, computed CTA

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1

## Context

Six of twelve entities have a functional currency other than USD: two CAD, two GBP, two EUR.
Translation choices determine reported revenue, margin and equity, and a mistake here is
invisible in summary review because the output still looks like plausible numbers.

Three questions had to be settled: which rate for the P&L, how CTA arises, and how budget and
forecast are translated.

## Decision

1. **P&L translates at the monthly average rate of the posting month.** Year-to-date figures
   are the sum of translated months, never a year-to-date balance multiplied by a
   year-to-date average rate.
2. **Balance sheet translates at the closing rate** (current rate method). Contributed
   capital and pre-acquisition reserves are frozen at historical rates. Opening retained
   earnings carries forward at its prior closing USD value and is never retranslated.
3. **CTA is a computed residual, independently verified.** Never an input, never a plug.
4. **All rates are quoted as USD per one unit of foreign currency.** Translation is always a
   multiplication.
5. **Three rate sets.** `ACTUAL` for actuals, `BUDGET` locked at budget approval and never
   restated, `FORECAST` frozen at forecast version issue.
6. **Constant currency is stored, not computed at query time**, as a third amount column
   (`amount_usd_cc`) holding actual local amounts translated at budget rates.

## Alternatives considered

**Annual or year-to-date average for the P&L.** Simpler, one rate per year. Produces a
different and wrong answer whenever activity is not evenly spread across the year — which it
never is, given turnaround seasonality and project milestones. It also makes `CTL-FX-03` (sum
of translated months equals the movement in the current-year equity result) impossible to
express. Rejected.

**Retranslate budget at actual rates so the comparison is like-for-like.** Superficially
attractive: it removes FX from every variance automatically. It destroys accountability,
because a manager cannot be held to a target that moved after it was agreed. Rejected in
favour of isolating FX explicitly through the constant-currency view.

**Compute constant currency at query time from the rate table.** Saves a column. Costs a rate
join on essentially every variance visual in the platform, since FX appears in nearly every
management report this group produces. Rejected on performance.

**Use the source systems' own translated amounts.** Aurora supplies a system-translated USD
column and Kestrel supplies a legacy EUR group-currency column. Using either means
translating an already-translated amount — a triangulated rate error that is close to
impossible to find months later. Both columns are ignored (`CTL-FX-06`). Everything is
translated exactly once, from local currency, by the engine.

## Consequences

**Positive.** Translation is correct under the current rate method and reconcilable month by
month. CTA cannot hide a defect, because `CTL-FX-04` compares it to an independent
expectation. Constant currency is a single subtraction. Inverted rates are caught on load by
the quotation-direction band check (`CTL-FX-05`).

**Negative.** Requires a complete monthly rate series for every currency, rate type and rate
set — a missing rate is a blocking failure rather than a silent zero. Requires an
entity-and-event-keyed historical rate table for equity, which is more infrastructure than
retranslating everything at closing rates would need.

**Note on the swap.** The $100m interest rate swap is not designated for hedge accounting, so
its fair value movement goes through the P&L (`730700`) rather than OCI. This keeps the equity
roll-forward to a single OCI component (CTA), which materially simplifies both the model and
its controls. Recorded as a scope simplification in `docs/open-questions.md`.
