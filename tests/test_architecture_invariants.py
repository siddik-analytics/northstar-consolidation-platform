"""
Phase 1.1 architecture invariants.

These tests exist because of defects found at the Phase 1 review: the consolidation layer
set was asserted in prose rather than defined once, and the NCI and CTA policies were
incomplete.  Each test below encodes an invariant that, if broken, would be silent -- the
statements would still balance while the architecture had drifted.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
DOCS = ROOT / "docs"

STATUTORY_LAYERS = {1, 2, 3, 5}
MANAGEMENT_LAYERS = {1, 2, 3, 4, 5}


def read(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def layers():
    return read(CONFIG / "dimensions" / "consolidation_layer.csv")


@pytest.fixture(scope="module")
def group_coa():
    return read(CONFIG / "coa" / "group_coa.csv")


@pytest.fixture(scope="module")
def ownership():
    return read(CONFIG / "entities" / "ownership_history.csv")


@pytest.fixture(scope="module")
def controls():
    return read(CONFIG / "controls" / "control_register.csv")


# =====================================================================================
# 1. CONSOLIDATION LAYERS -- the set is closed at five and consistent everywhere
# =====================================================================================
def test_exactly_five_layers_are_defined(layers):
    assert len(layers) == 5, f"expected exactly 5 consolidation layers, found {len(layers)}"


def test_layer_ids_are_one_to_five_with_no_gaps(layers):
    ids = sorted(int(r["layer_id"]) for r in layers)
    assert ids == [1, 2, 3, 4, 5], f"layer_id set is {ids}; it must be exactly 1-5"


def test_layer_codes_are_unique_and_expected(layers):
    codes = [r["layer_code"] for r in layers]
    assert len(codes) == len(set(codes)), "duplicate layer codes"
    assert set(codes) == {"REPORTED", "IC_ELIM", "CONSOL_ADJ", "MGMT_ADJ", "FX_CTA"}


def test_statutory_and_management_membership_matches_the_documented_formulas(layers):
    """Statutory = 1,2,3,5 and Management = 1,2,3,4,5. Config must agree with the docs."""
    statutory = {int(r["layer_id"]) for r in layers if r["in_statutory_view"] == "TRUE"}
    management = {int(r["layer_id"]) for r in layers if r["in_management_view"] == "TRUE"}
    assert statutory == STATUTORY_LAYERS, f"statutory layers are {sorted(statutory)}"
    assert management == MANAGEMENT_LAYERS, f"management layers are {sorted(management)}"


def test_only_management_adjustments_are_outside_the_statutory_view(layers):
    excluded = [r["layer_code"] for r in layers if r["in_statutory_view"] == "FALSE"]
    assert excluded == ["MGMT_ADJ"], (
        "exactly one layer -- management adjustments -- may sit outside the statutory view")


def test_every_layer_is_in_the_management_view(layers):
    """The management view is the superset. A layer in neither view is invisible."""
    for r in layers:
        assert r["in_management_view"] == "TRUE", (
            f"layer {r['layer_code']} appears in no reporting view at all")


def test_only_the_translation_layer_is_exempt_from_independent_balancing(layers):
    """Layer 5 IS the balancing entry, so it cannot also balance on its own."""
    exempt = [r["layer_code"] for r in layers if r["must_balance_independently"] == "FALSE"]
    assert exempt == ["FX_CTA"], (
        "only the translation layer may be exempt from independent balancing")


def test_elimination_layers_post_to_elimination_entities(layers):
    entities = {r["entity_code"]: r for r in read(CONFIG / "entities" / "entity_master.csv")}
    for r in layers:
        target = r["posted_to_entity"]
        if target.startswith("ELIM-"):
            assert target in entities, f"layer {r['layer_code']} posts to unknown entity {target}"
            assert entities[target]["is_elimination_entity"] == "TRUE"
            assert r["posted_to_entity_type"] == "ELIMINATION"
        else:
            assert r["posted_to_entity_type"] == "OPERATING"


def test_each_elimination_entity_carries_exactly_one_layer(layers):
    targets = [r["posted_to_entity"] for r in layers if r["posted_to_entity"].startswith("ELIM-")]
    assert sorted(targets) == ["ELIM-CON", "ELIM-IC", "ELIM-MGT"]


def test_layer_sequence_is_strictly_increasing(layers):
    seq = [int(r["layer_sequence"]) for r in sorted(layers, key=lambda r: int(r["layer_id"]))]
    assert seq == sorted(seq) and len(set(seq)) == len(seq), (
        "layer_sequence must be unique and increase with layer_id")


#: Narrow, explicit escape hatch. A line carrying this marker is skipped by the layer guard.
#: It exists only so that documentation can quote a deliberately-invalid example -- the Phase
#: 1.1 report shows the guard failing on an injected fault. Scanning is line-by-line rather
#: than whole-file so the exemption cannot accidentally cover a neighbouring real statement,
#: and fenced code blocks are NOT exempt: the statutory and management formulas live in them.
LAYER_GUARD_OPT_OUT = "layer-guard:ignore"


def test_no_document_references_an_undefined_layer():
    """THE CONTROL THE REVIEW ASKED FOR: no prose may invent a layer that does not exist."""
    defined = {int(r["layer_id"]) for r in read(CONFIG / "dimensions" / "consolidation_layer.csv")}
    pattern = re.compile(r"\blayer[_ ](?:id|key)?\s*(?:IN\s*)?\(?([0-9,\s]+)\)?", re.IGNORECASE)
    offenders = []
    for path in list(DOCS.rglob("*.md")) + [ROOT / "README.md"]:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if LAYER_GUARD_OPT_OUT in line:
                continue
            for match in pattern.finditer(line):
                for token in re.findall(r"\d+", match.group(1)):
                    if int(token) not in defined:
                        offenders.append(
                            (path.relative_to(ROOT).as_posix(), lineno, match.group(0)))
    assert not offenders, f"references to undefined consolidation layers: {offenders}"


def test_the_layer_guard_opt_out_is_used_sparingly():
    """An escape hatch that spreads stops being an escape hatch and becomes the rule."""
    used = [(p.relative_to(ROOT).as_posix(), n)
            for p in list(DOCS.rglob("*.md")) + [ROOT / "README.md"]
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if LAYER_GUARD_OPT_OUT in line]
    assert len(used) <= 4, f"layer guard opt-out used {len(used)} times: {used}"
    for path, _ in used:
        assert path.startswith("docs/phases/"), (
            f"the opt-out is only for phase reports quoting an invalid example; found in {path}")


def test_layer_count_stated_in_docs_matches_the_configuration():
    """Guards the specific defect found at review: 'five layers' with only four named."""
    text = (DOCS / "consolidation-design.md").read_text(encoding="utf-8")
    for code in ("REPORTED", "IC_ELIM", "CONSOL_ADJ", "MGMT_ADJ", "FX_CTA"):
        assert code in text, f"consolidation-design.md does not name layer {code}"
    contract = (DOCS / "data-contract.md").read_text(encoding="utf-8")
    for code in ("REPORTED", "IC_ELIM", "CONSOL_ADJ", "MGMT_ADJ", "FX_CTA"):
        assert code in contract, f"data-contract.md does not name layer {code}"


def test_a_control_enforces_layer_integrity(controls):
    ctl = next((r for r in controls if r["control_id"] == "CTL-CON-09"), None)
    assert ctl is not None, "no control enforces consolidation layer integrity"
    assert ctl["severity"] == "BLOCKING"


# =====================================================================================
# 2. NON-CONTROLLING INTEREST
# =====================================================================================
def test_ownership_history_covers_every_consolidated_subsidiary(ownership):
    entities = read(CONFIG / "entities" / "entity_master.csv")
    subsidiaries = {r["entity_code"] for r in entities
                    if r["entity_type"] == "OPERATING" and r["entity_code"] != "NIG-100"}
    covered = {r["entity_code"] for r in ownership}
    assert subsidiaries == covered, (
        f"ownership register does not match the entity master: "
        f"missing {sorted(subsidiaries - covered)}, extra {sorted(covered - subsidiaries)}")


def test_ownership_and_nci_sum_to_one_in_the_register(ownership):
    for r in ownership:
        total = float(r["group_ownership_pct"]) + float(r["nci_pct"])
        assert abs(total - 1.0) < 1e-9, f"{r['entity_code']}: ownership + NCI = {total}"


def test_no_overlapping_or_duplicate_ownership_periods(ownership):
    """CTL-CON-10: exactly one ownership row must be effective for any entity and date."""
    by_entity: dict[str, list[dict[str, str]]] = {}
    for r in ownership:
        by_entity.setdefault(r["entity_code"], []).append(r)
    for entity, rows in by_entity.items():
        open_ended = [r for r in rows if not r["effective_to"]]
        assert len(open_ended) == 1, (
            f"{entity} has {len(open_ended)} open-ended ownership rows; exactly one is required")


def test_ownership_effective_from_matches_consolidation_effective_from(ownership):
    entities = {r["entity_code"]: r for r in read(CONFIG / "entities" / "entity_master.csv")}
    for r in ownership:
        if not r["effective_to"]:
            assert r["effective_from"] == entities[r["entity_code"]]["consolidation_effective_from"], (
                f"{r['entity_code']}: ownership start disagrees with consolidation start")


def test_exactly_one_entity_has_a_non_controlling_interest(ownership):
    nci = [r for r in ownership if float(r["nci_pct"]) > 0]
    assert len(nci) == 1
    assert nci[0]["entity_code"] == "NIG-510"
    assert float(nci[0]["nci_pct"]) == pytest.approx(0.20)
    assert nci[0]["nci_holder"].strip(), "the NCI holder must be identified"


def test_nci_equity_rollforward_accounts_exist(group_coa):
    """A single moving NCI balance cannot be controlled. The roll-forward needs its parts."""
    accounts = {r["group_account"]: r for r in group_coa}
    required = {
        "340100": "opening balance",
        "340200": "share of result",
        "340300": "dividends and distributions",
        "340400": "share of translation adjustment",
        "340500": "acquisition and ownership changes",
    }
    for acct, what in required.items():
        assert acct in accounts, f"missing NCI roll-forward account {acct} ({what})"
        assert accounts[acct]["fs_caption_l2"] == "Non-controlling interests"
        assert accounts[acct]["account_class"] == "EQUITY"


def test_nci_dividends_are_a_financing_cash_flow(group_coa):
    """CTL-CON-13: a distribution to a minority owner is not an operating cost."""
    acct = next(r for r in group_coa if r["group_account"] == "340300")
    assert acct["cash_flow_category"] == "FIN_EQUITY"
    assert acct["normal_balance"] == "D", "a distribution reduces NCI equity"


def test_nci_income_statement_allocation_line_exists(group_coa):
    acct = next((r for r in group_coa if r["group_account"] == "850100"), None)
    assert acct is not None, "no income statement line allocates result to NCI"
    assert acct["statement"] == "IS"
    assert acct["account_class"] == "NCI"
    assert acct["is_ebitda"] == "FALSE", "the NCI allocation must never enter EBITDA"
    assert acct["is_ebitda_addback"] == "FALSE"


def test_nci_share_of_cta_is_not_translated_again(group_coa):
    """340400 is already a translated residual; retranslating it would double count."""
    acct = next(r for r in group_coa if r["group_account"] == "340400")
    assert acct["fx_method"] == "NONE"


def test_nci_controls_exist(controls):
    ids = {r["control_id"] for r in controls}
    for cid in ("CTL-CON-04", "CTL-CON-10", "CTL-CON-11", "CTL-CON-12", "CTL-CON-13", "CTL-FS-09"):
        assert cid in ids, f"missing NCI control {cid}"
    for cid in ("CTL-CON-10", "CTL-CON-11", "CTL-CON-12", "CTL-CON-13", "CTL-FS-09"):
        row = next(r for r in controls if r["control_id"] == cid)
        assert row["severity"] == "BLOCKING", f"{cid} must be blocking"


def test_nci_policy_document_covers_every_required_topic():
    text = (DOCS / "nci-policy.md").read_text(encoding="utf-8").lower()
    for topic in ["100%", "share of profit", "roll-forward", "dividends", "effective dat",
                  "acquisition", "disposal", "cash flow", "statutory", "management",
                  "elimination", "data model", "control"]:
        assert topic in text, f"NCI policy does not address: {topic}"


# =====================================================================================
# 3. FX AND CTA POLICY
# =====================================================================================
def test_cta_rollforward_accounts_exist(group_coa):
    accounts = {r["group_account"]: r for r in group_coa}
    for acct, what in {"330100": "opening", "330200": "movement",
                       "330300": "recycled on disposal"}.items():
        assert acct in accounts, f"missing CTA roll-forward account {acct} ({what})"
        assert accounts[acct]["fs_caption_l2"] == "Cumulative translation adjustment"
        assert accounts[acct]["fx_method"] == "NONE", (
            f"{acct}: CTA is a translation residual and is never itself translated")


def test_fx_policy_covers_every_required_subject():
    """The review required a complete policy. Assert each required subject is present."""
    rows = read(CONFIG / "fx" / "fx_translation_policy.csv")
    blob = " ".join(r["applies_to"] + " " + r["rate_basis"] + " " + r["rationale"]
                    for r in rows).lower()
    required = {
        "P&L monthly average": "monthly average",
        "balance sheet closing": "closing spot",
        "equity historical": "historical",
        "acquisition-date balances": "acquisition",
        "retained earnings": "retained earnings",
        "CTA opening": "cta opening",
        "CTA movement": "cta movement",
        "CTA closing": "cta closing",
        "cash flow FX effect": "exchange rate changes on cash",
    }
    applies = " ".join(r["applies_to"] for r in rows).lower()
    for label, needle in required.items():
        assert needle in blob or needle in applies, f"FX policy does not cover: {label}"


def test_fx_policy_defines_the_cta_rollforward_by_account():
    rows = {r["policy_id"]: r for r in read(CONFIG / "fx" / "fx_translation_policy.csv")}
    assert "330100" in rows["FX-P17"]["selector"], "no policy for CTA opening"
    assert "330200" in rows["FX-P06"]["selector"], "no policy for CTA movement"
    assert "330300" in rows["FX-P19"]["selector"], "no policy for CTA recycling"
    assert "340400" in rows["FX-P20"]["selector"], "no policy for the NCI share of CTA"


def test_cash_flow_fx_effect_is_split_not_lumped():
    """The Phase 1 defect: the whole CTA movement routed through the cash line."""
    rows = {r["policy_id"]: r for r in read(CONFIG / "fx" / "fx_translation_policy.csv")}
    rationale = rows["FX-P22"]["rationale"].lower()
    assert "operating" in rationale and "cash" in rationale
    assert "non-cash" in rationale


def test_fx_controls_exist(controls):
    ids = {r["control_id"] for r in controls}
    for cid in ("CTL-FX-04", "CTL-FX-09", "CTL-FX-10", "CTL-FX-11"):
        assert cid in ids, f"missing FX control {cid}"
        row = next(r for r in controls if r["control_id"] == cid)
        assert row["severity"] == "BLOCKING"


def test_acquisition_dates_have_an_fx_policy():
    """Both mid-year acquisitions need an acquisition-date translation base."""
    policy = read(CONFIG / "fx" / "fx_translation_policy.csv")
    acq = next(r for r in policy if r["policy_id"] == "FX-P16")
    for date in ("2023-04-01", "2024-07-01"):
        assert date in acq["exception_handling"], f"no acquisition-date rate named for {date}"


# =====================================================================================
# 4. CREDIT AGREEMENT, COVENANT AND EBITDA POLICY
# =====================================================================================
@pytest.fixture(scope="module")
def agreement():
    return {r["term_id"]: r for r in read(CONFIG / "debt" / "credit_agreement_terms.csv")}


def test_synergy_addbacks_are_not_permitted(agreement):
    assert agreement["CA-028"]["value"] == "FALSE"
    assert agreement["CA-028"]["unit"] == "NOT_PERMITTED"


def test_share_based_compensation_is_not_added_back(agreement, group_coa):
    assert agreement["CA-029"]["value"] == "FALSE"
    sbc = next(r for r in group_coa if r["group_account"] == "610500")
    assert sbc["is_ebitda_addback"] == "FALSE", (
        "share-based compensation must not be flagged as an add-back (CA-029)")


def test_sponsor_fee_addback_is_permitted_and_capped(agreement, group_coa):
    """The add-back is only legitimate because a clause explicitly permits it."""
    assert agreement["CA-026"]["value"] == "TRUE"
    assert agreement["CA-026"]["unit"] == "PERMITTED_CAPPED"
    cap = float(agreement["CA-027"]["value"])
    assert cap == pytest.approx(1.5)
    fee = next(r for r in group_coa if r["group_account"] == "630400")
    assert fee["is_ebitda_addback"] == "TRUE"


def test_operating_leases_are_excluded_from_covenant_net_debt(agreement):
    assert agreement["CA-018"]["value"] == "FALSE"


def test_every_addback_account_is_permitted_by_the_agreement(group_coa, agreement):
    """An add-back the agreement does not permit would make the two EBITDA measures diverge."""
    flagged = {r["group_account"] for r in group_coa if r["is_ebitda_addback"] == "TRUE"}
    permitted_text = " ".join(r["notes"] for r in agreement.values()
                              if r["category"] == "ADDBACK" and r["value"] == "TRUE")
    for acct in flagged:
        assert acct in permitted_text, (
            f"account {acct} is flagged as an add-back but no credit agreement clause permits it")


def test_addback_composition_reconciles_to_the_one_time_charge():
    comp = read(ROOT / "config" / "anchors" / "anchor_addback_composition.csv")
    cols = ["FY2023A", "FY2024A", "FY2025A", "FY2026B", "FY2026F"]
    total = next(r for r in comp if r["group_account"] == "TOTAL")
    parts = [r for r in comp if r["group_account"] != "TOTAL"]
    for c in cols:
        assert sum(float(r[c]) for r in parts) == pytest.approx(float(total[c]), abs=1e-6), \
            f"{c}: add-back composition does not sum to the total"


def test_sponsor_fee_never_exceeds_the_cap(agreement):
    cap = float(agreement["CA-027"]["value"])
    comp = {r["group_account"]: r for r in
            read(ROOT / "config" / "anchors" / "anchor_addback_composition.csv")}
    for c in ["FY2023A", "FY2024A", "FY2025A", "FY2026B", "FY2026F"]:
        assert float(comp["630400"][c]) <= cap + 1e-9, f"{c}: sponsor fee add-back exceeds the cap"


def test_covenant_thresholds_agree_between_agreement_and_anchors(agreement):
    kpi = {r["metric"]: r for r in read(ROOT / "config" / "anchors" / "anchor_kpi.csv")}
    expected = {"FY2023A": "CA-009", "FY2024A": "CA-010",
                "FY2025A": "CA-011", "FY2026B": "CA-012", "FY2026F": "CA-012"}
    for col, term in expected.items():
        assert float(kpi["covenant_max_leverage_x"][col]) == pytest.approx(
            float(agreement[term]["value"])), (
            f"{col}: anchor covenant threshold disagrees with the credit agreement")


# =====================================================================================
# 5. ECONOMIC LEVERAGE AND THE RESERVED DOWNSIDE SCENARIO
# =====================================================================================
def test_economic_leverage_is_reported_and_exceeds_covenant_leverage():
    kpi = {r["metric"]: r for r in read(ROOT / "config" / "anchors" / "anchor_kpi.csv")}
    for m in ("operating_lease_liabilities", "economic_net_debt", "economic_net_leverage_x"):
        assert m in kpi, f"missing KPI {m}"
    for c in ["FY2023A", "FY2024A", "FY2025A", "FY2026B", "FY2026F"]:
        econ = float(kpi["economic_net_leverage_x"][c])
        cov = float(kpi["net_leverage_x"][c])
        assert econ > cov, f"{c}: economic leverage must exceed covenant leverage"
        assert float(kpi["economic_net_debt"][c]) == pytest.approx(
            float(kpi["net_debt"][c]) + float(kpi["operating_lease_liabilities"][c]), abs=1e-6)


def test_economic_leverage_has_no_covenant_threshold():
    """It is a KPI, not a covenant. Comparing it to the covenant maximum would be wrong."""
    text = (DOCS / "reporting-design.md").read_text(encoding="utf-8")
    assert "no covenant threshold for Economic Net Leverage" in text


def test_base_case_does_not_breach_any_covenant():
    """The approved base case: no breach. Distorting it to create drama is out of bounds."""
    kpi = {r["metric"]: r for r in read(ROOT / "config" / "anchors" / "anchor_kpi.csv")}
    for c in ["FY2023A", "FY2024A", "FY2025A", "FY2026B", "FY2026F"]:
        assert float(kpi["covenant_leverage_headroom_x"][c]) > 0
        assert float(kpi["covenant_coverage_headroom_x"][c]) > 0


def test_approved_fy2026_forecast_covenant_position():
    """The reviewer approved these exact figures. Assert them so they cannot drift."""
    kpi = {r["metric"]: r for r in read(ROOT / "config" / "anchors" / "anchor_kpi.csv")}
    assert float(kpi["covenant_max_leverage_x"]["FY2026F"]) == pytest.approx(4.50)
    assert float(kpi["net_leverage_x"]["FY2026F"]) == pytest.approx(3.80, abs=0.005)
    assert float(kpi["covenant_leverage_headroom_x"]["FY2026F"]) == pytest.approx(0.70, abs=0.005)


def test_downside_scenario_is_reserved_and_not_populated():
    rows = read(CONFIG / "dimensions" / "scenario_version.csv")
    ds_scenario = next((r for r in rows if r["table"] == "scenario" and r["code"] == "DS"), None)
    ds_version = next((r for r in rows if r["table"] == "version"
                       and r["code"] == "DS_FY26_STRESS"), None)
    assert ds_scenario is not None, "no Downside scenario is reserved"
    assert ds_version is not None, "no Downside version is reserved"
    for r in (ds_scenario, ds_version):
        assert r["is_reserved"] == "TRUE"
        assert r["is_default"] == "FALSE", "a reserved scenario must never be a default"


def test_no_base_version_is_flagged_reserved():
    rows = read(CONFIG / "dimensions" / "scenario_version.csv")
    for r in rows:
        if r["code"] in ("ACT", "BUD", "FC", "PY", "ACTUAL", "BUD_FY26_V1", "FC_FY26_08"):
            assert r["is_reserved"] == "FALSE", f"{r['code']} must not be reserved"


def test_a_control_isolates_reserved_scenarios(controls):
    ctl = next((r for r in controls if r["control_id"] == "CTL-SCN-06"), None)
    assert ctl is not None and ctl["severity"] == "BLOCKING"
