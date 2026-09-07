# Open Questions — Decisions Requiring Owner Approval

Design decisions where a reasonable practitioner could go either way, and where guessing would
be worse than asking. Each has a **working assumption** so that Phase 2 is not blocked, and
each states what changes if the answer differs.

Nothing here is a blocker for Phase 2 unless marked as such.

> **Status after the Phase 1.1 review.** Four questions are **closed** by owner decision:
> OQ-01 (add-back policy), OQ-02 (net debt definition), OQ-04 (swap accounting, confirmed
> by omission from the approved decisions) and OQ-12 (covenant narrative). Eight remain open
> with working assumptions. Closed questions are retained rather than deleted, with the
> decision and its consequence recorded, so the reasoning survives.

---

## OQ-01 — Adjusted EBITDA add-back policy ✅ CLOSED
**Owner:** CFO · **Decided:** Phase 1.1 review · **Impact:** High

**DECISION.** All three sub-questions settled, and the synthetic credit agreement written down
in [`config/debt/credit_agreement_terms.csv`](../config/debt/credit_agreement_terms.csv) so the
policy rests on a clause rather than an assumption:

| Sub-question | Decision | Clause |
|---|---|---|
| Run-rate synergy add-backs | **Not permitted** | `CA-028` |
| Sponsor monitoring fee | **Permitted, capped at $1.5m p.a.** | `CA-026`, `CA-027` |
| Share-based compensation | **Not added back** | `CA-029` |

Consequence: Covenant EBITDA equals Adjusted EBITDA by construction, though the two are still
computed separately so a future divergence surfaces. Add-back composition is anchored per
account and asserted in the build. Anchors unchanged. See ADR-0013.

*Original framing retained below.*

Adjusted EBITDA drives covenant reporting and sponsor value tracking. Three sub-questions:

**(a) Run-rate synergy add-backs.** Many credit agreements permit adding back the annualised
effect of cost actions taken but not yet fully realised. This materially changes leverage: at
FY2025, adding back a plausible $3.5m of run-rate synergies would reduce net leverage from
4.01x to 3.78x.
*Working assumption:* **excluded.** Only costs actually incurred are added back.

**(b) Sponsor monitoring fee** (`630400`, ~$1.2m p.a.). Treated as an add-back for management
reporting. Whether the credit agreement also permits it needs confirmation against the
document.
*Working assumption:* **added back.**

**(c) Share-based compensation** ($1.4m in FY2025). Non-cash, and many sponsors add it back.
*Working assumption:* **not added back.**

See ADR-0013.

---

## OQ-02 — Net debt definition for covenant reporting ✅ CLOSED
**Owner:** CFO / Treasury · **Decided:** Phase 1.1 review · **Impact:** High

**DECISION.** Operating leases are **excluded** from covenant net debt, per credit agreement
clause `CA-018`. In addition, a **separate non-covenant KPI — Economic Net Leverage —** is
reported alongside, including lease liabilities. It does not replace covenant leverage and has
no threshold of its own. FY2025: covenant 4.01x, economic 4.43x. See ADR-0015.

*Original framing retained below.*

Net debt currently excludes operating lease liabilities, following the credit agreement.
Including them would raise FY2025 net leverage from 4.01x to 4.43x. Both are computable and
both will be available; the question is which is the default on the board pack.

*Working assumption:* **exclude operating leases** — the covenant definition governs, because
it is the one with consequences. The alternative is presented as a memo line.

---

## OQ-03 — Consolidation scope
**Owner:** CFO · **Needed by:** Phase 4 · **Impact:** Medium

Scope currently excludes equity-method associates, joint ventures, disposals, discontinued
operations and step acquisitions. It includes one 80%-owned entity with NCI, a multi-tier
ownership tree and two mid-year acquisitions with purchase accounting.

Adding a 30%-owned associate or a mid-period disposal would demonstrate additional
consolidation capability at a cost of roughly two to three days in Phase 4.

*Working assumption:* **current scope stands.** `dim_entity.consolidation_method` already
exists, so adding `EQUITY` later is a data change plus one code path, not a redesign.

See ADR-0009.

---

## OQ-04 — Interest rate swap accounting ✅ CLOSED
**Owner:** CFO / Group Financial Controller · **Decided:** Phase 1.1 review · **Impact:** Medium

**DECISION.** The working assumption stands: the swap is **not designated for hedge
accounting**, so fair value movements go through the P&L (`730700`). This keeps the equity
roll-forward to a single OCI component (CTA), which the Phase 1.1 CTA roll-forward now
specifies in full. The credit agreement's minimum hedging requirement (`CA-008`) is satisfied
by the swap regardless of its accounting designation.

*Original framing retained below.*

The $100m swap is modelled as **not designated for hedge accounting**, so fair value movements
go through the P&L (`730700`). Designating it as a cash flow hedge would route the effective
portion through OCI, adding a second OCI component alongside CTA and requiring effectiveness
testing.

*Working assumption:* **not designated.** This keeps the equity roll-forward to one OCI
component, which materially simplifies the model and its controls.

**Related and worth flagging separately:** the swap matures in December 2026. From FY2027 the
group's effective interest rate steps up unless it is replaced. This is a genuine board topic
and the reporting is designed to surface it (`docs/reporting-design.md`, page 8).

---

## OQ-05 — Tax modelling depth
**Owner:** CFO / Tax · **Needed by:** Phase 4 · **Impact:** Medium

Tax is modelled at a **group effective rate** with a single deferred tax movement. A full
provision would require statutory rates per jurisdiction, permanent and temporary difference
schedules, valuation allowances on the German and Dutch losses, and a rate reconciliation.

The FY2023 effective rate of −18% and the FY2024 rate of 55% are deliberate: they reflect a
loss year with valuation allowances and a near-breakeven year with non-deductible items,
which is realistic. But they are asserted rather than derived.

*Working assumption:* **effective-rate modelling.** A full provision is a meaningful piece of
work (three to four days) and is proposed as an optional extension.

---

## OQ-06 — Operating lease simplification
**Owner:** Group Financial Controller · **Needed by:** Phase 4 · **Impact:** Low

In the anchor model the ROU asset **equals** the operating lease liability exactly. In reality
they diverge — prepaid and accrued rent, lease incentives, impairment. The simplification is
asserted in `tests/test_anchors.py::test_rou_asset_equals_operating_lease_liability` so it
cannot drift silently.

*Working assumption:* **keep the simplification.** A full ASC 842 schedule adds
disproportionate complexity for a caption that is not decision-relevant here.

---

## OQ-07 — German pension obligation
**Owner:** Group Financial Controller · **Needed by:** Phase 4 · **Impact:** Low

`NIG-220` carries a small unfunded German pension obligation, currently sitting within other
long-term liabilities (`245100`) with no actuarial modelling, no service or interest cost split
and no remeasurement through OCI.

*Working assumption:* **not separately modelled.** Full defined benefit accounting would add a
second OCI component for one immaterial balance.

---

## OQ-08 — Intercompany transfer pricing
**Owner:** CFO / Tax · **Needed by:** Phase 2 · **Impact:** Medium

Current assumptions: management fee at 2.5% of external revenue; product transfers at cost plus
10–12%; service recharges at cost plus 5%; technology royalty at 1.5% of licensee revenue;
intercompany loans at 6.0% fixed.

These are plausible and internally consistent, but they are assumptions. They drive the
elimination volumes, the unrealised profit calculation and the entity-level P&Ls that BU
leaders are measured on.

*Working assumption:* **as stated in
[`config/ic/intercompany_matrix.csv`](../config/ic/intercompany_matrix.csv).**

---

## OQ-09 — Statutory year-end alignment
**Owner:** Group Financial Controller · **Needed by:** Phase 2 · **Impact:** Low

`NIG-320` Tyneside has a 31 March statutory year end but reports to group on a calendar basis.
The model handles group reporting only; the statutory difference is out of scope.

*Working assumption:* **all entities report to group on a calendar basis.** Modelling dual
calendars would be a significant addition and would demonstrate a capability the group does not
currently need.

---

## OQ-10 — Materiality threshold for variance commentary
**Owner:** CFO · **Needed by:** Phase 8 · **Impact:** Low

Commentary is required where a variance exceeds **$250k or 5% of the line, whichever is
greater**. At group scale $250k is roughly 0.06% of revenue, which may generate more commentary
than the board wants; at entity level it may generate too little.

*Working assumption:* **$250k or 5%**, applied at the level being reported, with the threshold
as a configuration value rather than a hard-coded number so it can be tuned in Phase 8 once
real volumes are visible.

---

## OQ-11 — Data volume target
**Owner:** Engagement Lead · **Needed by:** Phase 2 · **Impact:** Low

The design targets ~1.5m journal lines and ~3.2m rows overall: large enough that the physical
design has to be right, small enough to rebuild in minutes and to fit a Power BI import model.

*Working assumption:* **as stated in `docs/data-contract.md` §7.** Volume beyond this would
demonstrate nothing further and would slow every iteration.

---

## OQ-12 — Whether FY2026 should show a covenant breach ✅ CLOSED
**Owner:** CFO / Engagement Lead · **Decided:** Phase 1.1 review · **Impact:** Medium

**DECISION.** The FY2026 base case is **approved as it stands: no breach**, covenant threshold
4.50x, forecast net leverage 3.80x, headroom 0.70x. The base dataset is **not** to be distorted
to manufacture drama.

A **Downside scenario is reserved** (`DS` / `DS_FY26_STRESS`) to produce a realistic breach or
near-breach in a later phase, exercising waiver tracking, remediation reporting and the
two-per-four-quarters equity cure right at clause S7.3 (`CA-014`). It is registered in the
scenario configuration, **not populated**, and excluded from every default reporting view by
`CTL-SCN-06`. It must be generated as a separate version, never by amending the base forecast.

The approved figures are asserted in
`tests/test_architecture_invariants.py::test_approved_fy2026_forecast_covenant_position` so
they cannot drift. See ADR-0015.

*Original framing retained below.*

The FY2026 forecast currently shows leverage of 3.80x against a 4.50x covenant — **0.70x of
headroom, narrowing but not breached**.

A near-breach or an actual breach would be a richer demonstration: it would exercise waiver
tracking, remediation reporting and a genuinely difficult board conversation. It would also
change the character of the engagement from "a well-run group tightening" to "a group in
difficulty", which affects every piece of commentary in the board pack.

*Working assumption:* **no breach.** Headroom narrows visibly and covenant reporting is a
first-class output, which demonstrates the capability without changing the story.

This is the one open question where the answer would meaningfully change Phase 8's content,
and it is worth a decision before Phase 2 generates the underlying data.
