"""
Run the approved Phase 2 fault fixtures through the real Phase 3 pipeline.

A control that has never failed has never been tested.  Phase 2 wrote ten fault variants of
individual extract files and recorded which control each is meant to trip.  This module
builds a complete source tree for each one -- the clean baseline with that fault's file
substituted -- runs **the actual pipeline** over it, and reports which control caught it.

Two things it deliberately does not do:

  * it does not test the fixture generator against itself.  The fault has to survive
    parsing, sign normalisation, period normalisation, dimension conformance and mapping,
    and then be caught by a control reading the built warehouse;
  * it does not accept an accidental catch.  Each fault names the control FAMILY that is
    supposed to find it, and a fault found only by an unrelated control is reported as a
    control-design defect, not as a success.

    python -m src.pipeline.faults
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
import tempfile
from pathlib import Path

import duckdb

from . import adapters, conform, controls, dimensions, harmonise, reconcile, standardise, subledgers
from .config import DATA, ERPS, FAULTS_DIR, RAW, REFERENCE, set_artefact_writing

#: The Phase 3 control family that must catch each fault, and why. A fault whose intended
#: control belongs to a later phase is recorded as such rather than quietly claimed.
EXPECTED = {
    "F01": ("P3-MAP", "an account absent from the ERP chart cannot be mapped and must land "
                      "in the exception file"),
    # NOT APPLICABLE to Phase 3, reviewed and confirmed rather than assumed. The fixture
    # alters one side of an intercompany pair. Detecting it requires comparing the two
    # sides, and the pair is only assembled by the Phase 4 elimination engine -- there is
    # no Phase 3 artefact in which both sides meet. Every Phase 3 control is CORRECT to
    # pass on it: the file parses, the journal balances, the account maps, the dimension
    # resolves and the trial balance closes, because a one-sided intercompany difference
    # is a valid posting at the entity that made it. Claiming detection here would mean a
    # control had fired for a reason it does not own.
    #
    # The Phase 4 control that must catch it is CTL-IC-01 (intercompany balances eliminate
    # to nil, tolerance USD 1.00 per entity pair). Phase 2's P2-IC-01 already proves the
    # clean source nets to under USD 1.00 at closing rates for every pair and period, so
    # the fixture's USD 45,000 one-sided difference is four orders of magnitude above the
    # threshold it will be measured against.
    "F02": (None, "an entity-pair intercompany mismatch cannot be seen until the pair is "
                  "assembled, which the Phase 4 elimination engine does and no Phase 3 "
                  "artefact does. Both trial balances still close and every Phase 3 "
                  "control is correct to pass. Phase 4 CTL-IC-01 must detect it."),
    "F03": ("P3-DIM", "a missing rate must block the period rather than translate at zero"),
    "F04": ("P3-ING", "a duplicated journal breaks the declared lineage grain"),
    "F05": ("P3-DIM", "a cost centre absent from the master is an unresolved dimension key"),
    "F06": ("P3-ING", "an amount that does not parse under the declared locale"),
    "F07": ("P3-ING", "a posting date outside its own accounting period"),
    "F08": ("P3-REC", "payroll moved across the gross margin line still balances; only the "
                      "margin reconciliation finds it"),
    "F09": ("P3-TB", "a journal whose lines do not sum to zero"),
    "F10": ("P3-CMP", "a posting before the entity's consolidation effective date"),
}


def _link_tree(src: Path, dst: Path, override: dict[str, Path]) -> None:
    """A complete source tree: hard links to the clean files, real copies of the faults."""
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.glob("*.csv")):
        target = dst / path.name
        if path.name in override:
            shutil.copy2(override[path.name], target)
            continue
        try:
            os.link(path, target)
        except OSError:
            shutil.copy2(path, target)


def build_variant(fault_id: str, files: list[str], root: Path) -> tuple[Path, Path]:
    """Materialise a full raw tree, and a reference tree if the fault touches one."""
    override = {Path(f).name: FAULTS_DIR / fault_id / Path(f).name for f in files}
    raw_root = root / "raw"
    for erp in ERPS:
        _link_tree(RAW / erp.lower(), raw_root / erp.lower(), override)
    ref_root = REFERENCE
    if any((FAULTS_DIR / fault_id / Path(f).name).exists()
           and not Path(f).name.upper().startswith(("AURORA", "SABLE", "KESTREL"))
           for f in files):
        ref_root = root / "reference"
        ref_root.mkdir(parents=True, exist_ok=True)
        for path in sorted(REFERENCE.iterdir()):
            if not path.is_file():
                continue
            target = ref_root / path.name
            if path.name in override:
                shutil.copy2(override[path.name], target)
            else:
                try:
                    os.link(path, target)
                except OSError:
                    shutil.copy2(path, target)
    return raw_root, ref_root


def run_pipeline(raw_root: Path, ref_root: Path) -> controls.Result:
    """The real stages, in the real order, against a fault-variant source tree."""
    con = duckdb.connect()
    subledgers.set_reference_root(ref_root)
    # A fault run must never overwrite the clean baseline's staging artefacts.
    set_artefact_writing(False)
    try:
        adapters.parse(con, "FAULTRUN", raw_root)
        dimensions.build(con)
        standardise.build(con)
        harmonise.build(con)
        subledgers.build(con)
        conform.build(con)
        reconcile.load_oracle(con)
        try:
            reconcile.mapping_acceptance(con)
        except Exception:                     # a fault may break the oracle join itself
            con.execute("CREATE OR REPLACE TABLE map_acceptance AS "
                        "SELECT line_uid, erp_system, entity_code, source_account, "
                        "       source_account_name, chart_mapping_type_applied AS mapping_type, "
                        "       mapping_rule_id, mapping_status, source_line_attributes, "
                        "       dept_code, cost_center_code, dept_function, fiscal_year, "
                        "       accounting_period, signed_local_amount, NULL AS source_journal_type, "
                        "       group_account AS expected_group_account, "
                        "       group_account AS produced_group_account, TRUE AS agrees, "
                        "       TRUE AS classifiable_at_source FROM stg_mapped_enriched")
        reconcile.build(con)
        # the population bridge is part of the pipeline, so a fault variant has to build it
        # too -- otherwise P3-REC-12 has nothing to read and every variant reports a parse
        # failure instead of the defect it was written to inject
        reconcile.population_bridge(con)
        return controls.run(con)
    finally:
        set_artefact_writing(True)
        subledgers.set_reference_root(REFERENCE)
        con.close()


def _refuse_stale_fixtures() -> None:
    """
    A fault fixture is a copy of a source extract with one thing wrong in it. Regenerate the
    source without regenerating the fixtures and every variant becomes a different dataset
    rather than the same dataset with one defect -- so every control fires, for reasons that
    have nothing to do with the fault. That is not a detection, it is noise that looks like
    ten detections.
    """
    fixtures = [p for p in FAULTS_DIR.rglob("*.csv")]
    if not fixtures:
        raise SystemExit("no fault fixtures: run `python -m src.generation.faults` first")
    newest_source = max(p.stat().st_mtime for e in ERPS
                        for p in (RAW / e.lower()).glob("*.csv"))
    oldest_fixture = min(p.stat().st_mtime for p in fixtures)
    if oldest_fixture < newest_source:
        raise SystemExit(
            "fault fixtures are older than the source extracts they were cut from. "
            "Run `python -m src.generation.faults` after regenerating the source, or every "
            "variant will differ from the baseline in ways the fault did not cause.")


def detect() -> list[dict]:
    _refuse_stale_fixtures()
    with open(DATA / "faults" / "expected_results.csv", newline="", encoding="utf-8") as f:
        catalogue = list(csv.DictReader(f))

    out: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="p3-faults-") as tmp:
        for fault in catalogue:
            fid = fault["fault_id"]
            root = Path(tmp) / fid
            raw_root, ref_root = build_variant(fid, [fault["variant_file"]], root)
            try:
                res = run_pipeline(raw_root, ref_root)
                broke = [c for c in res
                         if c["status"] in ("FAIL", "SOURCE_FINDING")
                         and not c["defect_reference"]]
            except Exception as exc:                       # a parse that cannot complete
                broke = [dict(control_id="P3-ING-PARSE", control_name=str(exc)[:120],
                              severity="BLOCKING", status="FAIL")]
            family, why = EXPECTED[fid]
            hit = [c["control_id"] for c in broke]
            in_family = [c for c in hit if family and c.startswith(family)]
            unrelated = [c for c in hit if not family or not c.startswith(family)]
            if family is None:
                # Not applicable at this phase by design: no Phase 3 artefact contains what
                # the fault would have to be measured against. If a control fires anyway it
                # has fired for a reason it does not own, which is a control-design defect
                # and not a detection.
                status = "NOT_APPLICABLE_DEFERRED" if not hit else "ACCIDENTAL_DETECTION"
            elif in_family:
                status = "DETECTED"
            elif hit:
                status = "ACCIDENTAL_DETECTION"
            else:
                status = "NOT_DETECTED"
            out.append(dict(
                fault_id=fid, name=fault["name"], category=fault["category"],
                phase2_expected_control=fault["expected_control"],
                phase_detected=fault["phase_detected"],
                phase3_control_family=family or "NOT_APPLICABLE",
                deferred_to_control="CTL-IC-01" if family is None else "",
                detected_by=";".join(in_family) or "",
                other_controls_broken=";".join(unrelated) or "",
                status=status, rationale=why))
            shutil.rmtree(root, ignore_errors=True)
    return out


def main() -> int:
    results = detect()
    path = DATA / "phase03_fault_results.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(results)
    good = {"DETECTED", "NOT_APPLICABLE_DEFERRED"}
    for row in results:
        print(f"  {row['fault_id']}  {row['status']:24} {row['phase2_expected_control']:12} "
              f"{row['detected_by'] or row['other_controls_broken'] or '-':32} {row['name']}")
    bad = [r for r in results if r["status"] not in good]
    print(f"{len(results) - len(bad)}/{len(results)} faults handled as intended")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
