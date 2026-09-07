# ADR-0013 — Adjusted EBITDA definition and add-back policy

**Status:** Accepted · **Date:** 2026-09-06 · **Amended:** 2026-09-07 (Phase 1.1) · **Phase:** 1

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

## Amendment, Phase 1.1 — owner decisions applied

The three previously open points (OQ-01) are settled, and the synthetic credit agreement has
been written down so that the add-back policy rests on a document rather than an assumption.
See [`config/debt/credit_agreement_terms.csv`](../../config/debt/credit_agreement_terms.csv).

| Question | Decision | Clause |
|---|---|---|
| Run-rate synergy add-backs | **Not permitted.** Negotiated out at closing; only costs actually incurred may be added back. | `CA-028` (S1.1 vii) |
| Sponsor monitoring fee | **Permitted, capped at $1.5m per annum.** The actual charge is $1.0–1.2m, inside the cap in every modelled period. Any excess would not be addable. | `CA-026`, `CA-027` (S1.1 iv, S6.9) |
| Share-based compensation | **Not added back.** Not permitted by the agreement, and correspondingly excluded from the group's own definition so that the two measures agree. | `CA-029` |

This matters beyond bookkeeping: it means **Covenant EBITDA equals Adjusted EBITDA by
construction** under the current agreement. Every add-back the group makes is permitted, and
every add-back the agreement disallows is one the group does not make. The two are still
**computed separately**, so that a later change to either definition surfaces as a difference
rather than being absorbed silently.

The composition is now anchored account by account
([`config/anchors/anchor_addback_composition.csv`](../../config/anchors/anchor_addback_composition.csv))
and asserted to equal the total non-recurring charge in every period. An add-back that cannot
be attributed to an account fails the build, and a sponsor fee above the cap fails the build.

| USD m | FY2023A | FY2024A | FY2025A | FY2026B | FY2026F |
|---|---|---|---|---|---|
| `680100` Restructuring — severance | 1.80 | 1.40 | 1.50 | 0.50 | 2.00 |
| `680200` Restructuring — facility exit | 0.90 | 0.40 | 0.50 | 0.20 | 0.80 |
| `680300` Acquisition and transaction costs | 2.60 | 1.90 | 0.40 | — | — |
| `680400` Integration and ERP programme costs | 3.00 | 3.10 | 2.60 | 1.60 | 1.60 |
| `680600` Legal settlements and claims | 0.30 | 0.20 | 0.30 | — | 0.20 |
| `680700` Transaction and retention bonuses | 0.20 | 0.10 | — | — | — |
| `630400` Sponsor monitoring fee (cap $1.5m) | 1.00 | 1.10 | 1.20 | 1.20 | 1.20 |
| **Total add-backs** | **9.80** | **8.20** | **6.50** | **3.50** | **5.80** |

OQ-01 is closed.
