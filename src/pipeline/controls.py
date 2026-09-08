"""
Phase 3 controls.

Every control reads the built warehouse, not the pipeline's memory.  A control that shares
state with the thing it checks proves nothing.

Four families, in the order a break would actually be found:

    P3-ING   ingestion: files, encodings, locales, dates, keys, lineage
    P3-TB    accounting: the trial balance survives sign and period normalisation, and
             survives mapping
    P3-MAP   harmonisation: nothing unresolved, nothing ambiguous, nothing silently
             defaulted, and the result agrees with the acceptance oracle
    P3-DIM   conformance: every key resolves, and no dimension has two versions of itself
    P3-REC   reconciliation: the mapped numbers are the approved numbers
    P3-BR    business sense: checks that catch a mapping which is wrong but still balances

    python -m src.pipeline.controls
"""

from __future__ import annotations

import csv
import sys

import duckdb

from .config import (CONFIG, CONTROL_RESULTS, DUCKDB_PATH, ERPS,
                     FORBIDDEN_DOWNSTREAM_FIELDS, RAW)
from .reconcile import TOL_BS, TOL_PL

#: Accepted source findings, and the population each was accepted at.
#: `config/controls/source_exception_register.csv`.
EXCEPTION_REGISTER = CONFIG / "controls" / "source_exception_register.csv"

#: The declared numeric grammar of each source system. An amount that PARSES is not the
#: same thing as an amount that parses CORRECTLY: a German figure whose comma decimal has
#: been replaced by a period still parses, and lands a hundred times too large. The only
#: defence is to check the text against the format the system declares (CTL-DQ-09).
#: Gross margin agreement, as a fraction: 0.0001 = 0.01 percentage points = one basis
#: point. Deliberately far below any plausible misclassification -- fault F08 moves group
#: gross margin by 0.047pp by re-tagging eight payroll postings consistently, and the
#: original 0.05pp tolerance could not see it. The clean pipeline reproduces every
#: business unit's margin at exactly 0.000000, so there is nothing legitimate to absorb.
TOL_MARGIN = 0.0001

NUMERIC_GRAMMAR = {
    "AURORA":  (r"^-?[0-9]+(\.[0-9]{1,2})?$",              "plain decimal, point separator"),
    "SABLE":   (r"^-?[0-9]{1,3}(,[0-9]{3})*(\.[0-9]{1,2})?$",
                "US notation: comma thousands, point decimal"),
    "KESTREL": (r"^-?[0-9]{1,3}(\.[0-9]{3})*(,[0-9]{1,2})?$",
                "German notation: point thousands, comma decimal"),
}

#: Contra accounts and other places where the natural sign of a class is legitimately
#: reversed. Everything else must carry its class's normal sign at entity level.
CONTRA_ACCOUNTS = {
    "120200",   # allowance for doubtful accounts, a credit inside receivables
    "130400",   # inventory reserve
    "155100", "156100", "165100",   # accumulated depreciation and amortisation
    "230200",   # unamortised deferred financing costs, a debit inside debt
    "440100", "440200",             # contra revenue
    "735100", "795100", "745100", "750100", "740100", "740200",  # income within 7x
    "320300",   # distributions, a debit inside equity
    "830100",   # deferred tax, which can be a credit
}

#: Accounts whose balance is genuinely bidirectional. An intercompany current account is a
#: receivable when the entity is owed and a payable when it owes, and it is the same
#: account either way; retained earnings is a deficit across this group.
BIDIRECTIONAL_ACCOUNTS = {
    "120500", "210500",             # intercompany trade current account
    "125100", "225100",             # group treasury current account, both legs
    "175100", "235100",             # intercompany loans, both legs
    "320100", "320200",             # retained earnings and the current-year result
    "790100", "795100", "795200",   # intercompany result lines
}


class Result(list):
    """
    A control outcome is one of three things, and collapsing them would hide the one that
    matters:

        PASS            the control holds
        FAIL            the PIPELINE is wrong; a blocking failure stops the build
        SOURCE_FINDING  the control does not hold, and the cause is a defect in the frozen
                        source layer that Phase 3 is not permitted to patch. The pipeline
                        is behaving correctly; the data is not

    A source finding is never downgraded to a pass and never absorbed. It is reported with
    its population, its amount and the defect it belongs to, and it is carried onto the
    phase report as an open item for the owner.
    """

    def add(self, cid, name, severity, status, measured="", threshold="", detail="",
            defect=""):
        self.append(dict(control_id=cid, control_name=name, severity=severity,
                         status=status, measured=str(measured), threshold=str(threshold),
                         defect_reference=defect, detail=detail))

    @property
    def failed(self):
        return [r for r in self if r["status"] == "FAIL" and r["severity"] == "BLOCKING"]

    @property
    def findings(self):
        return [r for r in self if r["status"] == "SOURCE_FINDING"]

    def ok(self, cid, name, severity, condition, measured, threshold, detail="",
           defect=""):
        status = "PASS" if condition else ("SOURCE_FINDING" if defect else "FAIL")
        self.add(cid, name, severity, status, measured, threshold, detail, defect)


def _one(con, sql):
    return con.execute(sql).fetchone()[0]


def load_exceptions() -> dict[str, dict]:
    """
    The accepted source findings, keyed on the control that reports each one.

    A known defect in the frozen source layer is quarantined, not forgiven. Each exception
    records the population it was accepted at, and the control compares against it:

        measured == accepted   the known defect, unchanged -> SOURCE_FINDING
        measured >  accepted   something NEW is wrong      -> FAIL
        measured <  accepted   the source was corrected    -> FAIL, retire the exception

    Without the second of those, a fault of exactly the same shape as a known defect would
    hide inside it. Fault fixture F08 -- production payroll re-tagged to an SG&A department
    -- is precisely that shape.
    """
    with open(EXCEPTION_REGISTER, newline="", encoding="utf-8") as f:
        return {row["control_id"]: row for row in csv.DictReader(f)}


def registered(r: "Result", exceptions: dict, cid: str, name: str, severity: str,
               measured_population: int, unit: str, detail: str) -> None:
    """Report a control whose failure is an accepted source finding, against its baseline."""
    row = exceptions.get(cid)
    accepted = int(row["accepted_population"]) if row else 0
    if measured_population == 0:
        r.add(cid, name, severity, "PASS", 0, 0, detail,
              row["defect_reference"] if row else "")
    elif row and measured_population == accepted:
        r.add(cid, name, severity, "SOURCE_FINDING",
              f"{measured_population} {unit}", f"{accepted} accepted ({row['exception_id']})",
              detail + f" Accepted at {accepted} {unit} pending {row['expires']}.",
              row["defect_reference"])
    else:
        r.add(cid, name, severity, "FAIL", f"{measured_population} {unit}",
              f"{accepted} accepted" if row else 0,
              detail + (f" This is MORE than the {accepted} {unit} accepted as "
                        f"{row['exception_id']}: something new is wrong."
                        if row and measured_population > accepted else
                        f" This is FEWER than the {accepted} {unit} accepted as "
                        f"{row['exception_id']}: the source may have been corrected and the "
                        f"exception should be retired." if row else ""))


def run(con: duckdb.DuckDBPyConnection) -> Result:
    r = Result()
    exceptions = load_exceptions()

    # =================================================================== ingestion
    parsed_files = _one(con, """
        SELECT count(DISTINCT source_file) FROM (
            SELECT source_file FROM parsed_aurora UNION ALL
            SELECT source_file FROM parsed_sable UNION ALL
            SELECT source_file FROM parsed_kestrel)""")
    on_disk = sum(len(list((RAW / e.lower()).glob("*.csv"))) for e in ERPS)
    r.ok("P3-ING-01", "Every source extract file is ingested", "BLOCKING",
         parsed_files == on_disk, parsed_files, on_disk,
         "one parsed partition per file present in data/raw")

    # Every data row in every file reaches the parsed layer. Counted against the files
    # themselves rather than against a number the pipeline produced.
    disk_rows = 0
    for erp in ERPS:
        enc = "cp1252" if erp == "KESTREL" else "utf-8"
        for path in (RAW / erp.lower()).glob("*.csv"):
            with open(path, encoding=enc, newline="") as f:
                disk_rows += sum(1 for _ in f) - 1
    parsed_rows = _one(con, "SELECT count(*) FROM stg_parsed_union")
    r.ok("P3-ING-02", "Row counts survive ingestion", "BLOCKING",
         parsed_rows == disk_rows, parsed_rows, disk_rows,
         "parsed rows equal the data rows in the extract files, counted independently")

    bad_enc = _one(con, """
        SELECT count(*) FROM parsed_kestrel
        WHERE contains(native_SAKNR_BEZ, '�') OR contains(native_TXT50, '�')""")
    r.ok("P3-ING-03", "Windows-1252 text decodes without loss", "BLOCKING",
         bad_enc == 0, bad_enc, 0,
         "no replacement character in any Kestrel German account or item text")

    bad_amt = _one(con, """
        SELECT count(*) FROM stg_parsed_union
        WHERE native_signed_amount IS NULL OR isnan(native_signed_amount)""")
    r.ok("P3-ING-04", "Every amount parses under its declared locale", "BLOCKING",
         bad_amt == 0, bad_amt, 0,
         "German point-thousands / comma-decimal and US thousands separators")

    bad_date = _one(con, "SELECT count(*) FROM stg_parsed_union WHERE posting_date IS NULL")
    r.ok("P3-ING-05", "Every posting date parses", "BLOCKING", bad_date == 0, bad_date, 0,
         "ISO, US MM/DD/YYYY and German DD.MM.YYYY")

    # A date that parses can still be in the wrong period (CTL-DQ-06).
    off_period = _one(con, """
        SELECT count(*) FROM stg_standardised
        WHERE NOT is_adjustment_period
          AND (CAST(strftime(posting_date, '%Y') AS INTEGER) <> fiscal_year
               OR CAST(strftime(posting_date, '%m') AS INTEGER) <> accounting_period)""")
    r.ok("P3-ING-06", "Posting dates fall inside their own accounting period", "BLOCKING",
         off_period == 0, off_period, 0,
         "special periods 13-16 are excluded: they carry a December date by design")

    padded = _one(con, """SELECT count(*) FROM parsed_kestrel
                          WHERE source_account LIKE '0%'""")
    coerced = _one(con, """
        SELECT count(*) FROM parsed_kestrel
        WHERE length(source_account) <> 8
           OR source_account <> lpad(ltrim(source_account, '0'), 8, '0')""")
    r.ok("P3-ING-07", "Kestrel account keys keep their leading zeros as text", "BLOCKING",
         padded > 0 and coerced == 0, f"{padded} padded, {coerced} coerced", ">0 padded, 0 coerced",
         "an eight-character key coerced to a number loses its leading zeros silently")

    # CTL-DQ-09. An amount that parses is not an amount that parses correctly: replace a
    # German comma decimal with a period and "13.068,03" becomes "13.068.03", which strips
    # to 1,306,803 -- a hundredfold overstatement that no null check can see. The text is
    # therefore checked against the grammar the system declares.
    malformed = []
    for erp, (pattern, described) in NUMERIC_GRAMMAR.items():
        columns = ("native_SOLL", "native_HABEN") if erp == "KESTREL" else ("native_AMOUNT",)
        for column in columns:
            n = _one(con, f"""
                SELECT count(*) FROM parsed_{erp.lower()}
                WHERE trim(coalesce({column}, '')) <> ''
                  AND NOT regexp_matches(trim({column}), '{pattern}')""")
            if n:
                malformed.append(f"{erp}.{column.replace('native_', '')}={n}")
    r.ok("P3-ING-13", "Every amount matches its system's declared numeric grammar",
         "BLOCKING", not malformed, str(malformed) if malformed else 0, 0,
         "; ".join(f"{e}: {d}" for e, (_p, d) in NUMERIC_GRAMMAR.items()))

    dup = _one(con, """
        SELECT count(*) FROM (
            SELECT line_uid FROM stg_standardised GROUP BY 1 HAVING count(*) > 1)""")
    r.ok("P3-ING-08", "Every line has a unique lineage key", "BLOCKING", dup == 0, dup, 0,
         "erp | file | journal | line, the declared grain of the conformed fact")

    sparse = _one(con, """
        SELECT count(*) FROM (
            SELECT source_file, count(*) AS n, max(source_row_ordinal) AS m
            FROM stg_parsed_union GROUP BY 1 HAVING n <> m)""")
    r.ok("P3-ING-09", "Row ordinals are dense within every file", "BLOCKING",
         sparse == 0, sparse, 0, "1..N per file, so a dropped row is visible")

    specials = dict(con.execute("""
        SELECT special_period_type, count(*) FROM stg_standardised
        WHERE special_period IS NOT NULL GROUP BY 1""").fetchall())
    unclassified = _one(con, """
        SELECT count(*) FROM stg_standardised
        WHERE accounting_period > 12 AND special_period_type IS NULL""")
    r.ok("P3-ING-10", "Kestrel special periods are classified, not numbered", "BLOCKING",
         unclassified == 0 and len(specials) == 4, f"{sorted(specials)}", "4 types, 0 unclassified",
         "13 statutory close, 14 audit, 15 tax, 16 group reporting; all report in month 12")

    thirteenth = _one(con,
                      "SELECT count(*) FROM fact_journal_line WHERE management_period > 12")
    r.ok("P3-ING-11", "No thirteenth month can reach a management view", "BLOCKING",
         thirteenth == 0, thirteenth, 0,
         "the accounting period is retained; the reporting month is capped at December")

    # CTL-FX-06: both source systems ship a translated amount produced by their own rate
    # table. They are kept for lineage and must never reach a calculation.
    forbidden_used = [c for c in con.execute(
        "DESCRIBE SELECT * FROM fact_trial_balance").fetchall()
        if "translated" in c[0] or "usd_system" in c[0].lower()]
    r.ok("P3-ING-12", "Source-system translated amounts never reach a calculation",
         "BLOCKING", not forbidden_used, str([c[0] for c in forbidden_used]), "none",
         f"{FORBIDDEN_DOWNSTREAM_FIELDS} are carried on the journal-line fact for lineage "
         f"only and are absent from every aggregate")

    # =============================================================== accounting
    native_worst = _one(con, """
        SELECT coalesce(max(abs(s)), 0) FROM (
            SELECT sum(CASE WHEN p.erp_system = 'SABLE'
                            THEN p.native_signed_amount
                                 * CASE WHEN a.source_normal_balance = 'D' THEN 1 ELSE -1 END
                            ELSE p.native_signed_amount END) AS s
            FROM stg_parsed_union p
            JOIN dim_source_account a
              ON a.erp_system = p.erp_system AND a.source_account = p.source_account
            GROUP BY p.source_entity_key, p.erp_system, p.fiscal_year)""")
    r.ok("P3-TB-01", "Native trial balance closes in each ERP's own convention", "BLOCKING",
         native_worst <= 0.02, round(native_worst, 4), 0.02,
         "re-derived from the parsed layer: Aurora signed, Kestrel SOLL less HABEN, "
         "Sable natural sign against the approved chart")

    std_worst = _one(con, """
        SELECT coalesce(max(abs(s)), 0) FROM (
            SELECT sum(signed_local_amount) AS s FROM stg_standardised
            GROUP BY entity_code, fiscal_year, accounting_period)""")
    r.ok("P3-TB-02", "Trial balance closes after sign normalisation", "BLOCKING",
         std_worst <= 0.02, round(std_worst, 4), 0.02, "per entity and accounting period")

    map_worst = _one(con, """
        SELECT coalesce(max(abs(s)), 0) FROM (
            SELECT sum(signed_local_amount) AS s FROM fact_journal_line
            WHERE include_in_tb_balance
            GROUP BY entity_code, fiscal_year, accounting_period)""")
    r.ok("P3-TB-03", "Trial balance still closes after mapping", "BLOCKING",
         map_worst <= 0.02, round(map_worst, 4), 0.02,
         "mapping is classification only: it may not move a cent")

    stat = _one(con, "SELECT count(*) FROM fact_journal_line WHERE is_statistical")
    r.ok("P3-TB-04", "No statistical account enters the trial balance", "BLOCKING",
         stat == 0, stat, 0, "statistical accounts are outside the balancing population")

    moved = _one(con, """
        SELECT coalesce(max(abs(d)), 0) FROM (
            SELECT sum(s.signed_local_amount) - sum(m.signed_local_amount) AS d
            FROM stg_standardised s JOIN fact_journal_line m USING (line_uid)
            GROUP BY s.entity_code, s.fiscal_year)""")
    r.ok("P3-TB-05", "Mapping changes no amount", "BLOCKING", moved <= 0.005,
         round(moved, 6), 0.005,
         "the standardised and mapped amounts agree line for line")

    # CTL-DQ-05: normalisation must not have inverted an account class.
    #
    # The test is on the CLOSING BALANCE for a balance sheet account and on the YEAR'S
    # TOTAL for an income statement account, because a balance sheet account's movement in
    # a year is legitimately either way round -- cash goes down as often as it goes up --
    # while its balance is not. Accounts whose balance is genuinely bidirectional are named
    # and excluded rather than inferred.
    excluded = "', '".join(sorted(CONTRA_ACCOUNTS | BIDIRECTIONAL_ACCOUNTS))
    inverted_bs = con.execute(f"""
        SELECT j.group_account, j.entity_code, y.fy, round(sum(j.signed_local_amount), 2)
        FROM fact_journal_line j,
             (SELECT DISTINCT fiscal_year AS fy FROM fact_journal_line) y
        WHERE j.period_key <= y.fy * 100 + 12
          AND j.group_account NOT IN ('{excluded}')
          AND j.account_class IN ('ASSET', 'LIABILITY', 'EQUITY')
        GROUP BY ALL
        HAVING (j.account_class = 'ASSET' AND sum(j.signed_local_amount) < -1.0)
            OR (j.account_class IN ('LIABILITY', 'EQUITY')
                AND sum(j.signed_local_amount) > 1.0)
    """).fetchall()
    inverted_pl = con.execute(f"""
        SELECT group_account, entity_code, fiscal_year, round(sum(signed_local_amount), 2)
        FROM fact_journal_line
        WHERE group_account NOT IN ('{excluded}')
          AND account_class IN ('REVENUE', 'EXPENSE', 'COGS')
          AND source_event_type IS DISTINCT FROM 'YEAR_END_CLOSE'
          AND special_period_type IS DISTINCT FROM 'STATUTORY_CLOSE'
        GROUP BY ALL
        HAVING (account_class IN ('EXPENSE', 'COGS') AND sum(signed_local_amount) < -1.0)
            OR (account_class = 'REVENUE' AND sum(signed_local_amount) > 1.0)
    """).fetchall()
    inverted = inverted_bs + inverted_pl
    only_known = {row[0] for row in inverted} <= {"121100"}
    registered(r, exceptions, "P3-TB-06", "No account class has had its sign inverted",
               "BLOCKING", len(inverted) if only_known else 10_000 + len(inverted),
               "account-entity-years",
               "assets carry debit balances, liabilities, equity and revenue carry credits; "
               "contra and genuinely bidirectional accounts are named and excluded, never "
               "inferred. The accepted exception is contract assets at the Kestrel "
               "entities, driven into a credit balance by unclassified accrued-income "
               "postings.")

    # ================================================================== mapping
    unresolved = dict(con.execute("""
        SELECT mapping_status, count(*) FROM fact_journal_line
        WHERE mapping_status IN ('UNMAPPED_ACCOUNT','UNMAPPED_NO_RULE','OUT_OF_EFFECT',
                                 'INVALID_DIMENSION')
        GROUP BY 1""").fetchall())
    r.ok("P3-MAP-01", "No line is left unresolved", "BLOCKING", not unresolved,
         str(unresolved) if unresolved else 0, 0,
         "an unresolved line goes to data/10_staging/exceptions/mapping_exceptions.csv "
         "and blocks the close; it never defaults silently")

    ambiguous = _one(con,
                     "SELECT count(*) FROM fact_journal_line WHERE mapping_status = 'AMBIGUOUS'")
    r.ok("P3-MAP-02", "No line matches more than one rule branch", "BLOCKING",
         ambiguous == 0, ambiguous, 0,
         "priority does not resolve an ambiguity, it hides one: a line matching two "
         "branches is an exception, not a lookup")

    acc = con.execute("""
        SELECT count(*) AS graded,
               count(*) FILTER (WHERE agrees) AS matched,
               count(*) FILTER (WHERE classifiable_at_source) AS classifiable,
               count(*) FILTER (WHERE classifiable_at_source AND agrees) AS classifiable_matched
        FROM map_acceptance""").fetchone()
    graded, matched, classifiable, classifiable_matched = acc
    r.ok("P3-MAP-03", "Mapping agrees with the acceptance oracle where the source "
         "classified the line", "BLOCKING",
         classifiable_matched == classifiable,
         f"{classifiable_matched}/{classifiable} = "
         f"{classifiable_matched / classifiable * 100:.6f}%", "100.000000%",
         "the expected-mapping manifest is read here and nowhere else; the engine derives "
         "the group account from the approved charts and rules alone")

    registered(r, exceptions, "P3-MAP-04", "Mapping agreement across every line", "WARNING",
               graded - matched, "journal lines",
               f"{matched} of {graded} lines agree with the oracle "
               f"({matched / graded * 100:.6f}%). Every disagreement is a posting the "
               f"source system left unclassified; see P3-MAP-13.")

    out_of_effect = _one(con, """
        SELECT count(*) FROM stg_standardised s
        JOIN dim_source_account a
          ON a.erp_system = s.erp_system AND a.source_account = s.source_account
        WHERE s.posting_date < a.effective_from
           OR (a.effective_to IS NOT NULL AND s.posting_date > a.effective_to)""")
    r.ok("P3-MAP-05", "Every mapping is effective at the posting date", "BLOCKING",
         out_of_effect == 0, out_of_effect, 0,
         "effective-dated mappings are evaluated against the posting date, not the load date")

    no_default = con.execute("""
        SELECT erp_system, source_account FROM dim_source_account a
        WHERE a.mapping_type IN ('SPLIT', 'DERIVED')
          AND NOT EXISTS (SELECT 1 FROM map_rules r
                          WHERE r.erp_system = a.erp_system
                            AND r.source_account = a.source_account
                            AND r.rule_class IN ('SPLIT_DEFAULT', 'DERIVED'))""").fetchall()
    r.ok("P3-MAP-06", "Every conditional account declares a default branch", "BLOCKING",
         not no_default, len(no_default), 0,
         "a split with no default is a silent fall-through waiting to happen")

    bad_target = con.execute("""
        SELECT DISTINCT r.rule_id, r.target_group_account FROM map_rules r
        LEFT JOIN dim_account a ON a.group_account = r.target_group_account
        WHERE a.group_account IS NULL OR a.is_statistical""").fetchall()
    r.ok("P3-MAP-07", "Every rule target exists and is not statistical", "BLOCKING",
         not bad_target, len(bad_target), 0, "CTL-MAP-02, CTL-MAP-03")

    orphan = con.execute("""
        SELECT DISTINCT s.erp_system, s.source_account FROM stg_standardised s
        LEFT JOIN dim_source_account a
          ON a.erp_system = s.erp_system AND a.source_account = s.source_account
        WHERE a.source_account IS NULL""").fetchall()
    r.ok("P3-MAP-08", "No orphan source account", "BLOCKING", not orphan,
         str(orphan[:5]) if orphan else 0, 0,
         "every account posted to in an extract exists in that ERP's approved chart")

    covered = _one(con, """
        SELECT round(sum(abs(signed_local_amount)) FILTER (WHERE group_account IS NOT NULL)
                     / nullif(sum(abs(signed_local_amount)), 0) * 100, 6)
        FROM fact_journal_line""")
    r.ok("P3-MAP-09", "Mapping coverage of value, not just of codes", "BLOCKING",
         covered is not None and covered >= 99.9, covered, 99.9,
         "CTL-MAP-05: an unmapped rounding line and an unmapped acquisition are not the "
         "same problem")

    # CTL-MAP-08. The German total-cost-method items must leave the revenue block for cost
    # of sales. The amount does not change -- a credit stays a credit -- so what reverses is
    # the caption, not the number, and the trial balance above proves nothing moved.
    gkv = con.execute("""
        SELECT count(*) AS lines,
               count(*) FILTER (WHERE reporting_block = 'COST_OF_SALES') AS to_cos,
               count(*) FILTER (WHERE reporting_block = 'REVENUE') AS left_in_revenue,
               round(sum(signed_local_amount), 2) AS amount
        FROM fact_journal_line WHERE source_account IN ('00081000', '00081200')""").fetchone()
    r.ok("P3-MAP-10", "German total-cost-method items are reclassified into cost of sales",
         "BLOCKING", gkv[0] > 0 and gkv[1] == gkv[0] and gkv[2] == 0,
         f"{gkv[1]}/{gkv[0]} to cost of sales, {gkv[2]} left in revenue", "all, none",
         "Bestandsveraenderung and aktivierte Eigenleistungen sit above the revenue line "
         "under the Gesamtkostenverfahren and inside cost of sales under the group's "
         "cost-of-sales presentation")

    reclass_flagged = _one(con, """
        SELECT count(*) FROM fact_journal_line
        WHERE is_presentation_reclass AND presentation_reclass_type = 'GKV_TO_UKV'""")
    r.ok("P3-MAP-11", "Every presentation reclassification is flagged and traceable",
         "BLOCKING", reclass_flagged == gkv[0], reclass_flagged, gkv[0],
         "the source presentation stays visible on the line: source account, source "
         "account name in German, and the reclassification type")

    # The two source-data findings, reported rather than hidden.
    contradiction = con.execute("""
        SELECT count(*) AS lines, coalesce(round(sum(abs(signed_local_amount)), 2), 0) AS amount
        FROM fact_journal_line
        WHERE dimension_dept_function IS NOT NULL
          AND dept_function IS DISTINCT FROM dimension_dept_function""").fetchone()
    registered(r, exceptions, "P3-MAP-12",
               "A line's declared function agrees with the cost centre it was posted to",
               "BLOCKING", contradiction[0], "journal lines",
               f"{contradiction[1]:,.0f} local. The posting declares one classification and "
               f"sits in a cost centre carrying another. The declared attribute is "
               f"authoritative for the mapping contract, so the mapping is right; the source "
               f"data is not self-corroborating.")

    # Every ingested row has exactly one disposition in each bridge, and each bridge sums
    # to the ingested population. A row that falls out between two stages, or a difference
    # between two counts that nobody can name, is the failure this makes impossible.
    ingested = _one(con, "SELECT count(*) FROM fact_journal_line")
    residues = con.execute(f"""
        SELECT bridge, sum(lines) - {ingested} AS residue
        FROM rpt_population_bridge GROUP BY 1 HAVING residue <> 0""").fetchall()
    r.ok("P3-REC-12", "Every ingested row has exactly one disposition in every bridge",
         "BLOCKING", not residues, str(residues), 0,
         f"{ingested:,} ingested rows partitioned three ways -- by journal character, by "
         f"mapping status and by oracle grading. Each partition sums to the ingested "
         f"count with no residue, so no row is silently dropped between stages and no "
         f"unexplained difference between two population counts can survive.")

    unclassified_lines = con.execute("""
        SELECT count(*) AS lines,
               count(*) FILTER (WHERE NOT agrees) AS wrong,
               coalesce(round(sum(abs(signed_local_amount)) FILTER (WHERE NOT agrees), 2), 0) AS amount
        FROM map_acceptance WHERE NOT classifiable_at_source""").fetchone()
    registered(r, exceptions, "P3-MAP-13",
               "Every posting to a conditional account carries the attribute its rules read",
               "WARNING", unclassified_lines[1], "journal lines",
               f"{unclassified_lines[0]} postings carry no attribute their account's rules "
               f"read. Opening-balance, year-end-close and special-period journals are "
               f"written without the line attributes the mapping contract requires, so the "
               f"split cannot be derived.")

    # ============================================================== dimensions
    for cid, name, sql, detail in [
        ("P3-DIM-01", "Every entity resolves to a real operating entity",
         """SELECT count(*) FROM fact_journal_line f
            LEFT JOIN dim_entity e USING (entity_code)
            WHERE e.entity_code IS NULL OR e.is_elimination_entity
               OR e.entity_type <> 'OPERATING'""",
         "an elimination entity must never appear in a source extract"),
        ("P3-DIM-02", "Every cost centre resolves to the master",
         """SELECT count(*) FROM fact_journal_line f
            LEFT JOIN dim_cost_center c
              ON c.entity_code = f.entity_code AND c.cost_center_code = f.cost_center_code
            WHERE c.cost_center_code IS NULL""", "CTL-DQ-08"),
        ("P3-DIM-03", "Every currency is in the approved set",
         """SELECT count(*) FROM fact_journal_line f
            LEFT JOIN dim_currency c ON c.currency_code = f.currency_code
            WHERE c.currency_code IS NULL""",
         "USD, CAD, GBP, EUR"),
        ("P3-DIM-04", "Every group account resolves to the group chart",
         """SELECT count(*) FROM fact_journal_line f
            LEFT JOIN dim_account a ON a.group_account = f.group_account
            WHERE a.group_account IS NULL""",
         "CTL-DQ-08 referential integrity"),
        ("P3-DIM-05", "Every intercompany partner is valid and never the posting entity",
         """SELECT count(*) FROM fact_journal_line f
            LEFT JOIN dim_intercompany_partner p
              ON p.partner_entity_code = f.partner_entity_code
            WHERE f.partner_entity_code IS NOT NULL
              AND (p.partner_entity_code IS NULL
                   OR f.partner_entity_code = f.entity_code)""", "CTL-IC-04"),
    ]:
        n = _one(con, sql)
        r.ok(cid, name, "BLOCKING", n == 0, n, 0, detail)

    cc_mismatch = _one(con, """
        SELECT count(*) FROM fact_journal_line
        WHERE native_cost_center_code IS NOT NULL
          AND native_cost_center_code <> cost_center_code""")
    r.ok("P3-DIM-06", "Kestrel's native cost centre agrees with the resolved one",
         "BLOCKING", cc_mismatch == 0, cc_mismatch, 0,
         "Aurora and Sable carry no cost centre and one is resolved from the department; "
         "Kestrel carries KOSTL, and the same resolution must reproduce it")

    dup_dim = []
    for table, key in (("dim_entity", "entity_code"), ("dim_account", "group_account"),
                       ("dim_business_unit", "bu_code"), ("dim_department", "department_code"),
                       ("dim_version", "version_code"), ("dim_scenario", "scenario_code"),
                       ("dim_cost_center", "entity_code, cost_center_code"),
                       ("dim_source_account", "erp_system, source_account"),
                       ("dim_date", "fiscal_year, accounting_period")):
        n = _one(con, f"SELECT count(*) FROM (SELECT {key} FROM {table} "
                      f"GROUP BY ALL HAVING count(*) > 1)")
        if n:
            dup_dim.append((table, n))
    r.ok("P3-DIM-07", "No dimension has a duplicate natural key", "BLOCKING",
         not dup_dim, str(dup_dim), 0,
         "including effective-dated dimensions, where a duplicate key would make the "
         "as-at lookup non-deterministic")

    ic_no_partner = _one(con, """
        SELECT count(*) FROM fact_journal_line
        WHERE is_intercompany AND partner_entity_code IS NULL
          AND source_event_type IS DISTINCT FROM 'YEAR_END_CLOSE'
          AND special_period_type IS DISTINCT FROM 'STATUTORY_CLOSE'
          AND source_event_type IS DISTINCT FROM 'OPENING_BALANCE'""")
    registered(r, exceptions, "P3-DIM-08", "Intercompany postings carry a partner",
               "BLOCKING", ic_no_partner, "journal lines",
               "CTL-IC-04. The invoice leg of every intercompany flow carries its "
               "counterparty; the cash settlement leg, the treasury current account and the "
               "intercompany loans do not, so an intercompany BALANCE cannot be attributed "
               "to an entity pair. The opening balance and the year-end close are excluded "
               "as positions rather than transactions.")

    third_party_affiliate = _one(con, """
        SELECT count(*) FROM fact_journal_line
        WHERE group_account IN ('730100','730200','730300','730600','735100')
          AND source_line_attributes LIKE '%instrument_type=AFFILIATE%'""")
    r.ok("P3-DIM-09", "Affiliate interest is separated from third-party interest",
         "BLOCKING", third_party_affiliate == 0, third_party_affiliate, 0,
         "CTL-IC-05: affiliate interest left in the third-party accounts overstates "
         "consolidated net interest, because it does not eliminate")

    missing_fx = _one(con, """
        SELECT count(*) FROM (
            SELECT DISTINCT f.currency_code, f.period_key, t.rate_type
            FROM fact_journal_line f
            CROSS JOIN (SELECT 'AVG' AS rate_type UNION ALL SELECT 'CLOSE') t
            EXCEPT
            SELECT currency_code, period_key, rate_type FROM ref_fx_rate
            WHERE rate_set = 'ACTUAL')""")
    r.ok("P3-DIM-10", "FX rates are complete for every currency and period in use",
         "BLOCKING", missing_fx == 0, missing_fx, 0,
         "CTL-FX-01. A missing rate must block the period, not translate at zero")

    # ========================================================== reconciliation
    src_to_std = _one(con, """
        SELECT coalesce(max(abs(d)), 0) FROM (
            SELECT sum(abs(p.native_signed_amount)) - sum(abs(s.source_native_amount)) AS d
            FROM stg_parsed_union p JOIN stg_standardised s
              ON s.erp_system = p.erp_system AND s.journal_id = p.journal_id
             AND s.line_number = p.line_number AND s.source_file = p.source_file
            GROUP BY p.erp_system)""")
    r.ok("P3-REC-01", "Source amounts survive standardisation", "BLOCKING",
         src_to_std <= 0.01, round(src_to_std, 4), 0.01,
         "absolute value by ERP, before and after sign normalisation")

    worst_is = _one(con, "SELECT coalesce(max(deviation_pct), 1) FROM rec_group_income_statement")
    r.ok("P3-REC-02", "Mapped income statement reconciles to the source-layer target",
         "BLOCKING", worst_is <= TOL_PL, f"{worst_is * 100:.6f}%", f"{TOL_PL * 100:.1f}%",
         "revenue, cost of sales and operating expense, FY2023-FY2025, against "
         "config/anchors/phase02_source_layer_targets.csv")

    worst_bs_map = _one(con,
                        "SELECT coalesce(max(abs(mapping_variance_usd_m)), 0) FROM rec_balance_sheet")
    worst_bs_map_pct = _one(con, """
        SELECT coalesce(max(abs(mapping_variance_usd_m) / nullif(target_usd_m, 0)), 0)
        FROM rec_balance_sheet""")
    off_oracle = _one(con, """SELECT count(*) FROM rec_balance_sheet
                              WHERE abs(mapping_variance_usd_m) > 0.01""")
    registered(r, exceptions, "P3-REC-03",
               "Mapped balance sheet agrees with the acceptance oracle", "WARNING",
               off_oracle, "balance sheet caption-years",
               f"worst {worst_bs_map:.4f}m ({worst_bs_map_pct * 100:.2f}%). Contract assets "
               f"and prepayments differ because seven Kestrel postings to 00017000 carry no "
               f"accrual type and resolve to the default branch.")

    bs_ex_finding = _one(con, """
        SELECT coalesce(max(deviation_pct), 0) FROM rec_balance_sheet
        WHERE line_item NOT IN ('contract_assets', 'prepaid', 'accrued', 'tax_payable')""")
    r.ok("P3-REC-04", "Mapped balance sheet reconciles to the source-layer target",
         "BLOCKING", bs_ex_finding <= TOL_BS, f"{bs_ex_finding * 100:.6f}%",
         f"{TOL_BS * 100:.1f}%",
         "four captions carry a documented source finding and are reported separately by "
         "P3-REC-03 and P3-REC-08")

    rev_detail = _one(con, "SELECT coalesce(max(abs(variance_local)), 0) FROM rec_revenue_detail")
    r.ok("P3-REC-05", "Revenue detail reconciles to the mapped general ledger", "BLOCKING",
         rev_detail <= 0.05, round(rev_detail, 4), 0.05,
         "ADR-0008: customer and product detail lives in its own fact at its own grain and "
         "must tie to the ledger. It is never pushed into the journal-line fact")

    worst_margin = _one(con,
                        "SELECT coalesce(max(abs(margin_variance_pct)), 1) FROM rec_business_unit_margin")
    # One basis point of gross margin. The clean pipeline reproduces the anchor EXACTLY --
    # the worst variance across twelve business-unit-years is 0.000000 -- so there is no
    # legitimate noise for a loose threshold to absorb, and a loose one is how a small
    # misclassification hides. Eight payroll lines moved across the gross margin line move
    # the margin by 4.7 basis points; at 5 basis points that fault went undetected.
    r.ok("P3-REC-06", "Gross margin by business unit reproduces the anchor", "BLOCKING",
         worst_margin <= TOL_MARGIN, f"{worst_margin * 100:.6f}pp",
         f"{TOL_MARGIN * 100:.2f}pp",
         "THE control that catches a mapping which is wrong but still balances: move "
         "production payroll into SG&A and every other control still passes")

    worst_entity = _one(con,
                        "SELECT coalesce(max(abs(variance_usd_m)), 1) FROM rec_entity_revenue")
    r.ok("P3-REC-07", "External revenue by entity reproduces the anchor", "BLOCKING",
         worst_entity <= 0.01, round(worst_entity, 6), 0.01, "FY2023-FY2025")

    tb_tie = _one(con, """
        SELECT coalesce(max(abs(d)), 0) FROM (
            SELECT sum(t.signed_local_amount) - sum(j.signed_local_amount) AS d
            FROM (SELECT entity_code, sum(signed_local_amount) AS signed_local_amount
                  FROM fact_trial_balance GROUP BY 1) t
            JOIN (SELECT entity_code, sum(signed_local_amount) AS signed_local_amount
                  FROM fact_journal_line GROUP BY 1) j USING (entity_code)
            GROUP BY entity_code)""")
    r.ok("P3-REC-08", "The trial balance fact ties to the journal-line fact", "BLOCKING",
         tb_tie <= 0.02, round(tb_tie, 4), 0.02,
         "the aggregate is built from the detail, so the two cannot drift apart")

    plan_versions = set(x[0] for x in con.execute(
        "SELECT DISTINCT version_code FROM fact_plan").fetchall())
    want = {"BUD_FY26_V1", "FC_FY26_02", "FC_FY26_05", "FC_FY26_08"}
    reserved_leak = _one(con, "SELECT count(*) FROM fact_plan WHERE version_is_reserved")
    r.ok("P3-REC-09", "Planning data is complete and no reserved version leaks", "BLOCKING",
         want <= plan_versions and reserved_leak == 0,
         f"{sorted(plan_versions)}, reserved rows {reserved_leak}", f"{sorted(want)}, 0",
         "CTL-SCN-06. Superseded forecasts are retained; the Downside shell is not "
         "populated; Prior Year is derived, never stored (ADR-0004)")

    # The second balance sheet finding: the mapping agrees with the oracle exactly, so the
    # variance is between the SOURCE DATA and the anchor, not between the mapping and
    # either of them.
    caption_cross = con.execute("""
        SELECT fiscal_year, line_item, variance_usd_m FROM rec_balance_sheet
        WHERE line_item IN ('accrued', 'tax_payable') AND abs(variance_usd_m) > 0.01
    """).fetchall()
    worst_cross = max((abs(row[2]) for row in caption_cross), default=0.0)
    registered(r, exceptions, "P3-REC-11",
               "Special-period reclassifications stay inside one anchored caption",
               "WARNING", len(caption_cross), "balance sheet caption-years",
               f"worst {worst_cross:.3f}m. Kestrel special period 15 reallocates between "
               f"corporate income tax and trade tax, which moves an amount from the "
               f"income-taxes-payable caption into accrued liabilities. P2-FMT-09 tested "
               f"that a special period does not move the year's RESULT; it does not test "
               f"the balance sheet captions.")

    py_stored = _one(con, "SELECT count(*) FROM fact_plan WHERE scenario_code = 'PY'")
    r.ok("P3-REC-10", "Prior Year is not materialised as a scenario", "BLOCKING",
         py_stored == 0, py_stored, 0, "ADR-0004: derived by date offset from Actual")

    # ======================================================== business sense
    # A payroll mapping that lands in the wrong block still balances. These check that the
    # result means what it says.
    no_direct_labour = con.execute("""
        SELECT f.entity_code FROM fact_journal_line f
        JOIN dim_entity e ON e.entity_code = f.entity_code
        WHERE e.bu_code IN ('FC', 'IS', 'ES', 'AM')
        GROUP BY 1
        HAVING sum(CASE WHEN group_account IN ('515100','515200','515300')
                        THEN abs(signed_local_amount) ELSE 0 END) = 0""").fetchall()
    r.ok("P3-BR-01", "Every operating entity carries direct labour in cost of sales",
         "BLOCKING", not no_direct_labour, str(no_direct_labour), 0,
         "an entity that manufactures or delivers with no direct labour has had its "
         "payroll mapped into operating expenses")

    cos_share = _one(con, """
        SELECT coalesce(max(abs(share - 0.5)), 0) FROM (
            SELECT f.bu_code,
                   sum(CASE WHEN f.group_account
                            IN ('515100','515200','515300','520100')
                            THEN abs(f.signed_local_amount) ELSE 0 END)
                   / nullif(sum(CASE WHEN f.group_account IN
                            ('515100','515200','515300','520100','610100','610200','610300')
                            THEN abs(f.signed_local_amount) ELSE 0 END), 0) AS share
            FROM fact_journal_line f
            WHERE f.bu_code IN ('FC','IS','ES') GROUP BY 1)""")
    r.ok("P3-BR-02", "Payroll splits plausibly across the gross margin line", "WARNING",
         cos_share <= 0.40, round(cos_share, 4), 0.40,
         "the share of employment cost inside cost of sales stays inside a plausible band "
         "for a manufacturing or services unit; this is the shape CTL-MAP-04 protects")

    # Section 18 of the Phase 3 brief: no source-layer CTA and no balancing plug, ever.
    cta_at_source = _one(con, """
        SELECT count(*) FROM fact_journal_line
        WHERE group_account LIKE '33%' OR group_account LIKE '34%'
           OR group_account = '329100'""")
    r.ok("P3-BR-03", "No cumulative translation adjustment or reserve exists at layer 1",
         "BLOCKING", cta_at_source == 0, cta_at_source, 0,
         "CTA is created by translation at layer 5 and NCI by consolidation at layer 3. A "
         "source-layer balancing plug is a blocking defect (ADR-0017)")

    adj_rows = _one(con, "SELECT count(*) FROM stg_group_adjustment")
    r.ok("P3-ADJ-01", "Phase 3 posts no group adjustment", "BLOCKING", adj_rows == 0,
         adj_rows, 0,
         "the staging table exists so the consolidation engine has somewhere to raise a "
         "top-side entry; ingestion never writes to it")

    layers = [x[0] for x in con.execute(
        "SELECT DISTINCT layer_id FROM fact_journal_line").fetchall()]
    r.ok("P3-ADJ-02", "Phase 3 produces layer 1 only", "BLOCKING", layers == [1],
         str(layers), "[1]",
         "no elimination, no consolidation adjustment, no management layer, no CTA")

    # ============================================================ completeness
    missing_periods = con.execute("""
        SELECT e.entity_code, d.period_key
        FROM dim_entity e
        JOIN dim_date d ON d.accounting_period <= 12
          AND make_date(d.fiscal_year, d.accounting_period, 1) >= date_trunc('month', e.effective_from)
          AND d.period_key <= 202608
        LEFT JOIN (SELECT DISTINCT entity_code, period_key FROM fact_journal_line) f
          ON f.entity_code = e.entity_code AND f.period_key = d.period_key
        WHERE NOT e.is_elimination_entity AND f.entity_code IS NULL""").fetchall()
    r.ok("P3-CMP-01", "Every entity has every period from its effective date", "BLOCKING",
         not missing_periods, len(missing_periods), 0, str(missing_periods[:5]))

    early = _one(con, """
        SELECT count(*) FROM fact_journal_line f
        JOIN dim_entity e ON e.entity_code = f.entity_code
        WHERE f.posting_date < date_trunc('month', e.effective_from)""")
    r.ok("P3-CMP-02", "No entity posts before its consolidation effective date", "BLOCKING",
         early == 0, early, 0, "CTL-CON-02, tested at ingestion rather than at consolidation")

    coverage = dict(con.execute(
        "SELECT coverage_status, count(*) FROM rpt_group_account_coverage "
        "GROUP BY 1 ORDER BY 1").fetchall())
    r.add("P3-CMP-03", "Group accounts with no source postings", "INFO", "PASS",
          str(coverage), "reported, not failed",
          "CTL-MAP-06: an account created by translation or consolidation is expected to "
          "be empty at layer 1; an account a source chart maps to and never posts is not")
    return r


def write(results: Result) -> None:
    CONTROL_RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(CONTROL_RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(results)


def main() -> int:
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    res = run(con)
    write(res)
    report(res)
    return 1 if res.failed else 0


def report(res: Result) -> None:
    """Print the outcome, keeping a pipeline failure and a source finding apart."""
    npass = sum(1 for x in res if x["status"] == "PASS")
    print(f"{npass}/{len(res)} controls passed, {len(res.findings)} source findings, "
          f"{len(res.failed)} blocking failures")
    for x in res:
        if x["status"] != "PASS":
            tag = f"  [{x['defect_reference']}]" if x["defect_reference"] else ""
            print(f"  {x['status']:14} {x['severity']:8} {x['control_id']:12} "
                  f"{x['control_name'][:52]:54} {x['measured']} vs {x['threshold']}{tag}")


if __name__ == "__main__":
    sys.exit(main())
