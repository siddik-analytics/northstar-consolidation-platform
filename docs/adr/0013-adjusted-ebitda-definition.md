# ADR-0013 — Adjusted EBITDA definition and add-back policy

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1 · **Requires owner confirmation**

## Context

Adjusted EBITDA is the most consequential number in a private-equity-backed group. It drives
the covenant calculation, the sponsor's value-creation tracking and, ultimately, the exit
valuation. It is also the number most vulnerable to definitional drift: it is not a defined
term under any accounting framework, so whoever writes the formula decides what it means.

The classic failure is that the Excel pack, the semantic model and the board deck each carry a
slightly different version, nobody notices for two quarters, and then a lender asks a question.

## Decision

**Two definitions, both computed from the account hierarchy, neither hand-assembled.**

```
EBITDA          = Revenue − Cost of Sales − Operating Expenses
                  (accounts flagged is_ebitda = TRUE)

Adjusted EBITDA = EBITDA + Σ(accounts flagged is_ebitda_addback = TRUE)
```

**Reported EBITDA includes non-recurring operating costs.** Restructuring, transaction costs
and the ERP programme are real operating costs and belong above EBITDA in the reported
statements.

**Add-backs are an account-level attribute**, not a formula. The list is therefore visible,
reviewable and diffable in `config/coa/group_coa.csv`. Current add-back accounts:

| Account | Name |
|---|---|
| `630400` | Sponsor monitoring fee |
| `680100` | Restructuring — severance |
| `680200` | Restructuring — facility exit |
| `680300` | Acquisition and transaction costs |
| `680400` | Integration and ERP programme costs |
| `680600` | Legal settlements and claims |
| `680700` | Transaction and retention bonuses |

**No run-rate synergy add-backs.** Only costs actually incurred are added back.

## Alternatives considered

**One EBITDA definition, excluding non-recurring items from the start.** Simpler, but it means
the reported statements never show what the year actually cost. FY2023 carried $9.8m of
one-time spend; a reader is entitled to see it. Rejected.

**Add-backs as a hard-coded measure list in DAX.** How it is usually done. Invisible to
finance, un-diffable, and certain to diverge between the Excel pack and Power BI. Rejected —
this is exactly the drift the decision exists to prevent, and `CTL-FS-07` now asserts that both
definitions agree wherever they are computed.

**Add-backs by adjustment posting rather than by account flag.** More flexible, allowing
partial add-backs of a mixed account. It also makes Adjusted EBITDA depend on someone
remembering to post an adjustment each month. Rejected in favour of the account flag, which is
structural. Genuinely judgemental partial add-backs remain possible through the management
adjustment layer, where they are individually approved and visible.

**Include run-rate synergy add-backs** (the full-year effect of actions taken, unrealised cost
savings). Common in sponsor reporting and in credit agreement definitions of "Consolidated
EBITDA". They are estimates, they are contentious, and quantifying them is a judgement the
owner should make rather than one an architect should assume. **Excluded, and flagged.**

## Consequences

**Positive.** One definition, computed once from data, used by every consumer. Adding or
removing an add-back is a reviewed configuration change with a diff and a date. The add-back
list is visible on the EBITDA bridge page rather than hidden in a formula.

**Negative.** Account-level flagging cannot express "add back 60% of this account". Such cases
must go through the management adjustment layer, which is more effort — deliberately, since a
partial add-back is a judgement that should be individually approved.

**Requires owner confirmation.** Three points need a decision from the CFO before Phase 4:

1. Whether the credit agreement's "Consolidated EBITDA" permits run-rate synergy add-backs,
   and if so how they are quantified and evidenced.
2. Whether the sponsor monitoring fee (`630400`) is an add-back for covenant purposes as well
   as for management reporting. It is treated as an add-back here.
3. Whether share-based compensation should be added back. It is **not** added back in the
   current definition; many sponsors do add it back.

Recorded as open question OQ-01 in `docs/open-questions.md`.
