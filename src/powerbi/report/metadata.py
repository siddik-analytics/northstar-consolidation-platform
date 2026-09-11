"""
The governed numbers the Consolidation & Controls and Lineage pages display.

Nothing on those two pages is typed. Every count, digest and build id is read from the
platform's own registers and manifests at generation time, and `P6B-08` reads the same
registers at control time and fails if a displayed value has drifted from them. The
semantic model carries no control register, so these values travel as report text -- which
is exactly why they have to be generated and controlled rather than written.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ...lineage import build_id as _build_id
from .. import config as C

DATA = C.DATA


def _rows(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _manifest(name: str) -> dict:
    path = DATA / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def control_status() -> list[dict]:
    """One row per control family the platform runs, as the registers state them."""
    families = [
        ("Phase 2", "Generated source systems", "phase02_control_results.csv", None),
        ("Phase 3", "Ingestion, mapping, conformed layer", "phase03_control_results.csv",
         "phase03_fault_results.csv"),
        ("Phase 4", "Consolidation engine", "phase04_control_results.csv",
         "phase04_fault_results.csv"),
        ("Phase 5", "Reporting marts", "phase05_control_results.csv", None),
        ("Phase 5.1", "Keys, grain and versions", "phase07_key_control_results.csv",
         "phase07_key_fault_results.csv"),
        ("Phase 6A", "Semantic model and native project", "phase06a_control_results.csv",
         "phase06a_fault_results.csv"),
        ("Phase 6B", "Report on the model", "phase06b_control_results.csv",
         "phase06b_fault_results.csv"),
        ("Phase 6B.1", "Hierarchy sort grain, bridge scope", "phase06b1_control_results.csv",
         "phase06b1_fault_results.csv"),
    ]
    out = []
    for phase, scope, controls, faults in families:
        rows = _rows(controls)
        total = len(rows)
        passed = sum(r.get("status") == "PASS" for r in rows)
        blocking = sum(r.get("status") == "FAIL" and r.get("severity") == "BLOCKING" for r in rows)
        fixtures = _rows(faults) if faults else []
        # "handled as intended" is each register's own vocabulary: detected, deliberately
        # deferred to a later phase, suppressed by design, or proven as a separation.
        handled = ("DETECTED", "NOT_APPLICABLE_DEFERRED", "SUPPRESSED", "SEPARATION_PROVEN")
        detected = sum(r.get("status") in handled for r in fixtures)
        if not rows:
            continue   # a register that does not exist yet is not a row of dashes
        out.append(dict(phase=phase, scope=scope, controls=total, passed=passed,
                        blocking=blocking, fixtures=len(fixtures), detected=detected,
                        status="PASS" if total and not blocking and passed == total else
                               ("FAIL" if blocking else "—")))
    return out


def reconciliations() -> list[dict]:
    """The cross-artefact reconciliations, as the registers state them."""
    qa = _rows("phase05_workbook_qa.csv")
    excel = [dict(status="PASS" if r.get("detail", "").rstrip().endswith("PASS") else "FAIL")
             for r in qa if r.get("kind") == "reconciliation"]
    pbi = _rows("phase06a_control_results.csv")
    xar = [r for r in pbi if r["control_id"].startswith("P6-XAR")]
    xls = [r for r in pbi if r["control_id"].startswith("P6-XLS")]
    pbip = [r for r in pbi if r["control_id"].startswith("P6-PBIP")]
    rpt = _rows("phase06b_control_results.csv")
    b1 = _rows("phase06b1_control_results.csv")
    bridge = [r for r in b1 if r["control_id"].startswith("P6B1-BR")]
    recon = [r for r in rpt if r["control_id"] >= "P6B-30"]
    native = [r for r in rpt if r["control_id"] in ("P6B-20", "P6B-21", "P6B-22", "P6B-23",
                                                     "P6B-25")]
    return [
        dict(name="Excel workbook to marts", passed=sum(r.get("status") == "PASS" for r in excel),
             total=len(excel)),
        dict(name="Power BI to marts", passed=sum(r["status"] == "PASS" for r in xar),
             total=len(xar)),
        dict(name="Power BI to Excel", passed=sum(r["status"] == "PASS" for r in xls),
             total=len(xls)),
        dict(name="Native project (Desktop)", passed=sum(r["status"] == "PASS" for r in pbip),
             total=len(pbip), not_executed=sum(r["status"] == "NOT_EXECUTED" for r in pbip)),
    ] + ([
        dict(name="Report scope to engine to marts", passed=sum(r["status"] == "PASS" for r in recon),
             total=len(recon), not_executed=sum(r["status"] == "NOT_EXECUTED" for r in recon)),
        dict(name="Native render (Desktop)", passed=sum(r["status"] == "PASS" for r in native),
             total=len(native), not_executed=sum(r["status"] == "NOT_EXECUTED" for r in native)),
    ] if rpt else []) + ([
        dict(name="Layer bridge to the statements", passed=sum(r["status"] == "PASS" for r in bridge),
             total=len(bridge), not_executed=sum(r["status"] == "NOT_EXECUTED" for r in bridge)),
    ] if b1 else [])


def lineage() -> dict:
    """Build ids and digests along the chain, from the manifests."""
    m3, m4, m5, m6 = (_manifest(n) for n in ("phase03_manifest.json", "phase04_manifest.json",
                                             "phase05_manifest.json", "phase06a_manifest.json"))
    wb = _manifest("phase05_workbook_manifest.json")
    return dict(
        source_digest=(m3.get("source_layer_digest") or "")[:16],
        phase03=m3.get("build_id", ""),
        phase04=m4.get("build_id", ""),
        phase05=m5.get("build_id", ""),
        phase06a=m6.get("build_id", ""),
        # the report's own build id, computed here rather than read from a manifest: a
        # manifest written after generation can only hold the digest of the previous one
        report_build_id=_build_id(sorted(Path(__file__).parent.glob("*.py"))),
        definition_digest=m6.get("definition_digest", ""),
        workbook_digest=(wb.get("build_digest") or "")[:16],
        desktop=m6.get("desktop", ""),
        measures_table=m6.get("measures_table", C.MEASURES_TABLE),
        measures=m6.get("measures", 0),
        relationships=m6.get("relationships", 0),
        inactive=m6.get("inactive_relationships", 0),
        semantic_controls=(m6.get("controls") or {}).get("total", 0),
        semantic_passed=(m6.get("controls") or {}).get("passed", 0),
        generated=m6.get("generated_at") or m6.get("timestamp") or "",
    )
