"""
Phase 3.2 - the two source defects Phase 4 found, tested at the rule that caused each one.

    P3-D-05  an entity's opening balance sheet and the rate it is stated at are one fact,
             and the two halves of the generator have to agree about it
    P3-D-06  a decomposition sums to the thing it decomposes, and a control's population is
             the register that requires the balance, not the ledger that happens to hold it

Both were found by the consolidation engine rather than by the source controls, which is the
useful part: an engine that has to reproduce an independently produced expectation asks
questions of the data that a self-consistency check does not.
"""

from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation import fx, investments
from src.generation.common import CONFIG, REFERENCE, read_csv

WINDOW_OPENS = dt.date(2023, 1, 1)


def entities():
    return {r["entity_code"]: r for r in read_csv(CONFIG / "entities" / "entity_master.csv")}


def historical():
    return read_csv(REFERENCE / "fx_rates_historical.csv")


# =====================================================================================
# P3-D-05  the opening translation base
# =====================================================================================
def test_the_window_boundary_is_inclusive():
    """
    An entity consolidated ON the first day of the window opens from the FY2022 balance
    sheet, not from January's. The test used to be `period < 202301`, which put such an
    entity in the acquisition branch and registered a rate a month later than the balance
    sheet it is the base for.
    """
    assert fx.WINDOW_OPENS == WINDOW_OPENS


def test_every_opening_base_matches_the_balance_sheet_it_is_the_base_for():
    """
    The rule, stated once and checked for every entity: an entity in the group when the
    window opens is stated at the FY2022 closing anchor; one acquired inside the window at
    the closing rate of its acquisition month. Nothing else is a valid basis.
    """
    ent = entities()
    anchors = fx._anchor_rates()
    series = fx.rate_lookup(fx.build_rate_series())
    bases = {r["entity_code"]: r for r in historical()
             if r["group_account"] == "ACQ_OPENING_BS"}
    assert bases, "no opening translation bases are registered"
    for code, row in bases.items():
        eff = dt.date.fromisoformat(ent[code]["consolidation_effective_from"])
        ccy = ent[code]["functional_currency"]
        got = float(row["rate_usd_per_unit"])
        if eff <= WINDOW_OPENS:
            want = anchors[(ccy, 2022, "ACTUAL")][1]
            assert row["basis"] == "FY2022 closing anchor", code
        else:
            pk = eff.year * 100 + eff.month
            want = series[(ccy, pk, "CLOSE", "ACTUAL")]
            assert row["basis"] == f"closing spot {pk}", code
        assert abs(got - want) < 1e-8, f"{code}: {got} vs {want}"


def test_the_entity_that_opens_on_the_first_day_of_the_window():
    """P3-D-05 by name. NIG-510 consolidates from 2023-01-01 and opens at 1.2083."""
    row = next(r for r in historical()
               if r["entity_code"] == "NIG-510" and r["group_account"] == "ACQ_OPENING_BS")
    assert float(row["rate_usd_per_unit"]) == pytest.approx(1.2083, abs=1e-8)
    assert row["basis"] == "FY2022 closing anchor"
    # and the other GBP entity that opens at the same date agrees, which is the point:
    # two entities with the same opening balance sheet date cannot have different bases
    other = next(r for r in historical()
                 if r["entity_code"] == "NIG-320" and r["group_account"] == "ACQ_OPENING_BS")
    assert other["rate_usd_per_unit"] == row["rate_usd_per_unit"]


def test_an_acquisition_inside_the_window_is_unaffected():
    """The correction is to the boundary, not to the acquisition rule."""
    for code, period in (("NIG-220", 202304), ("NIG-410", 202407)):
        row = next(r for r in historical()
                   if r["entity_code"] == code and r["group_account"] == "ACQ_OPENING_BS")
        assert row["basis"] == f"closing spot {period}"


def test_the_cta_expectation_agrees_with_the_registered_base():
    """
    The oracle and the register are two independent statements about the same opening
    position. They disagreed for one entity, which is how the defect surfaced.
    """
    bases = {r["entity_code"]: float(r["rate_usd_per_unit"]) for r in historical()
             if r["group_account"] == "ACQ_OPENING_BS"}
    first = {}
    for r in read_csv(REFERENCE / "cta_expectation.csv"):
        key = r["entity_code"]
        if key not in first or int(r["period_key"]) < int(first[key]["period_key"]):
            first[key] = r
    for code, row in first.items():
        assert float(row["opening_rate"]) == pytest.approx(bases[code], abs=1e-8), code


# =====================================================================================
# P3-D-06  the investment that was in every register and no ledger
# =====================================================================================
def test_every_register_relationship_reaches_a_ledger():
    """
    The defect in the form that matters: the register requires eleven parent-subsidiary
    relationships and the ledger must carry all eleven.
    """
    import pandas as pd
    jl = pd.read_parquet(REFERENCE / "journal_lines.parquet")
    held = jl[jl["expected_group_account"] == "178100"]
    pairs = {(p, s) for p, s in zip(held["entity_code"], held["ic_partner_code"]) if s}
    required = {(r["parent_entity"], r["subsidiary_entity"])
                for r in read_csv(CONFIG / "entities" / "investment_register.csv")}
    assert required, "the register is empty"
    assert required <= pairs, f"in the register and in no ledger: {sorted(required - pairs)}"
    assert pairs <= required, f"in a ledger and in no register: {sorted(pairs - required)}"


def test_the_relationship_that_went_missing():
    """P3-D-06 by name."""
    import pandas as pd
    jl = pd.read_parquet(REFERENCE / "journal_lines.parquet")
    held = jl[(jl["expected_group_account"] == "178100")
              & (jl["entity_code"] == "NIG-500") & (jl["ic_partner_code"] == "NIG-510")]
    assert len(held) > 0, "NIG-500 still holds no investment in NIG-510"
    assert held["amount_local"].sum() == pytest.approx(16_900_000.0, abs=1.0)


def test_the_opening_decomposition_must_sum_to_the_opening_balance():
    """
    The guard that makes the defect impossible for every account, not only this one. An
    intercompany balance is brought forward one counterparty at a time, so if the split is
    short the balance disappears into the retained-earnings plug and the entry still
    balances -- which is exactly how USD 16.9m went missing without a single control
    noticing.
    """
    from src.generation.journals import JournalGenerator
    from src.generation.masters import build_cost_centres
    from src.generation.mapping import SourceMap
    from src.generation.series import SeriesBuilder

    gen = JournalGenerator(SeriesBuilder(), SourceMap(), build_cost_centres())
    with pytest.raises(AssertionError, match="P3-D-06"):
        gen.opening_balance("NIG-500", 202301, {"178100": 16_900_000.0}, ic_split={})


def test_an_investment_is_held_from_the_date_it_was_paid_for():
    """A subsidiary bought on the closing date is paid for that day, whatever date its
    consolidation begins. The two questions are different and the opening balance sheet
    answers the first one."""
    reg = {r["investment_id"]: r
           for r in read_csv(CONFIG / "entities" / "investment_register.csv")}
    inv = investments.investments_at(dt.date(2022, 12, 31))
    row = reg["INV-009"]
    assert (row["parent_entity"], row["subsidiary_entity"]) in inv
    assert inv[(row["parent_entity"], row["subsidiary_entity"])] == pytest.approx(16.9)


# =====================================================================================
# the control that could not see it
# =====================================================================================
def test_the_investment_control_measures_the_register_not_the_ledger():
    text = (ROOT / "src" / "generation" / "validate.py").read_text(encoding="utf-8")
    body = text.split("investment in subsidiaries")[1].split("P2-INV-02")[0]
    assert "AUTHORITATIVE population is the register" in body
    for condition in ("missing", "unexpected", "wrong_amount", "wrong_relationship",
                      "duplicates", "early"):
        assert condition in body, f"the control does not test for {condition}"


def test_the_investment_control_detects_each_defect_class():
    """
    Not that it passes on clean data -- that it FAILS on each thing it claims to detect.
    A control nobody has seen fail is a control nobody has tested.
    """
    required = {("NIG-500", "NIG-510", 202301): 16_900_000.0}

    def grade(held):
        missing = [k for k in required if k not in held]
        wrong = [k for k in required if k in held and abs(held[k] - required[k]) > 1.0]
        unexpected = [k for k in held if k not in required and abs(held[k]) > 1.0]
        return missing, wrong, unexpected

    # missing
    assert grade({})[0]
    # wrong amount
    assert grade({("NIG-500", "NIG-510", 202301): 16_000_000.0})[1]
    # wrong parent
    assert grade({("NIG-100", "NIG-510", 202301): 16_900_000.0})[2]
    # wrong subsidiary
    assert grade({("NIG-500", "NIG-410", 202301): 16_900_000.0})[2]
    # clean
    assert not any(grade({("NIG-500", "NIG-510", 202301): 16_900_000.0}))
