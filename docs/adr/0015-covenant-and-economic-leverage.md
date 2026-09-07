# ADR-0015 — Two leverage measures, and a reserved Downside scenario

**Status:** Accepted · **Date:** 2026-09-07 · **Phase:** 1.1

## Context

Two questions were settled at the Phase 1.1 review and both concern how leverage is reported.

**First**, the credit agreement's definition of Indebtedness excludes operating lease
liabilities (`CA-018`), because the facility predates the group's adoption of ASC 842. So the
tested covenant ratio understates the group's real obligations by about half a turn — $24.5m
of lease liabilities at FY2025 that a reader would reasonably regard as debt.

**Second**, the FY2026 base case shows covenant headroom of 0.70x. That is a good story, but
it never exercises covenant breach, waiver or equity-cure reporting — capabilities the
platform should demonstrate, and which a PE-backed group genuinely needs.

## Decision

### Two leverage measures, always reported together

```
Covenant net debt   = term loan (gross principal) + revolver + finance leases
                    − unrestricted cash                                  [CA-015..CA-020]
Covenant leverage   = covenant net debt ÷ TTM Covenant EBITDA            ← the TESTED ratio

Economic net debt   = covenant net debt + operating lease liabilities
Economic leverage   = economic net debt ÷ TTM Adjusted EBITDA            ← non-covenant KPI
```

**Covenant leverage is the default** on every covenant and board view. Economic Net Leverage
is presented **alongside** it, clearly labelled as non-covenant, with **no threshold of its
own**.

| | FY2023A | FY2024A | FY2025A | FY2026B | FY2026F |
|---|---|---|---|---|---|
| Covenant net leverage | 5.42x | 5.26x | 4.01x | 3.31x | 3.80x |
| Economic net leverage | 5.98x | 5.77x | 4.43x | 3.68x | 4.23x |
| Covenant maximum | 6.00x | 5.50x | 5.00x | 4.50x | 4.50x |

### The FY2026 base case is not distorted

The base dataset keeps its approved shape: **no breach**, 4.50x threshold, 3.80x forecast
leverage, 0.70x headroom. A **reserved Downside version** (`DS_FY26_STRESS`) is registered in
the scenario configuration but **not populated**, and is excluded from every default reporting
view by `CTL-SCN-06`.

## Alternatives considered

**Report only covenant leverage.** The single tested number, and the simplest. It leaves a
reader believing the group's leverage is 3.80x when its obligations imply 4.23x. The
difference arises from a definitional quirk of a 2021 credit agreement, not from economics.
Rejected as incomplete.

**Report only economic leverage, as the "true" measure.** Intellectually defensible and
actively harmful: it would misstate covenant compliance, which is the number with legal
consequences. A board reading 4.23x against a 4.50x covenant would think headroom was 0.27x
when it is actually 0.70x. Rejected.

**Redefine covenant leverage to include leases and note the difference.** Rejected outright.
The covenant ratio is defined by a contract; it is not ours to redefine, and a "corrected"
covenant ratio is simply a wrong covenant ratio.

**Blend the two, or show a single number with a footnote.** Rejected. Two measures with
different definitions and different consequences should be two labelled numbers.

**Make the FY2026 base case breach the covenant** to demonstrate breach reporting. Rejected,
and this is the decision worth being explicit about: the dataset exists to be *realistic*, and
manufacturing distress to make the reporting more interesting would be exactly the "fake
complexity" the engagement brief warns against. It would also change the character of every
piece of Phase 8 commentary — from a well-run group tightening to a group in difficulty — on
the basis of a demo requirement rather than a business fact.

**Omit a downside scenario entirely.** Rejected too. Covenant breach, waiver tracking and
equity-cure reporting are real capabilities. Reserving them as a separate, explicitly
non-default scenario gets both: an honest base case and a demonstrable stress case.

## Consequences

**Positive.** The covenant ratio stays exactly what the lender tests. The economic view is
visible without contaminating it. The base dataset keeps its integrity. The scenario
architecture is proven to carry a stress case without any schema change — `DS`/`DS_FY26_STRESS`
already resolve through the existing scenario and version dimensions.

**Negative.** Two leverage measures on one page invite confusion if labelling is sloppy.
Mitigated by never showing Economic Net Leverage against a covenant threshold, and by
labelling it "non-covenant" wherever it appears. A `is_reserved` flag must now be respected by
the mart layer (`CTL-SCN-06`); a reserved version leaking into a default view would misstate
the reported position.

**Deferred.** Populating `DS_FY26_STRESS` is out of scope for Phases 2–7. When it is built it
should exercise a genuine breach against the 4.50x FY2026 test, the two-per-four-quarters
equity cure right at clause S7.3 (`CA-014`), and waiver and remediation reporting. It must be
generated as a **separate version**, never by amending the base forecast.
