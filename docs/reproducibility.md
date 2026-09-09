# Reproducing the build

Everything in this repository is generated from a fixed seed and committed configuration.
Nothing depends on a clock, a counter, an environment variable or a machine. Two builds of the
same inputs produce byte-identical outputs — and that is a tested property, not an aspiration.

---

## 1. Environment

| | |
|---|---|
| Python | 3.12 |
| Packages | `requirements.txt`, fully pinned |
| Engine | DuckDB 1.5.5, embedded — no server, no container |
| Disk | ≈ 1.1 GB for the generated raw extracts and the warehouse |
| Platform | developed on Windows 11; no platform-specific code |

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements.txt
```

Nothing else is installed and nothing is downloaded at build time.

## 2. The full build

Run in order. The whole chain takes about **three and a half minutes**, of which the Phase 3
fault sweep is more than half — it runs ten complete pipelines.

| Step | Command | Produces | Time |
|---|---|---|---|
| 1 | `python src/anchors/build_anchors.py` | the anchor pack and `docs/financial-anchors.md` | 2 s |
| 2 | `python -m src.generation.build` | 507 native ERP extracts, reference and subledger data | 27 s |
| 3 | `python -m src.generation.validate` | Phase 2 source controls — **80/80** | 8 s |
| 4 | `python -m src.generation.faults` | the ten fault-variant extracts | 5 s |
| 5 | `python -m src.pipeline.run` | ingestion, mapping, the conformed layer, the warehouse — **62/62** | 63 s |
| 6 | `python -m src.pipeline.faults` | ten pipelines over fault trees — **10/10** | 110 s |
| 7 | `python -m src.consol.run` | the consolidation and its controls — **61/61** | 1.2 s |
| 8 | `python -m src.consol.faults` | nineteen consolidations over fault inputs — **19/19** | 45 s |
| 9 | `python -m src.marts.run` | the governed reporting marts and their controls — **36/36** | 4 s |
| 10 | `python -m src.excel.build` | the Excel management reporting workbook | 8 s |
| 11 | `python -m src.excel.qa` | Excel calculation, reconciliation and render — **17/17** | 32 s |
| 12 | `python -m src.integrity.controls` | every declared key, grain and version — **249/249** | 2 s |
| 13 | `python -m src.integrity.faults` | eighteen deliberate breakages — **18/18 detected** | 6 s |
| 14 | `python -m pytest tests -q` | **469** automated tests | 119 s |

A `Makefile` wraps steps 1, 2, 3, 4, 5, 6, 7, 8 and 9 as `anchors`, `build`, `validate`,
`faults`, `pipeline`, `pipeline-faults`, `consolidate`, `consol-faults` and `test`.

Steps 4 and 8 must follow step 2. A fault fixture is a copy of a source extract with one thing
wrong in it; regenerate the source without regenerating the fixtures and every variant becomes
a different dataset rather than the same dataset with one defect. Every control then fires, for
reasons that have nothing to do with the fault — ten detections that are really noise.
`src/pipeline/faults.py` refuses to run on stale fixtures rather than reporting that result.

## 3. Deterministic build identifiers

Three digests, each a property of inputs rather than of a run.

| Digest | Covers | Current value |
|---|---|---|
| Source dataset | every generated extract and reference file | `8013298c3fee35ef25b790104df6c0fd4f6d8bbacb017f709f17fb82ce2644c7` |
| Phase 3 build id | the source digest and the pipeline's configuration | `6e0c519360d3669b` |
| Phase 4 build id | the source digest, the Phase 3 manifest, and the five consolidation configuration files | `a99d9fba5694ad7d` |
| Phase 5 mart build id | the Phase 4 manifest and the reporting configuration | `24b65b7f05f7697d` |
| Workbook build digest | the mart build id and the workbook's own source | `0defa62662371119` |

**These moved at the Phase 5.1 rebaseline.** The source generator was corrected so that
`project_id` is a unique capital-project identifier
([ADR-0026](adr/0026-a-declared-key-is-a-contract.md)), which regenerated the source layer and
re-anchored every downstream id. The previous values were `fd7afb8f…`, `4e860643143938e8`,
`78e406e139662392`, `2caac83888d04d3f` and `ee8bf988…`.

Every one of those digests moving is the mechanism working, not evidence of drift. A digest
moves when a build id moves, so it can neither prove nor disprove that a number changed. What
settles that question is `tools/financial_invariance.py`, which compares values at sixteen
grains joined on the business key and required — and got — a maximum absolute difference of
`0.00` over 297,296 rows, together with `tools/workbook_diff.py`, which found **zero** numeric
differences across 615,262 valued workbook cells.

`data/phase04_manifest.json` also carries a SHA-256 for each of the 15 published consolidation
artefacts. Three consecutive rebuilds produce the same build id and **15 of 15 byte-identical
artefacts**.

Determinism is engineered, not hoped for:

* money is `DECIMAL(18,2)`, never floating point, so a sum does not depend on the order it was
  added in ([ADR-0022](adr/0022-money-is-decimal-and-artefacts-are-totally-ordered.md));
* every published artefact is written under `ORDER BY ALL` — a total order over all columns;
* no aggregate returns an arbitrary row. `any_value()` returns whichever row it saw first, so
  it is banned and `tests/test_phase04a_proof_gate.py` fails if one reappears;
* every identifier is derived from the business keys it represents, never from a counter or a
  clock — **and carries the full grain that makes its subject distinct**, which is the part
  `project_id` got wrong for four phases (ADR-0026);
* every declared key is proved unique over its whole population on every build, and
  every version code is proved to resolve, by `src/integrity/controls.py`;
* random draws come from a single declared master seed.

## 4. The clean-tree expectation

After a complete rebuild, `git status` must be empty.

```bash
python src/anchors/build_anchors.py
python -m src.generation.build
python -m src.pipeline.run
python -m src.consol.run
python -m src.consol.faults
git status --porcelain          # must print nothing
```

That is the strongest single statement about the platform. The committed manifests, control
results, fault results and anchor pack are all outputs, and a rebuild that changed any of them
would show as a modified file. Bulk data is not committed — 166 MB of extracts and the
warehouse are regenerated — but everything needed to prove a rebuild is identical *is*
committed: the manifests with per-file checksums, the control and fault results, the samples
and the small reference masters.

## 5. What to check if a rebuild differs

| Symptom | Likely cause |
|---|---|
| the source digest moved | an anchor or a generation config changed — check `git diff config/` |
| the Phase 4 build id moved but the source digest did not | one of the five consolidation config files changed |
| one artefact's checksum moved | an arbitrary-row aggregate or a missing `ORDER BY ALL` |
| the fault sweep refuses to run | fixtures are older than the extracts — rerun `python -m src.generation.faults` |
| a control fails after a config change | that is the control working; read what it measured against what it expected |
