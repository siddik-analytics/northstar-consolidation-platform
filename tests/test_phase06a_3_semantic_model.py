"""
Phase 6A — the governed semantic model.

Phase 6A was interrupted twice, and by defects of the same shape both times: an identifier in
use that resolved to nothing. `project_id` identified 1,846 capital projects with 395 values
(P6-D-01); `PY_DERIVED` was the version code on 12,516 mart rows and existed in no version
master (P7-D-01). Neither could be worked around in DAX, both were corrected upstream, and
these tests hold the semantic model that was finally built on the corrected baseline.

The tests that need a live Analysis Services engine skip when one is not running. They do not
substitute a SQL re-implementation of a measure and call the answer a Power BI value -- the
whole point of the `P6-XAR` family is that one side is the real engine.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.powerbi import config as C
from src.powerbi import controls as pbi_controls
from src.powerbi import dax
from src.powerbi.faults import FIXTURES
from src.powerbi.measures import MEASURES

DUCKDB_PATH = C.DUCKDB_PATH

pytestmark = pytest.mark.skipif(not DUCKDB_PATH.exists(),
                                reason="the warehouse has not been built")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def live():
    ok, why = dax.available()
    if ok and not dax.model_loaded():
        ok = False
    if not ok:
        pytest.skip("no live semantic model; run `python -m src.powerbi.run` first")
    return True


# ===================================================================== the two corrections
def test_capital_project_resolves_at_the_corrected_key(con):
    """1,846 projects, 1,846 identifiers -- the dimension P6-D-01 made impossible."""
    rows, ids = con.execute("""
        SELECT count(*), count(DISTINCT project_id) FROM dim_semantic_project""").fetchone()
    assert rows == ids == 1846


def test_no_surrogate_stands_in_for_the_capital_project_key():
    spec = next(t for t in C.TABLES if t["name"] == "Capital Project")
    assert spec["key"] == ("project_id",), "the business key is the key; no surrogate"
    assert not spec.get("calculated"), "no derived stand-in for the corrected key"


def test_the_scenario_dimension_carries_the_governed_derived_version(con):
    versions = {r[0] for r in con.execute(
        "SELECT version_code FROM dim_report_scenario").fetchall()}
    assert "PY_DERIVED" in versions, "P7-D-01: the derived version must be selectable"
    assert "DS_FY26_STRESS" not in versions, "a reserved scenario must not be reportable"


def test_every_fact_version_resolves_in_the_semantic_scenario_dimension(con):
    assert con.execute("""
        SELECT count(*) FROM mart_financial_ytd m
        WHERE NOT EXISTS (SELECT 1 FROM dim_report_scenario d
                          WHERE d.version_code = m.version_code)""").fetchone()[0] == 0


# ===================================================================== the star schema
def test_every_relationship_is_many_to_one_onto_a_unique_key(con):
    by_name = {t["name"]: t for t in C.TABLES}
    bad = []
    for _from_table, _from_col, to_table, to_col in C.RELATIONSHIPS:
        parent = by_name[to_table]
        rows, distinct = con.execute(f"""
            SELECT count(*), (SELECT count(*) FROM
                (SELECT DISTINCT {to_col} FROM {parent['source']}))
            FROM {parent['source']}""").fetchone()
        if rows != distinct:
            bad.append(f"{to_table}[{to_col}]")
    assert not bad, f"the one side is not unique: {bad}"


def test_no_two_tables_have_two_active_paths():
    seen: dict[tuple[str, str], int] = {}
    for from_table, _c, to_table, _d in C.RELATIONSHIPS:
        seen[(from_table, to_table)] = seen.get((from_table, to_table), 0) + 1
    assert not [k for k, n in seen.items() if n > 1]


def test_every_inactive_relationship_explains_itself():
    for from_table, from_col, to_table, to_col, why in C.INACTIVE_RELATIONSHIPS:
        assert len(why.strip()) > 30, f"{from_table}[{from_col}] -> {to_table} has no reason"


def test_the_model_has_at_most_one_calculated_column():
    """
    Derivation belongs upstream. One exception is declared and explained.

    Power BI relates on a single column and a cost centre is identified by entity and code
    together, so the composite has to be formed somewhere; it is formed in the model rather
    than added to a frozen mart, and it is concatenation with no business logic in it.
    """
    calculated = {t["name"]: tuple(t.get("calculated", {}))
                  for t in C.TABLES if t.get("calculated")}
    assert calculated == {"Financial Detail": ("cost_centre_key",)}, calculated


def test_no_semantic_table_recreates_a_mart():
    """
    Every table loads a governed published artefact; none is assembled in the model. The
    Phase 6B.1 publications (`fact_semantic_*`) are restatements of a mart at the grain the
    model sorts or reads at, published to 35_semantic and declared in the key registry.
    """
    for t in C.TABLES:
        assert t["source"].startswith(("mart_", "dim_", "fact_semantic_")), t["source"]
        if t["source"].startswith("fact_semantic_"):
            assert t["folder"] == "semantic"


# ===================================================================== statements and policy
def test_the_income_statement_hierarchy_is_complete_and_ordered(con):
    rows = con.execute("""
        SELECT measure_code FROM dim_report_measure ORDER BY sort_order""").fetchall()
    order = [r[0] for r in rows]
    required = ["REVENUE", "COST_OF_SALES", "GROSS_PROFIT", "OPEX", "EBITDA", "ADJ_EBITDA",
                "DA", "EBIT", "NET_FINANCE", "TAX", "NET_INCOME"]
    positions = [order.index(code) for code in required]
    assert positions == sorted(positions), "the P&L must run top to bottom, not alphabetically"


def test_statement_captions_sort_by_governed_order_not_alphabet():
    measure_line = next(t for t in C.TABLES if t["name"] == "Measure Line")
    balance_sheet = next(t for t in C.TABLES if t["name"] == "Balance Sheet")
    assert measure_line["sort"].get("measure_name") == "sort_order"
    assert balance_sheet["sort"].get("caption") == "sort_order"


def test_three_ebitda_definitions_exist_and_are_separately_defined():
    by_name = {n: e for n, e, f, fo, d in MEASURES}
    assert "Statutory EBITDA" in by_name
    assert "Management Adjusted EBITDA" in by_name
    assert "Covenant EBITDA" in by_name
    # Covenant EBITDA must not be an alias of Adjusted EBITDA, however close the values are.
    assert "[Management Adjusted EBITDA]" not in by_name["Covenant EBITDA"]
    assert "'Covenants'" in by_name["Covenant EBITDA"], \
        "Covenant EBITDA reads the covenant bridge, not the management measure"
    assert '"STATUTORY"' in by_name["Statutory EBITDA"]
    assert '"MANAGEMENT"' in by_name["Management Adjusted EBITDA"]


def test_every_statement_measure_states_a_reporting_basis():
    """
    Without a basis filter a measure sums statutory and management and reports twice the truth.

    This is not hypothetical: it is what every statement measure did until the model was
    deployed to a real engine, and it is invisible in the current data because layer 4 is
    unpopulated and the two bases hold identical values.
    """
    for name, expression, fmt, folder, desc in MEASURES:
        if "'Financials'[mtd_usd]" in expression:
            assert "'Financials'[basis]" in expression, f"{name} does not state a basis"


def test_high_risk_measures_document_definition_source_and_basis():
    HIGH_RISK = ("Management Adjusted EBITDA", "Covenant EBITDA", "Covenant Net Debt",
                 "Covenant Net Leverage", "Cumulative Translation Adjustment",
                 "Non-controlling Interest Equity", "Closing Cash")
    for name, expression, fmt, folder, desc in MEASURES:
        if name in HIGH_RISK:
            for element in ("Definition", "Source", "Basis", "Blank policy"):
                assert element in desc, f"{name} does not state its {element}"


# ===================================================================== live engine
def test_the_model_loads_with_every_declared_table(live):
    declared = {t["name"] for t in C.TABLES} | {"Period Basis", C.MEASURES_TABLE}
    assert declared <= set(dax.table_names())


def test_every_measure_evaluates_in_the_engine(live):
    broken = []
    for name, expression, fmt, folder, desc in MEASURES:
        try:
            dax.measure_at(name, C.REPORT_PERIOD)
        except Exception as exc:
            broken.append(f"{name}: {exc.__class__.__name__}")
    assert not broken, broken


def test_actual_is_blank_after_the_close_not_zero(live):
    act = "'Scenario'[version_code] = \"ACTUAL\""
    assert dax.measure_at("Revenue", 202609, act) is None, \
        "an unclosed month must be blank; the mart publishes 0.00 rows for it"
    assert dax.measure_at("Revenue", C.REPORT_PERIOD, act) is not None


def test_covenant_status_is_indicative_off_a_test_date(live):
    assert dax.scalar(
        "CALCULATE ( [Covenant Status], 'Date'[period_key] = 202608 )") == "Indicative"
    assert dax.scalar(
        "CALCULATE ( [Covenant Status], 'Date'[period_key] = 202512 )") in ("Compliant",
                                                                           "Breach")


def test_prior_year_resolves_to_the_governed_version(live):
    assert dax.scalar("[Prior Year Version]") == "PY_DERIVED"


def test_power_bi_reconciles_to_the_marts(con, live):
    res = pbi_controls.run(con)
    xar = [r for r in res if r["control_id"].startswith("P6-XAR-")]
    assert xar, "the reconciliation family did not run"
    assert all(r["status"] == "PASS" for r in xar), \
        [r["control_id"] for r in xar if r["status"] != "PASS"]


def test_power_bi_reconciles_to_the_workbook(con, live):
    res = pbi_controls.run(con)
    xls = [r for r in res if r["control_id"].startswith("P6-XLS-")]
    assert xls and all(r["status"] == "PASS" for r in xls), \
        [r["control_id"] for r in xls if r["status"] != "PASS"]


def test_the_whole_semantic_suite_is_clean(con, live):
    res = pbi_controls.run(con)
    assert not res.failed, [r["control_id"] for r in res.failed]
    # P6-PBIP-03 drives Desktop's UI and is run by the phase run, not by every test session;
    # its result is held by the committed control register and asserted below.
    skipped = [r["control_id"] for r in res.not_executed if r["control_id"] != "P6-PBIP-03"]
    assert not skipped, skipped


# ===================================================================== native project (6A.2)
def _tmdl(name: str) -> str:
    return (C.MODEL_DIR / "definition" / name).read_text(encoding="utf-8")


def test_doc_comments_only_on_objects_that_carry_a_description():
    """P6B-D-01: a /// above a relationship is a property the parser rejects."""
    bad = [t for t in pbi_controls._doc_comment_targets() if t[2] not in pbi_controls.DOCUMENTABLE]
    assert not bad, bad


def test_no_table_name_desktop_reserves():
    """P6B-D-02: `Measures` is reserved by Desktop and refused at open."""
    names = pbi_controls._declared_tables()
    assert len(names) == 28
    assert not [n for n in names if n.lower() in C.RESERVED_TABLE_NAMES]
    assert C.MEASURES_TABLE == "Northstar Measures"
    assert C.MEASURES_TABLE in names


def test_the_measures_host_kept_every_measure_folder_and_format():
    text = _tmdl(f"tables/{C.MEASURES_TABLE}.tmdl")
    assert text.count("\tmeasure '") == len(MEASURES) == 96
    for name, expression, fmt, folder, description in MEASURES:
        assert f"\tmeasure '{name}' =" in text
        assert f"displayFolder: {folder}" in text
        if fmt:
            assert f"formatString: {fmt}" in text
    assert "lineageTag" in text


def test_relationship_rationale_survives_as_an_annotation():
    """The rationale moved, it did not disappear: one annotation per inactive relationship."""
    text = _tmdl("relationships.tmdl")
    assert "///" not in text
    for *_, why in C.INACTIVE_RELATIONSHIPS:
        assert " ".join(why.split()) in text
    assert text.count("annotation Northstar_Rationale") == len(C.INACTIVE_RELATIONSHIPS) == 5


def test_auto_date_time_is_declared_off():
    """Otherwise Desktop adds a hidden date table per date column that no declaration owns."""
    assert "annotation __PBI_TimeIntelligenceEnabled = 0" in _tmdl("model.tmdl")


def test_the_definition_digest_ignores_container_naming():
    """Renaming the measures host is metadata drift, and the definition digest must not move."""
    from src.powerbi import run as pbi_run
    before = pbi_run.definition_digest()
    original = C.MEASURES_TABLE
    C.MEASURES_TABLE = "Measures"
    try:
        assert pbi_run.definition_digest() == before
    finally:
        C.MEASURES_TABLE = original


def _control_results() -> dict[str, dict]:
    path = C.CONTROL_RESULTS
    if not path.exists():
        pytest.skip("the semantic controls have not been run")
    with open(path, newline="", encoding="utf-8") as f:
        return {r["control_id"]: r for r in csv.DictReader(f)}


def test_the_phase_run_opened_the_project_in_desktop():
    """
    The decisive Phase 6A.2 test, read from the phase run's register: Desktop itself parsed
    and loaded the generated project, and the three forms of the model agree on structure.
    """
    res = _control_results()
    for cid in ("P6-PBIP-01", "P6-PBIP-02", "P6-PBIP-03", "P6-PBIP-04"):
        assert res[cid]["status"] == "PASS", (cid, res[cid]["detail"])
    assert "opened" in res["P6-PBIP-03"]["detail"]
    assert "native refresh loaded every partition" in res["P6-PBIP-03"]["detail"]
    assert "desktop" in res["P6-PBIP-04"]["measured"]


# ===================================================================== fixtures
def _fault_results() -> list[dict]:
    path = C.FAULT_RESULTS
    if not path.exists():
        pytest.skip("the semantic fault fixtures have not been run")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_sixteen_semantic_fixtures_are_declared():
    assert len(FIXTURES) == 16
    assert {f[0] for f in FIXTURES} == ({f"F6-XAR-{i:02d}" for i in range(1, 11)}
                                        | {"F6-PBIP-01", "F6-PBIP-02"}
                                        | {f"F6A3-{i:02d}" for i in range(1, 5)})


# ===================================================================== Phase 6A.3
def test_business_unit_reaches_every_fact_through_entity():
    """P6B-D-05: the active path exists and it is the only one."""
    assert ("Entity", "bu_code", "Business Unit", "bu_code") in C.RELATIONSHIPS
    edges, bidirectional = pbi_controls._active_graph(live=False)
    for fact in C.EXPECTED_PATHS["Business Unit"]:
        assert len(pbi_controls._paths(edges, "Business Unit", fact)) == 1, fact
    assert not bidirectional


def test_every_declared_dimension_reaches_its_facts_on_one_active_path():
    edges, _ = pbi_controls._active_graph(live=False)
    for dim, facts in C.EXPECTED_PATHS.items():
        for fact in facts:
            assert len(pbi_controls._paths(edges, dim, fact)) == 1, (dim, fact)


def test_variance_pct_is_a_ratio_of_governed_components_at_every_grain():
    """P6B-D-04: no stored-percentage branch, no HASONEVALUE, no SUM of a pct column."""
    expr = next(e for n, e, *_ in MEASURES if n == "Variance %")
    assert expr.strip() == "DIVIDE ( [Variance], ABS ( [Variance Comparator] ) )"
    assert "pct" not in expr


def test_money_formats_are_power_bi_grammar():
    """P6B-D-03: scaling commas before the decimal, brackets, en dash; never the Excel form."""
    from src.powerbi.measures import M_USD, M_USD2
    assert M_USD == '#,0,,.0;(#,0,,.0);"–"' and M_USD2 == '#,0,,.00;(#,0,,.00);"–"'
    assert not [n for n, e, f, *_ in MEASURES if f and ".0,," in f]


def test_business_unit_filters_the_facts(live):
    rows = dax.query("EVALUATE ADDCOLUMNS ( VALUES ( 'Business Unit'[bu_code] ), \"v\", "
                     "CALCULATE ( [Revenue], 'Date'[period_key] = 202608, "
                     "'Scenario'[scenario_code] = \"ACT\" ) )")
    values = [r[1] for r in rows]
    group = dax.measure_at("Revenue", 202608, "'Scenario'[scenario_code] = \"ACT\"")
    assert len(set(values)) == 5
    assert abs(sum(v or 0 for v in values) - group) < 0.05


def test_variance_pct_at_group_grain_is_the_workbook_figure(live):
    ebit = dax.query("EVALUATE ROW ( \"v\", CALCULATE ( [Variance %], 'Date'[period_key] = 202608, "
                     "'Comparison'[comparison_code] = \"ACT_VS_BUD\", "
                     "'Measure Line'[measure_code] = \"EBIT\" ) )")[0][0]
    assert abs(ebit - (-0.3276)) < 0.001     # the workbook's (32.8%), not 2,713.9%


def test_the_governed_money_format_renders(live):
    from src.powerbi.measures import M_USD
    fs = M_USD.replace('"', '""')
    got = [dax.query(f'EVALUATE ROW ( "s", FORMAT ( {v}, "{fs}" ) )')[0][0]
           for v in (5553457.5, -5553457.5, 0, 278980889.78, -939022.82)]
    assert got == ["5.6", "(5.6)", "–", "279.0", "(0.9)"]


def test_the_report_carries_no_format_override_and_no_stacked_display_unit():
    import json
    pages = C.REPORT_DIR / "definition" / "pages"
    if not pages.exists():
        pytest.skip("the report has not been generated")
    money = {n for n, e, f, *_ in MEASURES if f and ",,." in f}
    for vf in pages.rglob("visual.json"):
        v = json.loads(vf.read_text(encoding="utf-8"))
        for role in v.get("visual", {}).get("query", {}).get("queryState", {}).values():
            for pr in role.get("projections", []):
                m = pr.get("field", {}).get("Measure", {}).get("Property")
                assert not (m in money and pr.get("format")), (vf, m)


def test_deferred_concepts_are_on_record():
    deferred = {c for c, m in C.REPORT_CONCEPTS.items() if m is None}
    assert deferred == {"DSO", "DIO", "DPO", "Cash conversion cycle", "Revolver drawn",
                        "Revolver available", "Principal by instrument"}
    names = {m[0] for m in MEASURES}
    assert all(m in names for m in C.REPORT_CONCEPTS.values() if m)


def test_the_pbip_fixtures_were_accepted_by_the_engine_and_caught_by_the_project_controls():
    """Engine-valid, project-invalid -- the lesson of Phase 6A.2, held as a fixture."""
    rows = {r["fixture_id"]: r for r in _fault_results()}
    for fid, cid in (("F6-PBIP-01", "P6-PBIP-01"), ("F6-PBIP-02", "P6-PBIP-02")):
        assert rows[fid]["status"] == "DETECTED", rows[fid]
        assert cid in rows[fid]["controls_triggered"]
    # TMSL carries no comment, so the engine can never object to F6-PBIP-01.
    assert "engine accepted" in rows["F6-PBIP-01"]["controls_triggered"], rows["F6-PBIP-01"]
    # The engine's answer to the reserved name depends on its state: a fresh instance accepts
    # it (as Phase 6A recorded), one that Desktop has loaded a project into refuses it. Either
    # way the project control is what catches it, which is the point.
    assert "engine" in rows["F6-PBIP-02"]["controls_triggered"], rows["F6-PBIP-02"]


def test_every_semantic_fixture_is_caught_by_its_intended_control():
    for row in _fault_results():
        assert row["status"] == "DETECTED", (
            f"{row['fixture_id']} was not caught by {row['expected_control']}; "
            f"triggered instead: {row['controls_triggered']}")
