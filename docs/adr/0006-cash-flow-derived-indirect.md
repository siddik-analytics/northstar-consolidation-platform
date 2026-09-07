# ADR-0006 — Cash flow statement derived from balance sheet movements

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1

## Context

The brief requires a cash flow statement that reconciles to the balance sheet. There are two
ways to produce one: derive it from balance sheet movements (indirect), or build it from cash
book transactions (direct).

## Decision

**Indirect method, derived arithmetically** from the period movement in each balance sheet
account plus net income. Every balance sheet account carries a `cash_flow_category`
attribute; the statement is the aggregation of movements by that category, adjusted for
non-cash movements. The output is materialised as `fact_cash_flow`.

## Alternatives considered

**Direct method from cash book transactions.** Arguably more informative, since it shows
actual receipts and payments. It requires bank-level transaction data classified by nature
across three ERPs, which does not exist in a consistent form, and it still needs an indirect
reconciliation appended to satisfy most reporting frameworks. Rejected on data availability
and on effort-to-value.

**Hand-built cash flow in the Excel pack.** How it is done today. It breaks the moment the
balance sheet changes and it is not reproducible. Rejected — it is one of the problems the
engagement exists to remove.

## Consequences

**Positive.** The statement ties to balance sheet cash **by construction**, because it is an
algebraic rearrangement of the balance sheet:

```
Δcash = Δliabilities + Δequity − Δ(non-cash assets)
```

It is reproducible, needs no new source data, and can be produced at entity as well as group
level.

**Negative.** That property only holds if every balance sheet movement is categorised into
exactly one cash flow line. `CTL-FS-04` enforces that every balance sheet account has a
non-null category, and `CTL-FS-03` asserts the reconciliation regardless. Presentation quality
depends on the granularity of `cash_flow_category` — too coarse and the statement is
unhelpful, too fine and it is unreadable.

**Three movements need explicit handling**, and each is a known failure point:

| Movement | Treatment | If handled wrongly |
|---|---|---|
| FX on foreign-currency cash | "Effect of exchange rate changes on cash" | The statement does not tie |
| FX on foreign-currency working capital | Non-cash reconciling item within operating activities | Appears as a fictitious working capital swing |
| Working capital acquired in a business combination | Excluded from the operating movement; the whole consideration sits in investing | A $6.6m acquisition of working capital shows as a $6.6m operating outflow that never happened |

All three were implemented and asserted in the Phase 1 anchor model — and the first two were
found there, not anticipated. See `docs/phases/phase-01-report.md` §4.
