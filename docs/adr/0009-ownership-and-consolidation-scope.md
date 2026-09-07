# ADR-0009 — Full consolidation with one NCI; no equity-method investees

**Status:** Accepted · **Date:** 2026-09-06 · **Phase:** 1 · **Requires owner confirmation**

## Context

Consolidation scope determines how much accounting machinery the engine needs. Every
additional ownership pattern — non-controlling interests, equity-method associates, joint
ventures, step acquisitions, disposals, discontinued operations — adds real complexity and
real demonstration value. The question is where to stop.

## Decision

**In scope:**

- Twelve operating entities, all **fully consolidated**.
- Eleven wholly owned; **`NIG-510` Northstar Parts UK is 80% owned**, with the residual 20%
  presented as non-controlling interests on both the income statement and the balance sheet,
  including the NCI share of the CTA movement.
- A **multi-tier ownership tree**: `NIG-210`, `NIG-310`, `NIG-410` and `NIG-510` are held
  through intermediate subsidiaries, not directly by Topco.
- **Two mid-year acquisitions** with partial-period consolidation (`NIG-220` from April 2023,
  `NIG-410` from July 2024) and full purchase price allocation.

**Out of scope:**

- Equity-method associates and joint ventures.
- Step acquisitions and changes in ownership percentage.
- Disposals, discontinued operations and assets held for sale.
- Hyperinflationary economies (no entity qualifies).
- Defined benefit pension accounting. The small German obligation at `NIG-220` sits in other
  long-term liabilities and is not separately modelled.

## Alternatives considered

**All twelve entities wholly owned.** Simplest. Removes NCI allocation entirely, which is a
core consolidation competency and a genuine source of error in real groups — particularly the
NCI share of CTA and of unrealised profit eliminations. Rejected as too thin.

**Add a 30%-owned equity-method associate.** Would demonstrate one-line consolidation and
share-of-result accounting. It also introduces a second consolidation method, a second set of
elimination rules, and a whole additional reporting pattern for one account on the balance
sheet. Rejected: the complexity is not proportionate to what it demonstrates here, and the
engine's architecture already supports it — `dim_entity.consolidation_method` exists and
carries `FULL` for every current entity.

**Add a mid-period disposal.** Would exercise the effective-to date and discontinued
operations presentation. Rejected for the same reason, and because the effective-date
machinery is already exercised by the two mid-year acquisitions.

**Two or three NCI entities.** More NCI content, no new capability — the second one tests
nothing the first does not. Rejected.

## Consequences

**Positive.** Scope is proportionate: full consolidation, NCI allocation, multi-tier
investment elimination, partial-period consolidation and purchase accounting are all
exercised, without carrying two consolidation methods through every layer of the model.

**Negative.** The engine does not demonstrate equity-method accounting. This is stated
explicitly rather than left as a silent gap, and `dim_entity.consolidation_method` is present
so that adding `EQUITY` later is a data change plus one code path rather than a redesign.

**Requires owner confirmation.** Adding an equity-method associate or a disposal is a
reasonable request and would be an incremental Phase 4 change. Recorded as open question OQ-03
in `docs/open-questions.md`.
