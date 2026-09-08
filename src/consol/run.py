"""
Phase 4 consolidation orchestrator.

    python -m src.consol.run                 full consolidation of the Actual scenario
    python -m src.consol.run --no-controls   build only

    layer 1 (frozen, from Phase 3.1)
      -> translate      local -> USD per the FX policy; derive CTA
      -> eliminate      intercompany, by entity pair
      -> investments    investment elimination, PPA, goodwill, intangible amortisation
      -> nci            the non-controlling interest roll-forward
      -> pup            unrealised profit in inventory
      -> cta            post the derived CTA to layer 5
      -> mgmt           management adjustments, layer 4
      -> statements     the consolidated fact, the statements and the bridges

The order is not arbitrary. NCI needs the consolidated result of its subsidiary, which needs
the eliminations; the CTA posting needs the derivation; the statements need everything. Each
step is a deterministic function of the frozen source layer and the committed configuration,
so a rebuild produces byte-identical output. The build id is derived from those inputs rather
than from the clock.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import duckdb

from . import (controls, cta, eliminate, investments, journals, mgmt, nci, ownership, pup,
               statements, translate)
from .config import (CONFIG, CONSOL_DIR, DATA, DUCKDB_PATH, MANIFEST, ensure_dirs,
                     writing_artefacts)

BUILD_INPUTS = [
    DATA / "samples" / "build_digest.txt",                 # the frozen source layer
    DATA / "phase03_manifest.json",                        # the frozen conformed layer
    CONFIG / "consolidation" / "acquisition.csv",
    CONFIG / "consolidation" / "ppa_intangible.csv",
    CONFIG / "consolidation" / "management_adjustment.csv",
    CONFIG / "entities" / "ownership_history.csv",
    CONFIG / "entities" / "investment_register.csv",
    CONFIG / "fx" / "fx_translation_policy.csv",
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


def run(con: duckdb.DuckDBPyConnection | None = None, with_controls: bool = True) -> dict:
    t0 = time.time()
    ensure_dirs()
    own = con is None
    con = con or duckdb.connect(str(DUCKDB_PATH))
    counts: dict[str, int] = {}
    timing: dict[str, float] = {}

    def stage(name, fn):
        t = time.time()
        result = fn() or {}
        counts.update(result)
        timing[name] = round(time.time() - t, 2)
        return result

    # A consolidation always starts from an empty journal table. Appending to whatever was
    # there before would double every entry, and every total would still look plausible.
    journals.init(con)

    stage("ownership", lambda: ownership.build(con))
    stage("translate", lambda: {**translate.build(con), **translate.cta_movement(con)})
    stage("eliminate", lambda: eliminate.build(con))
    stage("investments", lambda: investments.build(con))
    stage("nci", lambda: nci.build(con))
    stage("pup", lambda: pup.build(con))
    stage("cta", lambda: cta.build(con))
    stage("mgmt", lambda: mgmt.build(con))
    stage("statements", lambda: statements.build(con))

    counts.update(journals.counts_by_layer(con))

    result = {}
    if with_controls:
        res = controls.run(con)
        controls.write(con, res)
        controls.report(res)
        result["controls"] = {"total": len(res), "failed": len(res.failed),
                              "findings": len(res.findings)}

    if writing_artefacts():
        manifest = {
            "phase": 4,
            "build_id": build_id(),
            "source_layer_digest": (DATA / "samples" / "build_digest.txt")
                .read_text(encoding="utf-8").splitlines()[0].split("=", 1)[1],
            "row_counts": counts,
            "artefacts": _artefact_checksums(),
        }
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(json.dumps({k: v for k, v in counts.items() if not k.startswith("L")},
                         indent=2, sort_keys=True))

    print("stage seconds :", json.dumps(timing))
    print(f"total seconds : {time.time() - t0:.1f}")
    if own:
        con.close()
    return result


def _artefact_checksums() -> dict[str, str]:
    out = {}
    for path in sorted(CONSOL_DIR.glob("*.parquet")):
        out[f"10_staging/05_consolidated/{path.name}"] = _sha256(path)
    for name in ("phase04_control_results.csv", "phase04_reconciliation.csv"):
        p = DATA / name
        if p.exists():
            out[name] = _sha256(p)
    return out


def main(argv: list[str]) -> int:
    res = run(with_controls="--no-controls" not in argv)
    failed = res.get("controls", {}).get("failed", 0)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
