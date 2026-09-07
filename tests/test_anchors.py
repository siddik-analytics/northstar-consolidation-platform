"""
Independent validation of the Phase 1 financial anchors.

These tests deliberately re-read the *generated CSV outputs* rather than importing the
model's internal state.  The point is to prove that what was written to disk is
internally consistent -- if the generator and the test shared logic, the test would
prove nothing.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ANCHORS = ROOT / "config" / "anchors"
PERIODS = ["FY2023A", "FY2024A", "FY2025A", "FY2026B", "FY2026F"]
TOL = 0.001  # USD thousands, i.e. one dollar on figures stated in millions


def load(name: str, key: str = "line_item") -> dict[str, dict[str, float]]:
    path = ANCHORS / name
    out: dict[str, dict[str, float]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row[key]] = {p: float(row[p]) for p in PERIODS}
    return out


@pytest.fixture(scope="module")
def pl():
    return load("anchor_income_statement.csv")


@pytest.fixture(scope="module")
def bs():
    return load("anchor_balance_sheet.csv")


@pytest.fixture(scope="module")
def cf():
    return load("anchor_cash_flow.csv")


@pytest.fixture(scope="module")
def kpi():
    return load("anchor_kpi.csv", key="metric")


# ---------------------------------------------------------------- income statement
@pytest.mark.parametrize("p", PERIODS)
def test_gross_profit_is_revenue_less_cost_of_sales(pl, p):
    assert pl["gross_profit"][p] == pytest.approx(
        pl["revenue"][p] - pl["cost_of_sales"][p], abs=TOL)


@pytest.mark.parametrize("p", PERIODS)
def test_ebitda_is_gross_profit_less_opex(pl, p):
    assert pl["ebitda"][p] == pytest.approx(pl["gross_profit"][p] - pl["opex"][p], abs=TOL)


@pytest.mark.parametrize("p", PERIODS)
def test_adjusted_ebitda_adds_back_one_time_items(pl, p):
    assert pl["adjusted_ebitda"][p] == pytest.approx(
        pl["ebitda"][p] + pl["one_time_in_opex"][p], abs=TOL)


@pytest.mark.parametrize("p", PERIODS)
def test_ebit_is_ebitda_less_da(pl, p):
    assert pl["da"][p] == pytest.approx(pl["depreciation"][p] + pl["amortisation"][p], abs=TOL)
    assert pl["ebit"][p] == pytest.approx(pl["ebitda"][p] - pl["da"][p], abs=TOL)


@pytest.mark.parametrize("p", PERIODS)
def test_net_income_walks_from_ebit(pl, p):
    assert pl["pbt"][p] == pytest.approx(pl["ebit"][p] - pl["net_interest"][p], abs=TOL)
    assert pl["net_income"][p] == pytest.approx(pl["pbt"][p] - pl["tax"][p], abs=TOL)
    assert pl["ni_parent"][p] == pytest.approx(pl["net_income"][p] - pl["nci"][p], abs=TOL)


# ---------------------------------------------------------------- balance sheet
@pytest.mark.parametrize("p", PERIODS)
def test_balance_sheet_balances(bs, p):
    assert bs["total_assets"][p] == pytest.approx(
        bs["total_liabilities_and_equity"][p], abs=TOL), \
        f"{p}: balance sheet does not balance"


@pytest.mark.parametrize("p", PERIODS)
def test_current_assets_subtotal(bs, p):
    parts = ["cash", "ar", "contract_assets", "inventory", "prepaid"]
    assert bs["total_current_assets"][p] == pytest.approx(
        sum(bs[k][p] for k in parts), abs=TOL)


@pytest.mark.parametrize("p", PERIODS)
def test_total_assets_subtotal(bs, p):
    parts = ["total_current_assets", "ppe_net", "rou_asset", "goodwill",
             "intangibles_net", "other_nca"]
    assert bs["total_assets"][p] == pytest.approx(sum(bs[k][p] for k in parts), abs=TOL)


@pytest.mark.parametrize("p", PERIODS)
def test_total_liabilities_subtotal(bs, p):
    parts = ["ap", "contract_liabilities", "accrued", "tax_payable", "rcf", "tlb_net",
             "finance_lease", "operating_lease", "dtl", "other_ltl"]
    assert bs["total_liabilities"][p] == pytest.approx(sum(bs[k][p] for k in parts), abs=TOL)


@pytest.mark.parametrize("p", PERIODS)
def test_total_equity_subtotal(bs, p):
    parts = ["contributed_capital", "retained_earnings", "cta", "nci"]
    assert bs["total_equity"][p] == pytest.approx(sum(bs[k][p] for k in parts), abs=TOL)


@pytest.mark.parametrize("p", PERIODS)
def test_rou_asset_equals_operating_lease_liability(bs, p):
    """Documented anchor-level simplification -- asserted so it cannot drift silently."""
    assert bs["rou_asset"][p] == pytest.approx(bs["operating_lease"][p], abs=TOL)


def test_retained_earnings_rolls_forward(bs, pl):
    """FY2024 and FY2025 roll from the prior year; FY2026 B and F both roll from FY2025."""
    assert bs["retained_earnings"]["FY2024A"] == pytest.approx(
        bs["retained_earnings"]["FY2023A"] + pl["ni_parent"]["FY2024A"], abs=TOL)
    assert bs["retained_earnings"]["FY2025A"] == pytest.approx(
        bs["retained_earnings"]["FY2024A"] + pl["ni_parent"]["FY2025A"], abs=TOL)
    for p in ("FY2026B", "FY2026F"):
        assert bs["retained_earnings"][p] == pytest.approx(
            bs["retained_earnings"]["FY2025A"] + pl["ni_parent"][p], abs=TOL), \
            f"{p}: retained earnings must roll from the FY2025 actual close"


# ---------------------------------------------------------------- cash flow
@pytest.mark.parametrize("p", PERIODS)
def test_cash_flow_subtotals(cf, p):
    op_parts = ["net_income", "da", "sbc", "dff_amortisation", "deferred_tax",
                "fx_non_cash_wc", "change_in_working_capital", "change_in_other"]
    assert cf["operating_cash_flow"][p] == pytest.approx(
        sum(cf[k][p] for k in op_parts), abs=TOL)

    assert cf["investing_cash_flow"][p] == pytest.approx(
        cf["capex"][p] + cf["acquisitions"][p], abs=TOL)

    fin_parts = ["tlb_draw", "tlb_repayment", "rcf_movement", "finance_lease_principal",
                 "financing_fees", "equity_contribution", "nci_dividend"]
    assert cf["financing_cash_flow"][p] == pytest.approx(
        sum(cf[k][p] for k in fin_parts), abs=TOL)


@pytest.mark.parametrize("p", PERIODS)
def test_net_change_in_cash(cf, p):
    total = (cf["operating_cash_flow"][p] + cf["investing_cash_flow"][p]
             + cf["financing_cash_flow"][p] + cf["fx_effect_on_cash"][p])
    assert cf["net_change_in_cash"][p] == pytest.approx(total, abs=TOL)


@pytest.mark.parametrize("p", PERIODS)
def test_cash_flow_ties_to_balance_sheet(cf, bs, p):
    """The single most important control in the whole model."""
    assert cf["closing_cash"][p] == pytest.approx(
        cf["opening_cash"][p] + cf["net_change_in_cash"][p], abs=TOL)
    assert cf["closing_cash"][p] == pytest.approx(bs["cash"][p], abs=TOL), \
        f"{p}: cash flow statement does not tie to balance sheet cash"


def test_opening_cash_chains_across_actual_years(cf):
    assert cf["opening_cash"]["FY2024A"] == pytest.approx(cf["closing_cash"]["FY2023A"], abs=TOL)
    assert cf["opening_cash"]["FY2025A"] == pytest.approx(cf["closing_cash"]["FY2024A"], abs=TOL)
    for p in ("FY2026B", "FY2026F"):
        assert cf["opening_cash"][p] == pytest.approx(cf["closing_cash"]["FY2025A"], abs=TOL)


@pytest.mark.parametrize("p", PERIODS)
def test_free_cash_flow_definition(cf, p):
    assert cf["free_cash_flow"][p] == pytest.approx(
        cf["operating_cash_flow"][p] + cf["capex"][p], abs=TOL)


@pytest.mark.parametrize("p", PERIODS)
def test_net_income_agrees_between_pl_and_cash_flow(cf, pl, p):
    assert cf["net_income"][p] == pytest.approx(pl["net_income"][p], abs=TOL)


# ---------------------------------------------------------------- KPIs
@pytest.mark.parametrize("p", PERIODS)
def test_margin_kpis_derive_from_the_statements(kpi, pl, p):
    assert kpi["gross_margin_pct"][p] == pytest.approx(
        pl["gross_profit"][p] / pl["revenue"][p], abs=1e-6)
    assert kpi["ebitda_margin_pct"][p] == pytest.approx(
        pl["ebitda"][p] / pl["revenue"][p], abs=1e-6)
    assert kpi["adjusted_ebitda_margin_pct"][p] == pytest.approx(
        pl["adjusted_ebitda"][p] / pl["revenue"][p], abs=1e-6)


@pytest.mark.parametrize("p", PERIODS)
def test_leverage_derives_from_the_balance_sheet(kpi, bs, pl, p):
    total_debt = bs["tlb_net"][p] + bs["rcf"][p] + bs["finance_lease"][p]
    # The KPI uses gross term loan; the balance sheet caption is net of financing costs.
    assert kpi["total_debt"][p] == pytest.approx(total_debt + bs["dff"][p], abs=TOL)
    assert kpi["net_debt"][p] == pytest.approx(kpi["total_debt"][p] - bs["cash"][p], abs=TOL)
    assert kpi["net_leverage_x"][p] == pytest.approx(
        kpi["net_debt"][p] / pl["adjusted_ebitda"][p], abs=1e-6)


@pytest.mark.parametrize("p", PERIODS)
def test_covenant_headroom_is_positive(kpi, p):
    """A covenant breach in the anchors would be a modelling accident, not a design choice."""
    assert kpi["covenant_leverage_headroom_x"][p] > 0, \
        f"{p}: net leverage breaches the covenant maximum"
    assert kpi["covenant_coverage_headroom_x"][p] > 0, \
        f"{p}: interest coverage breaches the covenant minimum"


@pytest.mark.parametrize("p", PERIODS)
def test_working_capital_days_are_consistent(kpi, p):
    assert kpi["cash_conversion_cycle"][p] == pytest.approx(
        kpi["dso"][p] + kpi["dio"][p] - kpi["dpo"][p], abs=TOL)


# ---------------------------------------------------------------- business story
def test_revenue_by_entity_rolls_up_to_business_unit_and_group(pl):
    by_entity: dict[str, dict[str, float]] = {}
    with open(ANCHORS / "anchor_by_entity.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            bu = row["bu_code"]
            for p in PERIODS:
                by_entity.setdefault(bu, dict.fromkeys(PERIODS, 0.0))
                by_entity[bu][p] += float(row[p])

    by_bu: dict[str, dict[str, float]] = {}
    with open(ANCHORS / "anchor_by_business_unit.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["measure"] == "revenue":
                by_bu[row["bu_code"]] = {p: float(row[p]) for p in PERIODS}

    for bu, vals in by_bu.items():
        for p in PERIODS:
            assert vals[p] == pytest.approx(by_entity[bu][p], abs=TOL), \
                f"{bu} {p}: entity revenue does not roll up to the business unit"

    for p in PERIODS:
        assert pl["revenue"][p] == pytest.approx(
            sum(v[p] for v in by_bu.values()), abs=TOL), \
            f"{p}: business unit revenue does not roll up to group"


def test_acquired_entities_report_nothing_before_acquisition():
    """Halden is a nine-month FY2023; Vector BV contributes nothing to FY2023."""
    with open(ANCHORS / "anchor_by_entity.csv", newline="", encoding="utf-8") as f:
        rows = {r["entity_code"]: r for r in csv.DictReader(f)}
    assert float(rows["NIG-410"]["FY2023A"]) == 0.0, \
        "Vector Systems B.V. was acquired in July 2024 and cannot have FY2023 revenue"
    assert float(rows["NIG-220"]["FY2024A"]) > float(rows["NIG-220"]["FY2023A"]), \
        "Halden's FY2023 covers nine months only and must be below its first full year"


def test_forecast_is_below_budget_as_the_narrative_requires(pl):
    """The engagement narrative depends on a forecast shortfall. Assert it rather than assume it."""
    assert pl["revenue"]["FY2026F"] < pl["revenue"]["FY2026B"]
    assert pl["adjusted_ebitda"]["FY2026F"] < pl["adjusted_ebitda"]["FY2026B"]


def test_margin_expands_across_the_actual_years(kpi):
    a = [kpi["adjusted_ebitda_margin_pct"][p] for p in ("FY2023A", "FY2024A", "FY2025A")]
    assert a[0] < a[1] < a[2], "Adjusted EBITDA margin must expand across the historical years"


def test_deleveraging_across_the_actual_years(kpi):
    a = [kpi["net_leverage_x"][p] for p in ("FY2023A", "FY2024A", "FY2025A")]
    assert a[0] > a[1] > a[2], "Net leverage must fall across the historical years"


def test_intercompany_gross_up_is_material_but_plausible(pl):
    ic: dict[str, dict[str, float]] = {}
    with open(ANCHORS / "anchor_intercompany.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ic[row["measure"]] = {p: float(row[p]) for p in PERIODS}
    for p in PERIODS:
        gross_up = sum(ic[k][p] for k in
                       ("mgmt_fee", "ic_product_sales", "ic_service_sales", "ic_royalty"))
        ratio = gross_up / pl["revenue"][p]
        assert 0.08 < ratio < 0.20, \
            f"{p}: intercompany gross-up of {ratio:.1%} of revenue is outside a plausible band"


def test_fx_rates_are_quoted_as_usd_per_unit():
    """Guards against an inverted quotation convention entering the anchor set."""
    bands = {"CAD": (0.60, 0.90), "GBP": (1.00, 1.60), "EUR": (0.90, 1.35), "USD": (1.0, 1.0)}
    with open(ANCHORS / "anchor_fx_rates.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lo, hi = bands[row["currency_code"]]
            for col in ("average_rate_usd", "closing_rate_usd"):
                assert lo <= float(row[col]) <= hi, \
                    f"{row['currency_code']} {row['fiscal_year']} {col} looks inverted"
