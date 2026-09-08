"""
ERP source adapters: raw -> parsed.

There is deliberately no generic parser.  The three source systems differ in encoding,
delimiter, numeric notation, date format, account-key typing, sign convention and period
structure, and a parser that pretended otherwise would have to guess at each of those.
Each adapter states its system's conventions explicitly and is the only place in the
pipeline that knows them.

The parsed layer keeps every native column **verbatim as text** alongside the typed
derivations, so a reviewer can always get back to what the extract actually said.  Nothing
is normalised here: sign, period and account harmonisation belong to the next stage.

    Aurora   modern cloud ERP.  UTF-8, comma-delimited, ISO dates, one signed amount with
             credits negative, four-digit account codes, a department segment and a
             system-translated USD column that is deliberately stale.
    Sable    project ERP.  UTF-8, comma-delimited, US dates, thousands separators, and
             amounts carried at the account's NATURAL sign -- so a signed value can only
             be recovered by knowing each account's normal balance.
    Kestrel  legacy European ERP.  Windows-1252, semicolon-delimited, comma decimals and
             point thousands separators, DD.MM.YYYY dates, zero-padded eight-character
             text account keys, separate positive SOLL and HABEN columns, fiscal periods
             1-16, and a legacy EUR group-currency column that must never be read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from .config import LAYER_DIR, RAW, writing_artefacts


@dataclass(frozen=True)
class Adapter:
    """One source system's ingestion contract."""

    erp_system: str
    subdir: str
    delimiter: str
    encoding: str
    #: DuckDB expressions producing the typed derivations, keyed on output column name.
    derive: dict[str, str]
    #: The extract's own line key, used to order rows deterministically within a file.
    line_key: tuple[str, str]
    #: Native columns preserved verbatim.  Order is the extract's own column order.
    native: list[str] = field(default_factory=list)
    #: A column carried for lineage that no downstream stage may read.
    forbidden: str | None = None
    notes: str = ""

    def read_options(self) -> str:
        opts = ["all_varchar=true", "header=true", "filename=true",
                f"delim='{self.delimiter}'"]
        if self.encoding != "utf-8":
            opts.append(f"encoding='{self.encoding}'")
        return ", ".join(opts)


# --------------------------------------------------------------------------- Aurora
AURORA = Adapter(
    erp_system="AURORA",
    subdir="aurora",
    delimiter=",",
    encoding="utf-8",
    native=["SUBSIDIARY", "PERIOD", "TRANDATE", "JOURNAL_ID", "LINE_ID", "ACCOUNT",
            "ACCOUNT_NAME", "DEPARTMENT", "CLASS", "LOCATION", "MEMO", "DOCUMENT_NUMBER",
            "DOCUMENT_TYPE", "CURRENCY", "AMOUNT", "AMOUNT_USD_SYSTEM",
            "SUBSIDIARY_PARTNER", "CUSTOMER", "ITEM", "LINE_ATTRIBUTES"],
    line_key=("JOURNAL_ID", "LINE_ID"),
    forbidden="AMOUNT_USD_SYSTEM",
    notes="Aurora carries no fiscal year column; the year comes from the posting date and "
          "is cross-checked against the file name. It carries no cost centre either -- the "
          "department segment plus the entity resolves one.",
    derive={
        # The account key is text. Aurora's codes are four digits and would survive an
        # integer cast, which is exactly why the cast must not be made anywhere: the
        # pipeline treats every source account key the same way, as text.
        "source_account": "CAST(ACCOUNT AS VARCHAR)",
        "source_account_name": "ACCOUNT_NAME",
        "source_entity_key": "SUBSIDIARY",
        "posting_date": "strptime(TRANDATE, '%Y-%m-%d')::DATE",
        "fiscal_year": "CAST(strftime(strptime(TRANDATE, '%Y-%m-%d'), '%Y') AS INTEGER)",
        "fiscal_period": "CAST(PERIOD AS INTEGER)",
        "journal_id": "JOURNAL_ID",
        "line_number": "CAST(LINE_ID AS INTEGER)",
        "document_id": "DOCUMENT_NUMBER",
        "document_type": "DOCUMENT_TYPE",
        "source_event_type": "CLASS",
        "source_description": "MEMO",
        "source_currency": "CURRENCY",
        # One signed amount, credits negative. The debit and credit columns are derived
        # from it so that every ERP presents the same three amount fields downstream.
        "native_signed_amount": "CAST(AMOUNT AS DOUBLE)",
        "debit_amount": "CASE WHEN CAST(AMOUNT AS DOUBLE) > 0 THEN CAST(AMOUNT AS DOUBLE) ELSE 0 END",
        "credit_amount": "CASE WHEN CAST(AMOUNT AS DOUBLE) < 0 THEN -CAST(AMOUNT AS DOUBLE) ELSE 0 END",
        "source_department_key": "replace(DEPARTMENT, 'DEPT-', '')",
        "source_cost_center_key": "NULL",
        "source_partner_key": "nullif(SUBSIDIARY_PARTNER, '')",
        "source_customer_key": "nullif(CUSTOMER, '')",
        "source_product_key": "nullif(ITEM, '')",
        "source_line_attributes": "coalesce(LINE_ATTRIBUTES, '')",
        "source_period_raw": "PERIOD",
        "source_normal_balance_declared": "NULL",
        "source_translated_amount": "CAST(AMOUNT_USD_SYSTEM AS DOUBLE)",
        "source_translated_currency": "'USD'",
    },
)

# --------------------------------------------------------------------------- Sable
SABLE = Adapter(
    erp_system="SABLE",
    subdir="sable",
    delimiter=",",
    encoding="utf-8",
    native=["COMPANY", "FISCALYEAR", "FISCALPERIOD", "POSTINGDATE", "JOURNALID",
            "LINENUM", "MAINACCOUNT", "ACCOUNTNAME", "NORMALBALANCE", "DIMENSIONSTRING",
            "DESCRIPTION", "DOCUMENTNUM", "DOCUMENTTYPE", "TRANSACTIONTYPE",
            "CURRENCYCODE", "AMOUNT", "CUSTOMERID", "ITEMID", "LINEATTRIBUTES"],
    line_key=("JOURNALID", "LINENUM"),
    notes="Amounts carry the account's natural sign, so a signed value is recoverable only "
          "with the account's normal balance. The extract states its own view of that in "
          "NORMALBALANCE; the pipeline uses the approved chart of accounts instead and "
          "proves the two agree (P3-TB-01). The dimension string is "
          "entity|department|project|partner.",
    derive={
        "source_account": "CAST(MAINACCOUNT AS VARCHAR)",
        "source_account_name": "ACCOUNTNAME",
        # COMPANY is the ERP company code (CAS-US), not the group entity code.
        "source_entity_key": "COMPANY",
        "posting_date": "strptime(POSTINGDATE, '%m/%d/%Y')::DATE",
        "fiscal_year": "CAST(FISCALYEAR AS INTEGER)",
        "fiscal_period": "CAST(FISCALPERIOD AS INTEGER)",
        "journal_id": "JOURNALID",
        "line_number": "CAST(LINENUM AS INTEGER)",
        "document_id": "DOCUMENTNUM",
        "document_type": "DOCUMENTTYPE",
        "source_event_type": "TRANSACTIONTYPE",
        "source_description": "DESCRIPTION",
        "source_currency": "CURRENCYCODE",
        # Natural sign, with US thousands separators. The value is positive as presented;
        # the sign is applied in `standardise` from the chart's normal balance.
        "native_signed_amount": "CAST(replace(AMOUNT, ',', '') AS DOUBLE)",
        "debit_amount": "NULL",
        "credit_amount": "NULL",
        "source_department_key": "split_part(DIMENSIONSTRING, '|', 2)",
        "source_cost_center_key": "NULL",
        "source_partner_key": "nullif(split_part(DIMENSIONSTRING, '|', 4), 'NONE')",
        "source_customer_key": "nullif(CUSTOMERID, '')",
        "source_product_key": "nullif(ITEMID, '')",
        "source_line_attributes": "coalesce(LINEATTRIBUTES, '')",
        "source_period_raw": "FISCALPERIOD",
        "source_normal_balance_declared": "NORMALBALANCE",
        "source_translated_amount": "NULL",
        "source_translated_currency": "NULL",
    },
)

# --------------------------------------------------------------------------- Kestrel
KESTREL = Adapter(
    erp_system="KESTREL",
    subdir="kestrel",
    delimiter=";",
    encoding="CP1252",
    native=["BUKRS", "GJAHR", "MONAT", "BUDAT", "BELNR", "BUZEI", "HKONT", "TXT50",
            "SAKNR_BEZ", "KOSTL", "PRCTR", "SEGMENT", "VBUND", "BSCHL", "WAERS",
            "SOLL", "HABEN", "DMBTR_KONZERN_EUR", "KUNNR", "MATNR", "ZUONR"],
    line_key=("BELNR", "BUZEI"),
    forbidden="DMBTR_KONZERN_EUR",
    notes="HKONT is a zero-padded eight-character key and is never cast to a number. "
          "Amounts arrive as separate positive SOLL and HABEN columns in German notation: "
          "point thousands separator, comma decimal. MONAT runs 1-16.",
    derive={
        # `CAST(... AS VARCHAR)` is a no-op here only because the reader was told
        # all_varchar. That is the point: the column never becomes a number, so its
        # leading zeros cannot be lost (CTL-DQ-10, P3-ING-07).
        "source_account": "CAST(HKONT AS VARCHAR)",
        "source_account_name": "SAKNR_BEZ",
        "source_entity_key": "BUKRS",
        "posting_date": "strptime(BUDAT, '%d.%m.%Y')::DATE",
        "fiscal_year": "CAST(GJAHR AS INTEGER)",
        "fiscal_period": "CAST(MONAT AS INTEGER)",
        "journal_id": "BELNR",
        "line_number": "CAST(BUZEI AS INTEGER)",
        "document_id": "BELNR",
        "document_type": "BSCHL",
        "source_event_type": "NULL",
        "source_description": "TXT50",
        "source_currency": "WAERS",
        "native_signed_amount":
            "coalesce(TRY_CAST(replace(replace(nullif(SOLL, ''), '.', ''), ',', '.') AS DOUBLE), 0)"
            " - coalesce(TRY_CAST(replace(replace(nullif(HABEN, ''), '.', ''), ',', '.') AS DOUBLE), 0)",
        "debit_amount":
            "coalesce(TRY_CAST(replace(replace(nullif(SOLL, ''), '.', ''), ',', '.') AS DOUBLE), 0)",
        "credit_amount":
            "coalesce(TRY_CAST(replace(replace(nullif(HABEN, ''), '.', ''), ',', '.') AS DOUBLE), 0)",
        "source_department_key": "replace(SEGMENT, 'SEG-', '')",
        "source_cost_center_key": "nullif(KOSTL, '')",
        "source_partner_key": "nullif(VBUND, '')",
        "source_customer_key": "nullif(KUNNR, '')",
        "source_product_key": "nullif(MATNR, '')",
        "source_line_attributes": "coalesce(ZUONR, '')",
        "source_period_raw": "MONAT",
        "source_normal_balance_declared": "NULL",
        "source_translated_amount":
            "TRY_CAST(replace(replace(nullif(DMBTR_KONZERN_EUR, ''), '.', ''), ',', '.') AS DOUBLE)",
        "source_translated_currency": "'EUR'",
    },
)

ADAPTERS = {a.erp_system: a for a in (AURORA, SABLE, KESTREL)}


def parse_sql(adapter: Adapter, build_id: str, raw_root: Path | None = None) -> str:
    """The statement that turns one ERP's extract directory into its parsed layer."""
    root = (raw_root or RAW) / adapter.subdir
    native = ",\n        ".join(f'"{c}" AS "native_{c}"' for c in adapter.native)
    derived = ",\n        ".join(f"{expr} AS {name}" for name, expr in adapter.derive.items())
    jkey, lkey = adapter.line_key
    return f"""
    SELECT
        '{adapter.erp_system}' AS erp_system,
        regexp_extract(replace(filename, '\\', '/'), '[^/]+$') AS source_file,
        row_number() OVER (
            PARTITION BY filename
            ORDER BY "{jkey}", CAST("{lkey}" AS INTEGER)
        ) AS source_row_ordinal,
        '{build_id}' AS ingest_build_id,
        {derived},
        {native}
    FROM read_csv('{root.as_posix()}/*.csv', {adapter.read_options()})
    """


def parse(con: duckdb.DuckDBPyConnection, build_id: str,
          raw_root: Path | None = None) -> dict[str, int]:
    """
    Materialise the parsed layer, one table and one parquet file per source system.

    `raw_root` overrides the source tree so that a fault-variant of the extracts can be run
    through the real pipeline rather than tested against a copy of it.
    """
    counts: dict[str, int] = {}
    for erp, adapter in ADAPTERS.items():
        table = f"parsed_{erp.lower()}"
        con.execute(
            f"CREATE OR REPLACE TABLE {table} AS {parse_sql(adapter, build_id, raw_root)}")
        if writing_artefacts():
            out = LAYER_DIR["parsed"] / f"{table}.parquet"
            con.execute(
                f"COPY (SELECT * FROM {table} ORDER BY source_file, source_row_ordinal) "
                f"TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        counts[table] = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    return counts
