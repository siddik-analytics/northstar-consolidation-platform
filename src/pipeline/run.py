"""
Phase 3 pipeline orchestrator.

    python -m src.pipeline.run                 full run against the clean baseline
    python -m src.pipeline.run --raw <dir>     run against a fault-variant source tree
    python -m src.pipeline.run --no-controls   build only

    raw -> parsed -> standardised -> mapped -> conformed

Determinism.  Every stage is a deterministic function of the frozen source layer and the
committed configuration, so a rebuild produces byte-identical outputs.  The build id is
derived from the Phase 2 dataset digest and the mapping configuration rather than from the
clock: a timestamp in a committed artefact would leave the working tree dirty after every
run and destroy the reproducibility it was meant to record.  The wall-clock duration is
printed and never written.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import duckdb

from . import adapters, conform, controls, dimensions, harmonise, reconcile, standardise, subledgers
from .config import (CONFIG, DATA, DUCKDB_PATH, LAYER_DIR, MANIFEST, STAGING,
                     ensure_dirs)

#: Files whose content defines the build. A change to any of them changes the build id.
BUILD_INPUTS = [
    DATA / "samples" / "build_digest.txt",           # the frozen Phase 2 dataset digest
    CONFIG / "mapping" / "mapping_rules.csv",
    CONFIG / "coa" / "group_coa.csv",
    CONFIG / "coa" / "source_coa_aurora.csv",
    CONFIG / "coa" / "source_coa_sable.csv",
    CONFIG / "coa" / "source_coa_kestrel.csv",
    CONFIG / "entities" / "entity_master.csv",
]


def build_id() -> str:
    h = hashlib.sha256()
    for path in BUILD_INPUTS:
        h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(raw_root: Path | None = None, with_controls: bool = True) -> dict:
    t0 = time.time()
    ensure_dirs()
    if DUCKDB_PATH.exists():
        DUCKDB_PATH.unlink()
    con = duckdb.connect(str(DUCKDB_PATH))
    con.execute("SET preserve_insertion_order = true")

    bid = build_id()
    counts: dict[str, int] = {}
    stage_seconds: dict[str, float] = {}

    def stage(name, fn):
        t = time.time()
        result = fn()
        stage_seconds[name] = round(time.time() - t, 2)
        if isinstance(result, dict):
            counts.update(result)
        elif isinstance(result, int):
            counts[name] = result
        return result

    stage("parsed", lambda: adapters.parse(con, bid, raw_root))
    stage("dimensions", lambda: dimensions.build(con))
    stage("standardised", lambda: {"stg_standardised": standardise.build(con)})
    stage("mapped", lambda: {f"mapping_status::{k}": v
                             for k, v in harmonise.build(con).items()})
    stage("subledgers", lambda: subledgers.build(con))
    stage("conformed", lambda: conform.build(con))

    def acceptance():
        reconcile.load_oracle(con)
        acc = reconcile.mapping_acceptance(con)
        reconcile.build(con)
        return acc

    acc = stage("reconciliation", acceptance)

    manifest = {
        "phase": 3,
        "build_id": bid,
        "source_layer_digest": _phase2_digest(),
        "row_counts": counts,
        "mapping_acceptance": acc,
        "artefacts": _artefact_checksums(),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps({k: v for k, v in manifest.items() if k != "artefacts"}, indent=2))
    print("stage seconds : " + json.dumps(stage_seconds))
    print(f"total seconds : {round(time.time() - t0, 1)}")

    if with_controls:
        res = controls.run(con)
        controls.write(res)
        controls.report(res)
        con.close()
        if res.failed:
            raise SystemExit(1)
    con.close()
    return manifest


def _phase2_digest() -> str:
    text = (DATA / "samples" / "build_digest.txt").read_text(encoding="utf-8")
    return text.splitlines()[0].split("=", 1)[1]


def _artefact_checksums() -> dict[str, str]:
    out: dict[str, str] = {}
    for base in sorted(LAYER_DIR.values()):
        for path in sorted(base.rglob("*.parquet")):
            out[path.relative_to(DATA).as_posix()] = _sha256(path)
    for path in sorted(STAGING.rglob("exceptions/*.csv")):
        out[path.relative_to(DATA).as_posix()] = _sha256(path)
    return out


def main(argv: list[str]) -> int:
    raw_root = None
    if "--raw" in argv:
        raw_root = Path(argv[argv.index("--raw") + 1])
    run(raw_root=raw_root, with_controls="--no-controls" not in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
