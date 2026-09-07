"""
Phase 2.1 regression tests.

Each test here corresponds to a defect the Phase 2 review found, and exists so that the
defect cannot come back silently:

  1. Kestrel special periods 13-16 -- Phase 1 specified four, Phase 2.0 generated one.
  2. Monthly balance sheet realism -- Phase 2.0 interpolated between anchored year ends.
  3. Investment in subsidiaries -- Phase 2.0 calibrated it to absorb a residual.
  4. Unrealised intercompany profit -- the source detail Phase 4 needs must be retained
     without Phase 2 performing the elimination.

Tests over generated data skip with a clear message unless a build has been run:

    python -m src.generation.build && python -m pytest tests -q
"""

from __future__ import annotations

import csv
import datetime as dt
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation.bsdrivers import (MIN_YEAR_END_SHARE, NONLINEAR_CAPTIONS,  # noqa: E402
                                      apply_year_end_anchor, linearity,
                                      prepaid_path, revolver_path, sawtooth_accrual)
from src.generation.common import (CONFIG, RAW, REFERENCE, build_periods,  # noqa: E402
                                   load_anchor, load_ic_anchor, read_csv)
from src.generation.investments import investments_at, load_register  # noqa: E402
from src.generation.journals import SPECIAL_PERIOD_ADJUSTMENTS  # noqa: E402

HAS_DATA = (REFERENCE / "journal_lines.parquet").exists()
needs_build = pytest.mark.skipif(
    not HAS_DATA, reason="run `python -m src.generation.build` to generate Phase 2 data")

SPECIAL_PERIODS = CONFIG / "coa" / "kestrel_special_periods.csv"


@pytest.fixture(scope="module")
def journal_lines():
    import pandas as pd
    return pd.read_parquet(REFERENCE / "journal_lines.parquet")


@pytest.fixture(scope="module")
def kestrel_special():
    """{special period: {(company code, fiscal year)}} read back off the native extracts."""
    found: dict[int, set] = defaultdict(set)
    lines: Counter = Counter()
    for path in sorted((RAW / "kestrel").glob("*.csv")):
        with open(path, newline="", encoding="cp1252") as f:
            for row in csv.DictReader(f, delimiter=";"):
                month = int(row["MONAT"])
                if month > 12:
                    found[month].add((row["BUKRS"], int(row["GJAHR"])))
                    lines[month] += 1
    return found, lines


# =====================================================================================
# 1. Kestrel special periods 13-16
# =====================================================================================
def test_special_periods_are_declared_as_configuration():
    """The four periods are config, not code, and each states its own purpose and rule."""
    rows = read_csv(SPECIAL_PERIODS)
    assert {int(r["special_period"]) for r in rows} == {13, 14, 15, 16}
    for r in rows:
        for field in ("purpose", "posted_by", "timing", "entry_nature", "population_rule"):
            assert r[field].strip(), f"period {r['special_period']} has no {field}"


def test_the_generator_implements_every_declared_special_period():
    """Period 13 is the statutory close; 14-16 each have a defined adjustment."""
    declared = {int(r["special_period"]) for r in read_csv(SPECIAL_PERIODS)}
    assert set(SPECIAL_PERIOD_ADJUSTMENTS) | {13} == declared


@needs_build
def test_all_four_special_periods_are_populated(kestrel_special):
    """The Phase 2.0 defect: periods 14, 15 and 16 were specified but never generated."""
    found, lines = kestrel_special
    assert set(found) == {13, 14, 15, 16}, f"only {sorted(found)} present"
    for period in (13, 14, 15, 16):
        assert lines[period] > 0


@needs_build
def test_statutory_close_is_universal_and_the_others_are_not(kestrel_special):
    """A finding at every entity every year would be as unrealistic as none at all."""
    found, _ = kestrel_special
    universe = found[13]
    assert universe, "period 13 must close every Kestrel company-year"
    for period in (14, 16):
        assert 0 < len(found[period]) < len(universe), (
            f"period {period} covers {len(found[period])} of {len(universe)} company-years; "
            "a conditional population rule must actually be conditional")


@needs_build
def test_unfiled_years_carry_no_audit_or_tax_period(kestrel_special):
    """FY2026 is neither audited nor filed at the reporting date."""
    found, _ = kestrel_special
    for period in (14, 15):
        assert not {y for _c, y in found[period] if y >= 2026}


@needs_build
def test_special_period_entries_do_not_move_the_reported_result(journal_lines):
    """
    Periods 14-16 are reclassifications within a caption.

    The group's reported result IS the approved anchor, so the generated ledger is the
    audited outturn: an adjustment that changed the result would contradict the anchor.
    """
    sp = journal_lines[journal_lines["line_attributes"].astype(str)
                       .str.contains("special_period=", na=False)]
    assert len(sp) > 0
    pl = sp[sp["expected_group_account"].astype(str).str[0].isin(list("45678"))]
    if len(pl):
        worst = float(pl.groupby(["entity_code", "period_key"])["amount_local"]
                      .sum().abs().max())
        assert worst <= 0.02, f"special periods moved the result by {worst}"


@needs_build
def test_special_periods_map_to_december_in_the_normalised_mirror(journal_lines):
    """Treating 13-16 as extra months would break every monthly comparison."""
    assert not (journal_lines["period_key"] % 100 > 12).any()


# =====================================================================================
# 2. Monthly balance sheet realism
# =====================================================================================
@needs_build
def test_interim_balances_are_not_straight_lines(journal_lines):
    """
    The Phase 2.0 defect: interim months interpolated between anchored year ends.

    `linearity` is 0.0 for a perfect straight line.  Every working-capital and accrual
    caption must show genuine driver-generated movement.
    """
    bs = journal_lines[journal_lines["expected_group_account"]
                       .isin(sorted(NONLINEAR_CAPTIONS))]
    monthly = (bs.groupby(["entity_code", "expected_group_account", "period_key"])
               ["amount_local"].sum().groupby(level=[0, 1]).cumsum())
    flat, tested = [], 0
    for (entity, account), series in monthly.groupby(level=[0, 1]):
        for year in (2023, 2024, 2025):
            vals = series[series.index.get_level_values(2) // 100 == year].to_numpy()
            if len(vals) < 12 or abs(vals).max() < 50_000:
                continue
            tested += 1
            if linearity(vals) < 0.02:
                flat.append(f"{entity}/{account}/{year}")
    assert tested > 200, "too few series tested for this to mean anything"
    assert not flat, f"{len(flat)} interpolated balance paths: {flat[:5]}"


def test_a_driver_path_is_oriented_to_the_sign_of_its_caption():
    """
    Drivers produce magnitudes.  Without orientation a credit caption receives a negative
    factor and, blended against the prior year, crosses zero mid-year -- which is how
    payables came to start the year as a debit.
    """
    path = np.linspace(100.0, 120.0, 12)          # a positive magnitude
    out, factor = apply_year_end_anchor(path, -240.0, prev_factor=1.0)
    assert (out < 0).all(), "an anchored credit caption must be a credit all year"
    assert out[-1] == pytest.approx(-240.0)
    assert factor > 0, "the factor applies to the oriented path, so it stays positive"


def test_the_build_refuses_a_driver_path_that_ends_at_a_trough():
    """
    Scaling a December trough onto the anchor inflates the other eleven months absurdly.
    That is a modelling error in the driver, so the build must fail rather than hide it.
    """
    trough = np.array([100.0] * 11 + [1.0])
    with pytest.raises(ValueError, match="trough"):
        apply_year_end_anchor(trough, 1_000.0)
    healthy = np.array([100.0] * 11 + [80.0])
    out, _ = apply_year_end_anchor(healthy, 1_000.0)
    assert out[-1] == pytest.approx(1_000.0)
    assert abs(healthy[-1]) >= MIN_YEAR_END_SHARE * float(np.mean(np.abs(healthy)))


def test_accrued_interest_settles_in_arrears_so_december_is_not_empty():
    """Settling on the balance sheet date leaves no year-end accrual to anchor."""
    periods = build_periods((2023, 1), (2023, 12))
    charge = np.full(12, 100_000.0)
    on_quarter_end = sawtooth_accrual(charge, periods, {3, 6, 9, 12})
    in_arrears = sawtooth_accrual(charge, periods, {1, 4, 7, 10})
    # settling on the quarter end leaves December at a trough the guard would reject
    assert on_quarter_end[-1] < MIN_YEAR_END_SHARE * float(np.mean(on_quarter_end))
    with pytest.raises(ValueError, match="trough"):
        apply_year_end_anchor(on_quarter_end, 1_300_000.0)
    # settling in arrears leaves a full quarter outstanding at the balance sheet date
    assert in_arrears[-1] > MIN_YEAR_END_SHARE * float(np.mean(in_arrears))
    out, _ = apply_year_end_anchor(in_arrears, 1_300_000.0)
    assert out[-1] == pytest.approx(1_300_000.0)


def test_prepaid_renewals_are_staggered_and_the_balance_is_a_sawtooth():
    periods = build_periods((2023, 1), (2023, 12))
    path = prepaid_path(np.full(12, 100_000.0), periods)
    assert linearity(path) > 0.3, "prepayments must not be a straight line"
    assert path[-1] > MIN_YEAR_END_SHARE * float(np.mean(path))
    assert path.min() > 0, "staggered renewals mean the balance never empties"


def test_the_revolver_is_drawn_to_need_and_repaid_in_blocks():
    pre = {202301: 20e6, 202302: -5e6, 202303: -12e6, 202304: 30e6,
           202305: 30e6, 202312: 9e6}
    activity = {pk: 1.0 for pk in pre}
    drawn = revolver_path(pre, {2023: 15e6}, activity, 6e6, 3e6, 60e6)
    assert drawn[202301] == 0.0, "no draw when the group is liquid"
    assert drawn[202303] > drawn[202302] > 0, "draw against a deepening shortfall"
    assert drawn[202305] < drawn[202303], "repaid once collections allow"
    assert drawn[202312] == 15e6, "December is the approved year-end anchor"
    assert max(drawn.values()) <= 60e6, "drawings must stay within the commitment"


@needs_build
def test_no_entity_runs_a_negative_bank_balance(journal_lines):
    """Pooling redistributes cash; the revolver is what creates it."""
    cash = journal_lines[journal_lines["expected_group_account"] == "110100"]
    balances = (cash.groupby(["entity_code", "period_key"])["amount_local"].sum()
                .groupby(level=0).cumsum())
    negative = balances[balances < -1000]
    assert negative.empty, f"{len(negative)} entity-months overdrawn"


@needs_build
def test_year_end_cash_ties_to_the_anchor_exactly():
    """
    Cash is externally verifiable and carries no residual.

    Phase 2.1 held this true by moving the difference into an equity reserve. Phase 2.2
    removed the difference itself, so the test now reads the layer-1 equity bridge that
    replaced the reserve's disclosure — the cash tie is the consequence, not the mechanism.
    """
    import pandas as pd
    jl = pd.read_parquet(REFERENCE / "journal_lines.parquet")
    rates = {(r["currency_code"], int(r["period_key"]), r["rate_type"], r["rate_set"]):
             float(r["rate_usd_per_unit"])
             for r in read_csv(REFERENCE / "fx_rates_monthly.csv")}
    bs = load_anchor("balance_sheet")
    cash = jl[jl["expected_group_account"] == "110100"]
    for year, col in ((2023, "FY2023A"), (2024, "FY2024A"), (2025, "FY2025A")):
        pk = year * 100 + 12
        upto = cash[cash["period_key"] <= pk]
        total = sum(v * rates[(c, pk, "CLOSE", "ACTUAL")] / 1e6 for v, c in zip(
            upto.groupby("currency_code")["amount_local"].sum(),
            upto.groupby("currency_code")["amount_local"].sum().index))
        assert total == pytest.approx(bs["cash"][col], abs=0.02), year


# =====================================================================================
# 3. Investment in subsidiaries
# =====================================================================================
def test_every_register_event_is_a_real_transaction():
    rows = read_csv(CONFIG / "entities" / "investment_register.csv")
    assert len(rows) >= 10
    valid = {"PLATFORM_ACQUISITION", "ACQUISITION", "ACQUIRED_WITH_PARENT",
             "FORMATION", "CARVE_OUT"}
    for row in rows:
        assert row["event_type"] in valid, row["investment_id"]
        assert float(row["consideration_usd_m"]) > 0, row["investment_id"]
        assert 0 < float(row["ownership_pct_acquired"]) <= 1
        assert row["notes"].strip(), f"{row['investment_id']} is unexplained"


def test_a_completed_deal_sits_in_the_opening_balance_sheet():
    """
    Northstar Parts UK completed on 31 December 2022 and consolidates from 1 January 2023.

    Collapsing the two dates moves the investment out of the group's opening balance sheet
    while its net assets stay in, which is why they are separate columns.
    """
    row = next(r for r in load_register() if r["investment_id"] == "INV-009")
    event = dt.date.fromisoformat(row["event_date"])
    effective = dt.date.fromisoformat(row["consolidation_effective_date"])
    assert event < effective
    assert ("NIG-500", "NIG-510") in investments_at(dt.date(2022, 12, 31))


def test_investment_balances_step_on_acquisition_dates():
    """Interpolating spreads one acquisition across twelve months."""
    before = investments_at(dt.date(2023, 3, 31))
    after = investments_at(dt.date(2023, 4, 30))
    assert ("NIG-100", "NIG-220") not in before, "Halden was acquired on 1 April 2023"
    assert after[("NIG-100", "NIG-220")] == pytest.approx(52.0)
    for month in (5, 6, 7, 8):
        later = investments_at(dt.date(2023, month, 28))
        assert later[("NIG-100", "NIG-220")] == pytest.approx(52.0), "cost does not drift"


@needs_build
def test_every_investment_balance_reconciles_to_the_register(journal_lines):
    """The Phase 2.0 defect: investment at cost was calibrated to absorb a residual."""
    closing = defaultdict(float)
    for row in read_csv(REFERENCE / "investment_rollforward.csv"):
        closing[(row["parent_entity"], int(row["period_key"]))] += float(
            row["closing_cost_usd"])
    ledger = (journal_lines[journal_lines["expected_group_account"] == "178100"]
              .groupby(["entity_code", "period_key"])["amount_local"].sum()
              .groupby(level=0).cumsum())
    assert len(ledger) > 0
    for (entity, period), value in ledger.items():
        assert abs(float(value) - closing[(entity, int(period))]) <= 1.0, (
            f"{entity} {period} is not explained by the register")


@needs_build
def test_the_rollforward_articulates():
    """Opening + additions - disposals = closing, in every row."""
    for row in read_csv(REFERENCE / "investment_rollforward.csv"):
        expected = (float(row["opening_cost_usd"]) + float(row["additions_usd"])
                    - float(row["disposals_usd"]))
        assert abs(expected - float(row["closing_cost_usd"])) <= 0.01, row


# =====================================================================================
# 4. Unrealised intercompany profit -- support, not elimination
# =====================================================================================
@needs_build
def test_intercompany_inventory_detail_supports_the_elimination():
    """Phase 4 must be able to compute the elimination from evidence, not assumption."""
    holdings = read_csv(REFERENCE / "ic_inventory_holdings.csv")
    assert holdings
    required = {"seller_entity", "buyer_entity", "transfer_price_usd", "seller_cost_usd",
                "ic_gross_profit_usd", "inventory_category", "transaction_period",
                "quantity_remaining", "value_remaining_usd", "unrealised_profit_usd"}
    assert required <= set(holdings[0]), sorted(required - set(holdings[0]))
    for row in holdings:
        gross = float(row["ic_gross_profit_usd"])
        assert abs((float(row["transfer_price_usd"]) - float(row["seller_cost_usd"]))
                   - gross) <= 0.02, "transfer price less seller cost must be the profit"


@needs_build
def test_holdings_are_fifo_layers_not_a_blended_balance():
    """One row per surviving purchase layer, so Phase 4 eliminates at the actual margin."""
    holdings = read_csv(REFERENCE / "ic_inventory_holdings.csv")
    for row in holdings:
        assert int(row["transaction_period"]) <= int(row["holding_period"])
        assert 0 < float(row["pct_remaining"]) <= 1.0
        assert float(row["value_remaining_usd"]) <= float(row["transfer_price_usd"]) + 0.01
    layered = Counter((r["holding_period"], r["seller_entity"], r["buyer_entity"])
                      for r in holdings)
    assert max(layered.values()) > 1, "a single row per month end is not layer detail"


@needs_build
def test_implied_unrealised_profit_tracks_the_anchor():
    holdings = read_csv(REFERENCE / "ic_inventory_holdings.csv")
    anchor = load_ic_anchor()["pup_in_inventory"]
    for year, col in ((2023, "FY2023A"), (2024, "FY2024A"), (2025, "FY2025A")):
        implied = sum(float(h["unrealised_profit_usd"]) for h in holdings
                      if int(h["holding_period"]) == year * 100 + 12) / 1e6
        assert abs(implied - anchor[col]) / anchor[col] <= 0.10, (
            f"{year}: implied {implied:.3f}m against anchored {anchor[col]:.3f}m")


@needs_build
def test_phase_2_does_not_perform_the_elimination(journal_lines):
    """
    The elimination is a layer-3 construct and belongs to Phase 4.

    Source inventory is carried GROSS of unrealised profit, and no source ledger may carry
    an elimination entry against it.
    """
    assert not journal_lines["entity_code"].astype(str).str.startswith("ELIM").any()
    events = set(journal_lines["event_type"].astype(str).unique())
    assert not {e for e in events if "ELIM" in e.upper() or "PUP" in e.upper()}


# =====================================================================================
# The approved anchors the Phase 2.1 corrections were not allowed to move
# =====================================================================================
def test_phase_21_left_every_approved_anchor_unchanged():
    """
    Phase 2.1 corrected source construction only and moved no anchor.

    Phase 2.2 revised exactly two, narrowly and with a derivation: the cumulative
    translation adjustment (ADR-0017) and the revolver's average drawn balance (ADR-0018).
    Those two move the year-end facility balance and total equity, so both are asserted at
    their restated values in tests/test_phase02_2_corrections.py.  Everything Phase 2.1 was
    forbidden to touch is still asserted here.
    """
    bs = load_anchor("balance_sheet")
    assert bs["cash"]["FY2023A"] == pytest.approx(15.0)
    assert bs["cash"]["FY2024A"] == pytest.approx(15.0)
    assert bs["cash"]["FY2025A"] == pytest.approx(22.0)
    assert bs["tlb_gross"]["FY2024A"] == pytest.approx(228.9, abs=1e-6)
    assert bs["ar"]["FY2025A"] == pytest.approx(65.484384, abs=1e-6)
    assert bs["inventory"]["FY2025A"] == pytest.approx(40.103425, abs=1e-6)
    assert bs["total_assets"]["FY2025A"] == pytest.approx(467.530808, abs=1e-6)
    ic = load_ic_anchor()
    assert ic["pup_in_inventory"]["FY2025A"] > 0
