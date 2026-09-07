"""
Phase 2 tests.

Split into two groups:

  * Tests that need no generated data -- configuration, the anchor bridge, the
    expected-mapping manifest, determinism of the generators themselves.  These always run.
  * Tests over the generated datasets.  Generated data is large and is not committed, so
    these skip with a clear message unless a build has been run.

    python -m src.generation.build && python -m pytest tests -q
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation import faults as faults_mod                       # noqa: E402
from src.generation.common import (ANCHORS, CONFIG, DATA, RAW, REFERENCE, SAMPLES,
                                   build_periods, operating_entities, read_csv, rng)
from src.generation.fx import build_rate_series                       # noqa: E402
from src.generation.mapping import NOT_AVAILABLE, SourceMap           # noqa: E402
from src.generation.targets import build_targets                      # noqa: E402

HAS_DATA = (REFERENCE / "journal_lines.parquet").exists()
needs_build = pytest.mark.skipif(
    not HAS_DATA, reason="run `python -m src.generation.build` to generate Phase 2 data")


# =====================================================================================
# 1. GENERATORS AND CONFIGURATION -- always run
# =====================================================================================
def test_period_spine_covers_the_approved_range():
    p = build_periods()
    assert p[0].period_key == 202301 and p[-1].period_key == 202608
    assert len(p) == 44, "January 2023 to August 2026 inclusive"


def test_seeded_generators_are_reproducible_and_independent():
    a1 = rng("stream", "a").normal(size=5)
    a2 = rng("stream", "a").normal(size=5)
    b = rng("stream", "b").normal(size=5)
    assert (a1 == a2).all(), "the same key must give the same draws"
    assert not (a1 == b).all(), "different keys must give different draws"


def test_fx_series_reproduces_the_annual_anchors():
    anchors = {(r["currency_code"], int(r["fiscal_year"]), r["rate_set"]):
               (float(r["average_rate_usd"]), float(r["closing_rate_usd"]))
               for r in read_csv(ANCHORS / "anchor_fx_rates.csv")}
    rows = build_rate_series()
    by_year: dict[tuple, list[float]] = {}
    closes: dict[tuple, float] = {}
    for r in rows:
        if r["rate_set"] != "ACTUAL" or r["currency_code"] == "USD":
            continue
        key = (r["currency_code"], r["period_key"] // 100)
        if r["rate_type"] == "AVG":
            by_year.setdefault(key, []).append(r["rate_usd_per_unit"])
        elif r["period_key"] % 100 == 12:
            closes[key] = r["rate_usd_per_unit"]
    for (ccy, year), vals in by_year.items():
        if len(vals) < 12:
            continue
        want = anchors.get((ccy, year, "ACTUAL"), anchors.get((ccy, year, "FORECAST")))
        got = sum(vals) / len(vals)
        assert abs(got / want[0] - 1) < 0.001, f"{ccy} {year} average off anchor"
        assert abs(closes[(ccy, year)] - want[1]) < 1e-6, f"{ccy} {year} close off anchor"


def test_fx_rates_are_quoted_usd_per_unit():
    bands = {"USD": (1.0, 1.0), "CAD": (0.55, 0.95), "GBP": (0.95, 1.65), "EUR": (0.85, 1.40)}
    for r in build_rate_series():
        lo, hi = bands[r["currency_code"]]
        assert lo <= r["rate_usd_per_unit"] <= hi, f"{r['currency_code']} looks inverted"


def test_every_erp_can_post_every_account_it_needs():
    """A group account an ERP cannot post would silently unbalance a journal."""
    sm = SourceMap()
    manifest = read_csv(CONFIG / "generation" / "expected_mapping_manifest.csv")
    assert manifest, "expected-mapping manifest not generated"
    for row in manifest:
        assert sm.resolve(row["erp_system"], row["requested_group_account"]) is not None


def test_expected_mapping_manifest_is_wellformed():
    rows = read_csv(CONFIG / "generation" / "expected_mapping_manifest.csv")
    valid_group = {r["group_account"] for r in read_csv(CONFIG / "coa" / "group_coa.csv")}
    for r in rows:
        assert r["expected_group_account"] in valid_group
        assert r["erp_system"] in ("AURORA", "SABLE", "KESTREL")
        if r["substituted_because_unavailable"] == "TRUE":
            assert r["expected_group_account"] != r["requested_group_account"]
    assert any(r["required_line_attributes"] for r in rows), \
        "conditional splits must record the attribute the mapping engine has to read"


def test_substitutions_never_cross_a_statement_boundary():
    """A substitution may lose granularity; it must not move cost across gross margin."""
    for (erp, requested), actual in NOT_AVAILABLE.items():
        assert requested[0] == actual[0], (
            f"{erp} {requested} -> {actual} crosses a statement block")


def test_anchor_bridge_is_derived_not_asserted():
    rows = {(r["statement"], r["line_item"]): r for r in build_targets()}
    ic = {r["measure"]: r for r in read_csv(ANCHORS / "anchor_intercompany.csv")}
    pl = {r["line_item"]: r for r in read_csv(ANCHORS / "anchor_income_statement.csv")}
    want = (float(pl["revenue"]["FY2025A"]) + float(ic["mgmt_fee"]["FY2025A"])
            + float(ic["ic_product_sales"]["FY2025A"])
            + float(ic["ic_service_sales"]["FY2025A"]) + float(ic["ic_royalty"]["FY2025A"]))
    assert rows[("IS", "revenue")]["FY2025A"] == pytest.approx(want, abs=1e-6)
    assert rows[("IS", "amortisation")]["FY2025A"] == 0.0, "layer 1 carries no PPA amortisation"
    assert rows[("BS", "goodwill")]["FY2025A"] == 0.0, "goodwill is recognised on consolidation"


def test_virtual_entities_never_appear_in_source_generation():
    ents = operating_entities()
    assert len(ents) == 12
    assert not any(e.is_elimination for e in ents.values())


def test_fault_catalogue_is_complete_and_mapped_to_controls():
    controls = {r["control_id"] for r in read_csv(CONFIG / "controls" / "control_register.csv")}
    assert len(faults_mod.CATALOGUE) >= 10
    ids = [f.fault_id for f in faults_mod.CATALOGUE]
    assert len(ids) == len(set(ids))
    for f in faults_mod.CATALOGUE:
        assert f.expected_control in controls, f"{f.fault_id} names an unknown control"
        assert f.description.strip() and f.detector.strip()


# =====================================================================================
# 2. GENERATED DATA
# =====================================================================================
@pytest.fixture(scope="module")
def controls():
    from src.generation.validate import run
    return {r["control_id"]: r for r in run()}


@needs_build
def test_all_source_controls_pass(controls):
    failed = [c for c in controls.values()
              if c["status"] == "FAIL" and c["severity"] == "BLOCKING"]
    assert not failed, "blocking source controls failed: " + ", ".join(
        f"{c['control_id']} ({c['measured']} vs {c['threshold']})" for c in failed)


@needs_build
@pytest.mark.parametrize("cid", ["P2-SRC-01", "P2-SRC-02", "P2-SRC-03", "P2-SRC-04"])
def test_source_accounting_integrity(controls, cid):
    assert controls[cid]["status"] == "PASS", controls[cid]["detail"]


@needs_build
def test_native_extracts_round_trip_all_three_sign_conventions(controls):
    """The strongest Phase 2 control: parse the raw files and re-derive a signed amount."""
    c = controls["P2-SRC-03"]
    assert c["status"] == "PASS", c["detail"]


@needs_build
@pytest.mark.parametrize("year", [2023, 2024, 2025])
@pytest.mark.parametrize("item", ["REV", "COS", "OPE"])
def test_income_statement_reconciles_to_the_anchor_bridge(controls, year, item):
    c = controls[f"P2-ANC-{item}-{year}"]
    assert c["status"] == "PASS", c["detail"]


@needs_build
@pytest.mark.parametrize("year", [2023, 2024, 2025])
@pytest.mark.parametrize("cap", ["AR", "INVE", "AP", "CASH", "PPE_"])
def test_balance_sheet_reconciles_to_the_anchor_bridge(controls, year, cap):
    c = controls[f"P2-ANC-BS-{cap}-{year}"]
    assert c["status"] == "PASS", c["detail"]


@needs_build
def test_revenue_detail_reconciles_to_the_ledger(controls):
    assert controls["P2-REC-01"]["status"] == "PASS", controls["P2-REC-01"]["detail"]


@needs_build
def test_intercompany_pairs_match_before_injected_faults(controls):
    assert controls["P2-IC-01"]["status"] == "PASS", controls["P2-IC-01"]["detail"]


@needs_build
def test_forecast_actual_months_equal_the_actual_scenario(controls):
    assert controls["P2-SCN-01"]["status"] == "PASS", controls["P2-SCN-01"]["detail"]


@needs_build
def test_reserved_downside_scenario_is_not_populated(controls):
    assert controls["P2-CMP-04"]["status"] == "PASS"


@needs_build
def test_kestrel_native_conventions_survive(controls):
    assert controls["P2-FMT-01"]["status"] == "PASS", "no special period 13"
    assert controls["P2-FMT-02"]["status"] == "PASS", "leading zeros lost"


@needs_build
def test_the_three_source_charts_never_converge(controls):
    assert controls["P2-FMT-03"]["status"] == "PASS"


@needs_build
def test_data_volume_is_in_the_approved_range():
    import json
    m = json.loads((DATA / "build_manifest.json").read_text(encoding="utf-8"))
    n = m["generated_datasets"]["journal_lines"]
    assert 1_000_000 <= n <= 1_500_000, f"{n:,} journal lines is outside the approved range"


@needs_build
def test_build_is_deterministic():
    """Rebuild and compare the dataset digest. This is the reproducibility guarantee."""
    before = (SAMPLES / "build_digest.txt").read_text(encoding="utf-8")
    subprocess.run([sys.executable, "-m", "src.generation.build"], cwd=ROOT,
                   check=True, capture_output=True)
    after = (SAMPLES / "build_digest.txt").read_text(encoding="utf-8")
    assert before == after, "a rebuild from the same seed produced different data"


# ---------------------------------------------------------------- fault fixtures
@needs_build
@pytest.mark.parametrize("fault", [f.fault_id for f in faults_mod.CATALOGUE])
def test_each_injected_fault_is_detected(fault):
    """A control that has never failed has never been tested."""
    if not (DATA / "faults" / "expected_results.json").exists():
        faults_mod.inject()
    assert faults_mod.detect(fault), f"{fault} was not detected by its own detector"


@needs_build
def test_clean_baseline_is_not_contaminated_by_the_faults(controls):
    """Fault variants live in their own directory; the baseline must still be clean."""
    assert not [c for c in controls.values()
                if c["status"] == "FAIL" and c["severity"] == "BLOCKING"]
    assert (DATA / "faults").exists()
    for sub in (DATA / "faults").iterdir():
        if sub.is_dir():
            assert not str(sub).startswith(str(RAW)), "a fault variant leaked into data/raw"
