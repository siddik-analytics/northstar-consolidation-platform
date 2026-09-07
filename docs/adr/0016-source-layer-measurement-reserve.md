# ADR-0016: The source-layer difference is a disclosed equity reserve, never a plug in a real balance

- **Status:** SUPERSEDED by [ADR-0017](0017-layer-1-equity-bridge-and-derived-cta.md) (Phase 2.2, 2026-09-07)
- **Date:** 2026-09-07
- **Phase:** 2.1
- **Superseded because:** the decision treated an unexplained residual as something to
  disclose. It was something to derive. There is no residual and no reserve.

---

## Why it was superseded

ADR-0016 accepted a difference between the sum of the generated entity ledgers and the
approved consolidated anchors, and decided the honest response was to name it, cap it,
disclose it and discard it at Phase 4 — `329100 Group reporting measurement reserve`.

The reasoning was sound about *disclosure* and wrong about *cause*. The difference was not a
measurement effect that could only be observed; it was the arithmetic consequence of two
defects in the source construction and one gap in the anchor bridge:

1. **Contributed capital was re-pinned to a closing-rate USD target every year.** A German
   subsidiary's Stammkapital moved because EUR/USD moved. With capital retranslated onto a
   USD target, the entity ledgers could not generate the translation adjustment a
   consolidation is supposed to compute — so a cumulative translation adjustment of roughly
   the right size had nowhere to arise.
2. **Share-based compensation was expensed with no credit to its reserve**, so a non-cash
   charge left the group as cash.
3. **The Phase 2 anchor bridge derived a layer-1 target for every asset, every liability and
   every income statement line — but not for equity.** With equity unconstrained, the
   layer-1 balance sheet had one free degree of freedom, and any generator will close a free
   degree of freedom with a plug. Phase 2.0 put it in investment-at-cost; Phase 2.1 put it in
   `329100`. Both are the same defect wearing different clothes.

Fix all three and the difference is not smaller — it is **zero**, in every year, to the
cent. ADR-0017 records the replacement decision and the derivation.

## What was removed

| Removed | Where |
|---|---|
| `329100 Group reporting measurement reserve` | `config/coa/group_coa.csv` |
| `AURORA 3250 Group Reporting Measurement Reserve` | `config/coa/source_coa_aurora.csv` |
| Its row in the expected mapping manifest | `config/generation/expected_mapping_manifest.csv` |
| `SeriesBuilder.apply_measurement_reserve` | `src/generation/series.py` |
| `P2-RES-01` reserve materiality cap · `P2-RES-02` cash carries none of it | `src/generation/validate.py` |
| `data/reference/translation_difference.csv` | replaced by `cta_expectation.csv`, `layer1_equity_bridge.csv`, `cta_group_bridge.csv` |

## What is retained from this decision

One principle survives and is carried into ADR-0017: **a residual must never be silently
absorbed into a real balance.** ADR-0016 was right that hiding the difference in cash, or in
investment at cost, was worse than naming it. The Phase 2.2 position is stronger only
because the difference no longer exists: `P2-EQ-01` fails the build if the layer-1 equity
roll-forward leaves anything unexplained, and `P2-EQ-03` fails it if any account in any
chart is named in a way that admits it exists to make the model agree.
