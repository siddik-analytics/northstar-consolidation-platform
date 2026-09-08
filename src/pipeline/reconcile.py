"""
Source-to-group reconciliation, and the mapping acceptance test.

Two questions have to be answered before Phase 3 can be signed off, and they are different
questions:

**Did the mapping engine produce the right answer?**  Phase 2 recorded, for every generated
journal line, the group account a Phase 3 mapping is expected to produce.  That expectation
is an **oracle**: it is read here, in the acceptance test, and nowhere else.  The pipeline
never sees it -- `harmonise.py` derives the group account from the approved charts and the
rule configuration alone.  `test_the_manifest_is_an_oracle_and_never_an_input` in
`tests/test_phase03_pipeline.py` asserts that separation directly.

**Do the mapped numbers mean anything?**  A mapping can be wrong and still balance.  Move
production payroll from cost of sales to SG&A and every trial balance still sums to zero,
the statements still tie, and gross margin moves by three points.  So the mapped result is
reconciled to the approved anchors at the level where that error shows: revenue, cost of
sales, gross profit and gross margin **by business unit**.

Everything here is layer 1.  The USD figures are produced by applying the approved monthly
average rates for comparison only -- no balance sheet is translated at closing rates for
reporting, no cumulative translation adjustment is computed and nothing is posted.
"""

from __future__ import annotations

import duckdb

from .config import CONFIG, DATA, REFERENCE, writing_artefacts

ORACLE = CONFIG / "generation" / "expected_mapping_manifest.csv"
#: Phase 2's per-line record of the group account each posting should map to.  It is a
#: reference artefact of the frozen source layer and is used ONLY as an oracle.
ORACLE_LINES = REFERENCE / "journal_lines.parquet"

RECONCILIATION = DATA / "phase03_reconciliation.csv"
MAPPING_ACCEPTANCE = DATA / "phase03_mapping_acceptance.csv"

#: Approved tolerances, unchanged from Phase 2. They are not relaxed here.
TOL_PL = 0.005     # 0.5% on income statement aggregates
TOL_BS = 0.010     # 1.0% on balance sheet captions


def load_oracle(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
    CREATE OR REPLACE TABLE oracle_mapping_manifest AS
    SELECT erp_system, source_account, source_account_name, mapping_type,
           expected_group_account, requested_group_account,
           required_line_attributes,
           substituted_because_unavailable = 'TRUE' AS substituted_because_unavailable
    FROM read_csv('{ORACLE.as_posix()}', all_varchar=true, header=true)
    """)
    con.execute(f"""
    CREATE OR REPLACE TABLE oracle_expected_line AS
    SELECT entity_code, journal_id, CAST(line_number AS INTEGER) AS line_number,
           erp_system, source_account, expected_group_account, event_type
    FROM read_parquet('{ORACLE_LINES.as_posix()}')
    """)


def mapping_acceptance(con: duckdb.DuckDBPyConnection) -> dict:
    """
    Grade every mapped line against the oracle, and say why any line disagrees.

    A line is **classifiable at source** when its account maps unconditionally, or when the
    posting declares at least one of the attributes its account's rule set reads.  A line
    that is not classifiable at source carries nothing the engine could have used, so the
    split resolves to the account's declared default branch.  Both populations are reported:
    the first is the mapping engine's score, the second is a property of the source data.
    """
    from .rules import load_rules
    from .standardise import LINE_ATTRIBUTES
    import re

    referenced: dict[tuple[str, str], set[str]] = {}
    for rule in load_rules():
        for field in re.findall(r"[a-z_]+(?=\s*(?:=|<>|<=|>=|<|>|IN\b|IS\b))", rule.condition):
            if field in LINE_ATTRIBUTES:
                referenced.setdefault((rule.erp_system, rule.source_account), set()).add(field)
    cases = " ".join(
        f"WHEN m.erp_system = '{erp}' AND m.source_account = '{acct}' THEN ("
        + " OR ".join(f"m.attr_{a} IS NOT NULL" for a in sorted(names)) + ")"
        for (erp, acct), names in sorted(referenced.items()))

    con.execute(f"""
    CREATE OR REPLACE TABLE map_acceptance AS
    SELECT
        m.line_uid, m.erp_system, m.entity_code, m.source_account, m.source_account_name,
        m.chart_mapping_type_applied AS mapping_type, m.mapping_rule_id, m.mapping_status,
        m.source_line_attributes, m.dept_code, m.cost_center_code, m.dept_function,
        m.fiscal_year, m.accounting_period, m.signed_local_amount,
        o.event_type AS source_journal_type,
        o.expected_group_account,
        m.group_account AS produced_group_account,
        m.group_account IS NOT DISTINCT FROM o.expected_group_account AS agrees,
        CASE {cases} ELSE TRUE END AS classifiable_at_source
    FROM stg_mapped_enriched m
    JOIN oracle_expected_line o
      ON o.entity_code = m.entity_code AND o.journal_id = m.journal_id
     AND o.line_number = m.line_number
    """)

    summary = con.execute("""
    SELECT classifiable_at_source,
           count(*) AS lines,
           count(*) FILTER (WHERE agrees) AS exact_matches,
           count(*) FILTER (WHERE NOT agrees) AS mismatches,
           count(*) FILTER (WHERE mapping_status LIKE 'UNMAPPED%') AS unmapped,
           count(*) FILTER (WHERE mapping_status = 'AMBIGUOUS') AS ambiguous
    FROM map_acceptance GROUP BY 1 ORDER BY 1 DESC
    """).fetchdf()

    if not writing_artefacts():
        return _acceptance_summary(summary)
    con.execute(f"""
    COPY (
        SELECT source_journal_type, erp_system, source_account, source_account_name,
               expected_group_account, produced_group_account, mapping_rule_id,
               classifiable_at_source,
               count(*) AS line_count,
               round(sum(abs(signed_local_amount)), 2) AS absolute_amount_local,
               min(source_line_attributes) AS example_line_attributes,
               min(dept_code) AS example_dept_code,
               min(cost_center_code) AS example_cost_centre
        FROM map_acceptance WHERE NOT agrees
        GROUP BY ALL
        ORDER BY line_count DESC, erp_system, source_account, expected_group_account,
                 produced_group_account, source_journal_type
    ) TO '{MAPPING_ACCEPTANCE.as_posix()}' (FORMAT CSV, HEADER)
    """)

    return _acceptance_summary(summary)


def _acceptance_summary(summary) -> dict:
    total = int(summary["lines"].sum())
    matched = int(summary["exact_matches"].sum())
    classifiable = summary[summary["classifiable_at_source"]]
    return {
        "lines_graded": total,
        "exact_matches": matched,
        "mismatches": total - matched,
        "unmapped": int(summary["unmapped"].sum()),
        "ambiguous": int(summary["ambiguous"].sum()),
        "agreement_pct": round(matched / total * 100, 6) if total else 0.0,
        "classifiable_lines": int(classifiable["lines"].iloc[0]) if len(classifiable) else 0,
        "classifiable_matches": int(classifiable["exact_matches"].iloc[0]) if len(classifiable) else 0,
        "classifiable_agreement_pct":
            round(float(classifiable["exact_matches"].iloc[0])
                  / float(classifiable["lines"].iloc[0]) * 100, 6) if len(classifiable) else 0.0,
    }


def build(con: duckdb.DuckDBPyConnection) -> None:
    """Reconcile the mapped result to the approved Phase 2 source-layer targets."""
    con.execute(f"""
    CREATE OR REPLACE TABLE anchor_source_layer_target AS
    SELECT statement, line_item,
           CAST(FY2023A AS DOUBLE) AS fy2023, CAST(FY2024A AS DOUBLE) AS fy2024,
           CAST(FY2025A AS DOUBLE) AS fy2025
    FROM read_csv('{(CONFIG / "anchors" / "phase02_source_layer_targets.csv").as_posix()}',
                  all_varchar=true, header=true)
    """)
    con.execute(f"""
    CREATE OR REPLACE TABLE anchor_business_unit AS
    SELECT bu_code, measure,
           CAST(FY2023A AS DOUBLE) AS fy2023, CAST(FY2024A AS DOUBLE) AS fy2024,
           CAST(FY2025A AS DOUBLE) AS fy2025
    FROM read_csv('{(CONFIG / "anchors" / "anchor_by_business_unit.csv").as_posix()}',
                  all_varchar=true, header=true)
    """)
    con.execute(f"""
    CREATE OR REPLACE TABLE anchor_entity AS
    SELECT entity_code, bu_code, measure,
           CAST(FY2023A AS DOUBLE) AS fy2023, CAST(FY2024A AS DOUBLE) AS fy2024,
           CAST(FY2025A AS DOUBLE) AS fy2025
    FROM read_csv('{(CONFIG / "anchors" / "anchor_by_entity.csv").as_posix()}',
                  all_varchar=true, header=true)
    """)

    con.execute("""
    CREATE OR REPLACE TABLE rec_group_income_statement AS
    WITH mapped AS (
        SELECT fiscal_year,
               sum(external_revenue_usd + intercompany_revenue_usd) / 1e6 AS revenue,
               sum(cost_of_sales_usd + intercompany_cost_of_sales_usd) / 1e6 AS cost_of_sales,
               sum(operating_expense_usd + intercompany_opex_usd) / 1e6 AS opex
        FROM vw_validation_pl_usd GROUP BY 1
    ), unpivoted AS (
        SELECT fiscal_year, 'revenue' AS line_item, revenue AS mapped_usd_m FROM mapped
        UNION ALL SELECT fiscal_year, 'cost_of_sales', cost_of_sales FROM mapped
        UNION ALL SELECT fiscal_year, 'opex', opex FROM mapped
    )
    SELECT u.fiscal_year, 'IS' AS statement, u.line_item,
           round(u.mapped_usd_m, 6) AS mapped_usd_m,
           round(CASE u.fiscal_year WHEN 2023 THEN t.fy2023 WHEN 2024 THEN t.fy2024
                                    ELSE t.fy2025 END, 6) AS target_usd_m,
           round(u.mapped_usd_m - CASE u.fiscal_year WHEN 2023 THEN t.fy2023
                                       WHEN 2024 THEN t.fy2024 ELSE t.fy2025 END, 6)
               AS variance_usd_m,
           round(abs(u.mapped_usd_m - CASE u.fiscal_year WHEN 2023 THEN t.fy2023
                                           WHEN 2024 THEN t.fy2024 ELSE t.fy2025 END)
                 / nullif(abs(CASE u.fiscal_year WHEN 2023 THEN t.fy2023
                                   WHEN 2024 THEN t.fy2024 ELSE t.fy2025 END), 0), 8)
               AS deviation_pct
    FROM unpivoted u
    JOIN anchor_source_layer_target t
      ON t.statement = 'IS' AND t.line_item = u.line_item
    WHERE u.fiscal_year <= 2025
    ORDER BY u.fiscal_year, u.line_item
    """)

    con.execute("""
    CREATE OR REPLACE TABLE rec_business_unit_margin AS
    SELECT g.fiscal_year, g.bu_code,
           round(g.revenue_usd_m, 6) AS mapped_revenue_usd_m,
           round(CASE g.fiscal_year WHEN 2023 THEN r.fy2023 WHEN 2024 THEN r.fy2024
                                    ELSE r.fy2025 END, 6) AS target_revenue_usd_m,
           round(g.gross_profit_usd_m, 6) AS mapped_gross_profit_usd_m,
           round(CASE g.fiscal_year WHEN 2023 THEN p.fy2023 WHEN 2024 THEN p.fy2024
                                    ELSE p.fy2025 END, 6) AS target_gross_profit_usd_m,
           round(g.gross_margin_pct, 6) AS mapped_gross_margin_pct,
           round(CASE g.fiscal_year WHEN 2023 THEN m.fy2023 WHEN 2024 THEN m.fy2024
                                    ELSE m.fy2025 END, 6) AS target_gross_margin_pct,
           round(g.gross_margin_pct - CASE g.fiscal_year WHEN 2023 THEN m.fy2023
                                          WHEN 2024 THEN m.fy2024 ELSE m.fy2025 END, 8)
               AS margin_variance_pct
    FROM vw_validation_gross_margin_usd g
    JOIN anchor_business_unit r ON r.bu_code = g.bu_code AND r.measure = 'revenue'
    JOIN anchor_business_unit p ON p.bu_code = g.bu_code AND p.measure = 'gross_profit'
    JOIN anchor_business_unit m ON m.bu_code = g.bu_code AND m.measure = 'gross_margin_pct'
    WHERE g.fiscal_year <= 2025
    ORDER BY g.fiscal_year, g.bu_code
    """)

    con.execute("""
    CREATE OR REPLACE TABLE rec_entity_revenue AS
    SELECT v.fiscal_year, v.entity_code, v.bu_code,
           round(sum(v.external_revenue_usd) / 1e6, 6) AS mapped_external_revenue_usd_m,
           round(any_value(CASE v.fiscal_year WHEN 2023 THEN a.fy2023 WHEN 2024 THEN a.fy2024
                                              ELSE a.fy2025 END), 6) AS target_usd_m,
           round(sum(v.external_revenue_usd) / 1e6
                 - any_value(CASE v.fiscal_year WHEN 2023 THEN a.fy2023
                                 WHEN 2024 THEN a.fy2024 ELSE a.fy2025 END), 6)
               AS variance_usd_m
    FROM vw_validation_pl_usd v
    JOIN anchor_entity a ON a.entity_code = v.entity_code AND a.measure = 'external_revenue'
    WHERE v.fiscal_year <= 2025
    GROUP BY ALL ORDER BY v.fiscal_year, v.entity_code
    """)

    # The same balance sheet built from the ORACLE's group account rather than the
    # pipeline's. Comparing the two separates a mapping difference from a source-data
    # difference: where the pipeline and the oracle agree, the mapping is right and any
    # remaining variance against the anchor is a property of the source layer.
    con.execute("""
    CREATE OR REPLACE VIEW vw_validation_bs_usd_oracle AS
    SELECT f.fiscal_year, f.group_account,
           sum(f.signed_local_amount * r.rate_usd_per_unit) AS closing_balance_usd
    FROM (
        SELECT y.fiscal_year, e.functional_currency AS currency_code,
               a.expected_group_account AS group_account,
               sum(a.signed_local_amount) AS signed_local_amount
        FROM map_acceptance a
        JOIN dim_entity e ON e.entity_code = a.entity_code
        JOIN (SELECT DISTINCT fiscal_year FROM fact_journal_line) y
          ON a.fiscal_year * 100 + LEAST(a.accounting_period, 12) <= y.fiscal_year * 100 + 12
        WHERE a.expected_group_account LIKE '1%' OR a.expected_group_account LIKE '2%'
           OR a.expected_group_account LIKE '3%'
        GROUP BY ALL
    ) f
    JOIN ref_fx_rate r
      ON r.currency_code = f.currency_code
     AND r.period_key = f.fiscal_year * 100 + 12
     AND r.rate_type = 'CLOSE'
     AND r.rate_set = CASE WHEN f.fiscal_year = 2026 THEN 'FORECAST' ELSE 'ACTUAL' END
    GROUP BY ALL
    """)

    # The balance sheet, at closing rates, against the same source-layer targets.
    con.execute("""
    CREATE OR REPLACE TABLE rec_balance_sheet AS
    WITH caption AS (
        SELECT 'cash' AS line_item, ['110100'] AS accounts
        UNION ALL SELECT 'ar', ['120100','120200']
        UNION ALL SELECT 'inventory', ['130100','130200','130300','130400']
        UNION ALL SELECT 'prepaid', ['140100']
        UNION ALL SELECT 'contract_assets', ['121100']
        UNION ALL SELECT 'ppe_net', ['150200','150300','150400','150500','150600','150800','155100']
        UNION ALL SELECT 'ap', ['210100','210200']
        UNION ALL SELECT 'accrued', ['215100','215200','215300','215400','215500','215600','216100','219100']
        UNION ALL SELECT 'tax_payable', ['218100']
        UNION ALL SELECT 'rcf', ['220200']
        UNION ALL SELECT 'tlb_gross', ['230100']
    ), mapped AS (
        SELECT c.line_item, b.fiscal_year, sum(b.closing_balance_usd) / 1e6 AS mapped_usd_m
        FROM vw_validation_bs_usd b JOIN caption c ON list_contains(c.accounts, b.group_account)
        GROUP BY 1, 2
    ), oracle AS (
        SELECT c.line_item, b.fiscal_year, sum(b.closing_balance_usd) / 1e6 AS oracle_usd_m
        FROM vw_validation_bs_usd_oracle b
        JOIN caption c ON list_contains(c.accounts, b.group_account)
        GROUP BY 1, 2
    )
    SELECT m.fiscal_year, 'BS' AS statement, m.line_item,
           round(abs(m.mapped_usd_m), 6) AS mapped_usd_m,
           round(abs(o.oracle_usd_m), 6) AS oracle_usd_m,
           round(abs(m.mapped_usd_m) - abs(o.oracle_usd_m), 6) AS mapping_variance_usd_m,
           round(abs(CASE m.fiscal_year WHEN 2023 THEN t.fy2023 WHEN 2024 THEN t.fy2024
                                        ELSE t.fy2025 END), 6) AS target_usd_m,
           round(abs(m.mapped_usd_m) - abs(CASE m.fiscal_year WHEN 2023 THEN t.fy2023
                       WHEN 2024 THEN t.fy2024 ELSE t.fy2025 END), 6) AS variance_usd_m,
           round(abs(abs(m.mapped_usd_m) - abs(CASE m.fiscal_year WHEN 2023 THEN t.fy2023
                       WHEN 2024 THEN t.fy2024 ELSE t.fy2025 END))
                 / nullif(abs(CASE m.fiscal_year WHEN 2023 THEN t.fy2023
                             WHEN 2024 THEN t.fy2024 ELSE t.fy2025 END), 0), 8) AS deviation_pct
    FROM mapped m
    JOIN oracle o USING (line_item, fiscal_year)
    JOIN anchor_source_layer_target t
      ON t.statement = 'BS' AND t.line_item = m.line_item
    WHERE m.fiscal_year <= 2025
    ORDER BY m.fiscal_year, m.line_item
    """)

    # Revenue detail to the mapped general ledger (ADR-0008).
    con.execute("""
    CREATE OR REPLACE TABLE rec_revenue_detail AS
    SELECT
        coalesce(gl.entity_code, d.entity_code) AS entity_code,
        coalesce(gl.period_key, d.period_key) AS period_key,
        round(coalesce(gl.gl_revenue, 0), 2) AS gl_revenue_local,
        round(coalesce(d.detail_revenue, 0), 2) AS detail_revenue_local,
        round(coalesce(gl.gl_revenue, 0) - coalesce(d.detail_revenue, 0), 2) AS variance_local
    FROM (
        SELECT entity_code, period_key, sum(-signed_local_amount) AS gl_revenue
        FROM fact_journal_line
        WHERE group_account LIKE '4%' AND group_account NOT LIKE '49%'
          AND group_account NOT LIKE '44%'
          AND source_event_type IS DISTINCT FROM 'YEAR_END_CLOSE'
          AND special_period_type IS DISTINCT FROM 'STATUTORY_CLOSE'
        GROUP BY 1, 2
    ) gl
    FULL OUTER JOIN (
        SELECT entity_code, period_key, sum(revenue_local) AS detail_revenue
        FROM fact_revenue_detail GROUP BY 1, 2
    ) d USING (entity_code, period_key)
    """)

    if not writing_artefacts():
        return
    con.execute(f"""
    COPY (
        SELECT 'GROUP_INCOME_STATEMENT' AS reconciliation, fiscal_year, statement,
               line_item AS item, mapped_usd_m AS mapped, target_usd_m AS target,
               variance_usd_m AS variance, deviation_pct AS deviation
        FROM rec_group_income_statement
        UNION ALL
        SELECT 'BALANCE_SHEET', fiscal_year, statement, line_item, mapped_usd_m,
               target_usd_m, variance_usd_m, deviation_pct
        FROM rec_balance_sheet
        UNION ALL
        SELECT 'BUSINESS_UNIT_MARGIN', fiscal_year, 'IS', bu_code,
               mapped_gross_margin_pct, target_gross_margin_pct, margin_variance_pct,
               abs(margin_variance_pct)
        FROM rec_business_unit_margin
        UNION ALL
        SELECT 'ENTITY_EXTERNAL_REVENUE', fiscal_year, 'IS', entity_code,
               mapped_external_revenue_usd_m, target_usd_m, variance_usd_m,
               abs(variance_usd_m) / nullif(abs(target_usd_m), 0)
        FROM rec_entity_revenue
        ORDER BY reconciliation, fiscal_year, item
    ) TO '{RECONCILIATION.as_posix()}' (FORMAT CSV, HEADER)
    """)
