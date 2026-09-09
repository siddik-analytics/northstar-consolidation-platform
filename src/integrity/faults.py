"""
Fault fixtures for the key and grain framework.

    python -m src.integrity.faults

A control suite that has never failed is a suite nobody has tested. Each fixture below breaks
one thing on purpose, runs the real controls against the damaged warehouse, and asserts that
the control which is *supposed* to catch it does -- named in advance, not read off afterwards.
A fixture that is detected by some other control is reported as a miss, because "something
went red" is not the same as "the right thing went red".

F7-KEY-01 is the one that matters: it recreates P6-D-01 exactly, by giving two capital
projects the same identifier. Before ADR-0026 the warehouse looked like this permanently and
every control in the platform passed.

Each fixture runs inside a transaction that is rolled back, so the warehouse is unchanged.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import duckdb

from . import controls

ROOT = Path(__file__).resolve().parents[2]
FAULT_RESULTS = ROOT / "data" / "phase07_key_fault_results.csv"


def _dup_project_id(con) -> None:
    """P6-D-01, recreated. Two projects, one identifier."""
    con.execute("""
        UPDATE fact_capex_project SET project_id = (
            SELECT min(project_id) FROM fact_capex_project
            WHERE entity_code = 'NIG-200' AND period_key = 202505)
        WHERE entity_code = 'NIG-200' AND period_key = 202505""")


def _null_key_column(con) -> None:
    """A key column that is null is not a key."""
    con.execute("""
        UPDATE fact_capex_project SET project_id = NULL
        WHERE project_id = (SELECT max(project_id) FROM fact_capex_project)""")


def _orphan_fixed_asset(con) -> None:
    """An asset that names a project which does not exist."""
    con.execute("""
        UPDATE ref_fixed_asset SET project_id = 'CP-999-209912-PLANT-01'
        WHERE asset_id = (SELECT min(asset_id) FROM ref_fixed_asset)""")


def _asset_class_disagreement(con) -> None:
    """An asset whose class contradicts the project that bought it."""
    con.execute("""
        UPDATE ref_fixed_asset SET asset_class = 'VEHICLE'
        WHERE asset_id = (SELECT min(asset_id) FROM ref_fixed_asset
                          WHERE asset_class = 'PLANT')""")


def _asset_entity_disagreement(con) -> None:
    """An asset booked to an entity other than the one that ran the project."""
    con.execute("""
        UPDATE ref_fixed_asset SET entity_code = 'NIG-999'
        WHERE asset_id = (SELECT min(asset_id) FROM ref_fixed_asset)""")


def _asset_cost_drift(con) -> None:
    """The identifier still resolves, but the money behind it no longer agrees."""
    con.execute("""
        UPDATE ref_fixed_asset SET cost_local = cost_local + 1000
        WHERE asset_id = (SELECT min(asset_id) FROM ref_fixed_asset)""")


def _undeclared_keyed_table(con) -> None:
    """A new keyed table appears that the registry has never heard of."""
    con.execute("""
        CREATE TABLE dim_new_undeclared_thing AS
        SELECT 1 AS thing_code, 'unregistered' AS thing_name""")


def _duplicate_dimension_row(con) -> None:
    """A dimension that silently gained a second row for one member."""
    con.execute("""
        INSERT INTO dim_entity SELECT * FROM dim_entity
        WHERE entity_code = (SELECT min(entity_code) FROM dim_entity)""")


def _mart_grain_duplicate(con) -> None:
    """A reporting mart that doubled a row -- every subtotal above it still foots."""
    con.execute("""
        INSERT INTO mart_capex SELECT * FROM mart_capex
        WHERE project_id = (SELECT min(project_id) FROM mart_capex)""")


#: fixture id -> (description, injector, the control that must catch it)
FIXTURES: tuple[tuple[str, str, object, str], ...] = (
    ("F7-KEY-01", "Two capital projects share one project identifier (P6-D-01 recreated)",
     _dup_project_id, "P7-CPX-01"),
    ("F7-KEY-02", "A dimension holds two rows for one member",
     _duplicate_dimension_row, "P7-KEY-dim_entity"),
    ("F7-KEY-03", "A reporting mart duplicates a row at its declared grain",
     _mart_grain_duplicate, "P7-KEY-mart_capex"),
    ("F7-NUL-01", "A declared key column is null",
     _null_key_column, "P7-NUL-fact_capex_project"),
    ("F7-REF-01", "A fixed asset references a project that does not exist",
     _orphan_fixed_asset, "P7-CPX-02"),
    ("F7-REG-01", "A keyed table exists that the registry does not declare",
     _undeclared_keyed_table, "P7-REG-01"),
    ("F7-CPX-01", "A fixed asset contradicts its project on asset class",
     _asset_class_disagreement, "P7-CPX-04"),
    ("F7-CPX-02", "A fixed asset contradicts its project on owning entity",
     _asset_entity_disagreement, "P7-CPX-05"),
    ("F7-CPX-03", "Asset cost no longer reconciles to the project spend",
     _asset_cost_drift, "P7-CPX-07"),
)


def _run_one(db: Path, fixture) -> dict:
    fid, description, inject, expected = fixture
    con = duckdb.connect(str(db))
    con.begin()
    try:
        inject(con)
        res = controls.run(con)
    finally:
        con.rollback()
        con.close()

    broken = [row["control_id"] for row in res
              if row["status"] in ("FAIL", "SOURCE_FINDING")]
    # The PY_DERIVED finding is open on every run and is not evidence of anything here.
    broken = [c for c in broken if c != "P7-REF-mart_financial_ytd->dim_report_scenario"]
    hit = expected in broken
    return dict(fixture_id=fid, description=description, expected_control=expected,
                status="DETECTED" if hit else "MISSED",
                controls_triggered=";".join(broken) or "none")


def run(db: Path) -> list[dict]:
    return [_run_one(db, f) for f in FIXTURES]


def main(argv: list[str]) -> int:
    rows = run(controls.DUCKDB_PATH)
    FAULT_RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(FAULT_RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    for row in rows:
        print(f"  {row['fixture_id']:11} {row['status']:9} {row['expected_control']:32} "
              f"{row['description']}")
        if row["status"] == "MISSED":
            print(f"              triggered instead: {row['controls_triggered']}")
    missed = sum(r["status"] == "MISSED" for r in rows)
    print(f"{len(rows) - missed}/{len(rows)} fixtures detected by their intended control")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
