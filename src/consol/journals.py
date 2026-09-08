"""
The consolidation journal engine.

Phase 4 does not calculate consolidated totals. It writes **journals**, and the consolidated
result is what those journals plus the entity ledgers add up to. The difference matters when
somebody asks why group equity moved: a total can only be recomputed, a journal can be read.

Every consolidation entry lands in one table, `fact_consol_journal`, at one row per leg:

    consol_journal_id   deterministic, derived from the business keys of the entry
    line_number         1..n within the entry
    layer_id            2, 3, 4 or 5 -- layer 1 is the entity ledger and is never written here
    process             which engine wrote it (IC_ELIM, INVESTMENT, PPA, NCI, PUP, CTA, MGMT)
    rule_id             the specific rule or register row that produced it
    entity_code         the entity the leg is posted to
    related_entity_code the entity the entry is ABOUT, where that differs from where it posts
    partner_entity_code the counterparty, on an intercompany leg
    group_account       the account
    period_key          the month
    scenario / version  the scenario this entry belongs to
    amount_usd          debit-positive, USD
    amount_local        where the entry has a local-currency origin
    currency_code
    narrative           what it is, in words
    evidence            the source row, register id or document the entry rests on

Two properties are enforced rather than assumed:

**Journals balance.** Every entry in layers 2, 3 and 4 sums to zero in USD to the cent.
Layer 5 is the exception by design: it is the entry that makes the *translated* layer-1 trial
balance sum to zero, so it does not balance alone (CTL-IC-06, CTL-CON-07 cover 2-4;
CTL-TB-03 covers 1 and 5 together).

**Identifiers are derived, never allocated.** A journal id is a hash of the business keys of
the entry -- process, period, entities, account, rule. Two runs over the same data produce the
same ids, so a diff between two builds is a diff of the accounting and not of a counter.
"""

from __future__ import annotations

import hashlib

import duckdb

COLUMNS = [
    "consol_journal_id", "line_number", "layer_id", "process", "rule_id",
    "entity_code", "related_entity_code", "partner_entity_code", "group_account",
    "period_key", "fiscal_year", "scenario_code", "version_code",
    "currency_code", "amount_local", "amount_usd", "narrative", "evidence",
]

CREATE = f"""
CREATE OR REPLACE TABLE fact_consol_journal (
    consol_journal_id    VARCHAR,
    line_number          INTEGER,
    layer_id             INTEGER,
    process              VARCHAR,
    rule_id              VARCHAR,
    entity_code          VARCHAR,
    related_entity_code  VARCHAR,
    partner_entity_code  VARCHAR,
    group_account        VARCHAR,
    period_key           INTEGER,
    fiscal_year          INTEGER,
    scenario_code        VARCHAR,
    version_code         VARCHAR,
    currency_code        VARCHAR,
    amount_local         DECIMAL(18,2),
    amount_usd           DECIMAL(18,2),
    narrative            VARCHAR,
    evidence             VARCHAR
)
"""


def journal_id(process: str, *keys) -> str:
    """
    A journal identifier derived from what the entry is about, never from a counter.

    Two builds over the same data produce the same ids, so a diff between builds shows the
    accounting that changed rather than the order rows happened to be generated in. A
    clock-based or sequence-based id would make every rebuild look different and would make
    the determinism proof meaningless.
    """
    digest = hashlib.sha256("|".join(str(k) for k in keys).encode()).hexdigest()[:10]
    return f"{process}-{digest}"


def init(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(CREATE)


def post_sql(con: duckdb.DuckDBPyConnection, select_sql: str) -> int:
    """
    Append the rows a SELECT produces to the journal table.

    The engines build their entries in SQL over the whole population at once rather than row
    by row in Python: 1.1m source rows and tens of thousands of consolidation legs is not a
    size at which a per-row loop is defensible (§32).
    """
    before = con.execute("SELECT count(*) FROM fact_consol_journal").fetchone()[0]
    con.execute(f"INSERT INTO fact_consol_journal BY NAME ({select_sql})")
    after = con.execute("SELECT count(*) FROM fact_consol_journal").fetchone()[0]
    return after - before


def unbalanced(con: duckdb.DuckDBPyConnection, layers=(2, 3, 4)) -> list[tuple]:
    """Entries in the self-balancing layers whose legs do not sum to zero."""
    layer_list = ", ".join(str(x) for x in layers)
    return con.execute(f"""
        SELECT consol_journal_id, process, period_key,
               round(sum(amount_usd), 2) AS residual
        FROM fact_consol_journal
        WHERE layer_id IN ({layer_list})
        GROUP BY ALL
        HAVING abs(sum(amount_usd)) > 0.005
        ORDER BY abs(residual) DESC
    """).fetchall()


def counts_by_layer(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    rows = con.execute("""
        SELECT layer_id, process, count(*) AS legs,
               count(DISTINCT consol_journal_id) AS entries
        FROM fact_consol_journal GROUP BY ALL ORDER BY 1, 2
    """).fetchall()
    out: dict[str, int] = {}
    for layer_id, process, legs, entries in rows:
        out[f"L{layer_id}:{process}:entries"] = entries
        out[f"L{layer_id}:{process}:legs"] = legs
    return out
