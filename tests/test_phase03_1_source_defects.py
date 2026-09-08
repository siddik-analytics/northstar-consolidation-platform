"""
Phase 3.1 - the four source defects, tested at the rule that caused each one.

An aggregate test would pass again the moment the aggregate happened to agree. Each test
here goes at the business rule that failed, so that the defect cannot come back quietly:

    P2-D-01  a posting must carry the attributes its account's mapping rule reads,
             whatever kind of journal it belongs to
    P2-D-02  a posting's declared classification and the cost centre it sits in are two
             views of one fact and must agree
    P2-D-03  an intercompany balance is a balance WITH somebody, and the posting says who
    P2-D-04  a post-close adjustment reclassifies within one anchored caption

The generator-level tests run against the module rather than the built dataset, so they
fail in a second rather than after a twenty-minute rebuild. The warehouse-level tests prove
the same thing about the data that was actually produced.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation import journals, mapping
from src.generation.masters import ACCOUNT_DEPTS, DEPT_FUNCTION
from src.pipeline.config import CONFIG, DUCKDB_PATH

needs_warehouse = pytest.mark.skipif(
    not DUCKDB_PATH.exists(),
    reason="run `python -m src.pipeline.run` first")


@pytest.fixture(scope="module")
def con():
    import duckdb
    connection = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    yield connection
    connection.close()


def one(con, sql):
    return con.execute(sql).fetchone()[0]


# =====================================================================================
# P2-D-01  every journal type carries the attributes the mapping contract reads
# =====================================================================================
def test_no_journal_writer_discards_the_attributes_it_resolved():
    """
    The defect in its original form: three writers resolved the required attributes and
    then wrote an empty string. Every writer now goes through one resolver.
    """
    text = (ROOT / "src" / "generation" / "journals.py").read_text(encoding="utf-8")
    for method in ("opening_balance", "special_period_adjustments", "year_end_close"):
        body = text.split(f"def {method}(")[1].split("\n    def ")[0]
        assert "self._resolve(" in body, \
            f"{method} does not resolve its lines through the shared resolver"
        assert "self.sm.resolve(" not in body or "is None" in body, \
            f"{method} resolves the source account itself and can discard the attributes"


@needs_warehouse
def test_every_posting_to_a_conditional_account_carries_what_its_rule_reads(con):
    """
    The rule-level statement of P2-D-01: for each account whose mapping is conditional,
    every posting to it carries at least one field the rules for that account evaluate.
    A posting that carries none of them cannot be classified from what it contains, and
    the engine's fallback to the default branch is then a guess dressed as an answer.
    """
    missing = one(con, """
        SELECT count(*) FROM map_acceptance WHERE NOT classifiable_at_source""")
    assert missing == 0, f"{missing} postings cannot be classified from what they carry"


@needs_warehouse
def test_the_conversion_and_close_journals_are_not_a_blind_spot(con):
    """
    P2-D-01 hid in the journal types nobody looks at. The measure is stated over those
    journal types on their own, with a guard that the population is not empty -- a test
    that passes because it found nothing to test is the same blind spot again.
    """
    for event in ("OPENING_BALANCE", "YEAR_END_CLOSE", "AUDIT_ADJUSTMENT",
                  "TAX_ADJUSTMENT", "GROUP_GAAP_ADJUSTMENT"):
        graded, unclassifiable = con.execute(f"""
            SELECT count(*), count(*) FILTER (WHERE NOT classifiable_at_source)
            FROM map_acceptance WHERE source_journal_type = '{event}'""").fetchone()
        assert graded > 0, f"no {event} postings were graded -- the test is blind"
        assert unclassifiable == 0, \
            f"{unclassifiable} of {graded} {event} postings cannot be classified"


@needs_warehouse
def test_the_accrual_that_moved_2m_between_two_captions_is_classified(con):
    """
    The specific consequence: seven Kestrel postings to Aktive Rechnungsabgrenzung carried
    no accrual_type, so USD 2.33m sat in prepayments instead of contract assets.
    """
    posted, unclassified = con.execute("""
        SELECT count(*),
               count(*) FILTER (WHERE source_line_attributes NOT LIKE '%accrual_type=%')
        FROM fact_journal_line
        WHERE erp_system = 'KESTREL' AND source_account = '00017000'""").fetchone()
    assert posted > 0
    assert unclassified == 0
    # and the two group accounts it splits into are both reached
    assert one(con, """
        SELECT count(DISTINCT group_account) FROM fact_journal_line
        WHERE erp_system = 'KESTREL' AND source_account = '00017000'""") == 2


# =====================================================================================
# P2-D-02  the declared classification and the cost centre agree
# =====================================================================================
def test_the_cost_centre_is_chosen_to_satisfy_the_split_not_labelled_afterwards():
    text = (ROOT / "src" / "generation" / "journals.py").read_text(encoding="utf-8")
    body = text.split("def _cost_centre(")[1].split("\n    @staticmethod")[0]
    assert "req" in body.split("\n")[0] or "req:" in body, \
        "_cost_centre does not take the split's requirement into account"
    assert "raise KeyError" in body, \
        "_cost_centre must refuse to post rather than apply a label the cost centre denies"


def test_a_cost_centre_that_cannot_satisfy_the_requirement_is_refused():
    """
    The behaviour that makes the defect impossible: where an entity has no department of
    the required function, the generator stops instead of writing a posting whose declared
    classification its cost centre contradicts.
    """
    gen = journals.JournalGenerator.__new__(journals.JournalGenerator)
    gen.cc_by_entity = {"E1": {"D500": [{"cost_center_code": "1-500"}]}}   # SGA only
    with pytest.raises(KeyError, match="P2-D-02"):
        gen._cost_centre("E1", "515100", {"dept_function": "PRODUCTION"})


def test_a_split_requirement_may_name_every_value_its_rule_accepts():
    """
    The reason the defect was widespread: the generator named ONE accepted value where the
    approved rule accepts a set, so a services entity had to declare PRODUCTION. Kestrel's
    temporary-staff account reaches cost of sales from three functions and says so.
    """
    _src, req = mapping.SourceMap().resolve("KESTREL", "510300")
    accepted = req["cost_center_function"]
    assert not isinstance(accepted, str), "the requirement collapsed back to a single value"
    assert set(accepted) == {"PRODUCTION", "FIELD", "PROJECT"}


def test_the_support_departments_are_not_labelled_as_delivery():
    """
    D210 and D215 support field operations, they do not deliver them. The department
    master calls both INDIRECT and the approved Aurora split groups them with the other
    indirect-operations departments rather than with the billable crews.
    """
    assert DEPT_FUNCTION["D210"] == "INDIRECT_OPS"
    assert DEPT_FUNCTION["D215"] == "INDIRECT_OPS"
    assert DEPT_FUNCTION["D200"] == "FIELD" and DEPT_FUNCTION["D205"] == "FIELD"
    indirect = set(ACCOUNT_DEPTS["520100"])
    assert {"D210", "D215"} <= indirect
    assert not ({"D210", "D215"} & set(ACCOUNT_DEPTS["515200"]))


def test_every_department_a_conditional_account_may_use_exists_somewhere():
    """A requirement no entity can satisfy is a split that should not have been written."""
    applies: dict[str, set[str]] = {}
    for row in csv.DictReader(open(CONFIG / "dimensions" / "department.csv",
                                   newline="", encoding="utf-8")):
        applies[row["department_code"]] = set(row["applies_to_bu"].split(";"))
    for account, depts in ACCOUNT_DEPTS.items():
        for d in depts:
            assert d in applies, f"{account} names department {d}, which does not exist"
            assert applies[d], f"{d} applies to no business unit"


@needs_warehouse
def test_no_posting_declares_one_classification_and_sits_in_another(con):
    contradictions = one(con, """
        SELECT count(*) FROM fact_journal_line
        WHERE dimension_dept_function IS NOT NULL
          AND dept_function IS DISTINCT FROM dimension_dept_function""")
    assert contradictions == 0


# =====================================================================================
# P2-D-03  an intercompany balance says who it is with
# =====================================================================================
def test_every_intercompany_balance_account_is_settled_by_counterparty():
    text = (ROOT / "src" / "generation" / "journals.py").read_text(encoding="utf-8")
    assert "IC_BALANCE_ACCOUNTS" in text
    for account in ("120500", "210500", "125100", "225100", "175100", "235100", "178100"):
        assert account in journals.IC_BALANCE_ACCOUNTS, \
            f"{account} is an intercompany balance and is not settled by counterparty"
    body = text.split("stage 3a")[1].split("stage 3:")[0]
    assert "partner=prt" in body, "the settlement posting does not name the counterparty"


def test_a_partnerless_residual_on_an_intercompany_account_is_an_error():
    """
    The generator refuses to clear an intercompany account with a plug that names nobody.
    Without this the decomposition could drift from the balance and nothing would say so.
    """
    text = (ROOT / "src" / "generation" / "journals.py").read_text(encoding="utf-8")
    assert "left \"\n                        f\"unattributed on intercompany account" in text \
        or "unattributed on intercompany account" in text


@needs_warehouse
def test_no_intercompany_posting_lacks_a_counterparty(con):
    missing = one(con, """
        SELECT count(*) FROM fact_journal_line
        WHERE is_intercompany
          AND (partner_entity_code IS NULL OR partner_entity_code = '')
          AND source_event_type IS DISTINCT FROM 'YEAR_END_CLOSE'
          AND special_period_type IS DISTINCT FROM 'STATUTORY_CLOSE'""")
    # The close is the one legitimate exception: it sweeps the whole income statement into
    # retained earnings in a single entry, so its lines are a position and not a
    # transaction with any one counterparty. Kestrel books the same thing in period 13.
    assert missing == 0


@needs_warehouse
def test_no_posting_names_itself_as_its_own_counterparty(con):
    assert one(con, """
        SELECT count(*) FROM fact_journal_line
        WHERE partner_entity_code = entity_code""") == 0


@needs_warehouse
def test_the_whole_intercompany_position_is_attributable_to_a_pair(con):
    """
    The measure that mattered for Phase 4: at FY2025 only 37% of the intercompany
    receivable and payable position could be attributed to an entity pair. It is all of it.
    """
    attributable, total = con.execute("""
        SELECT
            round(sum(abs(signed_local_amount))
                  FILTER (WHERE partner_entity_code IS NOT NULL), 2),
            round(sum(abs(signed_local_amount)), 2)
        FROM fact_journal_line
        WHERE group_account IN ('120500', '210500', '125100', '225100',
                                '175100', '235100', '178100')
          AND source_event_type IS DISTINCT FROM 'YEAR_END_CLOSE'""").fetchone()
    assert total > 0
    assert attributable == total, f"{total - attributable:,.2f} local is not attributable"


@needs_warehouse
def test_an_entity_carries_no_balance_with_a_company_that_is_not_yet_in_the_group(con):
    """
    A pair has no balance before both sides exist. The flow matrix used to be settled a
    year at a time, so a company acquired in April carried balances from January -- one
    side of a pair the other side could not have.
    """
    early = one(con, """
        SELECT count(*) FROM fact_journal_line f
        JOIN dim_entity p ON p.entity_code = f.partner_entity_code
        WHERE f.partner_entity_code IS NOT NULL
          AND f.posting_date < date_trunc('month', p.effective_from)""")
    assert early == 0, f"{early} postings name a counterparty that was not yet in the group"


# =====================================================================================
# P2-D-04  a post-close adjustment stays inside one anchored caption
# =====================================================================================
def test_no_special_period_adjustment_crosses_an_anchored_caption():
    """
    Every leg of every special-period entry moves between two accounts that share a
    financial statement caption. Crossing one changes an anchored subtotal after the year
    is closed, which is the whole thing these entries are documented not to do.
    """
    # The level that is anchored differs by statement, so the test has to follow it. The
    # balance sheet anchors are stated per caption -- income taxes payable and accrued
    # liabilities are separate figures -- so the second level is what must not be crossed.
    # The income statement anchors are stated per block: total tax is anchored, current
    # tax and other tax within it are not, so the first level is the binding one.
    coa = {row["group_account"]: row
           for row in csv.DictReader(open(CONFIG / "coa" / "group_coa.csv",
                                          newline="", encoding="utf-8"))}

    def anchored(account: str) -> tuple[str, str]:
        row = coa[account]
        level = "fs_caption_l2" if row["statement"] == "BS" else "fs_caption_l1"
        return row["statement"], row[level]

    for special, (_event, label, legs) in journals.SPECIAL_PERIOD_ADJUSTMENTS.items():
        for dr, cr, _share in legs:
            assert anchored(dr) == anchored(cr), (
                f"special period {special} ({label}) moves {dr} to {cr}, which crosses "
                f"{anchored(dr)} to {anchored(cr)}")


def test_the_tax_true_up_has_no_balance_sheet_leg():
    """
    Both German taxes are income taxes payable at group level, so a reallocation between
    them changes the charge and not the payable. The leg that used to sit here moved the
    corporation tax payable into the VAT account.
    """
    _event, _label, legs = journals.SPECIAL_PERIOD_ADJUSTMENTS[15]
    assert all(dr.startswith("8") and cr.startswith("8") for dr, cr, _ in legs)


@needs_warehouse
def test_special_periods_still_reach_the_ledger(con):
    """The corrections must not have quietly emptied the special periods."""
    by_type = dict(con.execute("""
        SELECT special_period_type, count(*) FROM fact_journal_line
        WHERE special_period_type IS NOT NULL GROUP BY 1""").fetchall())
    assert set(by_type) == {"STATUTORY_CLOSE", "AUDIT_ADJUSTMENT",
                            "TAX_ADJUSTMENT", "GROUP_REPORTING_ADJUSTMENT"}
    assert all(v > 0 for v in by_type.values())


# =====================================================================================
# the register itself
# =====================================================================================
def test_every_source_exception_is_closed_and_says_how():
    rows = list(csv.DictReader(open(CONFIG / "controls" / "source_exception_register.csv",
                                    newline="", encoding="utf-8")))
    assert rows
    for row in rows:
        assert row["status"] == "CLOSED", f"{row['exception_id']} is still open"
        assert int(row["accepted_population"]) == 0, \
            f"{row['exception_id']} is closed but still accepts a population"
        assert row["closed_in_phase"], f"{row['exception_id']} does not say when it closed"
        assert row["correction"], f"{row['exception_id']} does not say what fixed it"
        assert re.fullmatch(r"P2-D-\d{2}", row["defect_reference"])


def test_a_recurrence_of_a_closed_defect_fails_rather_than_passing():
    """
    A closed exception is not a deleted one. If the defect comes back the control fails,
    because the register still names it and the accepted population is nil.
    """
    from src.pipeline import controls
    exceptions = controls.load_exceptions()
    cid = next(iter(exceptions))
    for measured, expected in ((0, "PASS"), (1, "FAIL"), (5248, "FAIL")):
        r = controls.Result()
        controls.registered(r, exceptions, cid, "t", "BLOCKING", measured, "lines", "d")
        assert r[-1]["status"] == expected, f"{measured} should be {expected}"
