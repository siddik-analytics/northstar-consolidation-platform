# ADR-0025 — the entity ledger supersedes the Phase 1 NCI earnings estimate

**Status:** accepted, Phase 4A
**Supersedes:** the `NCI_INCOME` series in `docs/nci-policy.md` as approved in Phase 1
**Related:** [ADR-0011](0011-anchors-are-the-contract-for-generated-data.md),
[ADR-0021](0021-source-findings-are-baselined-not-downgraded.md), defect P3-D-07

## Context

Phase 1 set the non-controlling interest's share of result at **0.18 / 0.28 / 0.36** USD m for
FY2023-25. It was a top-down estimate: 20% of a plausible profit for `NIG-510`, made before any
entity-level profit and loss existed to take 20% of.

Phase 2 generated the entity ledgers. Phase 4 built the engine that computes the attribution
and the two disagreed **in sign**: derived from the ledger the minority's share is
**(0.197) / (0.219) / (0.266)** USD m. `NIG-510` is loss-making on its own books.

That is not an engine defect and it was not treated as one. `NIG-510` buys from `NIG-200` at
the approved transfer price and sells at a 12.6% gross margin, which does not cover its own
operating cost. `config/anchors/anchor_by_entity.csv` anchors its **external revenue** — 17.500
/ 19.500 / 22.300 USD m, which the ledger reproduces exactly — and nothing else. Its
profitability was never anchored, never calibrated and never tested, and the 42% gross margin
the Aftermarket business unit carries is a business-unit figure shared between `NIG-500` and
`NIG-510`.

So two approved inputs disagreed, and exactly one of them had ever been derived from anything.

## Decision

**The generated entity ledger and the approved transfer-pricing economics are the authority.
The Phase 1 NCI earnings estimate is superseded.**

`NCI_INCOME` is now **derived** by `tools/derive_nci_anchor.py` from `stg_nci_result`, the
engine's own attribution, rather than typed into `src/anchors/build_anchors.py` by hand:

    NCI share = (NIG-510's own result + the layer-3 consolidation adjustments attributable
                 to it) x the effective NCI percentage for the period

Intercompany eliminations are excluded from that base. An elimination removes a matched pair
and changes group profit by nothing; attributing the buyer's half to the buyer without the
seller's half to the seller would hand `NIG-510` its purchases for free. That error made the
first attribution five times the anchor, in the wrong direction, and it is the reason the base
is layer 3 and not layers 2 and 3.

The revised series, derived and written back rather than transcribed:

| | FY2023A | FY2024A | FY2025A | FY2026B | FY2026F |
|---|---|---|---|---|---|
| `NCI_INCOME` (USD m) | (0.197389) | (0.218966) | (0.265949) | (0.179968) | (0.179968) |

There is a feedback loop, exactly as there was for CTA in Phase 2.2: the anchor feeds net
income, which feeds retained earnings, which feeds the generated ledgers, which feed the
consolidation that produces the anchor. The tool therefore converges rather than computing
once. It converged at **iteration 1, with a difference of 0.000000**.

## What was explicitly not done

* **The transfer price was not changed** to force `NIG-510` into profit. It is an approved
  input to source generation with its own economics; moving it to fit a superseded estimate
  would be fabricating the subsidiary's profitability and would silently restate every
  intercompany margin, the unrealised profit provision and the Aftermarket gross margin with
  it.
* **The engine was not scaled to the anchor.** Scaling would have produced the approved number
  and destroyed the only evidence that the two inputs disagreed.
* **The anchor was not transcribed.** Copying (0.197389) into configuration by hand would make
  the next disagreement invisible in exactly the same way as the first one.

## Consequences

* `NCI_INCOME` joins CTA as a **derived** anchor. Both were estimates that the generated data
  later contradicted, and both are now computed by a tool with a `--check` mode that fails when
  the file and the engine drift apart. `tests/test_phase04a_proof_gate.py` runs that check.
* The sign of the series is now a tested property: a positive NCI share would mean `NIG-510`
  had become profitable, which cannot happen without a transfer-price decision.
* Nothing else moves. NCI is an attribution below the tax line and inside equity, so
  consolidated revenue, EBITDA, net income before attribution, total equity, cash and debt are
  all unaffected. What changes is the split of equity between the group and the minority, and
  the line below tax that names it.
* **P3-D-07 is closed** by this decision rather than by a correction, and is recorded in
  `config/controls/source_exception_register.csv` as `SX-010` with the owner decision as its
  rationale. Closing it required the roll-forward to reconcile exactly, which it does.
* The control that was missing is now present: `P4-NCI-02` proves the share uses the entity's
  own effective percentage from the ownership register, and the derivation tool proves the
  anchor and the engine agree. The absence of any comparison between them is what let a Phase 1
  estimate survive three phases without anyone noticing it had been contradicted.
