"""
Phase 6A orchestrator.

    python -m src.powerbi.run              generate, deploy if an engine is reachable, control
    python -m src.powerbi.run --no-deploy  generate and run only what needs no engine
    python -m src.powerbi.run --launch     start Power BI Desktop first, then the above

The semantic model is generated from `config.py` and `measures.py` into two forms that cannot
disagree because they come from one declaration: the **PBIP/TMDL project**, which is what a
person opens and what git reviews, and a **TMSL deployment** to a live Analysis Services
instance, which is what proves the model actually loads and evaluates.

Both matter. TMDL is text and text always parses; only an engine can tell you that a
relationship names a column which does not exist, or that every statement measure has been
quietly summing two reporting bases and reporting twice the truth. Both of those were in this
model until it was deployed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import duckdb

from .. import lineage

from . import config as C
from . import controls, dax, deploy, model
from .measures import MEASURES

BUILD_INPUTS = (
    Path(__file__).with_name("config.py"),
    Path(__file__).with_name("measures.py"),
    Path(__file__).with_name("model.py"),
)

APPX = ("shell:AppsFolder\\Microsoft.MicrosoftPowerBIDesktop_8wekyb3d8bbwe"
        "!Microsoft.MicrosoftPowerBIDesktop")


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


def launch_desktop(wait: int = 120) -> bool:
    """Start Desktop so an Analysis Services instance exists to deploy into."""
    if dax.find_port():
        return True
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Start-Process -FilePath '{APPX}'"],
                   capture_output=True, text=True, timeout=60)
    deadline = time.time() + wait
    while time.time() < deadline:
        if dax.find_port():
            return True
        time.sleep(5)
    return False


def project_digest() -> str:
    """
    A digest of the generated project text -- what a reviewer would diff.

    Canonical, for the same reason the build ids are: the PBIP project is text under version
    control, and a checkout that changes its line endings has not changed the model.
    """
    files = sorted(p for p in C.PBIP_DIR.rglob("*")
                   if p.is_file() and p.suffix in (".tmdl", ".pbip", ".pbism", ".pbir",
                                                   ".json"))
    return lineage.build_id(files)


def run(deploy_model: bool = True, launch: bool = False) -> dict:
    t0 = time.time()
    con = duckdb.connect(str(C.DUCKDB_PATH))

    dimensions = model.publish_dimensions(con)
    summary = model.generate(con)
    generated = round(time.time() - t0, 2)

    if launch:
        launch_desktop()

    deployed, message = False, "not attempted"
    if deploy_model:
        t1 = time.time()
        deployed, message = deploy.deploy(con)
        summary["deploy_seconds"] = round(time.time() - t1, 2)
    print(f"deploy: {deployed} -- {message}")

    t2 = time.time()
    res = controls.run(con)
    controls.write(res)
    controls.report(res)
    summary["control_seconds"] = round(time.time() - t2, 2)

    if C.SEMANTIC_DIR.exists():
        manifest = {
            "phase": "6A",
            "build_id": build_id(),
            "project_digest": project_digest(),
            "reporting_mart_build_id": json.loads(
                (C.DATA / "phase05_manifest.json").read_text(encoding="utf-8"))["build_id"],
            "tables": summary["tables"],
            "measures": summary["measures"],
            "relationships": summary["relationships"],
            "inactive_relationships": summary["inactive_relationships"],
            "semantic_dimension_rows": dimensions,
            "deployed": deployed,
            "controls": {"total": len(res),
                         "passed": sum(r["status"] == "PASS" for r in res),
                         "not_executed": len(res.not_executed),
                         "failed": len(res.failed)},
            "artefacts": {
                f"35_semantic/{name}.parquet": _sha256(C.SEMANTIC_DIR / f"{name}.parquet")
                for name in sorted(dimensions)
            },
        }
        C.MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")

    con.close()
    summary["generate_seconds"] = generated
    summary["seconds"] = round(time.time() - t0, 2)
    summary["deployed"] = deployed
    summary["failed"] = len(res.failed)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main(argv: list[str]) -> int:
    res = run(deploy_model="--no-deploy" not in argv, launch="--launch" in argv)
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
