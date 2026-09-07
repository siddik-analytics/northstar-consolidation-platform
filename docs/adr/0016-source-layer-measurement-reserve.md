# ADR-0016: The source-layer difference is a disclosed equity reserve, never a plug in a real balance

- **Status:** Accepted
- **Date:** 2026-09-07
- **Phase:** 2.1
- **Supersedes:** the investment-at-cost calibration described in Phase 2.0
- **Related:** ADR-0011 (anchor-first deterministic modelling), ADR-0005 (FX translation
  method), ADR-0004 (prior year derived, not stored), CTL-FX-04

## Context

Phase 2 generates entity as-reported ledgers only (layer 1). Two design commitments meet
head-on in the balance sheet:

1. every balance sheet caption is pinned to an approved anchor, pushed down to entities by
   economic driver; and
2. retained earnings rolls forward from each entity's own locally-measured net income.

Together these over-determine the balance sheet. The anchor model accumulates group results
at the rates ruling when they were earned and carries the group's own cumulative translation
adjustment; the entity ledgers accumulate locally-measured results and are translated at
closing rates. A difference therefore remains, and with every other caption pinned it falls
wherever the model lets it fall.

Phase 2.0 let it fall into **investment in subsidiaries**, calibrating the level so layer-1
cash reproduced the anchor. The Phase 2 review rejected this, correctly: an investment balance
that absorbs a residual cannot be explained from consideration paid, ownership percentages or
acquisition dates, and it is precisely the balance Phase 4 must eliminate against subsidiary
equity to derive goodwill. A plug there corrupts the one calculation it feeds.

The obvious alternative — let it fall into **cash** — is worse. Cash is the one group balance
that is externally verifiable, it is the balance a reviewer checks first, and a shortfall
there causes second-order damage: the generated revolver draws against a liquidity gap that
does not exist, distorting the monthly facility path as well.

## Decision

The difference is posted to a dedicated, named equity account:

**`329100 Group reporting measurement reserve`** — a holding-company equity reserve, struck at
each year end when the anchor is measured, carried at Topco (which is USD-functional, so the
reserve is not itself retranslated), and mapped from Aurora source account `3250`.

Three obligations attach to it:

1. **It is disclosed, not hidden.** `data/reference/translation_difference.csv` reports it
   year by year alongside the CTA the generated ledgers independently imply, using the standard
   formula (opening net assets × change in closing rate, plus result × the difference between
   closing and average rate), decomposed into its net-assets and result components.
2. **It is bounded.** Control `P2-RES-01` fails the build if it exceeds 2% of layer-1 total
   assets. It currently stands at 0.56%, 0.11% and 1.03%.
3. **It never reaches the consolidated result.** Phase 4 removes the reserve and replaces it
   with a CTA computed from the entity ledgers. It must never be treated as a consolidation
   input, and CTL-FX-04's prohibition on entering CTA as a plug is unaffected — that control
   governs the consolidation engine, and this is a source-layer reserve the engine discards.

Cash consequently ties to the anchored balance **exactly** in every year (`P2-RES-02`), and
investment balances tie to the investment register **exactly** in every month (`P2-INV-01`).

## Why not close the difference instead

It cannot be closed by source construction, and it was worth establishing that before
accepting a reserve.

A subsidiary's opening equity is constructed as the residual of its own opening balance sheet,
so raising a parent's contributed capital raises the subsidiary's investment and its equity by
the same amount and the two cancel at group level. Capital contributions between group members
are similarly self-cancelling. Nothing internal to the group moves the residual.

What would close it is re-deriving the anchor's cumulative translation adjustment from the
generated entity ledgers. That changes an approved anchor. The Phase 2.1 instruction is
explicit — *"do not change consolidated anchor results merely to eliminate a small
calibration"* — and the anchored CTA is an input to the anchor model's own equity roll-forward,
so re-deriving it would ripple through approved figures. The reserve is the honest alternative:
it leaves every approved number untouched and makes the residual visible instead of absorbing
it somewhere it would be mistaken for a real balance.

## Consequences

**Good.** Cash and investments are both exactly explainable. The residual is a single named
line, quantified in a committed reference dataset and bounded by an automated control, rather
than a distortion spread across a real caption. Phase 4 receives a clean signal about exactly
how much translation difference it must resolve.

**Costs.** Layer-1 equity carries an account that has no counterpart in a real ERP chart, and
Phase 3 mapping and Phase 4 consolidation must both handle it explicitly rather than by
default. `329100` is in the group chart and the Aurora source chart precisely so that
requirement is discoverable rather than tribal knowledge.

**Watch for.** If the reserve grows toward the 2% cap in later phases, that is a signal the
anchor model's CTA assumption and the generated currency mix have drifted apart, and the right
response is to re-examine the anchor rather than to raise the cap.
