"""
Prove that a rebuild changed no money.

    python tools/financial_invariance.py --snapshot data/95_invariance/before
    ... rebuild ...
    python tools/financial_invariance.py --snapshot data/95_invariance/after
    python tools/financial_invariance.py --compare data/95_invariance/before data/95_invariance/after

An identifier correction is supposed to move identifiers and nothing else. Saying so is not
proof; a digest moving is not disproof either, because a digest moves when a build id moves.
What settles it is a value-level comparison at the grain the business reads, joined on the
business key, with a required difference of exactly zero.

Each spec below declares the grain it compares on and the columns that carry money (or FTE,
or a ratio). The comparison is a full outer join, so a row that appears, disappears or moves
grain is a failure in its own right and cannot hide inside a matching total.

Deliberately excluded from the compared columns: anything that IS an identifier. The point of
the exercise is that identifiers may change. `capex_by_project` is therefore compared on
entity, period and asset class -- the economic grain of a capital project -- and never on
`project_id`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DUCKDB_PATH = ROOT / "data" / "20_warehouse" / "northstar.duckdb"

#: name -> (key columns, value columns, SQL). The SQL must return key + value columns only.
SPECS: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {

    # ------------------------------------------------------------------ the ledger itself
    "journal_by_month_entity_account": (
        ("period_key", "entity_code", "group_account", "layer_id"),
        ("amount_usd", "amount_local", "line_count"),
        """SELECT period_key, entity_code, group_account, layer_id,
                  round(sum(amount_usd), 2)   AS amount_usd,
                  round(sum(amount_local), 2) AS amount_local,
                  count(*)                    AS line_count
           FROM fact_consol_journal GROUP BY ALL"""),

    "financials_by_month_entity_account": (
        ("period_key", "entity_code", "group_account", "layer_id"),
        ("amount_usd", "amount_local", "fx_revaluation_usd"),
        """SELECT period_key, entity_code, group_account, layer_id,
                  round(sum(amount_usd), 2)         AS amount_usd,
                  round(sum(amount_local), 2)       AS amount_local,
                  round(sum(fx_revaluation_usd), 2) AS fx_revaluation_usd
           FROM fact_financials GROUP BY ALL"""),

    # ------------------------------------------------------------------ reporting marts
    "mart_measure_grain": (
        ("basis", "version_code", "entity_code", "bu_code", "measure_code", "period_key"),
        ("mtd_usd", "ytd_usd", "fy_usd"),
        """SELECT basis, version_code, entity_code, bu_code, measure_code, period_key,
                  round(sum(mtd_usd), 2) AS mtd_usd,
                  round(sum(ytd_usd), 2) AS ytd_usd,
                  round(sum(fy_usd),  2) AS fy_usd
           FROM mart_financial_ytd GROUP BY ALL"""),

    "mart_account_grain": (
        ("basis", "version_code", "entity_code", "bu_code", "cost_center_code",
         "group_account", "period_key"),
        ("amount_usd",),
        """SELECT basis, version_code, entity_code, bu_code, cost_center_code,
                  group_account, period_key, round(sum(amount_usd), 2) AS amount_usd
           FROM mart_financial_monthly GROUP BY ALL"""),

    "mart_variance": (
        ("comparison_code", "basis", "entity_code", "bu_code", "measure_code", "period_key"),
        ("base_mtd", "base_ytd", "base_fy", "comp_mtd", "comp_ytd", "comp_fy",
         "var_mtd_usd", "var_ytd_usd", "var_fy_usd", "var_ytd_pct", "var_fy_pct"),
        """SELECT comparison_code, basis, entity_code, bu_code, measure_code, period_key,
                  round(sum(base_mtd), 2)    AS base_mtd,
                  round(sum(base_ytd), 2)    AS base_ytd,
                  round(sum(base_fy), 2)     AS base_fy,
                  round(sum(comp_mtd), 2)    AS comp_mtd,
                  round(sum(comp_ytd), 2)    AS comp_ytd,
                  round(sum(comp_fy), 2)     AS comp_fy,
                  round(sum(var_mtd_usd), 2) AS var_mtd_usd,
                  round(sum(var_ytd_usd), 2) AS var_ytd_usd,
                  round(sum(var_fy_usd), 2)  AS var_fy_usd,
                  round(sum(var_ytd_pct), 6) AS var_ytd_pct,
                  round(sum(var_fy_pct), 6)  AS var_fy_pct
           FROM mart_variance GROUP BY ALL"""),

    # Prior year on its own. The version this correction gives a governed identity to, at the
    # grain a report reads it, so "PY is unchanged" is a measured statement rather than an
    # inference from a total that happens to include it.
    "prior_year_measure_grain": (
        ("basis", "entity_code", "bu_code", "measure_code", "period_key"),
        ("mtd_usd", "ytd_usd", "fy_usd"),
        """SELECT basis, entity_code, bu_code, measure_code, period_key,
                  round(sum(mtd_usd), 2) AS mtd_usd,
                  round(sum(ytd_usd), 2) AS ytd_usd,
                  round(sum(fy_usd),  2) AS fy_usd
           FROM mart_financial_ytd WHERE version_code = 'PY_DERIVED' GROUP BY ALL"""),

    "prior_year_comparison": (
        ("basis", "entity_code", "bu_code", "measure_code", "period_key"),
        ("base_ytd", "comp_ytd", "var_ytd_usd", "var_ytd_pct", "var_fy_usd"),
        """SELECT basis, entity_code, bu_code, measure_code, period_key,
                  round(sum(base_ytd), 2)    AS base_ytd,
                  round(sum(comp_ytd), 2)    AS comp_ytd,
                  round(sum(var_ytd_usd), 2) AS var_ytd_usd,
                  round(sum(var_ytd_pct), 6) AS var_ytd_pct,
                  round(sum(var_fy_usd), 2)  AS var_fy_usd
           FROM mart_variance WHERE comparison_code = 'ACT_VS_PY' GROUP BY ALL"""),

    "mart_balance_sheet": (
        ("period_key", "account_class", "caption"),
        ("balance_usd", "movement_usd", "yoy_movement_usd"),
        """SELECT period_key, account_class, caption,
                  round(sum(balance_usd), 2)      AS balance_usd,
                  round(sum(movement_usd), 2)     AS movement_usd,
                  round(sum(yoy_movement_usd), 2) AS yoy_movement_usd
           FROM mart_balance_sheet GROUP BY ALL"""),

    "mart_cash_flow": (
        ("period_key",),
        ("opening_cash_usd", "operating_cash_flow_usd", "investing_cash_flow_usd",
         "financing_cash_flow_usd", "fx_effect_on_cash_usd", "net_change_in_cash_usd",
         "closing_cash_usd", "liquidity_usd"),
        """SELECT period_key,
                  round(opening_cash_usd, 2)        AS opening_cash_usd,
                  round(operating_cash_flow_usd, 2) AS operating_cash_flow_usd,
                  round(investing_cash_flow_usd, 2) AS investing_cash_flow_usd,
                  round(financing_cash_flow_usd, 2) AS financing_cash_flow_usd,
                  round(fx_effect_on_cash_usd, 2)   AS fx_effect_on_cash_usd,
                  round(net_change_in_cash_usd, 2)  AS net_change_in_cash_usd,
                  round(closing_cash_usd, 2)        AS closing_cash_usd,
                  round(liquidity_usd, 2)           AS liquidity_usd
           FROM mart_cash_flow"""),

    "mart_covenants": (
        ("period_key",),
        ("covenant_ebitda_usd", "adjusted_ebitda_usd", "net_debt_usd", "covenant_debt_usd",
         "net_leverage", "headroom_turns", "headroom_usd", "in_compliance"),
        """SELECT period_key,
                  round(covenant_ebitda_usd, 2)  AS covenant_ebitda_usd,
                  round(adjusted_ebitda_usd, 2)  AS adjusted_ebitda_usd,
                  round(net_debt_usd, 2)         AS net_debt_usd,
                  round(covenant_debt_usd, 2)    AS covenant_debt_usd,
                  round(net_leverage, 6)         AS net_leverage,
                  round(headroom_turns, 6)       AS headroom_turns,
                  round(headroom_usd, 2)         AS headroom_usd,
                  CAST(in_compliance AS INTEGER) AS in_compliance
           FROM mart_covenants"""),

    "mart_working_capital": (
        ("period_key",),
        ("ar_usd", "inventory_usd", "ap_usd", "nwc_usd", "dso_days", "dio_days",
         "dpo_days", "ccc_days"),
        """SELECT period_key,
                  round(ar_usd, 2)        AS ar_usd,
                  round(inventory_usd, 2) AS inventory_usd,
                  round(ap_usd, 2)        AS ap_usd,
                  round(nwc_usd, 2)       AS nwc_usd,
                  round(dso_days, 4)      AS dso_days,
                  round(dio_days, 4)      AS dio_days,
                  round(dpo_days, 4)      AS dpo_days,
                  round(ccc_days, 4)      AS ccc_days
           FROM mart_working_capital"""),

    "mart_debt": (
        ("period_key", "instrument_id"),
        ("opening_principal_usd", "closing_principal_usd", "interest_expense_usd",
         "commitment_fee_usd"),
        """SELECT period_key, instrument_id,
                  round(sum(opening_principal_usd), 2) AS opening_principal_usd,
                  round(sum(closing_principal_usd), 2) AS closing_principal_usd,
                  round(sum(interest_expense_usd), 2)  AS interest_expense_usd,
                  round(sum(commitment_fee_usd), 2)    AS commitment_fee_usd
           FROM mart_debt GROUP BY ALL"""),

    "mart_headcount": (
        ("period_key", "entity_code", "department_code", "job_family_code"),
        ("fte_opening", "fte_closing", "headcount_closing", "base_salary_month_usd"),
        """SELECT period_key, entity_code, department_code, job_family_code,
                  round(sum(fte_opening), 4)           AS fte_opening,
                  round(sum(fte_closing), 4)           AS fte_closing,
                  sum(headcount_closing)               AS headcount_closing,
                  round(sum(base_salary_month_usd), 2) AS base_salary_month_usd
           FROM mart_headcount GROUP BY ALL"""),

    "mart_fx": (
        ("period_key", "currency_code"),
        ("avg_rate", "close_rate", "revenue_usd", "revenue_constant_ccy_usd",
         "cta_movement_usd", "cta_group_usd", "cta_nci_usd"),
        """SELECT period_key, currency_code,
                  round(avg_rate, 8)                 AS avg_rate,
                  round(close_rate, 8)               AS close_rate,
                  round(revenue_usd, 2)              AS revenue_usd,
                  round(revenue_constant_ccy_usd, 2) AS revenue_constant_ccy_usd,
                  round(cta_movement_usd, 2)         AS cta_movement_usd,
                  round(cta_group_usd, 2)            AS cta_group_usd,
                  round(cta_nci_usd, 2)              AS cta_nci_usd
           FROM mart_fx"""),

    "mart_layer_bridge": (
        ("fiscal_year", "layer_id"),
        ("ebitda_usd", "net_income_usd", "total_assets_movement_usd",
         "total_equity_movement_usd", "entries", "legs"),
        """SELECT fiscal_year, layer_id,
                  round(sum(ebitda_usd), 2)                AS ebitda_usd,
                  round(sum(net_income_usd), 2)            AS net_income_usd,
                  round(sum(total_assets_movement_usd), 2) AS total_assets_movement_usd,
                  round(sum(total_equity_movement_usd), 2) AS total_equity_movement_usd,
                  sum(entries)                             AS entries,
                  sum(legs)                                AS legs
           FROM mart_consolidation_bridge GROUP BY ALL"""),

    # ------------------------------------------------------- capex, at its ECONOMIC grain
    # Compared on entity, month and asset class rather than on project_id: the identifier is
    # exactly what this correction changes, so joining on it would compare nothing. The row
    # count is carried as a compared value, so a correction that split or merged projects
    # would fail here rather than pass on totals alone.
    "capex_by_entity_month_class": (
        ("period_key", "entity_code", "asset_class"),
        ("spend_usd", "approved_usd", "project_rows"),
        """SELECT period_key, entity_code, asset_class,
                  round(sum(spend_usd), 2)    AS spend_usd,
                  round(sum(approved_usd), 2) AS approved_usd,
                  count(*)                    AS project_rows
           FROM mart_capex GROUP BY ALL"""),

    "capex_source_by_entity_month_class": (
        ("period_key", "entity_code", "asset_class"),
        ("spend_local", "approved_local", "project_rows"),
        """SELECT period_key, entity_code, asset_class,
                  round(sum(spend_local), 2)           AS spend_local,
                  round(sum(approved_amount_local), 2) AS approved_local,
                  count(*)                             AS project_rows
           FROM fact_capex_project GROUP BY ALL"""),

    "fixed_assets_by_entity_class": (
        ("entity_code", "asset_class", "group_account"),
        ("cost_local", "asset_rows"),
        """SELECT entity_code, asset_class, group_account,
                  round(sum(cost_local), 2) AS cost_local,
                  count(*)                  AS asset_rows
           FROM ref_fixed_asset GROUP BY ALL"""),
}


def snapshot(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    for name, (_, _, sql) in SPECS.items():
        path = out_dir / f"{name}.parquet"
        con.execute(f"COPY ({sql} ORDER BY ALL) TO '{path.as_posix()}' (FORMAT PARQUET)")
        rows = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
        print(f"  {name:38} {rows:>8,} rows")
    con.close()
    print(f"snapshot written to {out_dir}")


def compare(before: Path, after: Path) -> int:
    con = duckdb.connect()
    failures = 0
    print(f"{'comparison':40}{'rows':>9}{'only<':>7}{'only>':>7}"
          f"{'max abs diff':>15}  verdict")
    print("-" * 92)
    for name, (keys, values, _) in SPECS.items():
        b, a = before / f"{name}.parquet", after / f"{name}.parquet"
        if not b.exists() or not a.exists():
            print(f"{name:40}{'MISSING SNAPSHOT':>45}")
            failures += 1
            continue
        on = " AND ".join(f"b.{k} IS NOT DISTINCT FROM a.{k}" for k in keys)
        diffs = ", ".join(
            f"abs(coalesce(b.{v}, 0) - coalesce(a.{v}, 0)) AS d_{v}" for v in values)
        greatest = ", ".join(f"coalesce(d_{v}, 0)" for v in values)
        row = con.execute(f"""
            WITH b AS (SELECT * FROM read_parquet('{b.as_posix()}')),
                 a AS (SELECT * FROM read_parquet('{a.as_posix()}')),
                 j AS (SELECT b.{keys[0]} AS bk, a.{keys[0]} AS ak, {diffs}
                       FROM b FULL OUTER JOIN a ON {on})
            SELECT count(*),
                   count(*) FILTER (WHERE ak IS NULL AND bk IS NOT NULL),
                   count(*) FILTER (WHERE bk IS NULL AND ak IS NOT NULL),
                   coalesce(max(greatest({greatest})), 0)
            FROM j
        """).fetchone()
        rows, only_b, only_a, max_diff = row
        ok = only_b == 0 and only_a == 0 and max_diff == 0
        failures += 0 if ok else 1
        print(f"{name:40}{rows:>9,}{only_b:>7}{only_a:>7}{max_diff:>15.6f}"
              f"  {'PASS' if ok else 'FAIL'}")
    print("-" * 92)
    print("ZERO ECONOMIC DRIFT" if not failures else f"{failures} comparison(s) FAILED")
    con.close()
    return failures


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", metavar="DIR")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    args = ap.parse_args(argv)
    if args.snapshot:
        snapshot(Path(args.snapshot))
        return 0
    if args.compare:
        return 1 if compare(Path(args.compare[0]), Path(args.compare[1])) else 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
