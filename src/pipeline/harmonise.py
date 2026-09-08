"""
standardised -> mapped: the chart-of-accounts harmonisation engine.

Three chart-of-accounts problems have to be solved at once, and none of them is a lookup:

    a source account may map straight through                          (DIRECT)
    several source accounts may collapse into one group account        (MERGE)
    one source account may map to different group accounts depending
    on the characteristics of the individual posting                   (SPLIT)
    a source account may need a presentation reclassification because
    the local ledger reports on a different basis entirely             (DERIVED)

The account-level mapping comes from the approved source charts.  The conditional logic
comes from `config/mapping/mapping_rules.csv` and is evaluated by `rules.py`.  Neither is
in code, and neither is copied from the expected-mapping manifest -- that file is the
acceptance oracle and this engine never reads it.

Nothing is defaulted silently.  Every line leaves this stage with exactly one status from
`config.MAPPING_STATUS`, and every line whose status is blocking is written to an exception
file with the attributes it carried, the rules that were candidates and the reason none of
them resolved it.
"""

from __future__ import annotations

import duckdb

from .config import EXCEPTIONS, LAYER_DIR, writing_artefacts
from .rules import Rule, load_rules, match_case_sql


def _rules_relation(rules: list[Rule]) -> str:
    rows = ",\n            ".join(
        "(" + ", ".join([
            f"'{r.rule_id}'", f"'{r.erp_system}'", f"'{r.source_account}'",
            str(r.priority), f"'{r.target_group_account}'", f"'{r.rule_class}'",
            f"DATE '{r.effective_from}'",
            f"DATE '{r.effective_to}'" if r.effective_to else "CAST(NULL AS DATE)",
            "TRUE" if r.is_active else "FALSE",
        ]) + ")"
        for r in rules)
    return f"""
        SELECT * FROM (VALUES
            {rows}
        ) AS t(rule_id, erp_system, source_account, priority, target_group_account,
               rule_class, effective_from, effective_to, is_active)
    """


def build(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Apply the mapping engine. Returns row counts by mapping status."""
    rules = load_rules()
    con.execute(f"CREATE OR REPLACE TABLE map_rules AS {_rules_relation(rules)}")

    # ---------------------------------------------------------------- rule hits
    # Each line joins only to the rules of its own source account, so the whole ledger is
    # evaluated in one pass rather than once per rule.
    con.execute(f"""
    CREATE OR REPLACE TABLE map_rule_hits AS
    SELECT l.line_uid, r.rule_id, r.priority, r.target_group_account, r.rule_class
    FROM stg_standardised l
    JOIN map_rules r
      ON r.erp_system = l.erp_system
     AND r.source_account = l.source_account
     AND r.is_active
     AND l.posting_date >= r.effective_from
     AND (r.effective_to IS NULL OR l.posting_date <= r.effective_to)
    WHERE {match_case_sql(rules)}
    """)

    con.execute("""
    CREATE OR REPLACE TABLE map_resolution AS
    SELECT
        line_uid,
        count(*) FILTER (WHERE rule_class = 'SPLIT_BRANCH')  AS branch_hits,
        count(*) FILTER (WHERE rule_class = 'SPLIT_DEFAULT') AS default_hits,
        count(*) FILTER (WHERE rule_class = 'DERIVED')       AS derived_hits,
        arg_min(rule_id, priority)               AS winning_rule_id,
        arg_min(target_group_account, priority)  AS winning_group_account,
        arg_min(rule_class, priority)            AS winning_rule_class,
        list(rule_id ORDER BY priority, rule_id) AS candidate_rule_ids
    FROM map_rule_hits
    GROUP BY line_uid
    """)

    # ------------------------------------------------------------------- mapped
    con.execute("""
    CREATE OR REPLACE TABLE stg_mapped AS
    SELECT
        l.*,
        res.winning_rule_id  AS mapping_rule_id,
        res.candidate_rule_ids,
        coalesce(res.branch_hits, 0)  AS matched_branch_count,
        -- The group account. A rule wins where one fired; otherwise the account-level
        -- mapping from the approved source chart applies.
        CASE
            WHEN sa.source_account IS NULL                       THEN NULL
            WHEN res.branch_hits > 1                             THEN NULL
            WHEN res.winning_group_account IS NOT NULL           THEN res.winning_group_account
            WHEN sa.mapping_type IN ('SPLIT', 'DERIVED')         THEN NULL
            ELSE sa.default_group_account
        END AS group_account,
        CASE
            WHEN sa.source_account IS NULL                       THEN 'UNMAPPED_ACCOUNT'
            WHEN l.posting_date < sa.effective_from
              OR (sa.effective_to IS NOT NULL AND l.posting_date > sa.effective_to)
                                                                 THEN 'OUT_OF_EFFECT'
            WHEN l.entity_code IS NULL OR l.cost_center_code IS NULL
                                                                 THEN 'INVALID_DIMENSION'
            WHEN res.branch_hits > 1                             THEN 'AMBIGUOUS'
            WHEN res.winning_rule_class = 'DERIVED'              THEN 'MAPPED_DERIVED'
            WHEN res.winning_rule_class = 'SPLIT_BRANCH'         THEN 'MAPPED_SPLIT'
            WHEN res.winning_rule_class = 'SPLIT_DEFAULT'        THEN 'MAPPED_SPLIT_DEFAULT'
            WHEN sa.mapping_type IN ('SPLIT', 'DERIVED')         THEN 'UNMAPPED_NO_RULE'
            WHEN sa.mapping_type = 'MERGE'                       THEN 'MAPPED_MERGE'
            ELSE 'MAPPED_DIRECT'
        END AS mapping_status,
        sa.mapping_type AS chart_mapping_type_applied,
        -- A presentation reclassification changes the caption an amount is reported
        -- under, never the amount itself. Flagged so it stays visible downstream.
        res.winning_rule_class = 'DERIVED' AS is_presentation_reclass,
        CASE WHEN res.winning_rule_class = 'DERIVED'
             THEN 'GKV_TO_UKV' END AS presentation_reclass_type
    FROM stg_standardised l
    LEFT JOIN map_resolution res USING (line_uid)
    LEFT JOIN dim_source_account sa
           ON sa.erp_system = l.erp_system AND sa.source_account = l.source_account
    """)

    # Account metadata comes from the group chart and from nowhere else, so a caption or
    # an EBITDA flag cannot be restated in three places and disagree in two of them.
    con.execute("""
    CREATE OR REPLACE TABLE stg_mapped_enriched AS
    SELECT m.*,
           a.account_name AS group_account_name,
           a.statement, a.fs_caption_l1, a.fs_caption_l2, a.account_class,
           a.normal_balance AS group_normal_balance, a.normal_sign AS group_normal_sign,
           a.fx_method, a.cash_flow_category, a.reporting_block,
           a.is_intercompany, a.is_ebitda, a.is_ebitda_addback, a.is_statistical,
           a.include_in_tb_balance
    FROM stg_mapped m
    LEFT JOIN dim_account a ON a.group_account = m.group_account
    """)

    if writing_artefacts():
        out = LAYER_DIR["mapped"] / "stg_mapped.parquet"
        con.execute(
            f"COPY (SELECT * FROM stg_mapped_enriched ORDER BY erp_system, source_file, "
            f"source_row_ordinal) TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    write_exceptions(con)
    return dict(con.execute(
        "SELECT mapping_status, count(*) FROM stg_mapped_enriched "
        "GROUP BY 1 ORDER BY 1").fetchall())


def write_exceptions(con: duckdb.DuckDBPyConnection) -> int:
    """
    The investigation file.

    A mapping exception report that says only "unmapped" is useless. This one carries what
    a finance transformation team would actually need to resolve the line: the system, the
    entity, the account and its name, the attributes the line presented, which rules were
    candidates, why none of them resolved it, and how much money is affected.
    """
    con.execute("""
    CREATE OR REPLACE TABLE map_exceptions AS
    SELECT
        mapping_status,
        erp_system, entity_code, source_account, source_account_name,
        chart_mapping_type_applied AS mapping_type,
        fiscal_year, accounting_period, count(*) AS line_count,
        round(sum(abs(signed_local_amount)), 2) AS absolute_amount_local,
        source_currency,
        -- min(), not any_value(): an exception file that names a different example
        -- line on every run cannot be diffed, and the build would not be reproducible.
        min(source_file) AS example_source_file,
        min(journal_id) AS example_journal_id,
        min(source_line_attributes) AS example_line_attributes,
        min(dept_code) AS example_dept_code,
        min(cost_center_code) AS example_cost_centre,
        min(dept_function) AS example_dept_function,
        list_sort(list_distinct(flatten(list(candidate_rule_ids)))) AS candidate_rules,
        CASE mapping_status
            WHEN 'UNMAPPED_ACCOUNT' THEN
                'The source account is not in this ERP''s approved chart. Add a mapping '
                || 'row with an effective date, or reject the extract.'
            WHEN 'UNMAPPED_NO_RULE' THEN
                'The account maps conditionally but no rule branch matched and no default '
                || 'branch exists. The rule set is incomplete for the attributes this line carries.'
            WHEN 'AMBIGUOUS' THEN
                'More than one non-default rule branch matched. The branches are not '
                || 'mutually exclusive for the attributes this line carries.'
            WHEN 'INVALID_DIMENSION' THEN
                'The entity or cost centre on the line does not resolve to a conformed '
                || 'dimension member.'
            WHEN 'OUT_OF_EFFECT' THEN
                'No mapping row is effective at the posting date.'
        END AS resolution_guidance
    FROM stg_mapped_enriched
    WHERE mapping_status IN ('UNMAPPED_ACCOUNT', 'UNMAPPED_NO_RULE', 'AMBIGUOUS',
                             'INVALID_DIMENSION', 'OUT_OF_EFFECT')
    GROUP BY ALL
    ORDER BY mapping_status, absolute_amount_local DESC
    """)
    if writing_artefacts():
        path = EXCEPTIONS / "mapping_exceptions.csv"
        con.execute(f"COPY (SELECT * FROM map_exceptions ORDER BY ALL) "
                    f"TO '{path.as_posix()}' (FORMAT CSV, HEADER, DELIMITER ',')")
    return con.execute("SELECT count(*) FROM map_exceptions").fetchone()[0]
