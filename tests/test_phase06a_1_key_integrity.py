"""
The upstream dimensional-integrity correction, and the framework that came out of it.

P6-D-01: `project_id` identified a capital project everywhere except in the data. 1,846 rows
carried 395 distinct identifiers, because the sequence number restarted inside each asset
class and every class in an entity-month reissued `-01`. Nothing caught it -- not at the
source, not at ingestion, not in the consolidation, not in the marts -- because no control
anywhere asked whether a declared key was a key. Power BI asked, four phases too late.

These tests hold three things:

    the corrected identifier, and its uniqueness over the whole population
    the capital-project traceability chain the defect broke
    the registry framework itself, including that it refuses to go stale

and, separately, that the correction moved no money. See ADR-0026.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.integrity import controls as integrity_controls
from src.integrity.faults import FIXTURES
from src.integrity.registry import KEYLESS, OUT_OF_SCOPE, REFERENCES, REGISTRY

DUCKDB_PATH = ROOT / "data" / "20_warehouse" / "northstar.duckdb"

pytestmark = pytest.mark.skipif(not DUCKDB_PATH.exists(),
                                reason="the warehouse has not been built")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    yield c
    c.close()


# ===================================================================== the corrected key
def test_project_id_is_unique_over_the_whole_population(con):
    """The P6-D-01 condition itself: 1,846 rows, 1,846 identifiers."""
    rows, ids = con.execute(
        "SELECT count(*), count(DISTINCT project_id) FROM fact_capex_project").fetchone()
    assert rows == 1846
    assert ids == rows, f"{rows - ids} capital projects share an identifier"


def test_the_identifier_carries_the_grain_that_makes_a_project_distinct():
    """
    Entity, period, asset class and a sequence -- in the identifier, not just implied by it.

    The asset class is the part the defect was missing, so it is the part worth asserting.
    """
    pattern = re.compile(r"^CP-\d{3}-\d{6}-[A-Z_]+-\d{2}$")
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    ids = [r[0] for r in con.execute(
        "SELECT project_id FROM fact_capex_project ORDER BY project_id").fetchall()]
    con.close()
    bad = [i for i in ids if not pattern.match(i)]
    assert not bad, f"identifiers that do not carry the full grain: {bad[:5]}"

    # and the class in the identifier is the class on the row
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    wrong = con.execute("""
        SELECT count(*) FROM fact_capex_project
        WHERE split_part(project_id, '-', 4) <> asset_class""").fetchone()[0]
    con.close()
    assert wrong == 0


def test_the_defect_shape_would_now_be_caught():
    """Two projects sharing an identifier must be detected, by the control named for it."""
    fixture = next(f for f in FIXTURES if f[0] == "F7-KEY-01")
    assert "share one project identifier" in fixture[1]
    results = {r["fixture_id"]: r for r in _fault_results()}
    assert results["F7-KEY-01"]["status"] == "DETECTED"
    assert results["F7-KEY-01"]["expected_control"] == "P7-CPX-01"


def _fault_results() -> list[dict]:
    path = ROOT / "data" / "phase07_key_fault_results.csv"
    if not path.exists():
        pytest.skip("the key fault fixtures have not been run")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_every_key_fixture_is_caught_by_its_intended_control():
    for row in _fault_results():
        assert row["status"] == "DETECTED", (
            f"{row['fixture_id']} was not caught by {row['expected_control']}; "
            f"triggered instead: {row['controls_triggered']}")


# ===================================================================== traceability
def test_every_fixed_asset_resolves_to_exactly_one_project(con):
    orphans, fanned = con.execute("""
        SELECT (SELECT count(*) FROM ref_fixed_asset f
                WHERE NOT EXISTS (SELECT 1 FROM fact_capex_project p
                                  WHERE p.project_id = f.project_id)),
               (SELECT count(*) FROM ref_fixed_asset f
                JOIN fact_capex_project p USING (project_id)) -
               (SELECT count(*) FROM ref_fixed_asset)""").fetchone()
    assert orphans == 0, f"{orphans} assets name a project that does not exist"
    assert fanned == 0, f"the join fans out by {fanned} rows -- the P6-D-01 symptom"


def test_asset_cost_reconciles_to_project_spend_project_by_project(con):
    worst = con.execute("""
        SELECT coalesce(max(abs(d)), 0) FROM (
            SELECT round(sum(f.cost_local) - min(p.spend_local), 2) AS d
            FROM ref_fixed_asset f JOIN fact_capex_project p USING (project_id)
            GROUP BY f.project_id)""").fetchone()[0]
    assert worst == 0, f"worst project reconciles {worst} out"


def test_the_corrected_key_reaches_the_reporting_mart(con):
    rows, ids = con.execute(
        "SELECT count(*), count(DISTINCT project_id) FROM mart_capex").fetchone()
    assert rows == ids == 1846


# ===================================================================== the framework
def test_the_registry_covers_every_keyed_object(con):
    """
    The control that stops the framework going stale, asserted independently of the framework.

    A registry that only knows about the tables someone remembered to add is the situation
    P6-D-01 was found in.
    """
    present = {r[0] for r in con.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'main' AND table_type = 'BASE TABLE'""").fetchall()}
    in_scope = {t for t in present
                if t.startswith(integrity_controls.IN_SCOPE_PREFIXES)
                and not any(t.startswith(p) for p in OUT_OF_SCOPE)}
    declared = {d.object for d in REGISTRY} | set(KEYLESS)
    assert not (in_scope - declared), f"undeclared keyed objects: {sorted(in_scope - declared)}"


def test_every_declared_key_is_actually_unique(con):
    """The registry executed directly, not through the control suite that reports on it."""
    failures = []
    for d in REGISTRY:
        key = ", ".join(d.key)
        rows, distinct = con.execute(f"""
            SELECT count(*), (SELECT count(*) FROM (SELECT DISTINCT {key} FROM {d.object}))
            FROM {d.object}""").fetchone()
        if rows != distinct:
            failures.append(f"{d.object}: {rows - distinct} duplicates on ({key})")
    assert not failures, "; ".join(failures)


def test_a_nullable_key_column_carries_a_reason():
    for d in REGISTRY:
        if d.nullable:
            assert d.nulls != "FORBIDDEN", f"{d.object} permits nulls but forbids them"
            assert len(d.nulls.strip()) > 20, f"{d.object} permits nulls without a reason"
        else:
            assert d.nulls == "FORBIDDEN", f"{d.object} gives a reason but permits nothing"


def test_no_key_column_outside_the_declared_nullable_set_is_null(con):
    failures = []
    for d in REGISTRY:
        strict = [c for c in d.key if c not in d.nullable]
        if not strict:
            continue
        n = con.execute(f"""
            SELECT count(*) FROM {d.object}
            WHERE {' OR '.join(f'{c} IS NULL' for c in strict)}""").fetchone()[0]
        if n:
            failures.append(f"{d.object}: {n} rows")
    assert not failures, "; ".join(failures)


def test_every_registry_entry_names_a_real_authority():
    for d in REGISTRY:
        assert d.source.strip(), f"{d.object} declares no authoritative source"
        assert d.owner.strip(), f"{d.object} declares no owner"


def test_an_accepted_reference_finding_names_the_defect_it_records():
    """An acceptance is a record of an open defect, never a way to silence a control."""
    for ref in REFERENCES:
        if ref.accepted:
            assert ref.defect, (
                f"{ref.child}->{ref.parent} accepts {ref.accepted} orphans without naming "
                f"the defect that tracks them")
            assert ref.note.strip()


def test_the_control_suite_has_no_blocking_failure(con):
    res = integrity_controls.run(con)
    assert not res.failed, [r["control_id"] for r in res.failed]
    assert len(res) > 200, "the suite should cover the whole registry, not a sample"


# ===================================================================== no economic drift
def test_every_rebaseline_snapshot_pair_shows_no_drift():
    """
    The pre/post comparison, asserted rather than eyeballed.

    Every complete `before_X` / `after_X` pair under `data/95_invariance/` is compared, so a
    later correction is covered by adding its snapshots rather than by editing this test.

    Skipped rather than failed when a pair is absent or predates the current comparison specs:
    the snapshots are evidence of a particular rebuild, they are not committed, and a fresh
    clone cannot reproduce a comparison whose "before" no longer exists. A stale pair is not a
    finding about the platform, it is a finding about the snapshot.
    """
    root = ROOT / "data" / "95_invariance"
    if not root.exists():
        pytest.skip("no invariance snapshots present")
    sys.path.insert(0, str(ROOT / "tools"))
    import financial_invariance

    expected = {f"{name}.parquet" for name in financial_invariance.SPECS}
    pairs = []
    for before in sorted(root.glob("before*")):
        after = root / before.name.replace("before", "after", 1)
        if not after.is_dir():
            continue
        have = {f.name for f in before.iterdir()} & {f.name for f in after.iterdir()}
        if expected <= have:
            pairs.append((before, after))

    if not pairs:
        pytest.skip("no snapshot pair matches the current comparison specs")
    for before, after in pairs:
        assert financial_invariance.compare(before, after) == 0,             f"{before.name} -> {after.name} shows economic drift"
