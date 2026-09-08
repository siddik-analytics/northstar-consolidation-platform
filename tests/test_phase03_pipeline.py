"""
Phase 3 - ingestion, staging and chart-of-accounts harmonisation.

The tests are grouped by the thing that would go wrong:

    the source freeze        Phase 3 must not have changed a byte of the Phase 2 layer
    the oracle separation    the expected-mapping manifest grades the engine and never
                             feeds it
    the rule language        configuration, with an allow-list, not arbitrary SQL
    the adapters             three source systems, three sets of conventions, stated
    the built warehouse      grain, sign, period, lineage, mapping, and the layer boundary
    the source findings      four defects found in the frozen source layer, reported and
                             not patched
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pipeline import (adapters, conform, controls, dimensions, harmonise, reconcile,
                          rules, standardise)
from src.pipeline.config import (CONFIG, CONTROL_RESULTS, DATA, DUCKDB_PATH, LAYERS,
                                 MAPPING_STATUS, RAW, SIGN_CONVENTION)

needs_warehouse = pytest.mark.skipif(
    not DUCKDB_PATH.exists(),
    reason="run `python -m src.pipeline.run` first")


@pytest.fixture(scope="module")
def con():
    import duckdb
    connection = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    yield connection
    connection.close()


def read(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def one(con, sql):
    return con.execute(sql).fetchone()[0]


# =====================================================================================
# 1.  The Phase 2 source layer is frozen
# =====================================================================================
def test_the_pipeline_never_writes_to_the_source_layer():
    """
    Ingestion reads. If any pipeline module opens a source path for writing, the source
    freeze is a promise rather than a property.
    """
    for module in (ROOT / "src" / "pipeline").glob("*.py"):
        text = module.read_text(encoding="utf-8")
        for pattern in (r"RAW\s*/[^)]*\)\s*\.write", r"open\(\s*RAW", r"COPY .* TO '.*data/raw"):
            assert not re.search(pattern, text), f"{module.name} writes into data/raw"


def test_the_phase_2_dataset_digest_is_unchanged():
    """The frozen source layer must still hash to what Phase 2.2 signed off."""
    digest_file = DATA / "samples" / "build_digest.txt"
    recorded = digest_file.read_text(encoding="utf-8").splitlines()[0].split("=", 1)[1]
    manifest = json.loads((DATA / "build_manifest.json").read_text(encoding="utf-8"))
    recomputed = hashlib.sha256(
        json.dumps(manifest["checksums"], sort_keys=True).encode()).hexdigest()
    assert recomputed == recorded


# =====================================================================================
# 2.  The expected-mapping manifest is an oracle, never an input
# =====================================================================================
def test_the_manifest_is_an_oracle_and_never_an_input():
    """
    The acceptance fixture may be read by the test harness and by the acceptance module.
    If a transformation stage could read it, the engine would be copying the answer rather
    than deriving it, and a 100% score would mean nothing.
    """
    stages = ["adapters.py", "standardise.py", "harmonise.py", "rules.py", "conform.py",
              "dimensions.py", "subledgers.py", "run.py"]
    for name in stages:
        text = (ROOT / "src" / "pipeline" / name).read_text(encoding="utf-8")
        assert "expected_mapping_manifest" not in text, f"{name} reads the oracle"
        assert "expected_group_account" not in text, f"{name} reads the oracle column"
        assert "journal_lines.parquet" not in text, f"{name} reads the Phase 2 mirror"
    grader = (ROOT / "src" / "pipeline" / "reconcile.py").read_text(encoding="utf-8")
    assert "expected_mapping_manifest" in grader
    assert "journal_lines.parquet" in grader


def test_the_mapping_engine_derives_from_configuration_only():
    text = (ROOT / "src" / "pipeline" / "harmonise.py").read_text(encoding="utf-8")
    assert "dim_source_account" in text, "the account-level mapping comes from the charts"
    assert "map_rules" in text, "the conditional logic comes from the rule configuration"


# =====================================================================================
# 3.  The rule language
# =====================================================================================
def test_every_rule_parses_and_names_only_permitted_fields():
    for rule in rules.load_rules():
        sql = rules.compile_condition(rule.condition)
        assert sql, rule.rule_id


def test_a_rule_cannot_reference_an_unknown_field():
    with pytest.raises(rules.RuleError):
        rules.compile_condition("nonsense_field = 'X'")


def test_a_rule_cannot_smuggle_sql_through_a_literal():
    for attempt in ("dept_code = 'D100'' OR 1=1--'",
                    "dept_code = (SELECT 1)",
                    "dept_code; DROP TABLE fact_journal_line"):
        with pytest.raises(rules.RuleError):
            rules.compile_condition(attempt)


def test_every_conditional_account_has_exactly_one_default_branch():
    ruleset = rules.load_rules()
    defaults = rules.defaults_by_account(ruleset)
    charts = {("AURORA", "source_coa_aurora.csv"), ("SABLE", "source_coa_sable.csv"),
              ("KESTREL", "source_coa_kestrel.csv")}
    for erp, filename in charts:
        for row in read(CONFIG / "coa" / filename):
            if row["mapping_type"] in ("SPLIT", "DERIVED"):
                assert (erp, row["source_account"]) in defaults, \
                    f"{erp} {row['source_account']} has no default branch"


def test_every_rule_target_is_a_real_non_statistical_group_account():
    accounts = {r["group_account"]: r for r in read(CONFIG / "coa" / "group_coa.csv")}
    for rule in rules.load_rules():
        target = accounts.get(rule.target_group_account)
        assert target is not None, f"{rule.rule_id} targets a missing account"
        assert target["is_statistical"] == "FALSE", f"{rule.rule_id} targets a statistical account"


def test_rule_ids_are_unique_and_effective_dated():
    ruleset = rules.load_rules()
    assert len({r.rule_id for r in ruleset}) == len(ruleset)
    for rule in ruleset:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", rule.effective_from), rule.rule_id


def test_a_default_branch_must_be_unconditional():
    for rule in rules.load_rules():
        if rule.is_default:
            assert rule.condition.strip().upper() == "TRUE", rule.rule_id


# =====================================================================================
# 4.  The adapters state their own conventions
# =====================================================================================
def test_each_adapter_declares_its_own_conventions():
    assert adapters.ADAPTERS["KESTREL"].encoding == "CP1252"
    assert adapters.ADAPTERS["KESTREL"].delimiter == ";"
    assert adapters.ADAPTERS["AURORA"].delimiter == ","
    assert adapters.ADAPTERS["SABLE"].encoding == "utf-8"
    for adapter in adapters.ADAPTERS.values():
        assert adapter.line_key and len(adapter.line_key) == 2
        assert adapter.native, "the native columns must be preserved verbatim"


def test_the_translated_source_columns_are_named_as_forbidden():
    from src.pipeline.config import FORBIDDEN_DOWNSTREAM_FIELDS
    assert adapters.ADAPTERS["AURORA"].forbidden == FORBIDDEN_DOWNSTREAM_FIELDS["AURORA"]
    assert adapters.ADAPTERS["KESTREL"].forbidden == FORBIDDEN_DOWNSTREAM_FIELDS["KESTREL"]
    assert adapters.ADAPTERS["SABLE"].forbidden is None


def test_no_account_key_is_ever_cast_to_a_number():
    for adapter in adapters.ADAPTERS.values():
        expr = adapter.derive["source_account"]
        assert "VARCHAR" in expr and "INTEGER" not in expr and "BIGINT" not in expr


def test_the_sign_convention_is_stated_once():
    assert SIGN_CONVENTION == "DEBIT_POSITIVE"
    assert LAYERS == ["raw", "parsed", "standardised", "mapped", "conformed"]


# =====================================================================================
# 5.  The built warehouse
# =====================================================================================
@needs_warehouse
def test_the_conformed_fact_holds_its_declared_grain(con):
    n, d = con.execute(
        "SELECT count(*), count(DISTINCT line_uid) FROM fact_journal_line").fetchone()
    assert n == d
    dupes = one(con, f"""SELECT count(*) FROM (SELECT {', '.join(conform.FACT_GRAIN)}
                         FROM fact_journal_line GROUP BY ALL HAVING count(*) > 1)""")
    assert dupes == 0


@needs_warehouse
def test_every_line_carries_full_lineage(con):
    missing = one(con, """
        SELECT count(*) FROM fact_journal_line
        WHERE source_file IS NULL OR source_row_ordinal IS NULL OR erp_system IS NULL
           OR source_account IS NULL OR journal_id IS NULL OR line_number IS NULL
           OR source_entity_key IS NULL OR source_native_amount IS NULL
           OR source_period_raw IS NULL""")
    assert missing == 0


@needs_warehouse
def test_the_trial_balance_survives_every_stage(con):
    for table, where in (("stg_standardised", ""), ("fact_journal_line", "")):
        worst = one(con, f"""
            SELECT coalesce(max(abs(s)), 0) FROM (
                SELECT sum(signed_local_amount) AS s FROM {table} {where}
                GROUP BY entity_code, fiscal_year, accounting_period)""")
        assert worst <= 0.02, table


@needs_warehouse
def test_mapping_moves_no_money(con):
    worst = one(con, """
        SELECT coalesce(max(abs(s.signed_local_amount - m.signed_local_amount)), 0)
        FROM stg_standardised s JOIN fact_journal_line m USING (line_uid)""")
    assert worst == 0


@needs_warehouse
def test_every_line_ends_with_exactly_one_declared_status(con):
    statuses = {x[0] for x in con.execute(
        "SELECT DISTINCT mapping_status FROM fact_journal_line").fetchall()}
    assert statuses <= set(MAPPING_STATUS)
    assert not one(con, "SELECT count(*) FROM fact_journal_line WHERE mapping_status IS NULL")


@needs_warehouse
def test_no_line_is_unmapped_or_ambiguous(con):
    bad = one(con, """SELECT count(*) FROM fact_journal_line
                      WHERE mapping_status IN ('UNMAPPED_ACCOUNT','UNMAPPED_NO_RULE',
                                               'AMBIGUOUS','INVALID_DIMENSION','OUT_OF_EFFECT')""")
    assert bad == 0


@needs_warehouse
def test_mapping_reproduces_the_oracle_where_the_source_classified_the_line(con):
    total, matched = con.execute("""
        SELECT count(*), count(*) FILTER (WHERE agrees) FROM map_acceptance
        WHERE classifiable_at_source""").fetchone()
    assert matched == total, f"{total - matched} classifiable lines disagree"


@needs_warehouse
def test_special_periods_are_classified_and_never_become_a_thirteenth_month(con):
    assert one(con, "SELECT count(*) FROM fact_journal_line WHERE management_period > 12") == 0
    kinds = {x[0] for x in con.execute("""
        SELECT DISTINCT special_period_type FROM fact_journal_line
        WHERE special_period IS NOT NULL""").fetchall()}
    assert kinds == {"STATUTORY_CLOSE", "AUDIT_ADJUSTMENT", "TAX_ADJUSTMENT",
                     "GROUP_REPORTING_ADJUSTMENT"}
    assert one(con, """SELECT count(*) FROM fact_journal_line
                       WHERE special_period IS NOT NULL AND management_period <> 12""") == 0


@needs_warehouse
def test_kestrel_account_keys_keep_their_leading_zeros(con):
    padded = one(con, """SELECT count(DISTINCT source_account) FROM fact_journal_line
                         WHERE erp_system = 'KESTREL' AND source_account LIKE '0%'""")
    assert padded > 0
    wrong_length = one(con, """SELECT count(*) FROM fact_journal_line
                               WHERE erp_system = 'KESTREL' AND length(source_account) <> 8""")
    assert wrong_length == 0


@needs_warehouse
def test_the_german_total_cost_method_items_land_in_cost_of_sales(con):
    rows = con.execute("""
        SELECT reporting_block, count(*), is_presentation_reclass
        FROM fact_journal_line WHERE source_account IN ('00081000','00081200')
        GROUP BY ALL""").fetchall()
    assert rows, "no total-cost-method postings found"
    for block, _n, flagged in rows:
        assert block == "COST_OF_SALES"
        assert flagged


@needs_warehouse
def test_the_reclassification_changes_no_amount(con):
    """A presentation reclassification moves a caption, never a number."""
    worst = one(con, """
        SELECT coalesce(max(abs(s.signed_local_amount - m.signed_local_amount)), 0)
        FROM stg_standardised s JOIN fact_journal_line m USING (line_uid)
        WHERE m.is_presentation_reclass""")
    assert worst == 0


@needs_warehouse
def test_phase_3_produces_layer_1_only(con):
    assert [x[0] for x in con.execute(
        "SELECT DISTINCT layer_id FROM fact_journal_line").fetchall()] == [1]
    assert one(con, "SELECT count(*) FROM stg_group_adjustment") == 0


@needs_warehouse
def test_no_source_layer_cta_or_balancing_reserve_exists(con):
    """Section 18 of the Phase 3 brief, and ADR-0017."""
    assert one(con, """SELECT count(*) FROM fact_journal_line
                       WHERE group_account LIKE '33%' OR group_account LIKE '34%'
                          OR group_account = '329100'""") == 0
    plugs = con.execute("""
        SELECT DISTINCT group_account, group_account_name FROM fact_journal_line
        WHERE lower(group_account_name) LIKE '%measurement reserve%'
           OR lower(group_account_name) LIKE '%balancing%'
           OR lower(group_account_name) LIKE '%suspense%'""").fetchall()
    assert not plugs


@needs_warehouse
def test_the_source_systems_translated_columns_reach_no_aggregate(con):
    columns = {c[0] for c in con.execute("DESCRIBE fact_trial_balance").fetchall()}
    assert not [c for c in columns if "translated" in c]
    detail = {c[0] for c in con.execute("DESCRIBE fact_journal_line").fetchall()}
    assert "source_translated_amount" in detail, "kept on the detail for lineage"


@needs_warehouse
def test_customer_and_product_stay_out_of_the_ledger_and_still_tie(con):
    """ADR-0008: separate fact, finer grain, reconciled."""
    worst = one(con, "SELECT coalesce(max(abs(variance_local)), 0) FROM rec_revenue_detail")
    assert worst <= 0.05
    gl_rows = one(con, """SELECT count(*) FROM fact_journal_line
                          WHERE customer_code IS NOT NULL AND group_account LIKE '4%'""")
    assert gl_rows > 0, "the customer reference stays on the line for lineage"
    assert "revenue_local" not in {c[0] for c in con.execute(
        "DESCRIBE fact_journal_line").fetchall()}


@needs_warehouse
def test_gross_margin_by_business_unit_reproduces_the_anchor(con):
    worst = one(con,
                "SELECT coalesce(max(abs(margin_variance_pct)), 1) FROM rec_business_unit_margin")
    assert worst <= 0.0005


@needs_warehouse
def test_the_group_income_statement_reproduces_the_source_layer_target(con):
    worst = one(con, "SELECT coalesce(max(deviation_pct), 1) FROM rec_group_income_statement")
    assert worst <= reconcile.TOL_PL


@needs_warehouse
def test_the_reserved_downside_scenario_is_not_populated(con):
    assert one(con, "SELECT count(*) FROM fact_plan WHERE version_is_reserved") == 0
    assert one(con, "SELECT count(*) FROM fact_plan WHERE scenario_code = 'PY'") == 0


@needs_warehouse
def test_every_conformed_dimension_carries_its_provenance(con):
    for table in dimensions.DIMENSION_SOURCES:
        columns = {c[0] for c in con.execute(f"DESCRIBE {table}").fetchall()}
        assert "source_config" in columns, table


# =====================================================================================
# 6.  Determinism
# =====================================================================================
def test_the_build_id_is_a_function_of_its_inputs_and_not_of_the_clock():
    from src.pipeline import run as runner
    assert runner.build_id() == runner.build_id()
    text = (ROOT / "src" / "pipeline" / "run.py").read_text(encoding="utf-8")
    manifest_block = text[text.index("manifest = {"):text.index("MANIFEST.write_text")]
    for forbidden in ("time.time", "datetime", "now(", "uuid"):
        assert forbidden not in manifest_block, "a clock value in a committed manifest"


@needs_warehouse
def test_the_manifest_records_the_frozen_source_digest():
    manifest = json.loads((DATA / "phase03_manifest.json").read_text(encoding="utf-8"))
    digest = (DATA / "samples" / "build_digest.txt").read_text(
        encoding="utf-8").splitlines()[0].split("=", 1)[1]
    assert manifest["source_layer_digest"] == digest
    assert manifest["phase"] == 3


# =====================================================================================
# 7.  The source findings are reported, not absorbed
# =====================================================================================
@needs_warehouse
def test_the_control_results_separate_a_pipeline_failure_from_a_source_finding():
    results = read(CONTROL_RESULTS)
    assert results, "no control results"
    statuses = {r["status"] for r in results}
    assert statuses <= {"PASS", "FAIL", "SOURCE_FINDING"}
    blocking_failures = [r for r in results
                         if r["status"] == "FAIL" and r["severity"] == "BLOCKING"]
    assert not blocking_failures, blocking_failures


@needs_warehouse
def test_every_source_finding_names_the_defect_it_belongs_to():
    findings = [r for r in read(CONTROL_RESULTS) if r["status"] == "SOURCE_FINDING"]
    assert findings, "the three known source defects should still be reported"
    for row in findings:
        assert re.fullmatch(r"P2-D-\d{2}", row["defect_reference"]), row["control_id"]
    assert {r["defect_reference"] for r in findings} == {"P2-D-01", "P2-D-02", "P2-D-03",
                                                        "P2-D-04"}


def test_the_source_defects_are_documented_in_the_phase_report():
    report = (ROOT / "docs" / "phases" / "phase-03-report.md").read_text(encoding="utf-8")
    for defect in ("P2-D-01", "P2-D-02", "P2-D-03", "P2-D-04"):
        assert defect in report, f"{defect} is not documented"
        assert "Proposed correction" in report
    assert "rather than patched" in report, "the report must say the defects stand"


def test_no_phase_2_generator_module_was_changed_by_phase_3():
    """The source freeze in the form a reviewer would check it: git says so."""
    changed = subprocess.run(
        ["git", "diff", "--name-only", "0ffe502..HEAD", "--", "src/generation"],
        capture_output=True, text=True, cwd=ROOT).stdout.split()
    phase22 = subprocess.run(
        ["git", "diff", "--name-only", "0ffe502..20355b2", "--", "src/generation"],
        capture_output=True, text=True, cwd=ROOT).stdout.split()
    assert set(changed) == set(phase22), \
        "src/generation changed after the Phase 2.2 freeze: " + str(set(changed) - set(phase22))


# ---------------------------------------------------------------------------
# The three control-design fixes the fault sweep forced (report §13.4-13.6)
# ---------------------------------------------------------------------------

def test_the_numeric_grammar_rejects_a_malformed_localised_amount():
    """F06's defect is not a null, so only a grammar can see it.

    A German ``13.068,03`` mistyped as ``13.068.03`` casts cleanly to 1,306,803 -- a
    hundredfold overstatement that still balances if both legs are affected.
    """
    kestrel = re.compile(controls.NUMERIC_GRAMMAR["KESTREL"][0])
    assert kestrel.match("13.068,03")
    assert kestrel.match("218,50")
    assert not kestrel.match("13.068.03"), "the F06 corruption must not be accepted"
    # Kestrel always writes its grouping separator, so an ungrouped four-digit amount is
    # itself a corruption -- a lost point, not a lost thousand.
    assert not kestrel.match("4218,50")

    us = re.compile(controls.NUMERIC_GRAMMAR["SABLE"][0])
    assert us.match("1,306,803.00")
    assert not us.match("1.306.803,00"), "a German amount must not pass a US grammar"


def test_every_erp_declares_a_numeric_grammar():
    assert set(controls.NUMERIC_GRAMMAR) == set(adapters.ADAPTERS)


def test_the_gross_margin_tolerance_is_tighter_than_a_plausible_misclassification():
    """F08 moves group gross margin by 0.047104pp. The clean result is exactly zero,
    so the tolerance has nothing legitimate to absorb."""
    assert controls.TOL_MARGIN * 100 <= 0.01, \
        "a tolerance above a basis point cannot see a consistent payroll misclassification"


def test_every_accepted_source_finding_is_registered_with_its_population():
    register = read(controls.EXCEPTION_REGISTER)
    assert register, "the source exception register is empty"
    for row in register:
        assert re.fullmatch(r"SX-\d{3}", row["exception_id"]), row
        assert re.fullmatch(r"P2-D-\d{2}", row["defect_reference"]), row
        assert int(row["accepted_population"]) > 0, row
        assert row["expires"], f"{row['exception_id']} has no expiry and cannot be retired"


@needs_warehouse
def test_a_source_finding_is_reported_only_at_its_accepted_population():
    exceptions = controls.load_exceptions()
    findings = [r for r in read(CONTROL_RESULTS) if r["status"] == "SOURCE_FINDING"]
    assert findings
    for row in findings:
        assert row["control_id"] in exceptions, \
            f"{row['control_id']} reports a source finding with no registered exception"
        accepted = int(exceptions[row["control_id"]]["accepted_population"])
        assert str(accepted) in row["measured"], \
            f"{row['control_id']} measured {row['measured']}, accepted {accepted}"


def test_a_new_break_of_a_known_shape_fails_rather_than_hiding():
    """The register's whole purpose: the population *is* the control."""
    exceptions = controls.load_exceptions()
    cid, row = next(iter(exceptions.items()))
    accepted = int(row["accepted_population"])
    for measured, expected in ((0, "PASS"), (accepted, "SOURCE_FINDING"),
                               (accepted + 1, "FAIL"), (accepted - 1, "FAIL")):
        r = controls.Result()
        controls.registered(r, exceptions, cid, "t", "BLOCKING", measured, "lines", "d")
        assert r[-1]["status"] == expected, \
            f"{measured} against {accepted} accepted should be {expected}"


# ---------------------------------------------------------------------------
# Reproducibility, measured rather than claimed (report §13.7)
# ---------------------------------------------------------------------------

def test_every_committed_artefact_is_written_in_a_total_order():
    """
    A COPY without an ORDER BY is a reproducibility hole. DuckDB's parallel scan may emit
    rows in a different sequence on an identical input, so the same build writes different
    bytes and the determinism proof means nothing.
    """
    for module in (ROOT / "src" / "pipeline").glob("*.py"):
        text = module.read_text(encoding="utf-8")
        for match in re.finditer(r"COPY\s*\(?(.*?)\)?\s*TO\s*'", text, re.S):
            body = match.group(1)
            assert "ORDER BY" in body.upper(), \
                f"{module.name}: a COPY is written without a total order"


@needs_warehouse
def test_money_is_a_decimal_and_never_a_float(con):
    """
    Floating-point addition is not associative, so a parallel SUM over DOUBLE totals a
    ledger differently depending on which thread finishes first. Money is DECIMAL.
    """
    for table in ("fact_journal_line", "fact_trial_balance"):
        types = dict(con.execute(f"""
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_name = '{table}'
              AND column_name IN ('signed_local_amount', 'debit_local', 'credit_local')
        """).fetchall())
        assert types, table
        for column, dtype in types.items():
            assert dtype.startswith("DECIMAL"), f"{table}.{column} is {dtype}"


@needs_warehouse
def test_the_decimal_representation_loses_nothing(con):
    """It is only safe because every source amount is already exact to the cent."""
    beyond_cents = one(con, """
        SELECT count(*) FROM parsed_aurora
        WHERE native_signed_amount IS NOT NULL
          AND abs(native_signed_amount - round(native_signed_amount, 2)) > 1e-9""")
    assert beyond_cents == 0


@needs_warehouse
def test_the_manifest_checksums_every_artefact_it_claims_to():
    manifest = json.loads((DATA / "phase03_manifest.json").read_text(encoding="utf-8"))
    artefacts = manifest.get("artefacts") or manifest["checksums"]
    assert len(artefacts) >= 25
    for name, digest in artefacts.items():
        assert re.fullmatch(r"[0-9a-f]{64}", digest), name
        assert (DATA / name).exists(), f"{name} is checksummed but absent"
