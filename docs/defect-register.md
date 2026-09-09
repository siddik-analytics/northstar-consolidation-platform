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

## Closed in Phase 6A.1

| id | found in | what it was | closed by | permanent control |
|---|---|---|---|---|
| **P6-D-02** | Phase 6A | **The build ids were checkout-dependent.** `build_id()` hashed the raw bytes of its declared inputs, so a build id changed when git rewrote a line ending. The form that reproduced each committed id was a per-file mixture of CRLF and LF — the ids identified which files had last been authored on Windows, not what the inputs said | one shared canonical hasher, `src/lineage/digest.py` ([ADR-0028](adr/0028-lineage-ids-hash-content-artefact-digests-hash-bytes.md)). Lineage ids hash canonical text; artefact digests still hash bytes | `P7-RPR-01` … `P7-RPR-05`, fixture `F7-RPR-01`, and `tools/checkout_reproducibility.py` |

### P6-D-02 in detail — as it was found

Exposed by rebasing the Phase 6A branch, which re-checked-out several declared build inputs and
changed their line endings. Content was byte-identical throughout; only the encoding moved, and
the ids moved with it.

The form that reproduces each committed id turns out to be a **per-file mixture** — some inputs
CRLF, some LF — which is the clearest possible demonstration of the problem: the ids depend on
the accident of which files were last authored on Windows rather than on what the inputs say.

```
phase03 reproduces with  build_digest.txt=CRLF, mapping_rules.csv=CRLF, group_coa.csv=CRLF,
                         source_coa_aurora.csv=CRLF, source_coa_sable.csv=CRLF,
                         source_coa_kestrel.csv=LF, entity_master.csv=LF
phase04 reproduces with  build_digest.txt=CRLF, phase03_manifest.json=CRLF,
                         investment_register.csv=CRLF, the rest LF
```

At the time the working tree was restored to those forms so the baseline would verify, which
was a local patch, not a fix: a fresh clone would still have produced different ids.

**Closed in Phase 6A.1.** `src/lineage/digest.py` is now the single canonical hasher every
phase calls. A lineage id hashes canonical text — UTF-8, BOM dropped, `
` and bare ``
folded to `
` — together with each input's repository-relative name and length. Whitespace is
deliberately **not** normalised, because a trailing space in a CSV field is data and
indentation in Python is syntax. Artefact digests still hash raw bytes, because "is this the
same file" is a different question from "is this the same input"
([ADR-0028](adr/0028-lineage-ids-hash-content-artefact-digests-hash-bytes.md)).

The ids rebaselined and cascaded: Phase 3 `6e0c519360d3669b` → `468dbf847805d6c9`, Phase 4
`fcfa135a222f58ba` → `cc89cf0317801b36`, Phase 5 `50d85b385b7a2a41` → `00d3dd24020f900d`,
workbook `0a26d3980bd463e5` → `e8b97d9e780a13a7`, Phase 6A `458ca84c1903b9f0` →
`fc2823eb5a85b42c`. The source layer digest did not move. Metadata only: 325,352 rows compared
at `0.00`, zero numeric change across 615,270 workbook cells, and an identical semantic model.

---

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

## Found by Phase 6A, and fixed inside it

Three defects were found in the **semantic model itself** by deploying it to a live engine.
They are not in the table above because they never reached an approved baseline -- they were
found and fixed within the phase -- but they are the clearest argument in this repository for
validating a model by running it rather than by reading it.

| what | how it was found |
|---|---|
| a relationship on `Financial Detail[cost_centre_key]`, a column that does not exist on the mart; and `Headcount -> Cost Centre`, a join to a dimension that fact has no key for | Analysis Services refused to load the model |
| **every** statement measure summed both reporting bases and reported exactly twice the truth | `Revenue` came back at 557,961,779.56 against a mart holding 278,980,889.78 |
| four measures did not parse: a measure reference used as a boolean table filter (three times), and `MIN` over a Boolean column | the engine returned calculation errors |

All three were invisible in the TMDL, which is text, and text always parses.

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
