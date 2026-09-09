# Defect register

Every genuine defect found in the platform, where it was found, what closed it, and what
permanent control now stops it coming back. One row per defect, oldest first.

Three things are true of this list and worth saying plainly. Every one of these defects was
found by the platform's own machinery rather than by review. None was corrected in the layer
that found it — each was escalated to the owner, decided, and fixed at its source. And more
than half of them **balanced**: the trial balance closed, the statement footed, the
reconciliation tied, and the number was still wrong.

`docs/architecture-lessons.md` is the companion to this file: the same defects, read for what
each one says about the design rather than for what happened.

---

## Open

*None.*

---

## Closed

| id | found in | what it was | closed by | permanent control |
|---|---|---|---|---|
| **P2-D-01** | Phase 3 | Source extract defects found by ingestion rather than by the source's own controls | Phase 3.1 source correction, regenerated | `CTL-DQ-*` at ingestion |
| **P2-D-02** | Phase 3 | ″ | Phase 3.1 | ″ |
| **P2-D-03** | Phase 3 | ″ | Phase 3.1 | ″ |
| **P2-D-04** | Phase 3 | ″ | Phase 3.1 | ″ |
| **P3-D-05** | Phase 4 | `ACQ_OPENING_BS` for NIG-510 registered at the January close instead of the FY2022 closing anchor — the translation base every later revaluation measures from | Phase 3.2, corrected at the generator | `P4-FX-10` recomputes the opening base rather than trusting it |
| **P3-D-06** | Phase 4 | Upstream defect found by the consolidation engine, not by a source control | Phase 3.2 | Phase 4 FX family |
| **P3-D-07** | Phase 4A | The Phase 1 NCI earnings estimate disagreed **in sign** with the entity ledger | Owner decision: the ledger supersedes the estimate ([ADR-0025](adr/0025-the-entity-ledger-supersedes-the-phase-1-nci-estimate.md)) | `tools/derive_nci_anchor.py --check` |
| **P4-D-01** | Phase 4B | The balance sheet presented USD 19.869m as the period result while the income statement reported 7.046m for the same year — the year-end close included in one and not the other | Phase 4C | `P4-XAR-06` |
| **P4-D-02** | Phase 4B | The EBITDA bridge summed a fiscal year including the close, reporting statutory EBITDA of (0.535)m against 28.705m | Phase 4C | `P4-XAR-02` |
| **P4-D-03** | Phase 4C | A `FILTER` matching nothing yielded NULL and voided the whole Covenant EBITDA expression — found by the new cross-artefact controls on their first run | Phase 4C | `P4-XAR-04`, plus the NULL policy and its lint test |
| **P6-D-01** | Phase 6A | `project_id` identified 1,846 capital projects with **395** values: the sequence restarted inside each asset class, so every class in an entity-month reissued `-01`. A fixed asset could not name the project that bought it | Phase 5.1, corrected at the generator ([ADR-0026](adr/0026-a-declared-key-is-a-contract.md)) | `P7-KEY-*` over all 61 keyed objects, `P7-CPX-01…09`, fixture `F7-KEY-01` |
| **P7-D-01** | Phase 5.1 | `PY_DERIVED` was the version code on 12,516 mart rows and every prior-year comparator, and existed in no version master. Found by the framework built for P6-D-01, on its first run | Phase 5.1, `PY_DERIVED` added as a governed derived version ([ADR-0027](adr/0027-a-derived-version-is-still-a-governed-version.md)) | `P7-VER-01…14`, fixtures `F7-VER-01…09` |

---

## How a defect gets onto this list

The rule is the same in every phase brief and has not been departed from:

> If a phase finds a genuine defect in a frozen upstream layer, it **stops and reports it**. It
> does not repair the data in the layer that found it, and it does not compensate downstream.

That is why `P3-D-05` was fixed in the generator rather than patched in the FX engine, why
`P6-D-01` was escalated instead of being worked around with a surrogate key in Power BI, and
why `P7-D-01` was reported and quarantined at its exact population for one review cycle before
being closed.

Quarantine is the mechanism for a defect that is real but cannot be fixed yet
([ADR-0021](adr/0021-source-findings-are-baselined-not-downgraded.md)). The control reports
`SOURCE_FINDING` at the population the defect was found at and **fails at any other number**, so
a second defect of the same shape cannot hide inside a known one, and a silent fix upstream does
not pass unnoticed either. It is a record of an open defect, never a way to make a suite green.

## What the pattern says

`P4-D-03`, `P6-D-01` and `P7-D-01` were each found by a control family built to catch the
*previous* defect, on its first run. That is the strongest argument in this repository for
building the general control rather than fixing the specific instance: the general control keeps
finding things.

`P6-D-01` and `P7-D-01` share a shape that none of the earlier ones had. Neither made a number
wrong. Both were identifiers in use that resolved to nothing, and both were invisible because
every query they appeared in still returned rows. Arithmetic controls cannot see that class of
defect at all — structure needs controls of its own.
