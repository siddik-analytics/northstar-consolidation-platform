"""
P7-D-01 — a version code that resolved to nothing.

`PY_DERIVED` was joined on by 12,516 rows of `mart_financial_ytd` and by every prior-year
comparator in `mart_variance`, and existed in no version master at all. `PY` *was* a
first-class scenario; its version simply had no row, because Prior Year is derived rather than
stored and nobody had separated **where a figure comes from** from **whether its identity is
governed**. `ref_default_version` unioned the PY default in by hand, which is the design
already working around the gap rather than closing it.

The correction gives Prior Year a governed derived version. It is still never stored: these
tests hold both halves of that — the identity exists and resolves everywhere, and the data
does not exist anywhere except as a view of Actual. See ADR-0027.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.integrity import controls as integrity_controls

DUCKDB_PATH = ROOT / "data" / "20_warehouse" / "northstar.duckdb"
CONFIG = ROOT / "config"

pytestmark = pytest.mark.skipif(not DUCKDB_PATH.exists(),
                                reason="the warehouse has not been built")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    yield c
    c.close()


def _one(con, sql):
    return con.execute(sql).fetchone()[0]


# ===================================================================== the governed member
def test_py_derived_exists_in_the_authoritative_version_master(con):
    row = con.execute("""
        SELECT version_code, version_name, scenario_code, scenario_type, fx_rate_set,
               is_default, is_locked, is_reserved, fiscal_year
        FROM dim_version WHERE version_code = 'PY_DERIVED'""").fetchone()
    assert row is not None, "P7-D-01: PY_DERIVED must exist in the version master"
    (code, name, scenario, vtype, rates, default, locked, reserved, fy) = row
    assert name == "Prior Year (Derived)"
    assert scenario == "PY"
    assert vtype == "DERIVED", "a derived version must be typed as one"
    assert rates == "ACTUAL", "Prior Year is Actual, so it carries actual rates"
    assert default is True, "the one PY version is the PY default"
    assert locked is True, "a derived version must not be editable"
    assert reserved is False
    assert fy is None, "Prior Year spans years, like Actual"


def test_the_derived_scenario_names_what_it_derives_from(con):
    assert _one(con, """
        SELECT derived_from_scenario_code FROM dim_scenario WHERE scenario_code = 'PY'
    """) == "ACT", "a derivation with no stated source is an assertion"


def test_py_derived_is_reportable(con):
    """It must reach the reporting dimension, not merely exist in the master."""
    assert _one(con, """
        SELECT count(*) FROM dim_report_scenario WHERE version_code = 'PY_DERIVED'""") == 1


# ===================================================================== nothing resolves to nothing
def test_every_version_code_in_every_fact_and_mart_resolves(con):
    """The P7-D-01 condition, over every column that carries a version."""
    failures = []
    for table, column in (
        ("fact_plan", "version_code"), ("fact_financials", "version_code"),
        ("fact_trial_balance", "version_code"), ("fact_consol_journal", "version_code"),
        ("mart_financial_ytd", "version_code"), ("mart_financial_monthly", "version_code"),
        ("mart_business_unit", "version_code"), ("mart_entity_performance", "version_code"),
        ("mart_variance", "base_version"), ("mart_variance", "comparator_version"),
        ("ref_default_version", "version_code"),
    ):
        n = _one(con, f"""
            SELECT count(*) FROM {table} c WHERE c.{column} IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM dim_version v
                              WHERE v.version_code = c.{column})""")
        if n:
            failures.append(f"{table}.{column}: {n} unresolved")
    assert not failures, "; ".join(failures)


def test_the_prior_year_rows_specifically_resolve(con):
    """12,516 rows was the size of the finding; it should now be the size of what resolves."""
    total = _one(con, """
        SELECT count(*) FROM mart_financial_ytd WHERE version_code = 'PY_DERIVED'""")
    assert total == 12516
    assert _one(con, """
        SELECT count(*) FROM mart_financial_ytd m WHERE m.version_code = 'PY_DERIVED'
          AND NOT EXISTS (SELECT 1 FROM dim_report_scenario d
                          WHERE d.version_code = m.version_code)""") == 0


def test_no_blank_semantic_member_is_possible(con):
    assert _one(con, """
        SELECT count(*) FROM dim_report_scenario
        WHERE version_code IS NULL OR trim(coalesce(version_name, '')) = ''
           OR scenario_code IS NULL OR trim(coalesce(scenario_name, '')) = ''""") == 0


# ===================================================================== one authority
def test_the_default_version_workaround_is_gone():
    """
    `ref_default_version` must not union anything in by hand any more.

    Read as SQL, not as prose: the comment above the statement explains the workaround that
    used to be there, and a naive text search finds the explanation as readily as the thing
    it describes.
    """
    source = (ROOT / "src" / "marts" / "build.py").read_text(encoding="utf-8")
    start = source.index("CREATE OR REPLACE TABLE ref_default_version")
    body = source[start:source.index('"""', start)]
    sql = "\n".join(line for line in body.splitlines()
                    if not line.strip().startswith("--"))
    assert "UNION" not in sql.upper(), \
        "ref_default_version must derive from the governed dimension alone"
    assert "PY_DERIVED" not in sql, "no version may be named by hand here"


def test_every_default_comes_from_the_governed_master(con):
    assert _one(con, """
        SELECT count(*) FROM (
            SELECT scenario_code, version_code FROM ref_default_version
            EXCEPT
            SELECT scenario_code, version_code FROM dim_version
            WHERE is_default AND NOT is_reserved)""") == 0


def test_each_reportable_scenario_has_exactly_one_default(con):
    rows = con.execute("""
        SELECT s.scenario_code, count(*) FILTER (WHERE v.is_default) AS defaults
        FROM dim_scenario s JOIN dim_version v USING (scenario_code)
        WHERE NOT s.is_reserved AND NOT v.is_reserved
        GROUP BY s.scenario_code ORDER BY 1""").fetchall()
    assert dict(rows) == {"ACT": 1, "BUD": 1, "FC": 1, "PY": 1}


def test_the_current_forecast_is_the_only_forecast_default(con):
    assert _one(con, """
        SELECT version_code FROM ref_default_version WHERE scenario_code = 'FC'
    """) == "FC_FY26_08"


# ===================================================================== derived means derived
def test_prior_year_is_never_source_loaded(con):
    """Identity is governed; the data is still a view of Actual and stored nowhere."""
    for table in ("fact_plan", "fact_financials", "fact_trial_balance"):
        assert _one(con, f"""
            SELECT count(*) FROM {table} t JOIN dim_version v USING (version_code)
            WHERE v.scenario_type = 'DERIVED'""") == 0, \
            f"{table} holds stored rows for a derived version"


def test_prior_year_equals_actual_twelve_months_earlier(con):
    """The derivation the master states, proved against the Actual it claims to be."""
    worst = _one(con, """
        SELECT coalesce(max(abs(py.ytd_usd - act.ytd_usd)), 0)
        FROM mart_financial_ytd py
        JOIN mart_financial_ytd act
          ON act.version_code = 'ACTUAL' AND act.period_key = py.period_key - 100
         AND act.basis = py.basis AND act.entity_code = py.entity_code
         AND act.bu_code = py.bu_code AND act.measure_code = py.measure_code
        WHERE py.version_code = 'PY_DERIVED'""")
    assert worst == 0, f"prior year drifts from actual by {worst}"


def test_every_actual_month_has_its_prior_year_row(con):
    """Iterated from Actual: a PY row the derivation failed to build is invisible from PY."""
    assert _one(con, """
        SELECT count(*) FROM mart_financial_ytd act
        WHERE act.version_code = 'ACTUAL' AND act.period_key < 202600
          AND NOT EXISTS (
              SELECT 1 FROM mart_financial_ytd py
              WHERE py.version_code = 'PY_DERIVED' AND py.period_key = act.period_key + 100
                AND py.basis = act.basis AND py.entity_code = act.entity_code
                AND py.bu_code = act.bu_code AND py.measure_code = act.measure_code)""") == 0


# ===================================================================== reserved stays reserved
def test_downside_remains_reserved_and_unreportable(con):
    assert _one(con, """
        SELECT is_reserved FROM dim_scenario WHERE scenario_code = 'DS'""") is True
    assert _one(con, """
        SELECT count(*) FROM dim_report_scenario WHERE scenario_code = 'DS'""") == 0
    assert _one(con, """
        SELECT count(*) FROM mart_financial_ytd m JOIN dim_version v USING (version_code)
        WHERE v.is_reserved""") == 0


def test_actual_and_budget_version_behaviour_is_unchanged(con):
    assert _one(con, """
        SELECT version_code FROM ref_default_version WHERE scenario_code = 'ACT'
    """) == "ACTUAL"
    assert _one(con, """
        SELECT version_code FROM ref_default_version WHERE scenario_code = 'BUD'
    """) == "BUD_FY26_V1"
    # and they are not derived
    assert _one(con, """
        SELECT count(*) FROM dim_version
        WHERE version_code IN ('ACTUAL', 'BUD_FY26_V1') AND scenario_type = 'DERIVED'""") == 0


# ===================================================================== the controls themselves
def test_the_version_family_passes_and_nothing_is_quarantined(con):
    res = integrity_controls.run(con)
    assert not res.failed, [r["control_id"] for r in res.failed]
    quarantined = [r["control_id"] for r in res if r["status"] == "SOURCE_FINDING"]
    assert not quarantined, f"still quarantined: {quarantined}"
    version_controls = [r for r in res if r["control_id"].startswith("P7-VER-")]
    assert len(version_controls) == 14
    assert all(r["status"] == "PASS" for r in version_controls)


def test_every_version_fixture_is_caught_by_its_intended_control():
    path = ROOT / "data" / "phase07_key_fault_results.csv"
    if not path.exists():
        pytest.skip("the key fault fixtures have not been run")
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["fixture_id"].startswith("F7-VER-")]
    assert len(rows) == 9
    for row in rows:
        assert row["status"] == "DETECTED", (
            f"{row['fixture_id']} was not caught by {row['expected_control']}; "
            f"triggered instead: {row['controls_triggered']}")
