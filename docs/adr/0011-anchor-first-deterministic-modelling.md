# ADR-0011 — Anchor-first deterministic modelling

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1

## Context

The platform is populated with synthetic data. Synthetic data has a characteristic failure
mode: it is generated bottom-up from plausible-looking random distributions, and the resulting
financial statements are internally arbitrary. Gross margin drifts for no reason, working
capital bears no relation to revenue, the balance sheet is forced to balance with a plug, and
there is no business story — just numbers that pass a type check.

That failure mode is fatal here, because the entire point of the engagement is management
reporting, and management reporting is about *explaining why numbers moved*.

## Decision

**Define the group financial anchors first, in Phase 1, as an executable driver-based model.
Generate transactions in Phase 2 to hit those anchors. Test the generated data back against
them in Phase 9.**

The anchor model (`src/anchors/build_anchors.py`) is:

- **Driver based.** Revenue is built bottom-up from twelve legal entities; margins, working
  capital days, capex, debt and tax are drivers. No output is typed in.
- **Self-proving.** The balance sheet closes by construction, because cash is derived from the
  accounting identity `Cash = L + E − non-cash assets` with the revolver set by an explicit
  treasury policy. The indirect cash flow statement, derived from balance sheet movements,
  therefore ties to cash to the cent. Both are asserted; the script refuses to emit output if
  either fails.
- **Deterministic.** No randomness. Same inputs, same outputs, byte for byte.
- **Independently tested.** `tests/test_anchors.py` re-reads the generated CSVs and re-derives
  every identity, rather than importing the model's internal state. A test that shares logic
  with the thing it tests proves nothing.
- **The generated documentation is the model's output.** `docs/financial-anchors.md` is
  written by the script, so the narrative cannot drift from the numbers.

## Alternatives considered

**Generate transactions from distributions and report whatever emerges.** Faster to build.
Produces data with no story, statements that need a plug to balance, and variances that cannot
be explained because they have no cause. Rejected — it would make the management reporting
layer, which is the actual deliverable, meaningless.

**Hand-write the anchor numbers in a markdown table.** Much faster. Arithmetic errors are
guaranteed at this scale, and every downstream document would quote figures that quietly
disagree with each other. Rejected. This was tested during Phase 1: the first hand-sketched
opening balance sheet was out by $40m and the first purchase-price allocation did not balance.
The executable model caught both immediately.

**Build the anchors in Excel.** Familiar and quick to iterate. Not diffable, not testable in
CI, and not reproducible from a clean clone. Rejected for the anchor layer specifically —
Excel remains a first-class deliverable for the reporting layer, where its interactivity is
the point.

## Consequences

**Positive.** The synthetic data has a defensible business narrative: margin expansion,
deleveraging, two mid-year acquisitions, a forecast miss with attributable causes. Phase 2 has
an unambiguous calibration target. Phase 9 has an unambiguous acceptance test (`CTL-REC-06`:
revenue, EBITDA and net income within 0.5%, balance sheet captions within 1.0%). Changing a
driver re-derives every dependent figure and every document that quotes it.

**Negative.** More Phase 1 effort before any data exists. Phase 2 generators are constrained —
they must hit the anchors, which is harder than generating freely. That constraint is the
point.

**Rule.** If generated data disagrees with the anchors, **the generators are wrong, not the
anchors**. Anchors change only by an explicit, reviewed change to a driver, which re-runs the
tests and regenerates the documentation.
