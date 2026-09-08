"""
Phase 2.2 - source-layer integrity.

Two things had to become true before the source data could be frozen.

1.  **No plug.**  The layer-1 balance sheet must close on its own arithmetic.  Phase 2.0
    absorbed a residual into investment-at-cost; Phase 2.1 moved it to a named equity
    reserve, `329100 Group reporting measurement reserve`.  Both were the same defect: a
    balance whose only purpose was to make the generated data agree with an independently
    specified group target.  Phase 2.2 derives the layer-1 equity target from the approved
    anchors, fixes contributed capital at historical rates so the translation adjustment
    can actually arise, and removes the reserve entirely.

2.  **A facility that pays for itself.**  The revolver's recorded interest must be
    supported by the balance the ledger produced, on the days it was drawn.

These tests assert the properties, not the implementation.  They fail if a plug reappears
under any name, if the CTA stops being derivable from source balances and the rate file, or
if the facility's charge stops being explained by its own utilisation.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation.common import (CONFIG, REFERENCE, load_anchor, load_credit_agreement,
                                   load_ic_anchor, load_source_coa, load_treasury_policy,
                                   read_csv)

needs_build = pytest.mark.skipif(
    not (REFERENCE / "layer1_equity_bridge.csv").exists(),
    reason="run `python -m src.generation.build` first")


def read(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# =====================================================================================
# 1.  The measurement reserve is gone, and nothing has taken its place
# =====================================================================================
def test_the_measurement_reserve_account_is_removed_from_the_group_chart():
    accounts = {r["group_account"] for r in read(CONFIG / "coa" / "group_coa.csv")}
    assert "329100" not in accounts


def test_the_measurement_reserve_account_is_removed_from_every_source_chart():
    for erp in ("aurora", "sable", "kestrel"):
        rows = load_source_coa(erp)
        if erp == "aurora":
            assert "3250" not in {r["source_account"] for r in rows}
        assert not any(r["group_account"] == "329100" for r in rows)


def test_no_account_in_any_chart_exists_to_balance_the_model():
    """
    The test is on purpose, not on one retired account number.

    A chart of accounts is source data.  An account whose name says it exists to make the
    group reporting model agree is not something a real ERP contains, whatever it is
    called, so the prohibition is written against the idea rather than the code.
    """
    banned = ("measurement reserve", "group reporting measurement", "balancing",
              "residual", "plug", "calibration", "suspense", "true-up to group")
    offenders = [r["account_name"] for r in read(CONFIG / "coa" / "group_coa.csv")
                 if any(w in r["account_name"].lower() for w in banned)]
    for erp in ("aurora", "sable", "kestrel"):
        offenders += [r["source_account_name"] for r in load_source_coa(erp)
                      if any(w in r["source_account_name"].lower() for w in banned)]
    assert not offenders, offenders


def test_the_expected_mapping_manifest_carries_no_reserve():
    rows = read(CONFIG / "generation" / "expected_mapping_manifest.csv")
    assert not [r for r in rows if r["expected_group_account"] == "329100"]
    assert not [r for r in rows if "measurement" in r["source_account_name"].lower()]


def test_adr_0016_is_superseded():
    text = (ROOT / "docs" / "adr" / "0016-source-layer-measurement-reserve.md").read_text(
        encoding="utf-8")
    assert "SUPERSEDED" in text[:400].upper(), "the status line must say so"
    assert "0017" in text, "a superseded ADR must name what replaced it"


@needs_build
def test_no_journal_line_posts_to_a_retired_reserve():
    import pandas as pd
    jl = pd.read_parquet(REFERENCE / "journal_lines.parquet")
    assert "329100" not in set(jl["expected_group_account"].unique())
    assert "3250" not in set(jl.loc[jl["erp_system"] == "AURORA", "source_account"].unique())


# =====================================================================================
# 2.  Layer-1 equity closes on its own arithmetic
# =====================================================================================
def test_the_bridge_derives_a_layer_1_equity_target():
    """Without this line the layer-1 balance sheet has an unconstrained degree of freedom."""
    rows = read(CONFIG / "anchors" / "phase02_source_layer_targets.csv")
    equity = next((r for r in rows if r["statement"] == "BS"
                   and r["line_item"] == "total_equity"), None)
    assert equity is not None, "no derived layer-1 equity target"
    bs = load_anchor("balance_sheet")
    ic = load_ic_anchor()
    invest = next(r for r in rows if r["line_item"] == "investments_in_subsidiaries")
    for col in ("FY2023A", "FY2024A", "FY2025A"):
        expected = (bs["total_equity"][col] + float(invest[col]) - bs["goodwill"][col]
                    - bs["intangibles_net"][col] + bs["dtl"][col]
                    + ic["pup_in_inventory"][col])
        assert float(equity[col]) == pytest.approx(expected, abs=1e-6)


def test_source_layer_carries_no_cta_target():
    """A local ledger has no CTA account. Translation creates it, at layer 5."""
    rows = read(CONFIG / "anchors" / "phase02_source_layer_targets.csv")
    cta = next(r for r in rows if r["line_item"] == "cumulative_translation_adjustment")
    assert all(float(cta[c]) == 0.0 for c in ("FY2023A", "FY2024A", "FY2025A"))


@needs_build
def test_layer_1_equity_roll_forward_has_nothing_unexplained():
    for row in read(REFERENCE / "layer1_equity_bridge.csv"):
        assert abs(float(row["unexplained_usd_m"])) <= 0.001, row["fiscal_year"]


@needs_build
def test_layer_1_equity_equals_the_derived_target():
    for row in read(REFERENCE / "layer1_equity_bridge.csv"):
        assert abs(float(row["variance_vs_anchor_usd_m"])) <= 0.001, row["fiscal_year"]


@needs_build
def test_every_line_of_the_equity_bridge_is_a_transaction_or_the_cta():
    """
    The bridge may contain only things that happened, plus the computed CTA.

    A line called anything else would be the reserve coming back under a new name.
    """
    allowed = {"fiscal_year", "opening_equity_usd_m", "result_for_the_year_usd_m",
               "share_based_compensation_usd_m", "capital_contributed_usd_m",
               "equity_acquired_usd_m", "distributions_usd_m", "cta_movement_usd_m",
               "closing_equity_rolled_usd_m", "closing_equity_generated_usd_m",
               "unexplained_usd_m", "anchor_layer1_equity_target_usd_m",
               "variance_vs_anchor_usd_m"}
    rows = read(REFERENCE / "layer1_equity_bridge.csv")
    assert set(rows[0]) == allowed


# =====================================================================================
# 3.  The CTA is derived from source balances and the approved FX policy
# =====================================================================================
@needs_build
def test_every_cta_row_recomputes_from_balances_and_rates_alone():
    rows = read(REFERENCE / "cta_expectation.csv")
    assert rows, "no CTA expectation was published"
    for row in rows:
        recomputed = (float(row["opening_net_assets_local"])
                      * (float(row["closing_rate"]) - float(row["opening_rate"]))
                      + float(row["result_local"])
                      * (float(row["closing_rate"]) - float(row["average_rate"]))) / 1e6
        recomputed += float(row["cta_on_equity_movements"])
        assert recomputed == pytest.approx(float(row["cta_movement_usd_m"]), abs=1e-4), row


@needs_build
def test_the_presentation_currency_generates_no_cta():
    rows = read(REFERENCE / "cta_expectation.csv")
    assert not [r for r in rows if r["currency_code"] == "USD"]


@needs_build
def test_local_net_assets_roll_forward_without_a_translation_artefact():
    """
    Closing net assets = opening + result + equity movements, in LOCAL currency.

    If this fails, the ledger is being re-pinned to a translated target and the CTA it
    implies is not the CTA a translation engine would compute.
    """
    for row in read(REFERENCE / "cta_expectation.csv"):
        rolled = (float(row["opening_net_assets_local"]) + float(row["result_local"])
                  + float(row["equity_movement_local"]))
        assert rolled == pytest.approx(float(row["closing_net_assets_local"]), abs=0.05), row


@needs_build
def test_the_anchored_cta_is_reproduced_from_the_source_ledgers():
    for row in read(REFERENCE / "cta_group_bridge.csv"):
        assert abs(float(row["derivation_variance_usd_m"])) <= 0.001, row["fiscal_year"]


def test_the_revised_cta_anchor_is_the_one_documented():
    """
    The narrow, approved CTA revision. Asserted so it cannot drift silently.

    Restated in Phase 3.1 to the sixth decimal. The CTA is derived from the generated
    entity balances, and correcting the intercompany balances moved those balances a
    little; the largest movement in any year is USD 2.2 thousand on a figure of USD 7.7m,
    which is 0.03% and changes nothing a reader would notice. It is restated rather than
    absorbed into a wider tolerance, because the point of the assertion is that the number
    is derived and reproducible.
    """
    cta = load_anchor("cta_rollforward")
    assert cta["cta_movement_group"]["FY2023A"] == pytest.approx(2.607244, abs=5e-4)
    assert cta["cta_movement_group"]["FY2024A"] == pytest.approx(-4.665178, abs=5e-4)
    assert cta["cta_movement_group"]["FY2025A"] == pytest.approx(7.740948, abs=5e-4)
    assert cta["cta_closing"]["FY2025A"] == pytest.approx(2.183014, abs=5e-4)
    # the roll-forward still articulates
    prev = -3.5
    for col in ("FY2023A", "FY2024A", "FY2025A"):
        assert cta["cta_opening"][col] == pytest.approx(prev, abs=1e-6)
        prev = prev + cta["cta_movement_group"][col]
        assert cta["cta_closing"][col] == pytest.approx(prev, abs=1e-6)


def test_the_nci_share_of_the_translation_movement_is_derived_not_estimated():
    cta = load_anchor("cta_rollforward")
    assert cta["cta_movement_nci"]["FY2023A"] == pytest.approx(0.070689, abs=5e-4)
    assert cta["cta_movement_nci"]["FY2025A"] == pytest.approx(0.059132, abs=5e-4)


def test_contributed_capital_is_a_historical_rate_balance():
    coa = {r["group_account"]: r for r in read(CONFIG / "coa" / "group_coa.csv")}
    for acct in ("310100", "310200", "315100"):
        assert coa[acct]["fx_method"] == "HIST", acct


@needs_build
def test_contributed_capital_does_not_move_with_the_spot_rate():
    """
    A subsidiary's share capital is a fixed amount in its own currency.

    Phase 2.1 re-pinned it to a closing-rate USD target every year, so a German
    subsidiary's Stammkapital moved because EUR/USD moved.  That is what suppressed the
    translation adjustment and forced the reserve.
    """
    import pandas as pd
    jl = pd.read_parquet(REFERENCE / "journal_lines.parquet")
    cap = jl[jl["expected_group_account"].isin(["310100", "310200"])]
    balances = (cap.groupby(["entity_code", "period_key"])["amount_local"].sum()
                .groupby(level=0).cumsum())
    for ent, ser in balances.groupby(level=0):
        values = ser.to_numpy()
        keys = [int(k) for k in ser.index.get_level_values(1)]
        for i in range(1, len(values)):
            if ent == "NIG-100" and keys[i] == 202304:
                continue                      # the sponsor contribution, on its own date
            assert abs(values[i] - values[i - 1]) <= 1.0, (ent, keys[i])


@needs_build
def test_share_based_compensation_is_settled_in_equity_not_in_cash():
    import pandas as pd
    jl = pd.read_parquet(REFERENCE / "journal_lines.parquet")
    reserve = jl[jl["expected_group_account"] == "315100"]
    assert len(reserve), "the share-based compensation reserve carries no postings"
    closing = -reserve.loc[reserve["period_key"] <= 202512, "amount_local"].sum() / 1e6
    cf = load_anchor("cash_flow")
    expected = sum(cf["sbc"][c] for c in ("FY2023A", "FY2024A", "FY2025A"))
    assert closing == pytest.approx(expected, abs=0.01)


@needs_build
def test_the_distribution_to_the_minority_leaves_the_group():
    import pandas as pd
    jl = pd.read_parquet(REFERENCE / "journal_lines.parquet")
    dist = jl[jl["expected_group_account"] == "320300"]
    assert set(dist["entity_code"].unique()) == {"NIG-510"}, \
        "NIG-510 is the group's only partly-owned entity"
    cf = load_anchor("cash_flow")
    assert abs(cf["nci_dividend"]["FY2025A"]) > 0
    paid = dist.loc[dist["period_key"] <= 202512, "amount_local"].sum()
    assert paid > 0, "a distribution is a debit to equity"


# =====================================================================================
# 4.  The revolving facility pays for itself
# =====================================================================================
def test_treasury_policy_is_configuration_shared_by_both_layers():
    tp = load_treasury_policy()
    for key in ("TP-001", "TP-002", "TP-003", "TP-004", "TP-005", "TP-006", "TP-007",
                "TP-008", "TP-009"):
        assert key in tp, key
    sys.path.insert(0, str(ROOT / "src" / "anchors"))
    import build_anchors
    assert build_anchors.MIN_CASH == tp["TP-001"]
    assert build_anchors.TARGET_CASH == tp["TP-002"]
    from src.generation import series
    assert series.MIN_GROUP_CASH_USD == tp["TP-003"] * 1e6
    assert series.DRAW_NOTICE_DAY == int(tp["TP-008"])


def test_the_revolver_rate_is_built_from_the_credit_agreement():
    ca = load_credit_agreement()
    assert ca["CA-033"]["term"].startswith("Revolving facility margin")
    sys.path.insert(0, str(ROOT / "src" / "anchors"))
    import build_anchors
    margin = float(ca["CA-033"]["value"])
    for col in ("FY2023A", "FY2024A", "FY2025A"):
        assert build_anchors.RCF_RATE[col] == pytest.approx(
            build_anchors.SOFR_BASE[col] + margin, abs=1e-9)
    # the decomposition reproduces the previously approved blended term-loan rates
    assert build_anchors.TLB_RATE["FY2023A"] == pytest.approx(0.0810, abs=1e-9)
    assert build_anchors.TLB_RATE["FY2024A"] == pytest.approx(0.0835, abs=1e-9)
    assert build_anchors.TLB_RATE["FY2025A"] == pytest.approx(0.0780, abs=1e-9)


@needs_build
def test_the_revolver_rolls_forward_without_a_break():
    rows = read(REFERENCE / "revolver_utilisation.csv")
    assert len(rows) == 44
    previous = None
    for row in rows:
        opening = float(row["opening_drawn"])
        closing = float(row["closing_drawn"])
        assert opening + float(row["drawings"]) - float(row["repayments"]) == \
            pytest.approx(closing, abs=0.01), row["period_key"]
        if previous is not None:
            assert opening == pytest.approx(previous, abs=0.01), row["period_key"]
        previous = closing
        assert not (float(row["drawings"]) and float(row["repayments"])), \
            "a month draws or repays, never both"


@needs_build
def test_the_average_daily_drawn_balance_lies_between_the_endpoints():
    for row in read(REFERENCE / "revolver_utilisation.csv"):
        lo, hi = sorted((float(row["opening_drawn"]), float(row["closing_drawn"])))
        assert lo - 0.01 <= float(row["average_daily_drawn"]) <= hi + 0.01, row["period_key"]


@needs_build
def test_recorded_revolver_interest_is_supported_by_the_daily_balance():
    """
    Average daily drawn x (base rate + margin) + the commitment fee on the average daily
    undrawn commitment = the recorded facility charge.  This is the reconciliation the
    Phase 2.1 revolver could not perform.
    """
    util = read(REFERENCE / "revolver_utilisation.csv")
    pl = load_anchor("income_statement")
    ca = load_credit_agreement()
    sys.path.insert(0, str(ROOT / "src" / "anchors"))
    import build_anchors
    fee_rate = float(ca["CA-007"]["value"])
    margin = float(ca["CA-033"]["value"])
    for year, col in ((2023, "FY2023A"), (2024, "FY2024A"), (2025, "FY2025A")):
        months = [x for x in util if int(x["period_key"]) // 100 == year]
        days = sum(float(x["days_in_month"]) for x in months)
        drawn = sum(float(x["average_daily_drawn"]) * float(x["days_in_month"])
                    for x in months) / days / 1e6
        undrawn = sum(float(x["average_daily_undrawn"]) * float(x["days_in_month"])
                      for x in months) / days / 1e6
        supported = drawn * (build_anchors.SOFR_BASE[col] + margin) + undrawn * fee_rate
        recorded = pl["interest_rcf"][col] + pl["commitment_fee"][col]
        assert supported == pytest.approx(recorded, rel=0.005), year


@needs_build
def test_the_average_drawn_anchor_is_the_generated_average_daily_balance():
    util = read(REFERENCE / "revolver_utilisation.csv")
    sys.path.insert(0, str(ROOT / "src" / "anchors"))
    import build_anchors
    for year, col in ((2023, "FY2023A"), (2024, "FY2024A"), (2025, "FY2025A")):
        months = [x for x in util if int(x["period_key"]) // 100 == year]
        days = sum(float(x["days_in_month"]) for x in months)
        drawn = sum(float(x["average_daily_drawn"]) * float(x["days_in_month"])
                    for x in months) / days / 1e6
        assert build_anchors.RCF_AVG_DRAWN[col] == pytest.approx(drawn, abs=0.001), year


@needs_build
def test_the_debt_schedule_is_the_ledgers_own_arithmetic():
    """Phase 2.1 interpolated the facility between year ends; the schedule disagreed."""
    import pandas as pd
    jl = pd.read_parquet(REFERENCE / "journal_lines.parquet")
    periods = sorted(jl["period_key"].unique())
    ledger = (-jl[jl["expected_group_account"] == "220200"]
              .groupby("period_key")["amount_local"].sum()
              .reindex(periods, fill_value=0.0).cumsum())
    for row in read(REFERENCE / "debt_schedule.csv"):
        if row["instrument_id"] != "RCF-2021":
            continue
        pk = int(row["period_key"])
        assert float(row["closing_principal"]) == pytest.approx(
            float(ledger[pk]), abs=0.05), pk


@needs_build
def test_the_facility_is_never_overdrawn():
    commitment = float(load_credit_agreement()["CA-006"]["value"]) * 1e6
    for row in read(REFERENCE / "revolver_utilisation.csv"):
        assert 0.0 <= float(row["closing_drawn"]) <= commitment, row["period_key"]
        assert float(row["headroom_usd"]) >= 0.0


# =====================================================================================
# 5.  The revised anchors, and everything that was not allowed to move
# =====================================================================================
def test_phase_22_moved_only_the_two_anchors_it_derived():
    """
    Revenue, EBITDA, cash, term debt and every working-capital caption are untouched.

    Phase 2.2 was permitted a narrow correction to the CTA target and to the revolver's
    average drawn balance.  Everything else in the approved model stands.
    """
    pl = load_anchor("income_statement")
    bs = load_anchor("balance_sheet")
    assert pl["revenue"]["FY2025A"] == pytest.approx(412.100000, abs=1e-6)
    assert pl["adjusted_ebitda"]["FY2025A"] == pytest.approx(57.845000, abs=1e-6)
    assert pl["ebitda"]["FY2024A"] == pytest.approx(38.974000, abs=1e-6)
    assert pl["ebit"]["FY2023A"] == pytest.approx(13.940000, abs=1e-6)
    for col in ("FY2023A", "FY2024A", "FY2025A"):
        assert bs["cash"][col] == pytest.approx({"FY2023A": 15.0, "FY2024A": 15.0,
                                                 "FY2025A": 22.0}[col])
        assert bs["total_assets"][col] == pytest.approx(
            {"FY2023A": 404.087890, "FY2024A": 448.714888,
             "FY2025A": 467.530808}[col], abs=1e-6)
    assert bs["tlb_gross"]["FY2025A"] == pytest.approx(226.600000, abs=1e-6)
    assert bs["ar"]["FY2025A"] == pytest.approx(65.484384, abs=1e-6)
    assert bs["inventory"]["FY2025A"] == pytest.approx(40.103425, abs=1e-6)
    assert bs["ap"]["FY2025A"] == pytest.approx(40.103425, abs=1e-6)
    assert bs["goodwill"]["FY2025A"] == pytest.approx(142.200000, abs=1e-6)


def test_the_restated_interest_and_net_income_are_the_documented_figures():
    """
    Restated again in Phase 3.1. Correcting the intercompany balances changed the
    intra-year cash position, and the revolver is drawn against exactly that: average
    daily drawn falls from 17.318 to 14.829 in FY2023 and from 26.347 to 23.902 in FY2024,
    so revolver interest falls and the commitment fee on the larger undrawn balance rises.
    FY2025 net income moves by USD 0.040m, 0.48%. Revenue, gross profit, EBITDA, cash and
    the term loan are untouched -- data/phase03_1_source_diff.json is the evidence.
    """
    pl = load_anchor("income_statement")
    assert pl["net_interest"]["FY2023A"] == pytest.approx(18.224227, abs=5e-4)
    assert pl["net_interest"]["FY2024A"] == pytest.approx(21.766617, abs=5e-4)
    assert pl["net_interest"]["FY2025A"] == pytest.approx(20.988903, abs=5e-4)
    assert pl["net_income"]["FY2025A"] == pytest.approx(8.477110, abs=5e-4)


def test_the_balance_sheet_still_balances_after_the_revision():
    bs = load_anchor("balance_sheet")
    for col in ("FY2023A", "FY2024A", "FY2025A", "FY2026B", "FY2026F"):
        assert bs["total_assets"][col] == pytest.approx(
            bs["total_liabilities_and_equity"][col], abs=1e-6)
        assert bs["total_equity"][col] == pytest.approx(
            bs["contributed_capital"][col] + bs["retained_earnings"][col]
            + bs["cta"][col] + bs["nci"][col], abs=1e-6)


def test_no_covenant_is_breached_after_the_revision():
    kpi = {r["metric"]: r for r in read(CONFIG / "anchors" / "anchor_kpi.csv")}
    for col in ("FY2023A", "FY2024A", "FY2025A", "FY2026B", "FY2026F"):
        assert float(kpi["covenant_leverage_headroom_x"][col]) > 0, col
        assert float(kpi["covenant_coverage_headroom_x"][col]) > 0, col


def test_the_derived_anchor_inputs_are_not_stale():
    """
    The three derived inputs must still equal what the generated data implies.

    This is the guard that stops a driver change from quietly leaving the CTA, the
    minority's share of it or the revolver's average drawn balance behind.
    """
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "derive_anchor_inputs.py"), "--check"],
        capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
