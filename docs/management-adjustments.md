# Management adjustments — layer 4

The layer that lets the group report a management view without ever touching the statutory
result.

---

## 1. Why layer 4 exists

In most hand-built consolidations "management adjustments" are made inside the consolidated
numbers and then backed out for statutory reporting. The statutory figure is therefore derived
by subtraction from a management figure, and nobody can be certain what was removed.

Here the direction is reversed. The **statutory result is the primary number** and the
management view is derived from it by adding one layer:

```
Statutory  = Layer 1 + Layer 2 + Layer 3 + Layer 5
Management = Statutory + Layer 4
```

It is far easier to defend a management view built on an audited base than an audited base
reconstructed out of a management view.

The separation is structural, not procedural. `vw_statutory_fact` selects its layers from
`dim_consolidation_layer.in_statutory_view`; layer 4 is not in that set. A management
normalisation cannot reach the reported result by being filtered wrongly in a report, because
the report never sees it. `P4-LAY-03` proves the statutory basis contains zero layer-4 rows.

## 2. The adjustment register

`config/consolidation/management_adjustment.csv`. Every adjustment carries, as configuration
and not as code:

| Field | Purpose |
|---|---|
| `adjustment_id`, `category`, `basis` | what it is and on what principle |
| `entity_code`, `group_account`, `offset_account` | where both sides are posted |
| `period_from`, `period_to` | the window it applies to |
| `amount_usd_m` | the amount |
| `ebitda_treatment`, `covenant_treatment` | how each measure treats it |
| `rationale` | why, in prose |
| `preparer`, `approver`, `approval_status` | who proposed it and who approved it |
| `reverses_next_period` | whether it unwinds |

Only an **APPROVED** adjustment is posted. An adjustment nobody has approved is a proposal, and
a management view built on proposals is not a management view. `P4-MGT-01` iterates the
register and compares what is approved with what was posted; `P4-MGT-02` rejects an adjustment
with no preparer, approver or rationale.

## 3. The current register contains no non-zero adjustment

**State this plainly: on the clean baseline, layer 4 is empty. Zero legs are posted, and the
management basis is numerically identical to the statutory basis for FY2023–FY2026.**

Both approved adjustments are presentation reclassifications carrying a **nil amount**:

| | Category | Basis | Effect |
|---|---|---|---|
| MA-001 | RECLASS | shared services presented where consumed | nets to nil within the income statement |
| MA-002 | ACQUISITION | acquired intangible amortisation shown apart from organic D&A | nets to nil within D&A |

Neither changes a subtotal, and **no amount has been invented to make the layer look busier**.
That is a finding about the approved policy set rather than an omission, and it has a specific
cause worth recording: the group's non-recurring items — restructuring, transaction costs, the
ERP programme, the sponsor fee — are already **inside operating expenses at layer 1**, flagged
`is_ebitda_addback` on the account ([ADR-0013](adr/0013-adjusted-ebitda-definition.md)).
Adjusted EBITDA is computed from an account attribute in the statutory data, not from a
management journal. Adding those items again at layer 4 would double count them.

`P4-BAS-02` reports the emptiness explicitly, so that a comparison of two identical columns is
never mistaken for a proof that the two bases were kept apart.

## 4. How the framework is proved without inventing numbers

Two fixtures, asserting opposite things. Both run a full consolidation through the real engine.

**`F4-MGT-LEAK` — separation.** An **APPROVED** adjustment of USD 2.5m a month is injected into
the register, moving an operating cost below the EBITDA line — the shape of a real management
add-back. Result: **96 legs posted at layer 4**, **8 measure-years moved** (EBITDA and EBIT,
four years each) on the management basis, and the statutory basis does not move at all.
`P4-LAY-03` and `P4-BAS-01` both still pass, and the difference between the bases is still
explained by layer 4 exactly.

**`F4-17` — suppression.** The same adjustment with the same amount, marked **DRAFT**. Result:
**zero legs**, **zero measures moved**. The approval gate holds.

Proving the gate holds is worth as much as proving a control fires, and neither proves the
other. Both fixtures read the engine's output back — layer-4 leg count and measures moved — so
that "nothing broke" cannot be confused with "the edit never reached the engine".

## 5. Adjusted EBITDA and Covenant EBITDA are not the same measure

Assuming they are is a common and expensive error: the covenant is tested on the credit
agreement's definition, and headroom calculated on the management definition can be wrong in
the direction that matters.

| | Adjusted EBITDA | Covenant EBITDA |
|---|---|---|
| Basis | approved add-back policy, [ADR-0013](adr/0013-adjusted-ebitda-definition.md) | the credit agreement, CA-021 to CA-030 |
| Restructuring, transaction costs, integration, legal, retention | added back | added back |
| Sponsor monitoring fee | added back in full | added back **capped at USD 1.5m a year** (CA-027) |
| Unrealised foreign exchange | not an add-back | **added back** (CA-030) |
| Share-based compensation | not an add-back | not permitted (CA-029) |
| Run-rate synergies | not claimed | not permitted (CA-028) |

The sponsor fee runs at 1.0 / 1.1 / 1.2 USD m a year against a 1.5m cap, so the cap does not
bite in the modelled window — but the cap is applied rather than assumed away, because it would
bite at a higher fee and the covenant calculation must not need editing when it does.

> **`rpt_ebitda_bridge`, the artefact that implements this table, is defective and must not be
> used.** Two faults, both found during Phase 4B documentation and neither corrected here:
> statutory EBITDA is computed including the year-end close, so three of the four years are
> wrong by the whole year's EBITDA; and Covenant EBITDA is NULL in every year because a `FILTER`
> that matches nothing yields NULL and voids the arithmetic. See
> [`phase-04b-engine-findings.md`](phases/phase-04b-engine-findings.md), defect **P4-D-02**.
> `rpt_income_statement` computes Adjusted EBITDA correctly (38.505 / 47.091 / 57.750 /
> 33.013 USD m) and the two artefacts disagree, which is how the fault was found.

## 6. Controls

| Control | Assertion | Severity |
|---|---|---|
| `P4-MGT-01` | only approved adjustments are posted; iterated from the register | blocking |
| `P4-MGT-02` | no adjustment is anonymous — preparer, approver and rationale required | blocking |
| `P4-MGT-03` | Adjusted and Covenant EBITDA are computed separately | warning, reported |
| `P4-LAY-03` | no layer-4 row reaches the statutory basis | blocking |
| `P4-BAS-01` | management less statutory equals layer 4, for every headline measure | blocking |
| `P4-BAS-02` | discloses that layer 4 is currently empty | warning, disclosed |
