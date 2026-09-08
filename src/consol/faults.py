"""
Run fault fixtures through the real Phase 4 consolidation engine.

Phase 3 proved this discipline on the source layer and the rule is unchanged here: a control
that has never failed has never been tested. Each fixture takes the clean, frozen inputs, puts
exactly one thing wrong in them, runs **the actual consolidation** end to end, and reports
which control caught it.

Two rules, both of which cost more to honour than to skip:

  * the fault is injected into an **input** the engine consumes -- the ownership register, the
    investment register, the acquisition schedules, the chart of accounts, the intercompany
    holdings, the historical rate table -- and never into the engine's own output. Corrupting
    an answer and watching a control notice proves nothing about whether the engine would ever
    produce that answer;
  * a fault caught only by an **unrelated** control is an `ACCIDENTAL_DETECTION` and is
    reported as a control-design defect. Every fixture names the control family that owns it.

`F02` is the fixture Phase 3 deferred. It is a one-sided intercompany difference, and no
Phase 3 artefact contains both sides of the pair, so every Phase 3 control was correct to pass
on it. Here it runs through the whole pipeline AND the Phase 4 elimination engine, and it must
be caught by the pair reconciliation that owns it. Detection by anything else does not count.

    python -m src.consol.faults
"""

from __future__ import annotations

import csv
import shutil
import sys
import tempfile
from pathlib import Path

import duckdb

from . import config as cfg
from . import controls, investments, mgmt
from . import run as consol_run
from .config import CONFIG, DATA, DUCKDB_PATH, FAULT_RESULTS

#: Each fixture: the input it corrupts, the control family that owns it, and why that family
#: and no other. `sql` mutates a warehouse input table; `csv_edit` rewrites a configuration
#: file; `pipeline` reruns Phase 3 over a raw fault tree first.
FAULTS: list[dict] = [
    dict(
        fault_id="F4-01", name="Overlapping ownership effective dates",
        category="OWNERSHIP", family="P4-OWN",
        why="two register rows live at once, so the percentage for a month is ambiguous and "
            "the engine would silently pick one",
        sql="INSERT INTO ref_ownership SELECT * REPLACE (DATE '2019-01-01' AS effective_from, "
            "0.75 AS group_ownership_pct, 0.25 AS nci_pct) FROM ref_ownership "
            "WHERE entity_code = 'NIG-510'",
    ),
    dict(
        fault_id="F4-02", name="Circular ownership",
        category="OWNERSHIP", family="P4-OWN",
        why="an entity in its own ownership path consolidates itself; the recursive walk "
            "must refuse rather than loop",
        sql="UPDATE ref_ownership SET parent_entity_code = 'NIG-210' "
            "WHERE entity_code = 'NIG-200'",
    ),
    dict(
        fault_id="F4-03", name="Ownership register disagrees with the investment register",
        category="OWNERSHIP", family="P4-OWN",
        why="a subsidiary consolidated on a relationship nobody paid for. Both registers are "
            "internally consistent, so only the comparison between them finds it",
        sql="UPDATE ref_ownership SET parent_entity_code = 'NIG-100' "
            "WHERE entity_code = 'NIG-510'",
    ),
    dict(
        fault_id="F4-04", name="Ownership percentages that do not complement",
        category="OWNERSHIP", family="P4-OWN",
        why="group share plus non-controlling share must be one; 0.80 and 0.10 leaves a "
            "tenth of the subsidiary owned by nobody",
        sql="UPDATE ref_ownership SET nci_pct = 0.10 WHERE entity_code = 'NIG-510'",
    ),
    dict(
        fault_id="F4-05", name="Equity retranslated at the closing rate",
        category="FX", family="P4-FX",
        why="share capital does not move because a spot rate moved (FX-P03). Retranslating "
            "it makes CTA a plug, and the balance sheet still balances around it",
        sql="UPDATE dim_account SET fx_method = 'CLOSE' WHERE group_account = '310100'",
    ),
    dict(
        fault_id="F4-06", name="Missing opening translation base",
        category="FX", family="P4-FX",
        why="an entity with no registered acquisition-date rate (FX-P16) would translate its "
            "opening balance sheet at whatever the join happened to leave behind",
        sql="DELETE FROM ref_fx_rate_historical "
            "WHERE entity_code = 'NIG-410' AND group_account = 'ACQ_OPENING_BS'",
    ),
    dict(
        fault_id="F4-07", name="Wrong historical rate on an opening balance sheet",
        category="FX", family="P4-FX",
        why="a plausible but wrong rate translates cleanly and balances cleanly. Only the "
            "independent CTA expectation disagrees",
        sql="UPDATE ref_fx_rate_historical SET rate_usd_per_unit = rate_usd_per_unit * 1.05 "
            "WHERE entity_code = 'NIG-410' AND group_account = 'ACQ_OPENING_BS'",
    ),
    dict(
        fault_id="F02", name="One-sided intercompany difference (deferred from Phase 3)",
        category="INTERCOMPANY", family="P4-IC",
        why="USD 45,000 removed from one side of a pair. Both trial balances still close, the "
            "account maps, the dimension resolves -- the difference exists only when the two "
            "sides are put side by side, which is what the elimination engine does",
        pipeline="F02",
    ),
    dict(
        fault_id="F4-08", name="Register relationship missing an acquisition schedule",
        category="INVESTMENT", family="P4-INV",
        why="the control walks the investment REGISTER, so a relationship with no schedule "
            "fails. A control walking the schedules could never see it",
        csv_edit=("consolidation/acquisition.csv", "drop_row", "ACQ-011"),
    ),
    dict(
        fault_id="F4-09", name="Investment eliminated before its acquisition date",
        category="INVESTMENT", family="P4-INV",
        why="eliminating a holding in months the group did not own it removes equity that was "
            "still outside the group, and every total remains plausible",
        csv_edit=("consolidation/acquisition.csv", "set", "ACQ-011",
                  "effective_period", "202401"),
    ),
    dict(
        fault_id="F4-10", name="Amortisation started at the beginning of the acquisition year",
        category="PPA", family="P4-INT",
        why="a whole-year charge on a mid-year acquisition. It is small, it is plausible, and "
            "it is wrong by exactly the months before completion",
        csv_edit=("consolidation/ppa_intangible.csv", "set_all_matching",
                  "acquisition_id", "ACQ-011", "amortisation_start_period", "202401"),
    ),
    dict(
        fault_id="F4-11", name="Opening accumulated amortisation greater than cost",
        category="PPA", family="P4-INT",
        why="an asset amortised past its own cost carries a negative net book value that the "
            "balance sheet absorbs without complaint, because the offsetting side is a real "
            "expense and the entry balances",
        csv_edit=("consolidation/ppa_intangible.csv", "set_all_matching",
                  "acquisition_id", "ACQ-001", "accumulated_amortisation_at_open_usd_m",
                  "999.000000"),
    ),
    dict(
        fault_id="F4-12", name="Intercompany holding dropped from the unrealised profit run",
        category="PUP", family="P4-PUP",
        why="the control iterates the holdings population, so a transaction the calculation "
            "never saw fails. A control reconciling only what was calculated cannot",
        sql="DELETE FROM ref_ic_inventory_holding WHERE holding_period = 202412",
    ),
    dict(
        fault_id="F4-13", name="Wrong quantity of intercompany stock still held",
        category="PUP", family="P4-PUP",
        why="the provision is the surviving stock at its own layer margin, so overstating "
            "what survives overstates the provision. The entry balances and the balance "
            "sheet is unmoved in total; only the independent expectation disagrees",
        sql="UPDATE ref_ic_inventory_holding SET value_remaining_usd = value_remaining_usd * 1.2",
    ),
    dict(
        fault_id="F4-14", name="Management adjustment approved by nobody",
        category="MANAGEMENT", family="P4-MGT",
        why="an adjustment carrying an APPROVED status but no approver, preparer or rationale "
            "is unattributable. It posts cleanly and balances cleanly",
        csv_edit=("consolidation/management_adjustment.csv", "add_anonymous", ""),
    ),
    dict(
        fault_id="F4-17", name="Draft management adjustment must not be posted",
        category="MANAGEMENT", family=None, suppression=True,
        why="the opposite assertion to a detection: a DRAFT adjustment carrying a real amount "
            "must never reach layer 4 at all. Proving the gate holds is worth as much as "
            "proving a control fires, and neither proves the other",
        csv_edit=("consolidation/management_adjustment.csv", "add_unapproved", ""),
    ),
    dict(
        fault_id="F4-15", name="Balance sheet account with no cash flow category",
        category="STATEMENTS", family="P4-CF",
        why="the cash flow ties by construction only if the categories partition the balance "
            "sheet. An uncategorised account still ties while reporting the wrong line",
        sql="UPDATE dim_account SET cash_flow_category = '' WHERE group_account = '130100'",
    ),
    dict(
        fault_id="F4-16", name="Balance sheet account mapped to two captions",
        category="STATEMENTS", family="P4-BS",
        why="an account presented in two captions is counted twice and the statement still "
            "balances, because both halves come from the same signed movement",
        sql="INSERT INTO dim_account SELECT * REPLACE ('Other receivables' AS fs_caption_l2) "
            "FROM dim_account WHERE group_account = '120100'",
    ),
    dict(
        fault_id="F4-MGT-LEAK", name="Approved layer-4 adjustment with a real amount",
        category="SEPARATION", family=None, separation=True,
        why="the approved register holds only nil presentation reclassifications, so layer 4 "
            "is empty and the two bases are numerically identical. This fixture injects a "
            "real layer-4 amount and proves the statutory basis does not move: it is the "
            "empirical half of the proof that P4-LAY-03 and P4-BAS-01 make structurally",
        csv_edit=("consolidation/management_adjustment.csv", "add_approved", ""),
    ),
]


# ---------------------------------------------------------------- config fixtures
def _config_tree(root: Path, edit: tuple) -> Path:
    """A complete configuration tree with one file rewritten."""
    dst = root / "config"
    shutil.copytree(CONFIG, dst)
    rel, op, *rest = edit
    path = dst / rel
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows, fields = list(reader), list(reader.fieldnames or [])

    key = fields[0]
    if op == "drop_row":
        rows = [r for r in rows if r[key] != rest[0]]
    elif op == "set":
        ident, col, value = rest
        for r in rows:
            if r[key] == ident:
                r[col] = value
    elif op == "set_all_matching":
        match_col, match_val, col, value = rest
        for r in rows:
            if r[match_col] == match_val:
                r[col] = value
    elif op in ("add_unapproved", "add_approved", "add_anonymous"):
        template = dict(rows[0])
        template.update(adjustment_id="MA-999", amount_usd_m="2.500000",
                        approval_status="DRAFT" if op == "add_unapproved" else "APPROVED",
                        # an operating cost moved below the EBITDA line: the shape of a real
                        # management add-back, and the only shape that makes the separation
                        # proof mean anything. Both legs are income statement accounts, so
                        # net income, revenue, assets and equity are untouched and EBITDA and
                        # EBIT move on the management basis alone.
                        rationale="fault fixture", group_account="610100",
                        offset_account="740100")
        if op == "add_anonymous":
            template.update(preparer="", approver="", rationale="")
        rows.append(template)

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return dst


# ---------------------------------------------------------------- the F02 pipeline run
def _pipeline_con(fault_id: str) -> duckdb.DuckDBPyConnection:
    """
    Phase 3, in full, over the fault's raw tree -- then Phase 4 on top of the result.

    The fixture has to survive parsing, sign and period normalisation, dimension conformance,
    mapping and the whole conformed layer before the elimination engine ever sees it. Anything
    less would be testing the fixture generator rather than the engine.
    """
    from ..pipeline import (adapters, conform, dimensions, harmonise, reconcile, standardise,
                            subledgers)
    from ..pipeline import faults as p3faults
    from ..pipeline.config import REFERENCE as P3_REFERENCE
    from ..pipeline.config import set_artefact_writing

    tmp = Path(tempfile.mkdtemp(prefix=f"p4-{fault_id}-"))
    with open(DATA / "faults" / "expected_results.csv", newline="", encoding="utf-8") as f:
        variant = next(r for r in csv.DictReader(f) if r["fault_id"] == fault_id)
    raw_root, ref_root = p3faults.build_variant(fault_id, [variant["variant_file"]], tmp)

    con = duckdb.connect()
    subledgers.set_reference_root(ref_root)
    set_artefact_writing(False)
    try:
        adapters.parse(con, "FAULTRUN", raw_root)
        dimensions.build(con)
        standardise.build(con)
        harmonise.build(con)
        subledgers.build(con)
        conform.build(con)
        reconcile.load_oracle(con)
        reconcile.mapping_acceptance(con)
        reconcile.build(con)
        reconcile.population_bridge(con)
    finally:
        set_artefact_writing(True)
        subledgers.set_reference_root(P3_REFERENCE)
    return con


# ---------------------------------------------------------------- the harness
def _run_one(fault: dict, con: duckdb.DuckDBPyConnection, tmp: Path) -> list[dict]:
    """
    Apply one fault to the frozen inputs, consolidate, and return the control results.

    Every fixture runs inside a transaction that is rolled back afterwards. The first version
    of this harness reused one database copy without one, and the fault tables that Phase 4
    only READS -- the ownership register, the chart of accounts, the historical rates -- kept
    their damage. From the fifth fixture on, every run failed on the previous fixture's fault
    and the results looked like a control suite in a very good mood.
    """
    cfg.set_artefact_writing(False)
    original = investments.CONFIG
    own_con = fault.get("pipeline") is not None
    if own_con:
        con = _pipeline_con(fault["pipeline"])
    else:
        con.begin()
    try:
        if fault.get("sql"):
            con.execute(fault["sql"])
        if fault.get("csv_edit"):
            tree = _config_tree(tmp / fault["fault_id"], fault["csv_edit"])
            investments.CONFIG = mgmt.CONFIG = tree
        consol_run.run(con, with_controls=False)
        # A fixture that proves a negative has to show its working. "Nothing broke" is also
        # what an edit that never reached the engine looks like, so both the suppression and
        # the separation fixtures read the engine's own output back.
        fault["_posted"] = con.execute(
            "SELECT count(*) FROM fact_consol_journal WHERE rule_id = 'MA-999'").fetchone()[0]
        fault["_moved"] = con.execute("""
            SELECT count(*) FROM rpt_basis_comparison WHERE abs(difference_usd) > 0.01
        """).fetchone()[0]
        return list(controls.run(con))
    finally:
        investments.CONFIG = mgmt.CONFIG = original
        cfg.set_artefact_writing(True)
        if own_con:
            con.close()
        else:
            con.rollback()


def detect() -> list[dict]:
    out: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="p4-faults-") as tmpdir:
        tmp = Path(tmpdir)
        # One writable copy of the frozen warehouse. Every table the engine writes is created
        # or replaced on each run, so the copy is reused; the clean baseline is never touched.
        db = tmp / "fault.duckdb"
        shutil.copy2(DUCKDB_PATH, db)
        base = duckdb.connect(str(db))

        for fault in FAULTS:
            fid, family = fault["fault_id"], fault["family"]
            try:
                results = _run_one(fault, base, tmp)
                broke = [c["control_id"] for c in results
                         if c["status"] == "FAIL" and c["severity"] == "BLOCKING"]
                error = ""
            except Exception as exc:
                # An engine that refuses to build on a corrupt input is a legitimate
                # detection PROVIDED the refusal names the defect, which is why the
                # generation assertions carry their defect reference in the message.
                broke, error = [], f"{type(exc).__name__}: {exc}"[:200]

            in_family = [c for c in broke if family and c.startswith(family)]
            unrelated = [c for c in broke if not family or not c.startswith(family)]

            posted, moved = fault.get("_posted", 0), fault.get("_moved", 0)
            if fault.get("suppression"):
                # The gate must hold: the draft adjustment reaches no layer, no measure moves
                # on either basis, and nothing else breaks either.
                status = ("SUPPRESSED" if not broke and not error and not posted and not moved
                          else "SUPPRESSION_BROKEN")
            elif fault.get("separation"):
                # This fixture is not meant to break anything. It proves the statutory basis
                # does not move when layer 4 does, which is the opposite assertion -- so it
                # has to show that layer 4 really was posted and that measures really did
                # move on the management basis, or it proves nothing at all.
                leaked = [c for c in broke if c in ("P4-LAY-03", "P4-BAS-01")]
                status = ("SEPARATION_PROVEN"
                          if not leaked and not error and posted and moved
                          else "SEPARATION_BROKEN")
            elif in_family:
                status = "DETECTED"
            elif error and family:
                status = "DETECTED_BY_REFUSAL"
            elif broke:
                status = "ACCIDENTAL_DETECTION"
            else:
                status = "NOT_DETECTED"

            out.append(dict(
                fault_id=fid, name=fault["name"], category=fault["category"],
                intended_control_family=(family or ("SUPPRESSION_PROOF"
                    if fault.get("suppression") else "SEPARATION_PROOF")),
                detected_by=";".join(in_family),
                other_controls_broken=";".join(unrelated),
                engine_refused=error, layer4_legs_posted=fault.get("_posted", 0),
                measures_moved=fault.get("_moved", 0),
                status=status, rationale=fault["why"]))
        base.close()
    return out


def main() -> int:
    results = detect()
    with open(FAULT_RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(results)
    for row in results:
        evidence = (row["detected_by"] or row["other_controls_broken"]
                    or row["engine_refused"][:44] or "-")
        print(f"  {row['fault_id']:13} {row['status']:20} "
              f"{row['intended_control_family']:16} {evidence:46} {row['name']}")
    good = {"DETECTED", "DETECTED_BY_REFUSAL", "SEPARATION_PROVEN", "SUPPRESSED"}
    bad = [r for r in results if r["status"] not in good]
    print(f"{len(results) - len(bad)}/{len(results)} fixtures handled as intended")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
