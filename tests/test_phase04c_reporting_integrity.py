"""
Phase 4C - the reporting layer, and the two defects that lived in it.

Both defects the Phase 4B documentation pass found were **reporting** errors sitting on top of
correct accounting: the balance sheet split equity between two captions wrongly while total
equity stayed exactly right, and the EBITDA bridge summed a fiscal year including the year-end
close while the income statement summed it correctly. Every one of the 61 accounting controls
passed throughout, because nothing was out of balance and nothing compared one artefact with
another.

These tests hold the corrections and the rule that came out of them:

    a component with no population contributes ZERO, never NULL
    two artefacts expressing one measure reconcile to the authoritative fact
"""

from __future__ import annotations

import csv
import pathlib
import re
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.consol.config import CONFIG, CONTROL_RESULTS, DUCKDB_PATH, FAULT_RESULTS, TOL_XAR_USD

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
# P4-D-01  the period result in equity
# =====================================================================================
def test_the_result_caption_is_the_fiscal_year_to_date(con):
    """
    The caption means one thing in every month: the fiscal year to date on the income
    statement's own basis. It previously meant the cumulative income statement INCLUDING the
    close, which is complete for layer 1 and not for the group -- no entity ledger closes a
    consolidation adjustment, so three years of them accumulated in it.
    """
    worst = con.execute("""
        WITH ytd AS (
            SELECT period_key,
                   sum(coalesce(sum(amount_usd) FILTER (WHERE counts_in_result), 0))
                       OVER (PARTITION BY fiscal_year ORDER BY period_key
                             ROWS UNBOUNDED PRECEDING) AS ytd_usd
            FROM vw_statutory_fact WHERE statement = 'IS' GROUP BY period_key, fiscal_year
        )
        SELECT max(abs(b.balance_usd - y.ytd_usd)) FROM rpt_balance_sheet b
        JOIN ytd y USING (period_key) WHERE b.fs_caption_l2 = 'Result for the period'
    """).fetchone()[0]
    assert float(worst) <= TOL_XAR_USD


def test_the_result_caption_agrees_with_the_income_statement_at_every_year_end(con):
    breaks = con.execute("""
        SELECT i.fiscal_year, sum(i.net_income_parent_usd), b.balance_usd
        FROM rpt_income_statement i
        JOIN rpt_balance_sheet b
          ON b.period_key = i.fiscal_year * 100 + 12
         AND b.fs_caption_l2 = 'Result for the period'
        GROUP BY i.fiscal_year, b.balance_usd
        HAVING abs(sum(i.net_income_parent_usd) + b.balance_usd) > 0.05
    """).fetchall()
    assert breaks == []


def test_moving_the_split_never_changes_total_earnings(con):
    """
    The split between retained earnings and the period result is a presentation decision. The
    total is not, and no presentation choice may create or destroy a dollar of it.
    """
    worst = con.execute("""
        WITH cum AS (
            SELECT d.period_key,
                   coalesce(sum(f.amount_usd) FILTER (
                       WHERE f.group_account IN ('320100', '320200', '320300')
                          OR f.statement = 'IS'), 0) AS earnings_usd
            FROM (SELECT DISTINCT period_key FROM rpt_balance_sheet) d
            JOIN vw_statutory_fact f ON f.period_key <= d.period_key GROUP BY 1
        ),
        artefact AS (
            SELECT period_key, sum(balance_usd) AS earnings_usd FROM rpt_balance_sheet
            WHERE fs_caption_l2 IN ('Retained earnings', 'Result for the period') GROUP BY 1
        )
        SELECT max(abs(a.earnings_usd - c.earnings_usd))
        FROM artefact a JOIN cum c USING (period_key)
    """).fetchone()[0]
    assert float(worst) <= TOL_XAR_USD


def test_the_balance_sheet_still_balances_at_the_cent(con):
    worst = con.execute("""
        SELECT max(abs(b)) FROM (SELECT period_key, sum(balance_usd) AS b
                                 FROM rpt_balance_sheet GROUP BY 1)
    """).fetchone()[0]
    assert float(worst) <= 0.01


# =====================================================================================
# P4-D-02  the EBITDA bridge
# =====================================================================================
def test_the_bridge_and_the_income_statement_agree_about_ebitda(con):
    breaks = con.execute("""
        SELECT b.fiscal_year, b.statutory_ebitda_usd, sum(i.ebitda_usd)
        FROM rpt_ebitda_bridge b JOIN rpt_income_statement i USING (fiscal_year)
        GROUP BY b.fiscal_year, b.statutory_ebitda_usd
        HAVING abs(b.statutory_ebitda_usd - sum(i.ebitda_usd)) > 0.05
    """).fetchall()
    assert breaks == []


def test_the_bridge_and_the_income_statement_agree_about_adjusted_ebitda(con):
    """Layer 4 is added rather than assumed nil, so this holds once an adjustment is approved."""
    breaks = con.execute("""
        SELECT b.fiscal_year
        FROM rpt_ebitda_bridge b JOIN rpt_income_statement i USING (fiscal_year)
        GROUP BY b.fiscal_year, b.adjusted_ebitda_usd, b.management_layer4_effect_usd
        HAVING abs(b.adjusted_ebitda_usd - sum(i.adjusted_ebitda_usd)
                   - b.management_layer4_effect_usd) > 0.05
    """).fetchall()
    assert breaks == []


def test_covenant_ebitda_is_never_null(con):
    """
    A NULL covenant metric is not a small number, it is no number at all -- and this one is
    what a lender tests leverage on.
    """
    nulls = con.execute("""
        SELECT count(*) FROM rpt_ebitda_bridge
        WHERE covenant_ebitda_usd IS NULL OR covenant_fx_addback_usd IS NULL
           OR sponsor_fee_cap_effect_usd IS NULL OR statutory_ebitda_usd IS NULL
           OR adjusted_ebitda_usd IS NULL OR approved_addbacks_usd IS NULL
           OR management_layer4_effect_usd IS NULL
    """).fetchone()[0]
    assert nulls == 0


def test_the_sponsor_fee_cap_is_applied_rather_than_assumed_away(con):
    """
    The fee runs below the USD 1.5m cap in this window, so the effect is nil -- but the cap is
    computed from the agreement's own term rather than skipped, because it would bite at a
    higher fee and the calculation must not need editing when it does.
    """
    cap = con.execute(
        "SELECT CAST(value AS DOUBLE) * 1e6 FROM ref_covenant_term WHERE term_id = 'CA-027'"
    ).fetchone()[0]
    assert cap > 0
    breaks = con.execute(f"""
        SELECT fiscal_year FROM rpt_ebitda_bridge b
        WHERE abs(b.sponsor_fee_cap_effect_usd
                  - least((SELECT coalesce(sum(v.amount_usd), 0) FROM vw_statutory_fact v
                           WHERE v.group_account = '630400' AND v.counts_in_result
                             AND v.fiscal_year = b.fiscal_year), {cap})
                  + (SELECT coalesce(sum(v.amount_usd), 0) FROM vw_statutory_fact v
                     WHERE v.group_account = '630400' AND v.counts_in_result
                       AND v.fiscal_year = b.fiscal_year)) > 0.05
    """).fetchall()
    assert breaks == []


# =====================================================================================
# the NULL / empty-population policy
# =====================================================================================
def test_an_empty_adjustment_population_contributes_zero(con):
    """
    Accounts 740100 and 740200 are never posted to, so the CA-030 covenant add-back has no
    population at all. That is a real zero, and it must be presented as one.
    """
    posted = con.execute("""
        SELECT count(*) FROM vw_statutory_fact WHERE group_account IN ('740100', '740200')
    """).fetchone()[0]
    assert posted == 0, "the fixture assumption has changed; this test needs revisiting"
    addbacks = [r[0] for r in con.execute(
        "SELECT covenant_fx_addback_usd FROM rpt_ebitda_bridge ORDER BY fiscal_year").fetchall()]
    assert all(v is not None and float(v) == 0.0 for v in addbacks)


def test_no_additive_filter_aggregate_is_left_un_coalesced():
    """
    A `FILTER` that matches nothing yields NULL, and one NULL anywhere in a sum or a
    subtraction voids the whole line. It has now cost this project three separate defects:
    gross profit and net income in the income statement, Covenant EBITDA in the bridge, and
    the entity that had cost and no revenue removing its own gross profit from the group.
    NULL means unknown. A component with no population is not unknown -- it is zero.
    """
    pattern = re.compile(
        r"(coalesce\(\s*)?(sum|avg|min|max)\s*\([^()]*(?:\([^()]*\)[^()]*)*\)\s*FILTER", re.S)
    offenders = []
    for path in sorted((ROOT / "src" / "consol").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            if match.group(1) is None:
                offenders.append(f"{path.name}:{text[:match.start()].count(chr(10)) + 1}")
    assert offenders == [], offenders


# =====================================================================================
# the cross-artefact control family
# =====================================================================================
def test_every_cross_artefact_control_passes():
    xar = [r for r in rows(CONTROL_RESULTS) if r["control_id"].startswith("P4-XAR")]
    assert len(xar) >= 11
    assert [r["control_id"] for r in xar if r["status"] != "PASS"] == []


def test_every_cross_artefact_control_blocks():
    """
    A reporting difference in a primary statement or a lender-facing measure is not an
    informational warning.
    """
    xar = [r for r in rows(CONTROL_RESULTS) if r["control_id"].startswith("P4-XAR")]
    assert [r["control_id"] for r in xar if r["severity"] != "BLOCKING"] == []


def test_the_control_register_documents_every_cross_artefact_control():
    register = {r["control_id"] for r in
                rows(CONFIG / "controls" / "phase04_control_register.csv")}
    built = {r["control_id"] for r in rows(CONTROL_RESULTS)}
    assert register == built, register ^ built


def test_every_cross_artefact_fixture_is_caught_by_its_own_family():
    fixtures = [r for r in rows(FAULT_RESULTS) if r["fault_id"].startswith("F4-XAR")]
    assert len(fixtures) == 4
    for row in fixtures:
        assert row["status"] == "DETECTED", (row["fault_id"], row["status"])
        assert any(c.startswith("P4-XAR") for c in row["detected_by"].split(";")), row


def test_the_equity_presentation_fixture_breaks_nothing_else():
    """
    F4-XAR-01 moves USD 5m between two equity captions. Total equity is untouched, the balance
    sheet still balances, and every accounting control passes -- so if any control outside the
    cross-artefact family fires, it is firing for a reason it does not own.
    """
    row = next(r for r in rows(FAULT_RESULTS) if r["fault_id"] == "F4-XAR-01")
    assert row["other_controls_broken"] == ""
    assert row["detected_by"] == "P4-XAR-06"
