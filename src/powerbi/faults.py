"""
Fault fixtures for the semantic layer.

    python -m src.powerbi.faults

Each fixture breaks the **model** on purpose -- a measure definition, a relationship, a
published dimension -- deploys the damaged model to the real engine, runs the real controls
against it, and asserts that the control named for it in advance is the one that fails.

That last part is the whole discipline. A fixture caught by some other control is reported as
a miss, because "something went red" and "the right thing went red" are different claims and
only the second one tells you the suite works.

Every fixture restores the model afterwards and the suite redeploys clean, so the fixtures
leave nothing behind.
"""

from __future__ import annotations

import csv
import sys
from contextlib import contextmanager

import duckdb

from . import config as C
from . import controls, dax, deploy
from . import measures as M


@contextmanager
def _patched_measure(name: str, expression: str):
    """Swap one measure's DAX for the duration of a fixture."""
    original = M.MEASURES
    M.MEASURES = tuple(
        (n, expression if n == name else e, f, fo, d) for n, e, f, fo, d in original)
    controls.MEASURES = M.MEASURES
    deploy.MEASURES = M.MEASURES
    try:
        yield
    finally:
        M.MEASURES = original
        controls.MEASURES = original
        deploy.MEASURES = original


@contextmanager
def _patched_tables(mutate):
    original = C.TABLES
    C.TABLES = mutate(original)
    try:
        yield
    finally:
        C.TABLES = original


@contextmanager
def _patched_relationships(mutate):
    original = C.RELATIONSHIPS
    C.RELATIONSHIPS = mutate(original)
    try:
        yield
    finally:
        C.RELATIONSHIPS = original


# --------------------------------------------------------------------------- the fixtures
def f01_revenue_omits_account_family():
    """Revenue reads a narrower measure line, so an account family silently disappears."""
    return _patched_measure(
        "Revenue",
        M.statement_measure("GROSS_PROFIT"))


def f02_ebitda_includes_the_close():
    """
    EBITDA summed on the full-year column at a year end, which sweeps the closing entry in.

    This is the Phase 4B defect (P4-D-02) attempted again in DAX: the close nets a fiscal
    year to approximately nil, so an EBITDA that includes it collapses.
    """
    return _patched_measure(
        "Statutory EBITDA",
        "CALCULATE ( SUM ( 'Financials'[fy_usd] ) + SUM ( 'Financials'[ytd_usd] ),\n"
        "    KEEPFILTERS ( 'Measure Line'[measure_code] = \"EBITDA\" ),\n"
        "    KEEPFILTERS ( 'Financials'[basis] = \"STATUTORY\" ) )")


def f03_future_actual_is_zero():
    """The cutoff guard removed, so an unclosed month reports zero instead of blank."""
    return _patched_measure(
        "Revenue",
        "CALCULATE (\n"
        "    SUM ( 'Financials'[ytd_usd] ),\n"
        "    KEEPFILTERS ( 'Measure Line'[measure_code] = \"REVENUE\" ),\n"
        "    KEEPFILTERS ( 'Financials'[basis] = "
        "SELECTEDVALUE ( 'Reporting Basis'[basis], \"STATUTORY\" ) )\n"
        ") + 0")


def f04_covenant_ebitda_aliases_adjusted():
    """Covenant EBITDA pointed at Adjusted EBITDA instead of its own governed bridge."""
    return _patched_measure("Covenant EBITDA", "[Management Adjusted EBITDA]")


def f05_statutory_includes_layer_four():
    """Statutory EBITDA reading the management basis, so layer 4 leaks into the statutory view."""
    return _patched_measure(
        "Statutory EBITDA",
        M.statement_measure("EBITDA", basis="MANAGEMENT"))


def f06_cash_disagrees_with_the_cash_flow():
    """Closing cash taken from somewhere other than the statement that explains it."""
    return _patched_measure(
        "Closing Cash",
        "CALCULATE ( SUM ( 'Cash Flow'[opening_cash_usd] ),\n"
        "    'Date'[period_key] = MAX ( 'Date'[period_key] ) )")


def f07_wrong_forecast_default():
    """A superseded forecast presented as the current forecast."""
    return _patched_measure("Current Forecast Version", '"FC_FY26_02"')


def f08_missing_statement_caption():
    """A balance sheet caption a report depends on, filtered out of the model."""
    def mutate(tables):
        out = []
        for t in tables:
            if t["name"] == "Balance Sheet":
                t = dict(t, source="stg_bs_missing_caption")
            out.append(t)
        return tuple(out)
    return _patched_tables(mutate)


def f09_py_derived_removed():
    """`PY_DERIVED` dropped from the semantic version dimension while facts still use it."""
    def mutate(tables):
        out = []
        for t in tables:
            if t["name"] == "Scenario":
                t = dict(t, source="stg_scenario_without_py")
            out.append(t)
        return tuple(out)
    return _patched_tables(mutate)


def f10_capital_project_old_key():
    """
    The Capital Project dimension keyed the way the WIP assumed before ADR-0026.

    Rebuilt at the pre-correction grain -- entity, period and sequence, with the asset class
    dropped out of the identifier -- so 1,846 projects collapse to 395 keys again.
    """
    def mutate(tables):
        out = []
        for t in tables:
            if t["name"] == "Capital Project":
                t = dict(t, source="stg_project_old_key")
            out.append(t)
        return tuple(out)
    return _patched_tables(mutate)


#: fixture id -> (description, factory, the control that must catch it)
FIXTURES: tuple[tuple[str, str, object, str], ...] = (
    ("F6-XAR-01", "Revenue omits a valid account family",
     f01_revenue_omits_account_family, "P6-XAR-01"),
    ("F6-XAR-02", "EBITDA sweeps in the year-end close (P4-D-02 attempted again in DAX)",
     f02_ebitda_includes_the_close, "P6-XAR-03"),
    ("F6-XAR-03", "Future Actual returns zero instead of blank",
     f03_future_actual_is_zero, "P6-POL-01"),
    ("F6-XAR-04", "Covenant EBITDA aliases Adjusted EBITDA instead of its governed bridge",
     f04_covenant_ebitda_aliases_adjusted, "P6-POL-02"),
    ("F6-XAR-05", "Statutory reporting includes layer 4",
     f05_statutory_includes_layer_four, "P6-POL-06"),
    ("F6-XAR-06", "Cash differs from the mart's closing cash",
     f06_cash_disagrees_with_the_cash_flow, "P6-XAR-11"),
    ("F6-XAR-07", "A superseded forecast is presented as the current forecast",
     f07_wrong_forecast_default, "P6-POL-07"),
    ("F6-XAR-08", "A required financial statement caption is missing",
     f08_missing_statement_caption, "P6-XAR-07"),
    ("F6-XAR-09", "PY_DERIVED removed from the semantic version dimension",
     f09_py_derived_removed, "P6-POL-04"),
    ("F6-XAR-10", "Capital Project reverts to the colliding pre-ADR-0026 key",
     f10_capital_project_old_key, "P6-SEM-01"),
)


def _publish(con, table: str, folder: str) -> None:
    """
    Write a damaged table to Parquet where the model's partition will look for it.

    The partitions read Parquet, not the warehouse. A fixture that only creates a DuckDB table
    deploys a partition pointing at a file that does not exist, the refresh fails, and the
    clean model stays loaded -- so the fixture reports a miss while proving nothing. That is
    what three of these fixtures did on their first run.
    """
    out = (C.DATA / folder / f"{table}.parquet").as_posix()
    con.execute(f"COPY (SELECT * FROM {table} ORDER BY ALL) TO '{out}' "
                f"(FORMAT PARQUET, COMPRESSION ZSTD)")


def _damaged_sources(con) -> None:
    """
    The damaged tables the data-level fixtures point at.

    Built beside the real ones rather than by editing them, so a fixture cannot leave the
    published dimensions in a state the next run inherits.
    """
    con.execute("""
        CREATE OR REPLACE TABLE stg_bs_missing_caption AS
        SELECT * FROM mart_balance_sheet WHERE caption <> 'Cash and cash equivalents'""")
    con.execute("""
        CREATE OR REPLACE TABLE stg_scenario_without_py AS
        SELECT * FROM dim_report_scenario WHERE version_code <> 'PY_DERIVED'""")
    # The pre-correction key: entity, period and a sequence within the entity-month, with the
    # asset class dropped -- which is exactly how five programmes came to share one id.
    con.execute("""
        CREATE OR REPLACE TABLE stg_project_old_key AS
        SELECT 'CP-' || substr(entity_code, 5, 3) || '-' || CAST(approved_period AS VARCHAR)
                   || '-' || lpad(CAST(row_number() OVER (
                       PARTITION BY entity_code, approved_period, asset_class
                       ORDER BY project_id) AS VARCHAR), 2, '0') AS project_id,
               project_name, asset_class, entity_code, bu_code,
               approved_period, approved_fiscal_year
        FROM dim_semantic_project""")
    _publish(con, "stg_bs_missing_caption", "30_marts")
    _publish(con, "stg_scenario_without_py", "30_marts")
    _publish(con, "stg_project_old_key", "35_semantic")


def _drop_damaged(con) -> None:
    for table, folder in (("stg_bs_missing_caption", "30_marts"),
                          ("stg_scenario_without_py", "30_marts"),
                          ("stg_project_old_key", "35_semantic")):
        con.execute(f"DROP TABLE IF EXISTS {table}")
        path = C.DATA / folder / f"{table}.parquet"
        if path.exists():
            path.unlink()


def run(con) -> list[dict]:
    live, why = dax.available()
    if not live:
        return [dict(fixture_id=fid, description=desc, expected_control=expected,
                     status="NOT_EXECUTED", controls_triggered=why)
                for fid, desc, _factory, expected in FIXTURES]

    _damaged_sources(con)
    rows = []
    try:
        for fid, description, factory, expected in FIXTURES:
            with factory():
                deployed, message = deploy.deploy(con)
                res = controls.run(con)
            broken = [r["control_id"] for r in res if r["status"] == "FAIL"]
            # The data-level controls do not need the model to load, so a failed deployment
            # does not excuse the suite from catching the fault -- it is checked first.
            # A refusal by the engine is recorded alongside, because a model the engine will
            # not load is itself a detection, and the most emphatic kind: F6-XAR-10 gives a
            # dimension a duplicate key, and Analysis Services rejects the relationship built
            # on it outright rather than quietly promoting it to many-to-many.
            triggered = ";".join(broken) or "none"
            if expected in broken:
                status = "DETECTED"
                if not deployed:
                    triggered += " (and the engine refused to load the model)"
            elif not deployed:
                status, triggered = "NOT_DEPLOYED", message[:200]
            else:
                status = "MISSED"
            rows.append(dict(
                fixture_id=fid, description=description, expected_control=expected,
                status=status, controls_triggered=triggered))
    finally:
        _drop_damaged(con)
        deploy.deploy(con)          # leave the clean model behind
    return rows


def main(argv: list[str]) -> int:
    con = duckdb.connect(str(C.DUCKDB_PATH))
    rows = run(con)
    con.close()
    C.FAULT_RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(C.FAULT_RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    for row in rows:
        print(f"  {row['fixture_id']:11} {row['status']:13} {row['expected_control']:12} "
              f"{row['description']}")
        if row["status"] == "MISSED":
            print(f"                triggered instead: {row['controls_triggered']}")
    bad = sum(r["status"] != "DETECTED" for r in rows)
    print(f"{len(rows) - bad}/{len(rows)} fixtures detected by their intended control")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
