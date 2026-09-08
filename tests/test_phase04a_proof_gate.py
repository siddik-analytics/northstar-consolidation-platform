"""
Phase 4A - the consolidation proof gate.

These tests read the built warehouse rather than rebuilding it. They are the assertions the
owner's proof gate asks for, held where a regression would break them:

    the NCI roll-forward reconciles to the revised anchor exactly (P3-D-07 closed)
    the cash flow ties in every period and closing cash ties to the balance sheet
    the statutory and management bases differ by layer 4 and by nothing else
    every control in the Phase 4 suite passes on the clean baseline
    the control register and the code agree about which controls exist

The fault fixtures are exercised by `src/consol/faults.py` rather than here: each one runs a
full consolidation, and forty seconds of rebuilds does not belong in a unit test suite. What
belongs here is that the recorded result of that run says every fixture was handled as
intended, so a regression that quietly turns a detection into a pass fails the suite.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.consol.config import (CONFIG, CONTROL_RESULTS, DATA, DUCKDB_PATH,
                               FAULT_RESULTS)

pytestmark = pytest.mark.skipif(not DUCKDB_PATH.exists(),
                                reason="the warehouse has not been built")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    yield c
    c.close()


def rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# =====================================================================================
# P3-D-07  the revised non-controlling interest anchor
# =====================================================================================
def test_the_nci_anchor_is_derived_from_the_engine():
    """
    The Phase 1 anchor was a top-down estimate made before entity profitability existed. The
    owner ruled the generated ledger and the approved transfer price authoritative, so the
    anchor is now derived from the engine and this test is the thing that keeps it derived.
    """
    from tools.derive_nci_anchor import COLUMNS, current, derive
    derived, in_file = derive(), current()
    for column in COLUMNS:
        assert abs(derived[column] - in_file[column]) <= 5e-4, (
            f"{column}: the anchor and the engine disagree. Run "
            f"tools/derive_nci_anchor.py and rebuild the source layer")


def test_the_nci_share_is_negative_because_the_subsidiary_loses_money():
    """
    The sign is the whole of P3-D-07. NIG-510 buys at the approved transfer price and sells at
    a 12.6% gross margin, which does not cover its own operating cost, so the minority's share
    of its result is a loss. Forcing this positive would mean changing the transfer price to
    fit a superseded estimate.
    """
    from tools.derive_nci_anchor import derive
    assert all(v < 0 for v in derive().values())


def test_the_nci_rollforward_closes_every_year(con):
    breaks = con.execute("""
        SELECT count(*) FROM rpt_nci_rollforward
        WHERE abs(opening_usd + share_of_result_usd + distributions_usd + share_of_cta_usd
                  + acquisition_and_ownership_usd - closing_usd) > 0.01
    """).fetchone()[0]
    assert breaks == 0


def test_the_nci_base_excludes_intercompany_eliminations(con):
    """
    An intercompany elimination removes a matched pair and changes group profit by nothing.
    Attributing the buyer's half to the buyer without the seller's half to the seller hands
    the buyer its purchases for free -- which is what made the first NCI figure five times
    the anchor.
    """
    layers = [r[0] for r in con.execute(
        "SELECT DISTINCT layer_id FROM fact_consol_journal WHERE process = 'NCI_RESULT'"
    ).fetchall()]
    assert layers == [3]


# =====================================================================================
# the cash flow
# =====================================================================================
def test_the_cash_flow_ties_in_every_period(con):
    worst = con.execute("""
        SELECT max(abs(opening_cash_usd + operating_cash_flow_usd + investing_cash_flow_usd
                       + financing_cash_flow_usd + fx_effect_on_cash_usd - closing_cash_usd))
        FROM rpt_cash_flow
    """).fetchone()[0]
    assert float(worst) <= 0.01


def test_closing_cash_ties_to_the_balance_sheet(con):
    worst = con.execute("""
        SELECT max(abs(c.closing_cash_usd - b.balance_usd))
        FROM rpt_cash_flow c JOIN rpt_balance_sheet b
          ON b.period_key = c.period_key
         AND b.fs_caption_l2 = 'Cash and cash equivalents'
    """).fetchone()[0]
    assert float(worst) <= 0.01


def test_the_translation_adjustment_is_not_the_fx_effect_on_cash(con):
    """
    Routing the whole translation movement through the cash line makes the statement tie while
    reporting an implausible foreign exchange effect on a mostly-USD cash balance. Every
    balancing control still passes; only the separation of the two is evidence.
    """
    on_cash, non_cash = con.execute("""
        SELECT sum(fx_effect_on_cash_usd), sum(fx_non_cash_usd) FROM rpt_cash_flow
    """).fetchone()
    assert on_cash != 0 and non_cash != 0
    assert abs(float(on_cash)) < abs(float(non_cash))


def test_every_balance_sheet_account_has_one_cash_flow_category(con):
    """The statement ties by construction only if the categories partition the balance sheet."""
    missing = con.execute("""
        SELECT count(*) FROM dim_account
        WHERE statement = 'BS' AND NOT is_statistical
          AND coalesce(cash_flow_category, '') = ''
    """).fetchone()[0]
    assert missing == 0


# =====================================================================================
# statutory and management
# =====================================================================================
def test_the_two_bases_differ_by_layer_four_and_nothing_else(con):
    unexplained = con.execute("""
        SELECT measure, fiscal_year, difference_usd, layer4_usd
        FROM rpt_basis_comparison WHERE NOT explained_by_layer_4
    """).fetchall()
    assert unexplained == []


def test_every_headline_measure_is_compared(con):
    measures = {r[0] for r in con.execute(
        "SELECT DISTINCT measure FROM rpt_basis_comparison").fetchall()}
    assert measures == {"Revenue", "Gross profit", "EBITDA", "EBIT", "Net income",
                        "Total assets", "Total equity"}


def test_no_management_adjustment_reaches_the_statutory_basis(con):
    assert con.execute("SELECT count(*) FROM vw_statutory_fact WHERE layer_id = 4"
                       ).fetchone()[0] == 0


# =====================================================================================
# the control suite and the fixtures
# =====================================================================================
def test_every_phase_four_control_passes_on_the_clean_baseline():
    failed = [r for r in rows(CONTROL_RESULTS)
              if r["status"] == "FAIL" and r["severity"] == "BLOCKING"]
    assert failed == [], [r["control_id"] for r in failed]


def test_the_control_register_and_the_code_agree():
    """
    A register listing a control the code does not run, or a control the register does not
    describe, is how a control suite drifts into decoration.
    """
    register = {r["control_id"] for r in rows(CONFIG / "controls" / "phase04_control_register.csv")}
    built = {r["control_id"] for r in rows(CONTROL_RESULTS)}
    assert register == built, (register ^ built)


def test_every_fault_fixture_was_handled_as_intended():
    good = {"DETECTED", "DETECTED_BY_REFUSAL", "SEPARATION_PROVEN", "SUPPRESSED"}
    bad = [r for r in rows(FAULT_RESULTS) if r["status"] not in good]
    assert bad == [], [(r["fault_id"], r["status"]) for r in bad]


def test_no_fixture_was_caught_only_by_an_unrelated_control():
    """
    A fault found by a control that does not own it is a control-design defect wearing the
    costume of a success.
    """
    accidental = [r["fault_id"] for r in rows(FAULT_RESULTS)
                  if r["status"] == "ACCIDENTAL_DETECTION"]
    assert accidental == []


def test_f02_is_caught_by_the_intercompany_pair_reconciliation():
    """
    Phase 3 deferred F02 with a reason: no Phase 3 artefact contains both sides of the pair.
    The gate is that the Phase 4 control which owns it catches it -- detection by anything
    else does not close the deferral.
    """
    f02 = next(r for r in rows(FAULT_RESULTS) if r["fault_id"] == "F02")
    assert f02["status"] == "DETECTED"
    assert "P4-IC-01" in f02["detected_by"].split(";")


def test_the_separation_fixture_actually_posted_something():
    """
    A fixture that proves a negative has to show its working: "nothing broke" is also what an
    edit that never reached the engine looks like.
    """
    leak = next(r for r in rows(FAULT_RESULTS) if r["fault_id"] == "F4-MGT-LEAK")
    assert leak["status"] == "SEPARATION_PROVEN"
    assert int(leak["layer4_legs_posted"]) > 0
    assert int(leak["measures_moved"]) > 0


def test_the_draft_adjustment_reached_no_layer():
    draft = next(r for r in rows(FAULT_RESULTS) if r["fault_id"] == "F4-17")
    assert draft["status"] == "SUPPRESSED"
    assert int(draft["layer4_legs_posted"]) == 0


# =====================================================================================
# determinism
# =====================================================================================
def test_the_build_is_reproducible_from_its_declared_inputs():
    """
    The build id is a digest of the frozen source layer and the committed configuration. If a
    rebuild produced a different id from unchanged inputs, no artefact could be used as
    evidence of anything.
    """
    from src.consol.run import build_id
    manifest = json.loads((DATA / "phase04_manifest.json").read_text(encoding="utf-8"))
    assert manifest["build_id"] == build_id()


def test_no_consolidation_step_resolves_a_value_arbitrarily():
    """
    `any_value()` returns whichever row the aggregate saw first, so an artefact built from it
    can change between two runs over identical data. One did: the balance sheet caption
    'Intercompany balances' spans assets and liabilities, and its class was being chosen at
    random. ADR-0022 is the reason this is a test and not a preference.
    """
    offenders = [p.name for p in (ROOT / "src" / "consol").glob("*.py")
                 if "any_value(" in p.read_text(encoding="utf-8")]
    assert offenders == []
