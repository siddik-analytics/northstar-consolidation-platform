"""
Reverse mapping: which source account does a given ERP use for a given group account?

Phase 2 generates source-system data, so it must choose a *source* account for every
posting.  The approved Phase 1 mapping runs the other way (source -> group), so this
module inverts it and records the result as an **expected-mapping manifest**.

That manifest is the fixture Phase 3 is graded against: for every generated journal line
it states the source account posted, the line attributes that a conditional split rule
must read, and the group account the mapping engine is expected to produce.  Phase 2 does
NOT execute any mapping -- it only records what the answer should be.
"""

from __future__ import annotations

from .common import CONFIG, load_group_coa, load_source_coa, write_csv

ERPS = ["AURORA", "SABLE", "KESTREL"]

# Inverse of the conditional split rules in the approved source charts.
# (erp, group_account) -> (source_account, {line attribute: required value})
# The attribute is what the Phase 3 rule evaluator must read to resolve the split.
SPLIT_INVERSE: dict[tuple[str, str], tuple[str, dict[str, str]]] = {
    # --- Aurora: one payroll account spans the gross margin line -------------
    ("AURORA", "515100"): ("6100", {"dept_function": "PRODUCTION"}),
    ("AURORA", "515200"): ("6100", {"dept_function": "FIELD"}),
    ("AURORA", "520100"): ("6100", {"dept_function": "INDIRECT_OPS"}),
    ("AURORA", "515300"): ("6110", {"dept_function": "PRODUCTION"}),
    ("AURORA", "610200"): ("6110", {"dept_function": "SGA"}),
    ("AURORA", "610300"): ("6120", {"dept_function": "SGA"}),
    ("AURORA", "510300"): ("6150", {"dept_function": "PRODUCTION"}),
    ("AURORA", "610600"): ("6150", {"dept_function": "SGA"}),
    ("AURORA", "520200"): ("6200", {"dept_function": "PRODUCTION"}),
    ("AURORA", "620100"): ("6200", {"dept_function": "SGA"}),
    ("AURORA", "620200"): ("6210", {"dept_function": "SGA"}),
    ("AURORA", "520300"): ("5100", {"dept_function": "INDIRECT_OPS"}),
    ("AURORA", "630300"): ("6320", {"dept_function": "SGA"}),
    ("AURORA", "680300"): ("6820", {}),
    ("AURORA", "680400"): ("6320", {"dept_code": "D910"}),
    ("AURORA", "710200"): ("7000", {"asset_class": "FINANCE_LEASE"}),
    ("AURORA", "710100"): ("7000", {"asset_class": "PLANT"}),
    ("AURORA", "720200"): ("7010", {"asset_class": "SOFTWARE"}),
    ("AURORA", "730100"): ("7100", {"instrument_type": "TERM_LOAN"}),
    ("AURORA", "730200"): ("7100", {"instrument_type": "RCF"}),
    ("AURORA", "730300"): ("7100", {"instrument_type": "LEASE"}),
    ("AURORA", "740200"): ("7300", {"revaluation_flag": "TRUE"}),
    ("AURORA", "740100"): ("7300", {"revaluation_flag": "FALSE"}),
    ("AURORA", "125100"): ("1160", {"maturity_months": "12"}),
    ("AURORA", "225100"): ("2060", {"maturity_months": "12"}),
    ("AURORA", "590200"): ("5900", {"partner_bu": "IS"}),
    ("AURORA", "590100"): ("5900", {"partner_bu": "FC"}),
    # --- Sable ---------------------------------------------------------------
    ("SABLE", "630100"): ("62000", {"vendor_category": "AUDIT"}),
    ("SABLE", "630200"): ("62000", {"vendor_category": "LEGAL"}),
    ("SABLE", "630300"): ("62000", {"vendor_category": "CONSULTING"}),
    ("SABLE", "680300"): ("62000", {"dept_code": "D905"}),
    ("SABLE", "680400"): ("62000", {"dept_code": "D910"}),
    ("SABLE", "640100"): ("63000", {"expense_subtype": "ADVERTISING"}),
    ("SABLE", "640200"): ("63000", {"expense_subtype": "TRADESHOW"}),
    ("SABLE", "640300"): ("63000", {"expense_subtype": "COMMISSION"}),
    ("SABLE", "520400"): ("65100", {"dept_function": "FIELD"}),
    ("SABLE", "660200"): ("65100", {"dept_function": "SGA"}),
    ("SABLE", "520300"): ("60700", {"dept_function": "FIELD"}),
    ("SABLE", "610800"): ("60700", {"dept_function": "SGA"}),
    ("SABLE", "150100"): ("15000", {"asset_class": "LAND"}),
    ("SABLE", "150200"): ("15000", {"asset_class": "BUILDING"}),
    ("SABLE", "710200"): ("70000", {"asset_class": "FINANCE_LEASE"}),
    ("SABLE", "710100"): ("70000", {"asset_class": "PLANT"}),
    ("SABLE", "730100"): ("71000", {"instrument_type": "TERM_LOAN"}),
    ("SABLE", "730200"): ("71000", {"instrument_type": "RCF"}),
    ("SABLE", "730300"): ("71000", {"instrument_type": "LEASE"}),
    ("SABLE", "810100"): ("80000", {"tax_jurisdiction": "FEDERAL"}),
    ("SABLE", "810200"): ("80000", {"tax_jurisdiction": "STATE"}),
    ("SABLE", "810300"): ("80000", {"tax_jurisdiction": "FOREIGN"}),
    ("SABLE", "590100"): ("50900", {"partner_bu": "FC"}),
    ("SABLE", "590200"): ("50900", {"partner_bu": "IS"}),
    ("SABLE", "740100"): ("73000", {"revaluation_flag": "FALSE"}),
    ("SABLE", "740200"): ("73000", {"revaluation_flag": "TRUE"}),
    ("SABLE", "225100"): ("24900", {"maturity_months": "12"}),
    ("SABLE", "235100"): ("24900", {"maturity_months": "60"}),
    # --- Kestrel -------------------------------------------------------------
    ("KESTREL", "515100"): ("00091000", {"cost_center_function": "PRODUCTION"}),
    ("KESTREL", "515200"): ("00091000", {"cost_center_function": "FIELD"}),
    ("KESTREL", "520100"): ("00091000", {"cost_center_function": "INDIRECT_OPS"}),
    ("KESTREL", "610100"): ("00091000", {"cost_center_function": "SGA"}),
    ("KESTREL", "515300"): ("00091200", {"cost_center_function": "PRODUCTION"}),
    ("KESTREL", "610300"): ("00091200", {"cost_center_function": "SGA"}),
    ("KESTREL", "610200"): ("00091400", {"cost_center_function": "SGA"}),
    ("KESTREL", "510300"): ("00091600", {"cost_center_function": "PRODUCTION"}),
    ("KESTREL", "610600"): ("00091600", {"cost_center_function": "SGA"}),
    ("KESTREL", "520200"): ("00093000", {"cost_center_function": "PRODUCTION"}),
    ("KESTREL", "620100"): ("00093000", {"cost_center_function": "SGA"}),
    ("KESTREL", "620200"): ("00093200", {"cost_center_function": "SGA"}),
    ("KESTREL", "630100"): ("00094000", {"advisor_type": "AUDIT"}),
    ("KESTREL", "630200"): ("00094000", {"advisor_type": "LEGAL"}),
    ("KESTREL", "630300"): ("00094000", {"advisor_type": "CONSULTING"}),
    ("KESTREL", "680300"): ("00098200", {}),
    ("KESTREL", "680400"): ("00098400", {}),
    ("KESTREL", "650100"): ("00095000", {"expense_subtype": "LICENCE"}),
    ("KESTREL", "650200"): ("00095000", {"expense_subtype": "SERVICES"}),
    ("KESTREL", "710100"): ("00092000", {"asset_class": "PLANT"}),
    ("KESTREL", "710200"): ("00092000", {"asset_class": "FINANCE_LEASE"}),
    ("KESTREL", "720100"): ("00092200", {"asset_class": "INTANGIBLE"}),
    ("KESTREL", "720200"): ("00092200", {"asset_class": "SOFTWARE"}),
    ("KESTREL", "730100"): ("00100000", {"instrument_type": "TERM_LOAN"}),
    ("KESTREL", "730200"): ("00100000", {"instrument_type": "RCF"}),
    ("KESTREL", "730300"): ("00100000", {"instrument_type": "LEASE"}),
    ("KESTREL", "795200"): ("00100000", {"instrument_type": "AFFILIATE"}),
    ("KESTREL", "795100"): ("00100200", {"instrument_type": "AFFILIATE"}),
    ("KESTREL", "735100"): ("00100200", {"instrument_type": "EXTERNAL"}),
    ("KESTREL", "410100"): ("00080000", {"product_group": "EQUIPMENT"}),
    ("KESTREL", "410200"): ("00080000", {"product_group": "COMPONENT"}),
    ("KESTREL", "435100"): ("00081500", {"income_type": "OPERATING"}),
    ("KESTREL", "740100"): ("00081500", {"income_type": "FX"}),
    ("KESTREL", "745100"): ("00081500", {"income_type": "DISPOSAL"}),
    ("KESTREL", "750100"): ("00081500", {"income_type": "OTHER"}),
    ("KESTREL", "150100"): ("00030000", {"asset_class": "LAND"}),
    ("KESTREL", "150200"): ("00030000", {"asset_class": "BUILDING"}),
    ("KESTREL", "121100"): ("00017000", {"accrual_type": "CONTRACT"}),
    ("KESTREL", "140100"): ("00017000", {"accrual_type": "PREPAID"}),
    ("KESTREL", "125100"): ("00016500", {"maturity_months": "12"}),
    ("KESTREL", "225100"): ("00061500", {"maturity_months": "12"}),
    ("KESTREL", "235100"): ("00061500", {"maturity_months": "60"}),
    ("KESTREL", "490200"): ("00089000", {"partner_bu": "IS"}),
    ("KESTREL", "490100"): ("00089000", {"partner_bu": "FC"}),
    ("KESTREL", "530100"): ("00081000", {"presentation": "TOTAL_COST_METHOD"}),
    ("KESTREL", "680200"): ("00098000", {"cost_type": "FACILITY"}),
    ("KESTREL", "680100"): ("00098000", {"cost_type": "SEVERANCE"}),
}

# Accounts a given ERP genuinely does not have. Postings that would need them are
# redirected to the stated substitute, which is a real chart-of-accounts difference and
# the reason `CTL-MAP-06` reports group accounts with no source.
NOT_AVAILABLE = {
    # --- Sable: job-cost chart, no finished goods and a thin accrual structure --------
    ("SABLE", "215300"): "215600",     # no accrued professional fees account
    ("SABLE", "215400"): "215600",     # no warranty accrual account
    ("SABLE", "215500"): "215600",     # no restructuring accrual account
    ("SABLE", "430100"): "435100",     # freight is inside one reimbursables account
    ("SABLE", "440200"): "440100",     # one credits-and-allowances account
    ("SABLE", "130300"): "130200",     # project and service work holds no finished goods
    # --- Kestrel: German nature-of-expense chart, no cost-of-sales detail -------------
    ("KESTREL", "420300"): "420100",   # turnarounds are not separately captioned
    ("KESTREL", "425200"): "425100",   # one project revenue account
    ("KESTREL", "430100"): "435100",   # freight billed sits in other operating income
    ("KESTREL", "440100"): "440200",   # one sales-deductions account
    ("KESTREL", "520300"): "510100",   # consumables inside Materialaufwand
    ("KESTREL", "520400"): "510300",   # equipment hire inside bezogene Leistungen
    ("KESTREL", "525100"): "510300",   # freight inbound inside bezogene Leistungen
    ("KESTREL", "525200"): "510100",   # duties inside Materialaufwand
    ("KESTREL", "530200"): "510100",   # warranty cost inside Materialaufwand
    ("KESTREL", "535100"): "510300",   # no contract EAC account
    ("KESTREL", "610400"): "610100",   # bonus inside Loehne und Gehaelter
    ("KESTREL", "610700"): "670400",   # recruitment inside sonstige Aufwendungen
    ("KESTREL", "610800"): "670400",   # training inside sonstige Aufwendungen
    # --- Aurora: US chart, one federal income tax account ----------------------------
    ("AURORA", "810300"): "810100",
    # Sable has a single affiliate receivables account and does not separate the group
    # treasury current account from ordinary intercompany trade balances.
    ("SABLE", "125100"): "120500",
    ("SABLE", "175100"): "120500",
    # Kestrel books all intercompany cost to one account under Materialaufwand
    ("KESTREL", "590200"): "590100",
}


class SourceMap:
    def __init__(self):
        self.group = load_group_coa()
        self.by_erp: dict[str, dict[str, dict]] = {}
        self.reverse: dict[tuple[str, str], tuple[str, dict]] = {}
        for erp in ERPS:
            rows = load_source_coa(erp)
            self.by_erp[erp] = {r["source_account"]: r for r in rows}
            for r in rows:
                key = (erp, r["group_account"])
                # DIRECT beats MERGE beats the default branch of a SPLIT
                rank = {"DIRECT": 0, "SPLIT": 1, "DERIVED": 1, "MERGE": 2}[r["mapping_type"]]
                cur = self.reverse.get(key)
                if cur is None or rank < cur[1].get("_rank", 9):
                    self.reverse[key] = (r["source_account"], {"_rank": rank})
        for (erp, ga), (sa, attrs) in SPLIT_INVERSE.items():
            self.reverse[(erp, ga)] = (sa, {**attrs, "_rank": -1})

    def resolve(self, erp: str, group_account: str) -> tuple[str, dict[str, str]] | None:
        ga = NOT_AVAILABLE.get((erp, group_account), group_account)
        hit = self.reverse.get((erp, ga))
        if hit is None:
            return None
        sa, attrs = hit
        return sa, {k: v for k, v in attrs.items() if not k.startswith("_")}

    def expected_group(self, erp: str, group_account: str) -> str:
        """The group account a Phase 3 mapping will actually produce for this posting."""
        return NOT_AVAILABLE.get((erp, group_account), group_account)

    def coverage_gaps(self, erp: str, accounts) -> list[str]:
        return sorted(a for a in accounts if self.resolve(erp, a) is None)

    def write_manifest(self, used: dict[str, set[str]]) -> int:
        """The expected-mapping fixture Phase 3 is validated against."""
        rows = []
        for erp in ERPS:
            for ga in sorted(used.get(erp, set())):
                hit = self.resolve(erp, ga)
                if hit is None:
                    continue
                sa, attrs = hit
                src = self.by_erp[erp][sa]
                rows.append([
                    erp, sa, src["source_account_name"], src["mapping_type"],
                    NOT_AVAILABLE.get((erp, ga), ga), ga,
                    ";".join(f"{k}={v}" for k, v in sorted(attrs.items())) or "",
                    self.group[ga]["account_name"], self.group[ga]["statement"],
                    "TRUE" if (erp, ga) in NOT_AVAILABLE else "FALSE",
                ])
        write_csv(CONFIG / "generation" / "expected_mapping_manifest.csv",
                  ["erp_system", "source_account", "source_account_name", "mapping_type",
                   "expected_group_account", "requested_group_account",
                   "required_line_attributes", "group_account_name", "statement",
                   "substituted_because_unavailable"], rows)
        return len(rows)
