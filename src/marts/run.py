"""
Phase 5 reporting-mart orchestrator.

    python -m src.marts.run                 build the marts, run the controls, export
    python -m src.marts.run --no-controls   build only

Deterministic in the same way everything upstream is: the marts are a function of the frozen
consolidation and the committed reporting configuration, every artefact is written under
`ORDER BY ALL`, and the build id is a digest of the inputs rather than of the run.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import duckdb

from .. import lineage

from . import build, controls
from .config import (CONTROL_RESULTS, DATA, DUCKDB_PATH, MANIFEST, MARTS_DIR, ensure_dirs,
                     writing_artefacts)

#: Every mart published for downstream consumption. Excel and, later, Power BI read these.
PUBLISHED = (
    "dim_report_scenario", "dim_report_measure", "dim_report_comparison", "dim_report_ratio",
    "mart_financial_monthly", "mart_financial_ytd", "mart_variance",
    "mart_business_unit", "mart_entity_performance",
    "mart_balance_sheet", "mart_cash_flow", "mart_working_capital",
    "mart_headcount", "mart_capex", "mart_debt", "mart_covenants", "mart_fx",
    "mart_management_adjustments", "mart_consolidation_bridge",
)

BUILD_INPUTS = (
    DATA / "phase04_manifest.json",
    Path(__file__).with_name("config.py"),
    Path(__file__).with_name("build.py"),
)


def build_id() -> str:
    """
    A lineage id for this phase's declared inputs, from the shared canonical hasher.

    Canonical, not byte-for-byte: line endings are folded so the id survives a checkout. See
    `src/lineage/digest.py` and defect P6-D-02. The published artefacts below keep their
    byte-for-byte digests, because those answer a different question.
    """
    return lineage.build_id(BUILD_INPUTS)


def _sha256(path: Path) -> str:
    """A published artefact's exact byte digest. Deliberately NOT canonicalised."""
    return lineage.exact_digest(path)


def run(con: duckdb.DuckDBPyConnection | None = None, with_controls: bool = True) -> dict:
    t0 = time.time()
    ensure_dirs()
    own = con is None
    con = con or duckdb.connect(str(DUCKDB_PATH))

    counts = build.build(con)
    result: dict = {"row_counts": counts}

    if with_controls:
        res = controls.run(con)
        controls.write(con, res)
        controls.report(res)
        result["controls"] = {"total": len(res), "failed": len(res.failed)}

    if writing_artefacts():
        for name in PUBLISHED:
            out = MARTS_DIR / f"{name}.parquet"
            con.execute(f"COPY (SELECT * FROM {name} ORDER BY ALL) TO '{out.as_posix()}' "
                        f"(FORMAT PARQUET, COMPRESSION ZSTD)")
        consol = json.loads((DATA / "phase04_manifest.json").read_text(encoding="utf-8"))
        manifest = {
            "phase": 5,
            "build_id": build_id(),
            "consolidation_build_id": consol["build_id"],
            "source_layer_digest": consol["source_layer_digest"],
            "row_counts": counts,
            "artefacts": {
                f"30_marts/{name}.parquet": _sha256(MARTS_DIR / f"{name}.parquet")
                for name in PUBLISHED
            },
        }
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")

    result["seconds"] = round(time.time() - t0, 2)
    print(json.dumps(counts, indent=2, sort_keys=True))
    print(f"marts built in {result['seconds']}s")
    if own:
        con.close()
    return result


def main(argv: list[str]) -> int:
    res = run(with_controls="--no-controls" not in argv)
    return 1 if res.get("controls", {}).get("failed", 0) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
