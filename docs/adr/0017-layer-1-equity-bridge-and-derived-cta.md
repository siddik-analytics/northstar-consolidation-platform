# ADR-0017: The layer-1 equity bridge, and a CTA derived from source balances

- **Status:** Accepted
- **Date:** 2026-09-07
- **Phase:** 2.2
- **Supersedes:** [ADR-0016](0016-source-layer-measurement-reserve.md) (the source-layer
  measurement reserve), and the provisional CTA target set in Phase 1
- **Related:** ADR-0005 (FX translation method), ADR-0011 (anchor-first deterministic
  modelling), ADR-0003 (consolidation layers), CTL-FX-04, FX-P03

## Context

Phase 2 generates layer 1 only: what each legal entity's own ledger says, in its own
functional currency. `src/generation/targets.py` derives, from the approved consolidated
anchors, what the sum of those ledgers must be — the intercompany gross-up on revenue,
receivables and payables, and the exclusion of goodwill, acquired intangibles, their
deferred tax and unrealised intercompany profit, which exist only on consolidation.

That bridge covered every asset, every liability and every income statement line. It did not
cover **equity**. A balance sheet with a target for everything except equity is a balance
sheet with one free variable, and a generator will close a free variable with whatever is
left over. Phase 2.0 left it in investment-at-cost. Phase 2.1 named it
`329100 Group reporting measurement reserve`, capped it at 2% of layer-1 assets and disclosed
it. It stood at \$4.24m, \$0.92m and \$8.93m.

At the same time the source ledgers could not generate a translation adjustment. Contributed
capital was carried at a closing-rate USD target, recomputed every year, so a subsidiary's
share capital in its own currency moved whenever the spot rate moved. Under the closing-rate
method the CTA is precisely the difference between net assets translated at closing rates and
capital at historical rates plus results at the rates when earned. Freeze nothing at a
historical rate and there is nothing for the CTA to be.

Phase 1.1 had already recorded that the CTA remained *a target rather than a proof* until a
translation engine existed. Phase 2 produced the entity ledgers that let the target be
tested. It failed.

## Decision

**1. Derive the layer-1 equity target.**

```
layer-1 equity = consolidated total equity
               + investment in subsidiaries, at cost
               - goodwill
               - acquired intangibles, net
               + deferred tax on the purchase price allocation
               + unrealised intercompany profit in inventory
```

Consolidation replaces each subsidiary's equity with the parent's investment in it,
recognises the goodwill and intangibles that investment bought, provides deferred tax on
those intangibles, and eliminates the profit sitting in intercompany stock. Reverse those
four and the consolidated equity becomes the layer-1 equity. The identity holds **exactly at
the 31 December 2022 opening balance sheet**, before any generated period — which is what
established that it is the right bridge and not a fitted one.

It is published as a row of `config/anchors/phase02_source_layer_targets.csv` alongside every
other bridge line.

**2. Hold contributed capital at historical rates, and give every equity movement a date.**

Share capital and paid-in capital are fixed amounts in the entity's own currency, struck at
the rate ruling when they were contributed (FX-P03), and they move only when capital is
actually contributed or distributed. `src/generation/ledger.py::EQUITY_EVENTS` is the
register:

| Event | Entity | Date | Amount |
|---|---|---|---|
| Sponsor equity contribution funding the Halden Valve acquisition (INV-010) | NIG-100 | 2023-04-01 | \$20.0m |
| Distribution to the non-controlling shareholder of Northstar Parts UK | NIG-510 | 2024-06-30 | \$0.15m |
| Distribution to the non-controlling shareholder | NIG-510 | 2025-06-30 | \$0.20m |
| Distribution to the non-controlling shareholder | NIG-510 | 2026-06-30 | \$0.25m |

Two consequences follow that are corrections in their own right. Phase 2.1 spread the sponsor
contribution evenly across twelve months, so the equity that funded an April acquisition
arrived a twelfth at a time and the revolver covered the gap. And share-based compensation,
which is equity-settled, now credits `315100` instead of leaving the group as cash.

**3. Compute the CTA from the source ledgers and let the anchor follow.**

For every foreign entity and month:

```
CTA movement = opening net assets  x (closing rate - prior closing rate)
             + result for the period x (closing rate - average rate)
             + equity movements      x (closing rate - transaction rate)
```

Every term is a balance in the entity's own ledger or a rate in the approved rate file.
Nothing references a group target. Published as `data/reference/cta_expectation.csv`, one row
per entity and period — the expected result the Phase 5 translation engine (FX_CTA) will be
tested against, not a number it will be given.

The consolidated anchor is then derived from it:

```
CTA(group) = CTA(layer 1)
           + FX on goodwill + FX on acquired intangibles   (layer-3 balances)
           - the non-controlling interest's share
           - the movement in unrealised intercompany profit
```

Only the two layer-3 FX terms remain estimates, because goodwill and acquired intangibles
exist in no source ledger. Everything else is computed. `tools/derive_anchor_inputs.py`
regenerates the constants in `src/anchors/build_anchors.py` and iterates to a fixed point;
`--check` fails the build if they go stale.

**4. Therefore: no reserve.** With the equity target derived and the capital frozen at
historical rates, layer-1 cash lands on the approved anchor to the cent with nothing added to
the ledger. `329100` and `AURORA 3250` are removed from the charts, from the mapping manifest
and from the generator.

## The anchor revision this forced

The provisional CTA target could not survive contact with the ledgers. Superseded:

| CTA movement attributable to the group | FY2023 | FY2024 | FY2025 |
|---|---|---|---|
| Phase 1 provisional target | 3.500 | (5.300) | 8.800 |
| **Phase 2.2 derived** | **2.607** | **(4.666)** | **7.743** |
| Change | (0.893) | 0.634 | (1.057) |

| Closing CTA balance | FY2023 | FY2024 | FY2025 |
|---|---|---|---|
| Phase 1 | 0.000 | (5.300) | 3.500 |
| **Phase 2.2** | **(0.893)** | **(5.559)** | **2.184** |

The minority's share of the translation movement is derived on the same basis — 20% of the
adjustment arising in NIG-510 — and moves from 0.100 / (0.050) / 0.180 to 0.071 / (0.019) /
0.059.

Total equity falls by \$0.89m, \$1.02m and \$3.20m. **Cash is fixed by treasury policy at the
year end, so the balance sheet rebalances through the revolving facility**, which is the only
uncommitted line left in the anchor's closing identity. Revenue, EBITDA, Adjusted EBITDA,
EBIT, total assets, term debt and every working-capital caption are unchanged. The full
quantification, including the interaction with ADR-0018, is in
`docs/phases/phase-02-2-report.md`.

## Alternatives considered

**Keep the reserve, disclosed and capped (ADR-0016).** Rejected on the reviewer's ground and
on a stronger one: it is not merely inelegant, it is *unnecessary*. Once the bridge derives
equity, the residual it disclosed does not exist.

**Let the difference fall into cash.** Rejected. Cash is the one group balance an auditor
confirms with a third party. A shortfall there would also make the generated revolver draw
against a funding need that never arose.

**Keep the CTA target and adjust working-capital anchors so the layer-1 equity agrees.**
Rejected. It reverses the direction of proof — moving receivables and inventory to preserve
an FX estimate — and the reviewer excluded it explicitly.

**Solve it by raising subsidiary contributed capital.** Does not work, and the arithmetic is
worth recording: a subsidiary's opening equity is the residual of its own opening balance
sheet, so raising its share capital lowers its opening retained earnings by the same amount.
Layer-1 equity is unchanged.

## Consequences

- Layer-1 cash ties to the approved anchor with no reserve (`P2-EQ-04`), and the equity
  roll-forward leaves nothing unexplained (`P2-EQ-01`, `P2-EQ-02`).
- Contributed capital is constant in local currency, tested per entity per month
  (`P2-FX-01`).
- Every CTA row is reconstructible from source balances and the rate file alone
  (`P2-FX-03`); the anchored roll-forward is reproduced from them (`P2-FX-02`).
- Phase 5 inherits a testable expectation rather than a target. Its translation engine must
  reproduce `cta_expectation.csv`; CTL-FX-04's prohibition on CTA as a plug is now
  enforceable, because there is a derived figure to test against.
- The CTA is no longer free. A change to any driver that moves foreign net assets moves it,
  and the balance sheet with it, so `tools/derive_anchor_inputs.py --check` runs as a test.
