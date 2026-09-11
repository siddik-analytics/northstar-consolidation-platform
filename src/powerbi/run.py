"""
Phase 6A orchestrator.

    python -m src.powerbi.run              generate, deploy if an engine is reachable, control
    python -m src.powerbi.run --no-deploy  generate and run only what needs no engine
    python -m src.powerbi.run --launch     start Power BI Desktop first, then the above
    python -m src.powerbi.run --native     also exercise the report in Desktop (Phase 6B)
    python -m src.powerbi.run --no-fixtures   skip the Phase 6B report fixtures (~10 min)

Phase 6B runs after the semantic phase in the same command: the report's own controls, its
fixtures, the object inventory and -- with `--native` -- the pass through Power BI Desktop
that reads what was actually rendered.

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
from . import controls, dax, deploy, desktop, model
from .measures import MEASURES, PERIOD_BASIS_ROWS

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


def definition_digest() -> str:
    """
    A digest of the model's **definitions** only: every measure (name, DAX, format, folder,
    description), every table specification, every relationship and its rationale, the
    period-basis rows and the reporting close.

    It deliberately excludes container and display metadata -- the name of the table the
    measures live on, lineage tags, annotations, file layout -- so that a change like Phase
    6A.2's (rename the measures host, move relationship rationale into an annotation) leaves
    it untouched while `project_digest()` moves. Metadata drift and definition drift are
    different claims and get different digests.
    """
    payload = {
        "measures": [list(m) for m in MEASURES],
        "tables": [dict(t) for t in C.TABLES],
        "relationships": [list(r) for r in C.RELATIONSHIPS],
        "inactive_relationships": [list(r) for r in C.INACTIVE_RELATIONSHIPS],
        "period_basis": [list(r) for r in PERIOD_BASIS_ROWS],
        "report_period": C.REPORT_PERIOD,
    }
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


REPORT_INPUTS = tuple(sorted((Path(__file__).parent / "report").glob("*.py")))


def report_build_id() -> str:
    """The Phase 6B lineage id: the report package's declared inputs, canonically hashed."""
    return lineage.build_id(REPORT_INPUTS)



def _native_summary() -> dict:
    from .report.controls import NATIVE_QA
    if not NATIVE_QA.exists():
        return {}
    qa = json.loads(NATIVE_QA.read_text(encoding="utf-8"))
    return {"project_digest": qa.get("project_digest"), "desktop": qa.get("desktop"),
            "visual_errors": sum(len(v) for v in qa.get("visual_errors", {}).values()),
            "navigation": qa.get("navigation", {}).get("passed"),
            "unit_narrowed": qa.get("unit_slicer", {}).get("narrowed"),
            "cutoff": qa.get("cutoff", {}).get("stops_at_close"),
            "seconds": qa.get("seconds")}


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
    controls.DESKTOP_OPEN = deploy_model and "--no-desktop" not in sys.argv
    res = controls.run(con)
    controls.write(res)
    controls.report(res)
    # The report's Consolidation & Controls and Lineage pages display the registers. Write
    # the report again now that this run's register exists, so the page says what the run
    # found rather than what the previous one did.
    from .report import build as report_build
    report_build.generate(C.REPORT_DIR)
    summary["control_seconds"] = round(time.time() - t2, 2)

    # ---- Phase 6B: the report on the model
    t3 = time.time()
    from .report import controls as RK
    from .report import faults as RF
    rres = RK.run(con, native=False)
    RK.write(rres)
    fixtures = [] if "--no-fixtures" in sys.argv else RF.run(con)
    if fixtures:
        RF.write(fixtures)
    # the Consolidation & Controls page now has this phase's register to read
    report_build.generate(C.REPORT_DIR)
    if "--native" in sys.argv:
        from .report import native_qa
        native_qa.run()
    rres = RK.run(con, native=True)
    RK.write(rres)
    # ---- Phase 6B.1: hierarchy sort grain and layer-bridge scope
    from . import controls_b1 as K1
    from . import faults_b1 as F1
    b1 = K1.run(con)
    K1.write(b1)
    b1_fixtures = [] if "--no-fixtures" in sys.argv else F1.run(con)
    if b1_fixtures:
        F1.write(b1_fixtures)
    K1.report(b1)
    summary["b1_failed"] = len(b1.failed)
    report_build.generate(C.REPORT_DIR)   # and the page reads the registers this run wrote
    inventory = RK.inventory()
    RK.INVENTORY.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    RK.report(rres)
    summary["report_control_seconds"] = round(time.time() - t3, 2)
    summary["report_failed"] = len(rres.failed)

    if C.SEMANTIC_DIR.exists():
        manifest = {
            "phase": "6A.3",
            "build_id": build_id(),
            "project_digest": project_digest(),
            "definition_digest": definition_digest(),
            "measures_table": C.MEASURES_TABLE,
            "desktop": desktop.version(),
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

    report_manifest = {
        "phase": "6B",
        "build_id": report_build_id(),
        "project_digest": project_digest(),
        "semantic_build_id": build_id(),
        "desktop": desktop.version(),
        "pages": inventory["visuals"] and len(inventory["pages"]),
        "visuals": inventory["visuals"],
        "objects": inventory["total"],
        "controls": {"total": len(rres),
                     "passed": sum(r["status"] == "PASS" for r in rres),
                     "not_executed": len(rres.not_executed),
                     "failed": len(rres.failed)},
        "fixtures": {"total": len(fixtures),
                     "detected": sum(f["status"] == "DETECTED" for f in fixtures)},
        "native": _native_summary(),
        "workbook_digest": json.loads(
            (C.DATA / "phase05_workbook_manifest.json").read_text(encoding="utf-8")
        ).get("build_digest", "")[:16],
    }
    RK.MANIFEST.write_text(json.dumps(report_manifest, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    (C.DATA / "phase06b1_manifest.json").write_text(json.dumps({
        "phase": "6B.1",
        "definition_digest": definition_digest(),
        "report_build_id": report_build_id(),
        "project_digest": project_digest(),
        "controls": {"total": len(b1), "passed": sum(r["status"] == "PASS" for r in b1),
                     "not_executed": len(b1.not_executed), "failed": len(b1.failed)},
        "fixtures": {"total": len(b1_fixtures),
                     "detected": sum(f["status"] == "DETECTED" for f in b1_fixtures)},
        "workbook_digest": report_manifest["workbook_digest"],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    con.close()
    summary["generate_seconds"] = generated
    summary["seconds"] = round(time.time() - t0, 2)
    summary["deployed"] = deployed
    summary["failed"] = len(res.failed)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main(argv: list[str]) -> int:
    res = run(deploy_model="--no-deploy" not in argv, launch="--launch" in argv)
    return 1 if res["failed"] or res.get("report_failed") or res.get("b1_failed") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
