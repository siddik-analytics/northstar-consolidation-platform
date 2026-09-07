"""
Phase 2 build orchestrator.

    python -m src.generation.build            full deterministic build
    python -m src.generation.build --quick    reference data only, no journals

Writes native ERP extracts to data/raw/, reference and planning data to data/reference/,
small committed samples to data/samples/, and a manifest with row counts and SHA-256
checksums so a rebuild can be proven identical.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import datasets, investments, masters, translation
from .common import (DATA, FAULTS, RAW, REFERENCE, SAMPLES, ROOT, load_anchor, write_csv)
from .erp import make_writers
from .fx import build_rate_series, rate_lookup, write_reference as write_fx
from .journals import COLUMNS, JournalGenerator
from .mapping import SourceMap
from .series import SeriesBuilder
from .targets import write_targets

MANIFEST = DATA / "build_manifest.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, compression="zstd")


def _sample(df: pd.DataFrame, path: Path, n: int = 300) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.head(n).to_csv(path, index=False, lineterminator="\n")


def run(quick: bool = False) -> dict:
    t0 = time.time()
    counts: dict[str, int] = {}
    sb = SeriesBuilder()
    rows = sb.build_actuals()
    counts["entity_months"] = len(rows)

    # ---------------- reference and master data --------------------------
    counts.update(write_fx(sb.ent))
    counts.update(masters.write_all(sb.m))
    rates = rate_lookup(build_rate_series())

    def rate_fn(ccy: str, period_key: int, target: str) -> float:
        rs = "FORECAST" if period_key // 100 == 2026 else "ACTUAL"
        usd = rates[(ccy, period_key, "CLOSE", rs)]
        if target == "USD_STALE":
            # Aurora translates on its own month-lag rate table; deliberately not the
            # rate the consolidation engine will use.
            prev = period_key - 1 if period_key % 100 > 1 else (period_key // 100 - 1) * 100 + 12
            return rates.get((ccy, prev, "CLOSE", rs), usd)
        if target == "EUR":
            return usd / rates[("EUR", period_key, "CLOSE", rs)]
        return usd

    cost_centres = masters.build_cost_centres()
    customers = masters.build_customers(sb.m)
    products = masters.build_products()
    employees = masters.build_employees(sb.m)

    plan = datasets.build_plan(sb)
    _write_parquet(pd.DataFrame(plan), REFERENCE / "plan_fact.parquet")
    counts["plan_fact"] = len(plan)

    hc = datasets.build_headcount(sb, employees)
    _write_parquet(pd.DataFrame(hc), REFERENCE / "headcount_fact.parquet")
    counts["headcount_fact"] = len(hc)

    proj, assets = datasets.build_capex(sb)
    write_csv(REFERENCE / "capex_projects.csv", list(proj[0]), [list(r.values()) for r in proj])
    write_csv(REFERENCE / "fixed_assets.csv", list(assets[0]), [list(r.values()) for r in assets])
    counts["capex_projects"], counts["fixed_assets"] = len(proj), len(assets)

    debt = datasets.build_debt(sb)
    write_csv(REFERENCE / "debt_schedule.csv", list(debt[0]), [list(r.values()) for r in debt])
    counts["debt_schedule"] = len(debt)

    util = datasets.build_revolver_utilisation(sb)
    write_csv(REFERENCE / "revolver_utilisation.csv", list(util[0]),
              [list(r.values()) for r in util])
    counts["revolver_utilisation"] = len(util)

    counts["investment_rollforward"] = investments.write_reference()
    counts.update(translation.write_reference(sb, rows))
    icx, ich = datasets.build_ic_inventory(sb)
    write_csv(REFERENCE / "ic_inventory_transactions.csv", list(icx[0]),
              [list(r.values()) for r in icx])
    write_csv(REFERENCE / "ic_inventory_holdings.csv", list(ich[0]),
              [list(r.values()) for r in ich])
    counts["ic_inventory_transactions"] = len(icx)
    counts["ic_inventory_holdings"] = len(ich)

    rev = datasets.build_revenue_detail(sb, customers, products)
    _write_parquet(pd.DataFrame(rev), REFERENCE / "revenue_detail.parquet")
    counts["revenue_detail"] = len(rev)

    sm = SourceMap()
    used: dict[str, set] = {}
    for em in rows:
        erp = sb.ent[em.entity].erp
        used.setdefault(erp, set()).update(em.pl.keys())
        used[erp].update(em.bs_close.keys())
        used[erp].add("320200" if erp == "KESTREL" else "320100")
    counts["expected_mapping_manifest"] = sm.write_manifest(used)

    if quick:
        return _finish(counts, t0)

    # ---------------- journals -------------------------------------------
    jg = JournalGenerator(sb, sm, cost_centres)
    all_lines: list[tuple] = []
    ytd: dict[tuple[str, int], dict[str, float]] = {}
    seen_entity: set[str] = set()
    for em in rows:
        if em.entity not in seen_entity:
            seen_entity.add(em.entity)
            # opening balances exclude retained earnings, which the journal derives
            opening = {a: v for a, v in em.bs_open.items()
                       if a not in ("320100", "320200") and abs(v) >= 0.005}
            all_lines.extend(jg.opening_balance(em.entity, em.period_key, opening))
        all_lines.extend(jg.generate(em, sb.ic_legs))
        year = em.period_key // 100
        acc = ytd.setdefault((em.entity, year), {})
        for a, v in em.pl.items():
            acc[a] = acc.get(a, 0.0) + v
        if em.period_key % 100 == 12:
            all_lines.extend(jg.year_end_close(em.entity, em.period_key, acc))
            all_lines.extend(jg.special_period_adjustments(
                em.entity, em.period_key, acc, em.bs_close))
    counts["journal_lines"] = len(all_lines)

    df = pd.DataFrame(all_lines, columns=COLUMNS)
    _write_parquet(df, REFERENCE / "journal_lines.parquet")
    _sample(df, SAMPLES / "journal_lines_sample.csv")

    writers = make_writers(rate_fn)
    files: list[tuple[str, int]] = []
    for erp, w in writers.items():
        subset = [ln for ln in all_lines if ln[1] == erp]
        files.extend(w.write(subset))
        counts[f"lines_{erp.lower()}"] = len(subset)
    counts["raw_files"] = len(files)

    # ---------------- committed samples ----------------------------------
    for erp in ("aurora", "sable", "kestrel"):
        src = sorted((RAW / erp).glob("*.csv"))
        if src:
            head = src[len(src) // 2]
            enc = "cp1252" if erp == "kestrel" else "utf-8"
            text = head.read_text(encoding=enc, errors="replace").split("\n")[:60]
            (SAMPLES / f"{erp}_extract_sample.csv").write_text(
                "\n".join(text), encoding=enc, errors="replace")

    return _finish(counts, t0)


def _finish(counts: dict, t0: float) -> dict:
    write_targets()
    checksums = {}
    for base in (REFERENCE, RAW):
        for p in sorted(base.rglob("*")):
            if p.is_file():
                checksums[p.relative_to(DATA).as_posix()] = _sha256(p)
    manifest = {
        "phase": 2,
        "master_seed": 20260907,
        "generated_datasets": counts,
        "file_count": len(checksums),
        "checksums": checksums,
    }
    # Build duration is deliberately NOT in the manifest: it varies between runs and the
    # manifest is committed, so including it would leave the working tree dirty after
    # every regeneration and defeat the reproducibility check.
    elapsed = round(time.time() - t0, 1)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    # A short, committed digest so a clean clone can prove reproducibility without the data
    digest = hashlib.sha256(
        json.dumps(manifest["checksums"], sort_keys=True).encode()).hexdigest()
    (SAMPLES / "build_digest.txt").parent.mkdir(parents=True, exist_ok=True)
    (SAMPLES / "build_digest.txt").write_text(
        f"phase2_dataset_digest={digest}\nfiles={len(checksums)}\n"
        + "".join(f"{k}={v}\n" for k, v in sorted(counts.items())), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "checksums"}, indent=2))
    print(f"build seconds : {elapsed}")
    print(f"dataset digest: {digest}")
    return manifest


if __name__ == "__main__":
    run(quick="--quick" in sys.argv)
