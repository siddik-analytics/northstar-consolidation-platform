"""
The ownership tree, walked rather than assumed.

Twelve legal entities are not twelve direct subsidiaries of the parent. Four are held through
another operating company -- Meridian Canada through Meridian US, Cascade Canada through
Cascade US, Vector Systems through Vector Engineered Systems, Parts UK through Aftermarket --
and one of those, Parts UK, is 80% owned. Treating the register as a flat list of subsidiaries
gets the investment elimination wrong in a way that still balances, because the investment and
the equity it eliminates against are both real balances; only the *pairing* is wrong.

This module resolves, for every entity and every month:

    the direct parent and the ownership percentage of that link
    the full path back to the ultimate parent
    the EFFECTIVE group ownership, being the product of the percentages along that path
    whether the entity is consolidated at all in that month

and proves the things that would otherwise be assumed: no cycles, exactly one path, effective
dates that do not overlap, and a register that agrees with the investments actually held.
"""

from __future__ import annotations

import duckdb

ULTIMATE_PARENT = "NIG-100"


def build(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Resolve the ownership tree per entity-month and expose it as a dimension."""
    con.execute(f"""
    CREATE OR REPLACE TABLE dim_ownership_period AS
    WITH RECURSIVE periods AS (
        SELECT DISTINCT period_key, fiscal_year FROM dim_date WHERE accounting_period <= 12
    ),
    link AS (
        -- the ownership link effective for each entity in each month
        SELECT p.period_key, p.fiscal_year, o.entity_code, o.parent_entity_code,
               o.group_ownership_pct AS direct_pct, o.nci_pct AS direct_nci_pct,
               o.consolidation_method, o.effective_from, o.effective_to, o.nci_holder
        FROM periods p
        JOIN ref_ownership o
          ON o.effective_from <= make_date(p.period_key // 100, p.period_key % 100, 1)
                                 + INTERVAL 1 MONTH - INTERVAL 1 DAY
         AND (o.effective_to IS NULL
              OR o.effective_to >= make_date(p.period_key // 100, p.period_key % 100, 1))
    ),
    -- walk to the ultimate parent, multiplying the percentages on the way
    walk AS (
        SELECT period_key, fiscal_year, entity_code, parent_entity_code,
               direct_pct, direct_nci_pct, consolidation_method, nci_holder,
               direct_pct AS effective_pct,
               entity_code || ' <- ' || parent_entity_code AS ownership_path,
               1 AS tier
        FROM link
        UNION ALL
        SELECT w.period_key, w.fiscal_year, w.entity_code, l.parent_entity_code,
               w.direct_pct, w.direct_nci_pct, w.consolidation_method, w.nci_holder,
               w.effective_pct * l.direct_pct,
               w.ownership_path || ' <- ' || l.parent_entity_code,
               w.tier + 1
        FROM walk w
        JOIN link l ON l.entity_code = w.parent_entity_code AND l.period_key = w.period_key
        WHERE w.parent_entity_code <> '{ULTIMATE_PARENT}' AND w.tier < 10
    ),
    resolved AS (
        SELECT period_key, fiscal_year, entity_code,
               any_value(direct_pct) AS direct_ownership_pct,
               any_value(direct_nci_pct) AS direct_nci_pct,
               any_value(consolidation_method) AS consolidation_method,
               any_value(nci_holder) AS nci_holder,
               max(tier) AS tiers_to_parent,
               -- the row that reached the ultimate parent carries the effective percentage
               max(CASE WHEN parent_entity_code = '{ULTIMATE_PARENT}'
                        THEN effective_pct END) AS effective_ownership_pct,
               max(CASE WHEN parent_entity_code = '{ULTIMATE_PARENT}'
                        THEN ownership_path END) AS ownership_path
        FROM walk GROUP BY ALL
    )
    SELECT r.period_key, r.fiscal_year, r.entity_code,
           l.parent_entity_code AS direct_parent_entity_code,
           '{ULTIMATE_PARENT}' AS ultimate_parent_entity_code,
           r.direct_ownership_pct, r.effective_ownership_pct,
           round(1.0 - r.effective_ownership_pct, 6) AS effective_nci_pct,
           r.direct_nci_pct, r.consolidation_method, r.nci_holder,
           r.tiers_to_parent, r.ownership_path,
           e.effective_from AS consolidation_effective_from,
           e.effective_to AS consolidation_effective_to,
           e.functional_currency, e.bu_code
    FROM resolved r
    JOIN link l ON l.entity_code = r.entity_code AND l.period_key = r.period_key
    JOIN dim_entity e ON e.entity_code = r.entity_code
    WHERE e.effective_from <= make_date(r.period_key // 100, r.period_key % 100, 1)
                              + INTERVAL 1 MONTH - INTERVAL 1 DAY
      AND (e.effective_to IS NULL
           OR e.effective_to >= make_date(r.period_key // 100, r.period_key % 100, 1))
    ORDER BY period_key, entity_code
    """)

    # The parent is consolidated too: it has no ownership link of its own, and leaving it out
    # of the dimension would quietly drop every Topco balance from the consolidation.
    con.execute(f"""
    INSERT INTO dim_ownership_period
    SELECT p.period_key, p.fiscal_year, '{ULTIMATE_PARENT}', NULL, '{ULTIMATE_PARENT}',
           1.0, 1.0, 0.0, 0.0, 'PARENT', NULL, 0, '{ULTIMATE_PARENT}',
           e.effective_from, e.effective_to, e.functional_currency, e.bu_code
    FROM (SELECT DISTINCT period_key, fiscal_year FROM dim_date WHERE accounting_period <= 12) p
    CROSS JOIN (SELECT * FROM dim_entity WHERE entity_code = '{ULTIMATE_PARENT}') e
    """)

    return {"dim_ownership_period": con.execute(
        "SELECT count(*) FROM dim_ownership_period").fetchone()[0]}


def cycles(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Any entity that appears in its own ownership path is a cycle."""
    return con.execute("""
        SELECT DISTINCT entity_code, ownership_path FROM dim_ownership_period
        WHERE ownership_path IS NOT NULL
          AND len(string_split(ownership_path, ' <- '))
              <> len(list_distinct(string_split(ownership_path, ' <- ')))
    """).fetchall()


def missing_path(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """An entity-month with no resolved path back to the ultimate parent."""
    return con.execute("""
        SELECT entity_code, min(period_key), max(period_key), count(*)
        FROM dim_ownership_period
        WHERE ownership_path IS NULL OR effective_ownership_pct IS NULL
        GROUP BY 1
    """).fetchall()


def overlapping_effective_dates(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """
    Two ownership rows for one entity whose effective windows overlap.

    An overlap makes the percentage for a month ambiguous, and the engine would silently pick
    one -- so the same period could consolidate differently on a different day.
    """
    return con.execute("""
        SELECT a.entity_code, a.effective_from, a.effective_to,
               b.effective_from, b.effective_to
        FROM ref_ownership a JOIN ref_ownership b
          ON a.entity_code = b.entity_code AND a.effective_from < b.effective_from
        WHERE coalesce(a.effective_to, DATE '9999-12-31') >= b.effective_from
    """).fetchall()


def register_disagreement(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """
    Ownership links the investment register does not support, and investments the ownership
    register does not recognise. Either one means a subsidiary is being consolidated on a
    relationship nobody paid for, or an investment is held in something not consolidated.
    """
    return con.execute("""
        SELECT coalesce(o.entity_code, i.subsidiary_entity) AS subsidiary,
               o.parent_entity_code AS ownership_parent,
               i.parent_entity AS register_parent
        FROM (SELECT DISTINCT entity_code, parent_entity_code FROM ref_ownership) o
        FULL OUTER JOIN (SELECT DISTINCT subsidiary_entity, parent_entity
                         FROM ref_investment_register) i
          ON i.subsidiary_entity = o.entity_code
        WHERE o.entity_code IS NULL OR i.subsidiary_entity IS NULL
           OR o.parent_entity_code IS DISTINCT FROM i.parent_entity
    """).fetchall()


def invalid_percentages(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """A percentage outside (0, 1], or one whose NCI complement does not add back to 1."""
    return con.execute("""
        SELECT entity_code, effective_from, group_ownership_pct, nci_pct
        FROM ref_ownership
        WHERE group_ownership_pct <= 0 OR group_ownership_pct > 1
           OR nci_pct < 0 OR nci_pct >= 1
           OR abs(group_ownership_pct + nci_pct - 1.0) > 1e-9
    """).fetchall()
