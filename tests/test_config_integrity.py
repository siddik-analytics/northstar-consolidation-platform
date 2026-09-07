"""
Structural integrity of the Phase 1 configuration seeds.

These are the tests that stop a broken chart-of-accounts mapping, a dangling entity
reference or a malformed control definition from ever reaching the consolidation
engine.  They run in CI on every change to config/.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"

SOURCE_COA_FILES = {
    "AURORA": CONFIG / "coa" / "source_coa_aurora.csv",
    "SABLE": CONFIG / "coa" / "source_coa_sable.csv",
    "KESTREL": CONFIG / "coa" / "source_coa_kestrel.csv",
}
BOOLEANS = {"TRUE", "FALSE"}


def read(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def group_coa():
    return read(CONFIG / "coa" / "group_coa.csv")


@pytest.fixture(scope="module")
def entities():
    return read(CONFIG / "entities" / "entity_master.csv")


@pytest.fixture(scope="module")
def source_coas():
    return {erp: read(path) for erp, path in SOURCE_COA_FILES.items()}


# ---------------------------------------------------------------- group chart of accounts
def test_group_accounts_are_unique(group_coa):
    codes = [r["group_account"] for r in group_coa]
    dupes = {c for c in codes if codes.count(c) > 1}
    assert not dupes, f"duplicate group accounts: {sorted(dupes)}"


def test_group_accounts_are_six_digit_numeric(group_coa):
    for r in group_coa:
        assert re.fullmatch(r"\d{6}", r["group_account"]), \
            f"{r['group_account']} is not a six-digit account code"


def test_account_code_block_matches_statement(group_coa):
    """The leading digit encodes the statement section; drift here breaks every report."""
    expected = {"1": "BS", "2": "BS", "3": "BS", "4": "IS", "5": "IS",
                "6": "IS", "7": "IS", "8": "IS", "9": "STAT"}
    for r in group_coa:
        assert r["statement"] == expected[r["group_account"][0]], \
            f"{r['group_account']} {r['account_name']}: block and statement disagree"


def test_boolean_flags_are_wellformed(group_coa):
    flags = ["is_intercompany", "is_ebitda", "is_ebitda_addback",
             "is_statistical", "include_in_tb_balance"]
    for r in group_coa:
        for flag in flags:
            assert r[flag] in BOOLEANS, f"{r['group_account']}: {flag} = {r[flag]!r}"


def test_normal_balance_is_valid(group_coa):
    for r in group_coa:
        assert r["normal_balance"] in {"D", "C"}, r["group_account"]


def test_statistical_accounts_are_excluded_from_the_trial_balance(group_coa):
    """CTL-TB-04. Including headcount in a debits-equals-credits test creates false failures."""
    for r in group_coa:
        if r["is_statistical"] == "TRUE":
            assert r["include_in_tb_balance"] == "FALSE", \
                f"{r['group_account']} is statistical but included in trial balance testing"
            assert r["fx_method"] == "NONE", \
                f"{r['group_account']} is statistical and must not be translated"
        else:
            assert r["include_in_tb_balance"] == "TRUE", \
                f"{r['group_account']} is financial and must be included in trial balance testing"


def test_account_class_is_from_the_controlled_vocabulary(group_coa):
    allowed = {"ASSET", "LIABILITY", "EQUITY", "REVENUE", "COGS", "OPEX",
               "DA", "NONOP", "TAX", "NCI", "STAT"}
    for r in group_coa:
        assert r["account_class"] in allowed, \
            f"{r['group_account']}: unknown account class {r['account_class']!r}"


def test_ebitda_flag_only_on_operating_pl_accounts(group_coa):
    """EBITDA must not accidentally include D&A, interest, tax, NCI or balance sheet accounts."""
    for r in group_coa:
        if r["is_ebitda"] == "TRUE":
            assert r["account_class"] in {"REVENUE", "COGS", "OPEX"}, \
                f"{r['group_account']} {r['account_name']} is flagged into EBITDA but is {r['account_class']}"
        if r["account_class"] in {"DA", "NONOP", "TAX", "NCI"}:
            assert r["is_ebitda"] == "FALSE", \
                f"{r['group_account']} {r['account_name']} must sit below EBITDA"


def test_addbacks_are_a_subset_of_ebitda_accounts(group_coa):
    """An add-back that is not in EBITDA would be added back twice."""
    for r in group_coa:
        if r["is_ebitda_addback"] == "TRUE":
            assert r["is_ebitda"] == "TRUE", \
                f"{r['group_account']} is an add-back but is not inside EBITDA"


def test_fx_method_is_appropriate_for_the_statement(group_coa):
    for r in group_coa:
        m, stmt, cls = r["fx_method"], r["statement"], r["account_class"]
        assert m in {"AVG", "CLOSE", "HIST", "NONE"}, f"{r['group_account']}: {m}"
        if stmt == "IS":
            assert m == "AVG", f"{r['group_account']}: income statement must translate at average"
        if stmt == "BS" and cls in {"ASSET", "LIABILITY"}:
            assert m in {"CLOSE", "HIST"}, \
                f"{r['group_account']}: balance sheet items translate at closing or historical rates"


def test_every_balance_sheet_account_has_a_cash_flow_category(group_coa):
    """CTL-FS-04. An uncategorised movement vanishes from the cash flow statement."""
    for r in group_coa:
        if r["statement"] == "BS":
            assert r["cash_flow_category"] not in {"", "NONE"}, \
                f"{r['group_account']} {r['account_name']} has no cash flow category"


def test_intercompany_accounts_exist_on_both_sides(group_coa):
    ic = {r["group_account"] for r in group_coa if r["is_intercompany"] == "TRUE"}
    for receivable, payable in [("120500", "210500"), ("125100", "225100"),
                                ("175100", "235100"), ("490100", "590100"),
                                ("490200", "590200"), ("795100", "795200")]:
        assert receivable in ic and payable in ic, \
            f"intercompany pair {receivable}/{payable} is incomplete"


def test_sort_order_is_unique(group_coa):
    orders = [r["sort_order"] for r in group_coa]
    assert len(orders) == len(set(orders)), "duplicate sort_order values produce unstable report ordering"


# ---------------------------------------------------------------- source charts of accounts
def test_every_source_account_maps_to_a_real_group_account(source_coas, group_coa):
    """CTL-MAP-02. This is the test that stops a broken mapping being merged."""
    valid = {r["group_account"] for r in group_coa}
    for erp, rows in source_coas.items():
        for r in rows:
            assert r["group_account"] in valid, \
                f"{erp} {r['source_account']} maps to unknown group account {r['group_account']}"


def test_no_source_account_maps_to_a_statistical_account(source_coas, group_coa):
    """CTL-MAP-03. Mapping a financial account to a statistical one unbalances the entity."""
    statistical = {r["group_account"] for r in group_coa if r["is_statistical"] == "TRUE"}
    for erp, rows in source_coas.items():
        for r in rows:
            assert r["group_account"] not in statistical, \
                f"{erp} {r['source_account']} maps to statistical account {r['group_account']}"


def test_source_accounts_are_unique_within_each_erp(source_coas):
    for erp, rows in source_coas.items():
        codes = [r["source_account"] for r in rows]
        dupes = {c for c in codes if codes.count(c) > 1}
        assert not dupes, f"{erp} has duplicate source accounts: {sorted(dupes)}"


def test_source_account_formats_match_the_erp_profile(source_coas):
    patterns = {"AURORA": r"\d{4}", "SABLE": r"\d{5}", "KESTREL": r"\d{8}"}
    for erp, rows in source_coas.items():
        for r in rows:
            assert re.fullmatch(patterns[erp], r["source_account"]), \
                f"{erp} account {r['source_account']!r} does not match the documented format"


def test_kestrel_codes_retain_leading_zeros(source_coas):
    """CTL-DQ-10. Coercing these to integers is the classic way to lose them."""
    assert any(r["source_account"].startswith("0") for r in source_coas["KESTREL"]), \
        "Kestrel account codes must be zero-padded text"


def test_split_mappings_carry_a_rule(source_coas):
    """CTL-MAP-04. A SPLIT with no rule cannot resolve and will silently fall through."""
    for erp, rows in source_coas.items():
        for r in rows:
            if r["mapping_type"] == "SPLIT":
                assert r["mapping_rule"].strip(), \
                    f"{erp} {r['source_account']} is a SPLIT with no mapping rule"


def test_mapping_types_are_from_the_controlled_vocabulary(source_coas):
    allowed = {"DIRECT", "MERGE", "SPLIT", "DERIVED"}
    for erp, rows in source_coas.items():
        for r in rows:
            assert r["mapping_type"] in allowed, \
                f"{erp} {r['source_account']}: unknown mapping type {r['mapping_type']!r}"


def test_intercompany_source_accounts_require_a_partner(source_coas, group_coa):
    """CTL-IC-04. An intercompany balance with no partner can never be matched."""
    ic_group = {r["group_account"] for r in group_coa if r["is_intercompany"] == "TRUE"}
    exempt = {"130500", "178100"}  # engine-generated, never posted from a source system
    for erp, rows in source_coas.items():
        for r in rows:
            if r["group_account"] in ic_group - exempt:
                assert "REQUIRES_PARTNER" in r["mapping_rule"] or r["mapping_type"] == "SPLIT", \
                    f"{erp} {r['source_account']} posts to intercompany {r['group_account']} without requiring a partner"


def test_material_gross_margin_split_rules_are_documented(source_coas):
    """The payroll accounts that decide whether cost lands above or below gross margin."""
    aurora = {r["source_account"]: r for r in source_coas["AURORA"]}
    kestrel = {r["source_account"]: r for r in source_coas["KESTREL"]}
    assert aurora["6100"]["mapping_type"] == "SPLIT"
    assert kestrel["00091000"]["mapping_type"] == "SPLIT"


def test_kestrel_total_cost_method_accounts_are_reclassified(source_coas):
    """CTL-MAP-08. Leaving these in revenue overstates revenue and gross margin."""
    kestrel = {r["source_account"]: r for r in source_coas["KESTREL"]}
    for acct in ("00081000", "00081200"):
        row = kestrel[acct]
        assert row["mapping_type"] == "DERIVED"
        assert "sign_reversal" in row["mapping_rule"]
        assert not row["group_account"].startswith("4"), \
            f"{acct} must not remain in the revenue block"


def test_each_erp_has_a_genuinely_different_chart(source_coas):
    """The engagement premise is three divergent charts. Assert they did not converge."""
    sets = {erp: {r["source_account"] for r in rows} for erp, rows in source_coas.items()}
    for a, b in [("AURORA", "SABLE"), ("AURORA", "KESTREL"), ("SABLE", "KESTREL")]:
        assert not sets[a] & sets[b], f"{a} and {b} share source account codes"


# ---------------------------------------------------------------- entities
def test_entity_codes_are_unique(entities):
    codes = [r["entity_code"] for r in entities]
    assert len(codes) == len(set(codes))


def test_twelve_operating_legal_entities(entities):
    operating = [r for r in entities if r["entity_type"] == "OPERATING"]
    assert len(operating) == 12, f"expected 12 legal entities, found {len(operating)}"


def test_every_entity_except_topco_has_a_valid_parent(entities):
    codes = {r["entity_code"] for r in entities}
    for r in entities:
        if r["entity_code"] == "NIG-100":
            assert r["parent_entity_code"] == ""
        else:
            assert r["parent_entity_code"] in codes, \
                f"{r['entity_code']} has unknown parent {r['parent_entity_code']!r}"


def test_ownership_and_nci_sum_to_one(entities):
    """CTL-CON-01."""
    for r in entities:
        total = float(r["ownership_pct"]) + float(r["nci_pct"])
        assert abs(total - 1.0) < 1e-9, \
            f"{r['entity_code']}: ownership {r['ownership_pct']} + NCI {r['nci_pct']} != 1"


def test_exactly_one_entity_carries_nci(entities):
    nci = [r for r in entities if float(r["nci_pct"]) > 0]
    assert len(nci) == 1 and nci[0]["entity_code"] == "NIG-510"


def test_ownership_tree_has_no_cycles(entities):
    parents = {r["entity_code"]: r["parent_entity_code"] for r in entities}
    for start in parents:
        seen, node = set(), start
        while node:
            assert node not in seen, f"ownership cycle detected at {start}"
            seen.add(node)
            node = parents.get(node, "")


def test_currencies_are_in_scope(entities):
    allowed = {"USD", "CAD", "GBP", "EUR"}
    assert {r["functional_currency"] for r in entities} <= allowed
    # all four in-scope currencies are actually used, or the FX design is untested
    assert {r["functional_currency"] for r in entities if r["entity_type"] == "OPERATING"} == allowed


def test_all_three_erp_systems_are_used(entities):
    used = {r["erp_system"] for r in entities if r["entity_type"] == "OPERATING"}
    assert used == set(SOURCE_COA_FILES), f"ERP coverage is {used}"


def test_elimination_entities_are_flagged_and_never_sourced(entities):
    elim = [r for r in entities if r["entity_type"] == "ELIMINATION"]
    assert len(elim) == 3, "expected separate elimination entities for IC, consolidation and management layers"
    for r in elim:
        assert r["is_elimination_entity"] == "TRUE"
        assert r["erp_system"] == "CONSOL"
        assert r["functional_currency"] == "USD"


def test_acquired_entities_have_an_acquisition_date(entities):
    for r in entities:
        if r["acquisition_type"] == "ACQUISITION":
            assert r["acquisition_date"], f"{r['entity_code']} has no acquisition date"
            assert r["consolidation_effective_from"] == r["acquisition_date"], \
                f"{r['entity_code']}: consolidation must start on the acquisition date (CTL-CON-02)"


# ---------------------------------------------------------------- intercompany matrix
def test_intercompany_matrix_references_real_entities_and_accounts(group_coa, entities):
    codes = {r["entity_code"] for r in entities}
    accounts = {r["group_account"] for r in group_coa}
    rows = read(CONFIG / "ic" / "intercompany_matrix.csv")
    for r in rows:
        assert r["seller_entity"] in codes, f"{r['ic_flow_id']}: unknown seller {r['seller_entity']}"
        assert r["buyer_entity"] in codes, f"{r['ic_flow_id']}: unknown buyer {r['buyer_entity']}"
        assert r["seller_entity"] != r["buyer_entity"], \
            f"{r['ic_flow_id']}: an entity cannot trade with itself (CTL-IC-04)"
        for col in ("seller_pl_account", "buyer_pl_account",
                    "seller_bs_account", "buyer_bs_account"):
            if r[col]:
                assert r[col] in accounts, f"{r['ic_flow_id']}: unknown account {r[col]} in {col}"


def test_intercompany_flows_use_intercompany_accounts(group_coa):
    ic = {r["group_account"] for r in group_coa if r["is_intercompany"] == "TRUE"}
    for r in read(CONFIG / "ic" / "intercompany_matrix.csv"):
        for col in ("seller_pl_account", "buyer_pl_account", "seller_bs_account", "buyer_bs_account"):
            if r[col] and r["flow_type"] != "EQUITY":
                assert r[col] in ic, \
                    f"{r['ic_flow_id']}: {r[col]} is not flagged as an intercompany account"


def test_unrealised_profit_only_where_a_margin_is_charged():
    for r in read(CONFIG / "ic" / "intercompany_matrix.csv"):
        if r["creates_unrealised_profit"] == "TRUE":
            assert float(r["margin_pct"] or 0) > 0, \
                f"{r['ic_flow_id']}: cannot create unrealised profit with no transfer margin"


def test_reverse_direction_and_cross_currency_flows_exist():
    """Guards against an elimination engine that assumes a single USD hub."""
    rows = read(CONFIG / "ic" / "intercompany_matrix.csv")
    assert any(r["seller_entity"] == "NIG-220" for r in rows), "no reverse-direction product flow"
    assert any(r["seller_entity"] == "NIG-320" and r["buyer_entity"] == "NIG-410" for r in rows), \
        "no non-USD to non-USD intercompany pair"


# ---------------------------------------------------------------- controls and policies
def test_control_register_is_wellformed():
    rows = read(CONFIG / "controls" / "control_register.csv")
    ids = [r["control_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate control IDs"
    assert len(rows) >= 50, f"only {len(rows)} controls defined"
    for r in rows:
        assert r["severity"] in {"BLOCKING", "WARNING", "INFO"}, r["control_id"]
        assert r["test_logic"].strip(), f"{r['control_id']} has no test logic"
        assert r["owner"].strip(), f"{r['control_id']} has no owner"
        assert r["remediation"].strip(), f"{r['control_id']} has no remediation"
        assert r["phase_enforced"].isdigit(), r["control_id"]


def test_every_control_category_is_represented():
    rows = read(CONFIG / "controls" / "control_register.csv")
    categories = {r["category"] for r in rows}
    required = {"DATA_QUALITY", "MAPPING", "TRIAL_BALANCE", "FIN_STATEMENT", "FX",
                "INTERCOMPANY", "CONSOLIDATION", "SCENARIO", "RECONCILIATION", "REASONABLENESS"}
    assert required <= categories, f"missing control categories: {required - categories}"


def test_fx_policy_covers_every_fx_method_used(group_coa):
    policy = read(CONFIG / "fx" / "fx_translation_policy.csv")
    covered = {r["rate_type"] for r in policy}
    for method in {r["fx_method"] for r in group_coa}:
        assert method in covered or method == "NONE", f"no FX policy covers method {method}"


def test_scenario_and_version_definitions_are_consistent():
    rows = read(CONFIG / "dimensions" / "scenario_version.csv")
    scenarios = {r["code"] for r in rows if r["table"] == "scenario"}
    assert {"ACT", "BUD", "FC", "PY"} <= scenarios
    for r in rows:
        if r["table"] == "version":
            assert r["parent_code"] in scenarios, \
                f"version {r['code']} references unknown scenario {r['parent_code']}"
    # Prior Year must be derived, never stored as its own version
    py = next(r for r in rows if r["table"] == "scenario" and r["code"] == "PY")
    assert py["scenario_type"] == "DERIVED", "Prior Year must be derived (ADR-0004)"
    assert not any(r["parent_code"] == "PY" for r in rows if r["table"] == "version")


def test_department_business_unit_references_are_valid():
    bus = {r["bu_code"] for r in read(CONFIG / "dimensions" / "business_unit.csv")}
    for r in read(CONFIG / "dimensions" / "department.csv"):
        for bu in r["applies_to_bu"].split(";"):
            assert bu.strip() in bus, f"department {r['department_code']} references unknown BU {bu!r}"
        assert r["pl_destination"] in {"COS", "OPEX"}, r["department_code"]


def test_entity_business_units_are_valid(entities):
    bus = {r["bu_code"] for r in read(CONFIG / "dimensions" / "business_unit.csv")}
    for r in entities:
        assert r["primary_business_unit"] in bus, \
            f"{r['entity_code']} references unknown business unit {r['primary_business_unit']}"
