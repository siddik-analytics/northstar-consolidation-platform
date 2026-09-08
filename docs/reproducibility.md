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
| 9 | `python -m pytest tests -q` | **421** automated tests | 45 s |

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
| Source dataset | every generated extract and reference file | `fd7afb8fd7dc80580d4ca64016ae9ca51a96209c546555dfff01813d1a525836` |
| Phase 3 build id | the source digest and the pipeline's configuration | `4e860643143938e8` |
| Phase 4 build id | the source digest, the Phase 3 manifest, and the five consolidation configuration files | `78e406e139662392` |

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
  clock;
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
