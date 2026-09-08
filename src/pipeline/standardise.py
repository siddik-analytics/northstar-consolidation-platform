"""
parsed -> standardised: one canonical journal-line model for all three source systems.

This is where the three ERPs stop being different.  Four normalisations happen, each of
them explicit and each of them tested:

**Sign.**  The canonical convention is stated once in `config.SIGN_CONVENTION` and is
DEBIT-POSITIVE.  Aurora and Kestrel already express a signed value -- one as a single
signed amount, the other as separate SOLL and HABEN columns.  Sable does not: its amounts
carry the account's *natural* sign, so a signed value exists only once the account's normal
balance is known.  That normal balance is taken from the **approved chart of accounts**,
not from the extract's own `NORMALBALANCE` column; the two are then compared, because a
source system disagreeing with the chart about an account's normal balance is a finding,
not a convenience (P3-TB-01).  Nothing infers a sign from how a statement is presented.

**Period.**  Three period concepts are kept apart rather than collapsed:

    accounting_period      what the source system posted to: 1-12, or 13-16 at Kestrel
    management_period      the calendar month a reader sees: always 1-12
    special_period_type    what a 13-16 posting is: statutory close, audit, tax, group

A special period is part of the December close, so its management period is 12.  Keeping
the two apart is the only thing that stops a thirteenth month appearing in a chart, and it
keeps the adjustment identifiable all the way through (CTL-DQ-07).

**Dimensions.**  Entity, cost centre, department and partner are resolved to conformed
keys.  Aurora and Sable carry no cost centre at all -- their extracts carry a department
segment -- so one is resolved from the entity and department.  Kestrel carries KOSTL
natively and it is used as given, then checked against the same resolution (P3-DIM-04).

**Attributes.**  The line-attribute string each system carries is parsed into named
columns.  These are what a conditional mapping rule reads, so they are extracted once,
here, rather than by string-matching inside the rule engine.
"""

from __future__ import annotations

import duckdb

from .config import LAYER_DIR, SPECIAL_PERIODS, writing_artefacts

#: Line-attribute names the mapping rules may reference.  A rule condition naming anything
#: outside this list is rejected when the rule set is loaded, which is what keeps the rule
#: language a language rather than arbitrary SQL.
LINE_ATTRIBUTES = [
    "dept_function", "cost_center_function", "dept_code", "asset_class",
    "instrument_type", "partner_bu", "maturity_months", "product_group", "income_type",
    "presentation", "advisor_type", "expense_subtype", "cost_type", "accrual_type",
    "vendor_category", "tax_jurisdiction", "revaluation_flag", "reimbursable_type",
    "project_code", "special_period",
]

#: Native and dimension-resolved fields a rule may also reference.
CONTEXT_FIELDS = [
    "erp_system", "entity_code", "bu_code", "country_code", "source_account",
    "dept_code", "cost_center_code", "dept_function", "partner_entity_code",
    "source_currency", "document_type", "source_event_type",
]


def _attr(name: str) -> str:
    """Pull one named attribute out of the `k=v;k=v` string the extract carries."""
    return (f"nullif(regexp_extract(source_line_attributes, "
            f"'(?:^|;){name}=([^;]*)', 1), '') AS attr_{name}")


def _special_period_case(column: str) -> str:
    whens = " ".join(f"WHEN {k} THEN '{v}'" for k, v in SPECIAL_PERIODS.items())
    return f"CASE {column} {whens} ELSE NULL END"


def build(con: duckdb.DuckDBPyConnection) -> int:
    """Create the standardised journal-line table. Returns the row count."""
    attrs = ",\n            ".join(_attr(a) for a in LINE_ATTRIBUTES)

    con.execute(f"""
    CREATE OR REPLACE TABLE stg_parsed_union AS
        SELECT erp_system, source_file, source_row_ordinal, ingest_build_id,
               source_account, source_account_name, source_entity_key, posting_date,
               fiscal_year, fiscal_period, journal_id, line_number, document_id,
               document_type, source_event_type, source_description, source_currency,
               native_signed_amount, debit_amount, credit_amount, source_department_key,
               source_cost_center_key, source_partner_key, source_customer_key,
               source_product_key, source_line_attributes, source_period_raw,
               source_normal_balance_declared, source_translated_amount,
               source_translated_currency
        FROM parsed_aurora
        UNION ALL BY NAME
        SELECT erp_system, source_file, source_row_ordinal, ingest_build_id,
               source_account, source_account_name, source_entity_key, posting_date,
               fiscal_year, fiscal_period, journal_id, line_number, document_id,
               document_type, source_event_type, source_description, source_currency,
               native_signed_amount, debit_amount, credit_amount, source_department_key,
               source_cost_center_key, source_partner_key, source_customer_key,
               source_product_key, source_line_attributes, source_period_raw,
               source_normal_balance_declared, source_translated_amount,
               source_translated_currency
        FROM parsed_sable
        UNION ALL BY NAME
        SELECT erp_system, source_file, source_row_ordinal, ingest_build_id,
               source_account, source_account_name, source_entity_key, posting_date,
               fiscal_year, fiscal_period, journal_id, line_number, document_id,
               document_type, source_event_type, source_description, source_currency,
               native_signed_amount, debit_amount, credit_amount, source_department_key,
               source_cost_center_key, source_partner_key, source_customer_key,
               source_product_key, source_line_attributes, source_period_raw,
               source_normal_balance_declared, source_translated_amount,
               source_translated_currency
        FROM parsed_kestrel
    """)

    con.execute(f"""
    CREATE OR REPLACE TABLE stg_standardised AS
    WITH base AS (
        SELECT p.*,
            {attrs}
        FROM stg_parsed_union p
    ), joined AS (
        SELECT
            b.*,
            e.entity_code, e.bu_code, e.country_code, e.functional_currency,
            e.erp_company_code, e.effective_from AS entity_effective_from,
            sa.source_normal_balance AS chart_normal_balance,
            sa.mapping_type AS chart_mapping_type,
            sa.default_group_account AS chart_default_group_account,
            sa.effective_from AS account_effective_from,
            sa.effective_to AS account_effective_to,
            -- Aurora and Sable carry a department, not a cost centre; Kestrel carries
            -- both. The resolution is the same for all three so that the check on
            -- Kestrel's native value means something.
            cc_dept.cost_center_code AS resolved_cost_center_code,
            cc_dept.dept_function AS dimension_dept_function,
            cc_native.dept_function AS native_cost_center_dept_function
        FROM base b
        LEFT JOIN dim_entity e
               ON e.erp_system = b.erp_system
              AND e.source_entity_key = b.source_entity_key
        LEFT JOIN dim_source_account sa
               ON sa.erp_system = b.erp_system
              AND sa.source_account = b.source_account
        LEFT JOIN dim_cost_center cc_dept
               ON cc_dept.entity_code = e.entity_code
              AND cc_dept.department_code = b.source_department_key
        LEFT JOIN dim_cost_center cc_native
               ON cc_native.entity_code = e.entity_code
              AND cc_native.cost_center_code = b.source_cost_center_key
    )
    SELECT
        -- ------------------------------------------------------------- lineage
        erp_system || '|' || source_file || '|' || journal_id || '|'
            || CAST(line_number AS VARCHAR) AS line_uid,
        erp_system, source_file, source_row_ordinal, ingest_build_id,
        source_entity_key, source_account, source_account_name,
        source_period_raw, source_line_attributes,
        native_signed_amount AS source_native_amount,
        source_normal_balance_declared,
        source_translated_amount, source_translated_currency,
        -- ------------------------------------------------------------- identity
        entity_code, bu_code, country_code, functional_currency, erp_company_code,
        journal_id, document_id, document_type, line_number,
        source_event_type, source_description,
        -- --------------------------------------------------------------- period
        posting_date,
        fiscal_year,
        fiscal_period AS accounting_period,
        LEAST(fiscal_period, 12) AS management_period,
        fiscal_year * 100 + LEAST(fiscal_period, 12) AS period_key,
        CASE WHEN fiscal_period > 12 THEN fiscal_period END AS special_period,
        {_special_period_case('fiscal_period')} AS special_period_type,
        fiscal_period > 12 AS is_adjustment_period,
        -- ----------------------------------------------------------------- sign
        -- Sable is the only system whose amount is not already signed. Its sign comes
        -- from the approved chart, never from the extract's own opinion.
        --
        -- This is also where money stops being a DOUBLE. Every source amount is exact to
        -- the cent, and a parallel SUM over DOUBLE adds its partial results in whatever
        -- order the threads happen to finish in -- so the same input can produce a
        -- different last bit from one run to the next. DuckDB's decimal sum is exact
        -- integer arithmetic and independent of that order.
        CAST(CASE
            WHEN erp_system = 'SABLE'
                THEN native_signed_amount * CASE WHEN chart_normal_balance = 'D' THEN 1 ELSE -1 END
            ELSE native_signed_amount
        END AS DECIMAL(18,2)) AS signed_local_amount,
        CAST(CASE
            WHEN erp_system = 'SABLE'
                THEN greatest(native_signed_amount * CASE WHEN chart_normal_balance = 'D' THEN 1 ELSE -1 END, 0)
            ELSE greatest(native_signed_amount, 0)
        END AS DECIMAL(18,2)) AS debit_local,
        CAST(CASE
            WHEN erp_system = 'SABLE'
                THEN greatest(-native_signed_amount * CASE WHEN chart_normal_balance = 'D' THEN 1 ELSE -1 END, 0)
            ELSE greatest(-native_signed_amount, 0)
        END AS DECIMAL(18,2)) AS credit_local,
        debit_amount AS native_debit, credit_amount AS native_credit,
        chart_normal_balance, chart_mapping_type, chart_default_group_account,
        account_effective_from, account_effective_to,
        source_currency,
        -- ----------------------------------------------------------- dimensions
        source_department_key AS native_dept_code,
        -- Like `dept_function`, the department a rule reads is attribute-first: where the
        -- posting declares its own classification the source system is stating something
        -- about that line, and the posted segment is the fallback. `P3-MAP-07` reports
        -- every line where the two disagree.
        coalesce(attr_dept_code, source_department_key) AS dept_code,
        coalesce(source_cost_center_key, resolved_cost_center_code) AS cost_center_code,
        source_cost_center_key AS native_cost_center_code,
        resolved_cost_center_code,
        dimension_dept_function,
        native_cost_center_dept_function,
        -- The function a conditional rule reads. A posting's own declared attribute is
        -- the source system's statement about the line and takes precedence; the
        -- cost-centre dimension supplies it when the line does not. `P3-MAP-07` reports
        -- every line where the two disagree -- which is a source-data finding, not a
        -- mapping one.
        coalesce(attr_dept_function, attr_cost_center_function,
                 native_cost_center_dept_function, dimension_dept_function)
            AS dept_function,
        source_partner_key AS partner_entity_code,
        source_customer_key AS customer_code,
        source_product_key AS product_code,
        -- ---------------------------------------------------------- attributes
        {", ".join(f"attr_{a}" for a in LINE_ATTRIBUTES)}
    FROM joined
    """)

    if writing_artefacts():
        out = LAYER_DIR["standardised"] / "stg_standardised.parquet"
        con.execute(
            f"COPY (SELECT * FROM stg_standardised ORDER BY erp_system, source_file, "
            f"source_row_ordinal) TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    return con.execute("SELECT count(*) FROM stg_standardised").fetchone()[0]
