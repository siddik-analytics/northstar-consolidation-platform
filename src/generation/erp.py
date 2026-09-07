"""
Native ERP extract renderers.

The three source systems stay genuinely different here -- this is the last point at which
that difference is created, and Phase 3 is the first point at which it is removed.  Nothing
in this module normalises anything.

  Aurora   modern cloud ERP.  One signed amount, credits negative, UTF-8, ISO dates.
  Sable    project ERP.  Amounts carry the account's NATURAL sign, so the reader must
           know each account's normal balance to recover a signed value.  Thousands
           separators, US dates, a pipe-delimited dimension string.
  Kestrel  legacy European ERP.  Separate debit and credit columns, both positive.
           Windows-1252, semicolon-delimited, comma decimals, DD.MM.YYYY dates,
           zero-padded text account keys, periods 13-16 for year-end adjustments, and a
           legacy EUR group-currency column that must never be used (CTL-FX-06).
"""

from __future__ import annotations

import csv
from pathlib import Path

from .common import RAW, load_source_coa

# column index into the journal line tuple produced by journals.py
(I_ENT, I_ERP, I_CC, I_PERIOD, I_JID, I_LINE, I_DATE, I_DOC, I_DOCTYPE, I_EVENT, I_DESC,
 I_SRC, I_GRP, I_COSTCTR, I_DEPT, I_FUNC, I_CCY, I_AMT, I_PARTNER, I_CUST, I_PROD,
 I_ATTRS) = range(22)


def _fmt_us(x: float) -> str:
    return f"{x:,.2f}"


def _fmt_de(x: float) -> str:
    return f"{abs(x):,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


class ErpWriter:
    """Base: groups lines into one file per entity (or company code) per period."""

    header: list[str] = []
    encoding = "utf-8"
    delimiter = ","
    subdir = ""

    def __init__(self, source_coa: list[dict]):
        self.names = {r["source_account"]: r["source_account_name"] for r in source_coa}
        self.normal = {r["source_account"]: r["source_normal_balance"] for r in source_coa}
        self.local_names = {r["source_account"]: r.get("source_account_name_local",
                                                       r["source_account_name"])
                            for r in source_coa}

    def filename(self, entity: str, company: str, period: int) -> str:
        raise NotImplementedError

    def row(self, ln: tuple) -> list:
        raise NotImplementedError

    def write(self, lines: list[tuple]) -> list[tuple[str, int]]:
        buckets: dict[tuple[str, str, int], list[tuple]] = {}
        for ln in lines:
            buckets.setdefault((ln[I_ENT], ln[I_CC], ln[I_PERIOD]), []).append(ln)
        out = []
        base = RAW / self.subdir
        base.mkdir(parents=True, exist_ok=True)
        for (entity, company, period), group in sorted(buckets.items()):
            path = base / self.filename(entity, company, period)
            with open(path, "w", newline="", encoding=self.encoding,
                      errors="replace") as f:
                w = csv.writer(f, delimiter=self.delimiter, lineterminator="\n",
                               quoting=csv.QUOTE_MINIMAL)
                w.writerow(self.header)
                for ln in group:
                    w.writerow(self.row(ln))
            out.append((path.name, len(group)))
        return out


class AuroraWriter(ErpWriter):
    subdir = "aurora"
    header = ["SUBSIDIARY", "PERIOD", "TRANDATE", "JOURNAL_ID", "LINE_ID", "ACCOUNT",
              "ACCOUNT_NAME", "DEPARTMENT", "CLASS", "LOCATION", "MEMO", "DOCUMENT_NUMBER",
              "DOCUMENT_TYPE", "CURRENCY", "AMOUNT", "AMOUNT_USD_SYSTEM",
              "SUBSIDIARY_PARTNER", "CUSTOMER", "ITEM", "LINE_ATTRIBUTES"]

    def __init__(self, source_coa, usd_rate):
        super().__init__(source_coa)
        self.usd_rate = usd_rate

    def filename(self, entity, company, period):
        return f"AURORA_GL_{company}_{period}.csv"

    def row(self, ln):
        # Aurora's own USD column uses its internal rate table and is deliberately
        # slightly stale. Phase 3 must ignore it (CTL-FX-06).
        rate = self.usd_rate(ln[I_CCY], ln[I_PERIOD])
        return [ln[I_ENT], ln[I_PERIOD] % 100, ln[I_DATE], ln[I_JID], ln[I_LINE],
                ln[I_SRC], self.names.get(ln[I_SRC], ""), f"DEPT-{ln[I_DEPT]}",
                ln[I_EVENT], f"LOC-{ln[I_ENT][-3:]}", ln[I_DESC], ln[I_DOC], ln[I_DOCTYPE],
                ln[I_CCY], f"{ln[I_AMT]:.2f}", f"{ln[I_AMT] * rate:.2f}",
                ln[I_PARTNER], ln[I_CUST], ln[I_PROD], ln[I_ATTRS]]


class SableWriter(ErpWriter):
    subdir = "sable"
    header = ["COMPANY", "FISCALYEAR", "FISCALPERIOD", "POSTINGDATE", "JOURNALID",
              "LINENUM", "MAINACCOUNT", "ACCOUNTNAME", "NORMALBALANCE", "DIMENSIONSTRING",
              "DESCRIPTION", "DOCUMENTNUM", "DOCUMENTTYPE", "TRANSACTIONTYPE",
              "CURRENCYCODE", "AMOUNT", "CUSTOMERID", "ITEMID", "LINEATTRIBUTES"]

    def filename(self, entity, company, period):
        return f"SABLE_LEDGERTRANS_{company}_{period}.csv"

    def row(self, ln):
        nb = self.normal.get(ln[I_SRC], "D")
        amount = ln[I_AMT] if nb == "D" else -ln[I_AMT]
        d = ln[I_DATE]
        us_date = f"{d[5:7]}/{d[8:10]}/{d[0:4]}"
        dim = f"{ln[I_ENT][-3:]}|{ln[I_DEPT]}|{ln[I_PROD] or 'NOPROJ'}|{ln[I_PARTNER] or 'NONE'}"
        return [ln[I_CC], ln[I_PERIOD] // 100, ln[I_PERIOD] % 100, us_date, ln[I_JID],
                ln[I_LINE], ln[I_SRC], self.names.get(ln[I_SRC], ""), nb, dim,
                ln[I_DESC], ln[I_DOC], ln[I_DOCTYPE], ln[I_EVENT], ln[I_CCY],
                _fmt_us(amount), ln[I_CUST], ln[I_PROD], ln[I_ATTRS]]


class KestrelWriter(ErpWriter):
    subdir = "kestrel"
    encoding = "cp1252"
    delimiter = ";"
    header = ["BUKRS", "GJAHR", "MONAT", "BUDAT", "BELNR", "BUZEI", "HKONT", "TXT50",
              "SAKNR_BEZ", "KOSTL", "PRCTR", "SEGMENT", "VBUND", "BSCHL", "WAERS",
              "SOLL", "HABEN", "DMBTR_KONZERN_EUR", "KUNNR", "MATNR", "ZUONR"]

    def __init__(self, source_coa, eur_rate):
        super().__init__(source_coa)
        self.eur_rate = eur_rate

    def filename(self, entity, company, period):
        return f"KESTREL_BSEG_{company}_{period}.csv"

    def row(self, ln):
        amt = ln[I_AMT]
        soll = _fmt_de(amt) if amt >= 0 else ""
        haben = _fmt_de(amt) if amt < 0 else ""
        posting_key = "40" if amt >= 0 else "50"
        d = ln[I_DATE]
        de_date = f"{d[8:10]}.{d[5:7]}.{d[0:4]}"
        # Legacy group-currency column inherited from Halden's pre-acquisition parent.
        # It is a EUR translation at Kestrel's own rate and must never be used (CTL-FX-06).
        eur = amt * self.eur_rate(ln[I_CCY], ln[I_PERIOD])
        period = ln[I_PERIOD] % 100
        if ln[I_EVENT] == "YEAR_END_CLOSE":
            period = 13                       # special period for year-end adjustments
        return [ln[I_CC], ln[I_PERIOD] // 100, period, de_date, ln[I_JID], ln[I_LINE],
                ln[I_SRC], ln[I_DESC][:50],
                self.local_names.get(ln[I_SRC], "")[:50],
                ln[I_COSTCTR], f"PC{ln[I_ENT][-3:]}", f"SEG-{ln[I_DEPT]}",
                ln[I_PARTNER], posting_key, ln[I_CCY], soll, haben, _fmt_de(eur),
                ln[I_CUST], ln[I_PROD], ln[I_ATTRS]]


def make_writers(rate_fn):
    """rate_fn(currency, period_key, target) -> rate to `target` currency."""
    return {
        "AURORA": AuroraWriter(load_source_coa("aurora"),
                               lambda c, p: rate_fn(c, p, "USD_STALE")),
        "SABLE": SableWriter(load_source_coa("sable")),
        "KESTREL": KestrelWriter(load_source_coa("kestrel"),
                                 lambda c, p: rate_fn(c, p, "EUR")),
    }
