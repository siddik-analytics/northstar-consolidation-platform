"""
Phase 6B — the report on the governed model.

The report is generated from declarations (`src/powerbi/report/`) and controlled as an
artefact of its own: every number a page shows is a governed measure in a stated scope, the
scope is the one the page claims, and nothing on a page is typed, computed locally, scaled
twice or dressed up as a verdict the agreement never gave.

The static families run on the committed report folder and need no engine. The live and
native families are exercised by `python -m src.powerbi.run --native`; here they are read
back from the register that run wrote.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.powerbi import config as C
from src.powerbi.controls import Result
from src.powerbi.report import build as BUILD
from src.powerbi.report import controls as K
from src.powerbi.report import faults as F
from src.powerbi.report import layout as L
from src.powerbi.report import pages as PAGES
from src.powerbi.report import theme as T

pytestmark = pytest.mark.skipif(not C.DUCKDB_PATH.exists(),
                                reason="the warehouse has not been built")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(C.DUCKDB_PATH), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def rep():
    return K.Report()


@pytest.fixture(scope="module")
def static(rep):
    r = Result()
    K._static(r, rep)
    K._inert_slicers(r, rep)
    K._style(r, rep)
    return {x["control_id"]: x for x in r}


def _rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ===================================================================== the generated report
def test_the_committed_report_is_what_the_declarations_generate():
    """Regenerating into a scratch folder reproduces the committed folder file for file."""
    scratch = Path(tempfile.mkdtemp(prefix="northstar-6b-test-"))
    try:
        BUILD.generate(scratch)
        committed = {p.relative_to(C.REPORT_DIR): p.read_text("utf-8")
                     for p in C.REPORT_DIR.rglob("*.json")}
        fresh = {p.relative_to(scratch): p.read_text("utf-8") for p in scratch.rglob("*.json")}
        assert committed == fresh
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_ten_pages_in_the_declared_order(rep):
    assert [p["name"] for p in rep.pages] == [name for name, _ in L.PAGES]
    assert rep.index["activePageName"] == "p01_executive"


def test_every_static_control_passes(static):
    failed = {cid: row["measured"] for cid, row in static.items() if row["status"] != "PASS"}
    assert failed == {}


# ===================================================================== what the pages bind
def test_headline_kpis_are_the_four_governed_primaries(static):
    assert static["P6B-03"]["measured"] == str(list(K.HEADLINE_PRIMARY))


def test_no_typed_amount_and_no_implicit_measure(static):
    assert static["P6B-01"]["status"] == "PASS"
    assert static["P6B-02"]["status"] == "PASS"


def test_the_deferred_concepts_are_absent(rep):
    blob = " ".join(json.dumps(v) for _, v in rep.visuals())
    for name in ("DSO", "DIO", "DPO", "Cash conversion cycle"):
        assert not re.search(rf"\b{name}\b", blob)
    assert {c for c, m in C.REPORT_CONCEPTS.items() if m is None} >= {"DSO", "DIO", "DPO"}


def test_control_counts_are_read_not_typed(static):
    assert static["P6B-13"]["status"] == "PASS"
    src = (ROOT / "src" / "powerbi" / "report" / "pages.py").read_text("utf-8")
    assert not re.search(r'"[^"\n]*\b(49|53|68)\b[^"\n]*"', src)


def test_every_nofilter_has_a_reason():
    for pg in BUILD.build_pages():
        for i in pg.interactions:
            assert pg.reasons.get((i["source"], i["target"])), i


def test_a_nofilter_without_a_reason_cannot_be_declared():
    pg = L.Page("p99_test", "99 Test", "t", "s", slicers=("sl_period",))
    with pytest.raises(ValueError):
        pg.no_filter("sl_period", "title", reason="")


def test_group_level_pages_carry_no_unit_slicer(rep):
    for page in rep.pages:
        if page["name"] in ("p04_balance", "p05_cash", "p07_debt", "p09_controls", "p10_lineage"):
            assert not any(v["name"].endswith("_sl_bu") for v in page["visuals"]), page["name"]


# ===================================================================== the inventory
def test_the_object_inventory_classifies_every_visual():
    inv = K.inventory()
    assert inv["visuals"] == sum(p["objects"] for p in inv["pages"].values())
    assert set(inv["total"]) <= set(L.KINDS)
    assert inv["total"]["analytical"] >= 25
    for display, counts in inv["pages"].items():
        assert counts.get("analytical", 0) <= L.MAX_ANALYTICAL, display
        assert counts.get("navigation") == len(L.PAGES), display


def test_every_page_states_its_management_question():
    assert len(PAGES.QUESTIONS) == len(L.PAGES)
    for _, question in PAGES.QUESTIONS:
        assert question.endswith("?")


# ===================================================================== style
def test_palette_and_type_scale(static):
    assert static["P6B-26"]["status"] == "PASS"
    assert static["P6B-27"]["status"] == "PASS"
    assert T.NAVY_HOVER.upper() in K.PALETTE


# ===================================================================== fixtures
def test_twelve_report_fixtures_are_declared():
    assert len(F.FIXTURES) == 12
    assert [f[0] for f in F.FIXTURES[:8]] == [f"F6B-0{i}" for i in range(1, 9)]


@pytest.mark.parametrize("fixture", [f for f in F.FIXTURES if f[2].__code__.co_argcount == 1
                                     and f[3] not in ("P6B-12",)],
                         ids=lambda f: f[0])
def test_a_file_fixture_is_detected_statically(fixture, con):
    """The file-mutation fixtures are caught by the static families alone."""
    fid, _, mutate, intended = fixture
    scratch = Path(tempfile.mkdtemp(prefix="northstar-6b-fx-"))
    try:
        BUILD.generate(scratch)
        mutate(scratch)
        rep = K.Report(scratch, BUILD.build_pages())
        r = Result()
        K._static(r, rep)
        K._inert_slicers(r, rep)
        hit = next(x for x in r if x["control_id"] == intended)
        assert hit["status"] == "FAIL", fid
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ===================================================================== the registers
@pytest.fixture(scope="module")
def register():
    if not K.RESULTS.exists():
        pytest.skip("no Phase 6B register; run `python -m src.powerbi.run --native` first")
    return {r["control_id"]: r for r in _rows(K.RESULTS)}


def test_the_register_has_no_blocking_failure(register):
    failed = [cid for cid, r in register.items()
              if r["status"] == "FAIL" and r["severity"] == "BLOCKING"]
    assert failed == []


def test_the_thirteen_reconciliations_are_in_the_register(register):
    ids = [cid for cid, _, _, _, _, _, _ in K.RECON]
    assert len(ids) == 13
    for cid in ids:
        assert cid in register


def test_the_fault_register_detects_every_fixture():
    if not K.FAULT_RESULTS.exists():
        pytest.skip("no Phase 6B fault register yet")
    rows = _rows(K.FAULT_RESULTS)
    assert len(rows) == len(F.FIXTURES)
    assert all(r["status"] == "DETECTED" for r in rows)


def test_the_native_record_is_bound_to_a_project_digest():
    if not K.NATIVE_QA.exists():
        pytest.skip("no native record yet")
    qa = json.loads(K.NATIVE_QA.read_text("utf-8"))
    assert re.fullmatch(r"[0-9a-f]{16}", qa["project_digest"])
    assert qa["opened"] and qa["refreshed"]
    assert sum(len(v) for v in qa["visual_errors"].values()) == 0
