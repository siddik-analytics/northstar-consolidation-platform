"""
Phase 6B.1 — the two corrections the owner held Phase 6B for.

P6B-D-06: every reportable level of the financial-statement hierarchy carries a sort key at
its own grain, derived from the governed chart order. And the consolidation bridge follows
the period basis and the reporting close exactly as the headline measures do, so a bridge
and the figure it claims to reconcile are never on different scopes.

Static checks run on the published dimensions and the committed report; the engine-side
checks are read back from the register `python -m src.powerbi.run --native` writes.
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

from src.powerbi import config as C
from src.powerbi import controls_b1 as K1
from src.powerbi import faults_b1 as F1
from src.powerbi.controls import Result
from src.powerbi.measures import MEASURES
from src.powerbi.report import controls as RK

pytestmark = pytest.mark.skipif(not C.DUCKDB_PATH.exists(),
                                reason="the warehouse has not been built")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(C.DUCKDB_PATH), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def static(con):
    r = Result()
    K1._hierarchy(r, con, live=False, why="tests are static")
    K1._scope(r, RK.Report())
    K1._bridge(r, con, live=False, why="tests are static")
    return {x["control_id"]: x for x in r}


# ===================================================================== the hierarchy
def test_every_sorted_column_is_one_to_one_with_its_key(static):
    assert static["P6B1-HS-01"]["status"] == "PASS", static["P6B1-HS-01"]["measured"]


def test_the_statement_hierarchy_keeps_chart_order_not_alphabet(static):
    assert static["P6B1-HS-02"]["status"] == "PASS", static["P6B1-HS-02"]["measured"]


def test_account_dimension_declares_caption_grain_keys():
    spec = next(t for t in C.TABLES if t["name"] == "Account")
    assert spec["sort"] == {"fs_caption_l1": "fs_caption_l1_sort",
                            "fs_caption_l2": "fs_caption_l2_sort",
                            "account_name": "sort_order"}
    assert {"fs_caption_l1_sort", "fs_caption_l2_sort"} <= set(spec["hide"])


def test_caption_keys_are_derived_from_the_governed_chart(con):
    """A caption's key is the smallest account sort order beneath it -- deterministic."""
    src = K1._published(con, next(t for t in C.TABLES if t["name"] == "Account"))
    bad = con.execute(f"""
        SELECT count(*) FROM (
            SELECT fs_caption_l2, fs_caption_l2_sort, min(sort_order) AS derived
            FROM {src} GROUP BY 1, 2
        ) WHERE fs_caption_l2_sort <> derived""").fetchone()[0]
    assert bad == 0
    reused = con.execute(f"""
        SELECT count(*) FROM (
            SELECT fs_caption_l2 FROM {src} GROUP BY 1
            HAVING count(DISTINCT fs_caption_l1) > 1)""").fetchone()[0]
    assert reused == 0, "a level-2 label reused under two level-1 captions is two nodes"


def test_scenario_and_balance_sheet_sort_at_their_own_grain(con):
    for name in ("Scenario", "Balance Sheet"):
        spec = next(t for t in C.TABLES if t["name"] == name)
        src = K1._published(con, spec)
        for col, key in spec["sort"].items():
            values, pairs = con.execute(f"""
                SELECT count(DISTINCT "{col}"), count(DISTINCT ("{col}", "{key}"))
                FROM {src}""").fetchone()
            assert values == pairs, f"{name}[{col}] by [{key}]"


# ===================================================================== the bridge
def test_the_bridge_is_read_in_the_headline_scope(static):
    assert static["P6B1-SC-01"]["status"] == "PASS", static["P6B1-SC-01"]["measured"]


def test_month_grain_bridge_sums_to_the_phase_5_bridge(static):
    assert static["P6B1-BR-01"]["status"] == "PASS", static["P6B1-BR-01"]["measured"]


def test_layer_measures_follow_the_period_basis_and_the_close():
    dax = {m[0]: m[1] for m in MEASURES}
    for name in ("Layer EBITDA", "Layer Net Income"):
        assert "'Period Basis'[basis_code]" in dax[name]
        assert "[Reporting Period Key]" in dax[name]
        assert '"MTD"' in dax[name] and '"FY"' in dax[name]
    assert dax["Layer Entries"] == "SUM ( 'Layer Bridge'[entries] )"
    assert "consolidation bridge" in dax["Consolidation Bridge Title"]


def test_the_bridge_table_is_monthly_and_dated():
    spec = next(t for t in C.TABLES if t["name"] == "Layer Bridge")
    assert spec["source"] == "fact_semantic_layer_bridge"
    assert spec["key"] == ("layer_id", "period_key")
    assert ("Layer Bridge", "period_key", "Date", "period_key") in C.RELATIONSHIPS
    assert "Layer Bridge" in C.EXPECTED_PATHS["Date"]


def test_the_bridge_title_states_its_scope():
    rep = RK.Report()
    bridge = next(v for _, v in rep.visuals() if v["name"] == "p09_controls_layer_bridge")
    title = bridge["visual"]["visualContainerObjects"]["title"][0]["properties"]["text"]
    assert title["expr"]["Measure"]["Property"] == "Consolidation Bridge Title"
    page = next(p for p in rep.pages if p["name"] == "p09_controls")
    assert {v["name"] for v in page["visuals"]} >= {"p09_controls_sl_period", "p09_controls_sl_basis"}


def test_no_annual_bridge_stands_beside_the_ytd_headline():
    """Nothing on the page pins a fiscal year onto a layer measure."""
    rep = RK.Report()
    for page, v in rep.visuals():
        if rep.measures_used(v) & {"Layer EBITDA", "Layer Net Income"}:
            assert not any(c in ("fiscal_year", "fiscal_year_label") for _, c, _ in rep.filters(v))


# ===================================================================== fixtures and registers
def test_three_fixtures_are_declared():
    assert [f[0] for f in F1.FIXTURES] == ["F6B1-01", "F6B1-02", "F6B1-03"]
    assert [f[3] for f in F1.FIXTURES] == ["P6B1-HS-01", "P6B1-SC-01", "P6B1-BR-03"]


def test_the_scope_fixture_is_detected_statically(con):
    import tempfile
    import shutil
    from src.powerbi.report import build as BUILD
    scratch = Path(tempfile.mkdtemp(prefix="northstar-6b1-test-"))
    try:
        with F1.f02_bridge_ignores_the_period():
            BUILD.generate(scratch)
            r = Result()
            K1._scope(r, RK.Report(scratch, BUILD.build_pages()))
        assert r[0]["status"] == "FAIL"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_the_register_reconciles_the_bridge_on_every_basis():
    if not K1.RESULTS.exists():
        pytest.skip("no Phase 6B.1 register; run `python -m src.powerbi.run --native` first")
    rows = {r["control_id"]: r for r in _rows(K1.RESULTS)}
    for cid in ("P6B1-BR-02", "P6B1-BR-03", "P6B1-BR-04", "P6B1-BR-05", "P6B1-BR-06",
                "P6B1-BR-07", "P6B1-BR-08", "P6B1-HS-03"):
        assert rows[cid]["status"] == "PASS", cid
    assert re.search(r"28,100,907\.83", rows["P6B1-BR-03"]["detail"])


def test_the_fault_register_detects_every_fixture():
    if not K1.FAULT_RESULTS.exists():
        pytest.skip("no Phase 6B.1 fault register yet")
    rows = _rows(K1.FAULT_RESULTS)
    assert len(rows) == 3 and all(r["status"] == "DETECTED" for r in rows)
