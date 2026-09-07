"""
Phase 2 generation foundations: configuration loading, the period spine, deterministic
seeding and shared helpers.

Determinism contract
--------------------
Every random draw in Phase 2 comes from a generator derived from MASTER_SEED plus a
*stable string key* (entity, period, stream).  No generator is shared across streams and
none depends on iteration order, so adding a new stream cannot shift the numbers produced
by an existing one.  See docs/synthetic-data-methodology.md.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
ANCHORS = CONFIG / "anchors"
DATA = ROOT / "data"
RAW = DATA / "raw"
REFERENCE = DATA / "reference"
SAMPLES = DATA / "samples"
FAULTS = DATA / "faults"

MASTER_SEED = 20260907

# --------------------------------------------------------------------------- period spine
FIRST_ACTUAL = (2023, 1)
LAST_ACTUAL = (2026, 8)          # August 2026 is the last closed month
PLAN_YEAR = 2026


@dataclass(frozen=True)
class Period:
    period_key: int              # YYYYMM
    year: int
    month: int
    start: date
    end: date
    days: int
    quarter: int
    is_year_end: bool

    @property
    def label(self) -> str:
        return f"{self.year}-{self.month:02d}"


def _month_end(y: int, m: int) -> date:
    return date(y + (m == 12), 1 if m == 12 else m + 1, 1) - timedelta(days=1)


def build_periods(first=FIRST_ACTUAL, last=LAST_ACTUAL) -> list[Period]:
    out, (y, m) = [], first
    while (y, m) <= last:
        end = _month_end(y, m)
        out.append(Period(y * 100 + m, y, m, date(y, m, 1), end, end.day,
                          (m - 1) // 3 + 1, m == 12))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def plan_periods(year: int = PLAN_YEAR) -> list[Period]:
    return build_periods((year, 1), (year, 12))


ACTUAL_PERIODS: list[Period] = build_periods()
PERIOD_BY_KEY: dict[int, Period] = {p.period_key: p for p in ACTUAL_PERIODS}


# --------------------------------------------------------------------------- seeding
def rng(*key_parts: object) -> np.random.Generator:
    """A generator seeded from MASTER_SEED and a stable string key."""
    key = "|".join(str(k) for k in key_parts)
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8, key=str(MASTER_SEED).encode())
    return np.random.default_rng(int.from_bytes(digest.digest(), "big"))


def stable_id(*key_parts: object, width: int = 8) -> str:
    key = "|".join(str(k) for k in key_parts)
    return hashlib.blake2b(key.encode("utf-8"), digest_size=8).hexdigest()[:width].upper()


# --------------------------------------------------------------------------- config
def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, header: list[str], rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


@dataclass
class Entity:
    code: str
    name: str
    short_name: str
    country: str
    currency: str
    erp: str
    erp_company_code: str
    bu: str
    parent: str
    ownership: float
    nci: float
    entity_type: str
    effective_from: date
    acquisition_date: date | None
    is_elimination: bool

    def active_periods(self, periods: list[Period]) -> list[Period]:
        return [p for p in periods if p.end >= self.effective_from]


def _d(s: str) -> date | None:
    return date.fromisoformat(s) if s else None


def load_entities() -> dict[str, Entity]:
    out = {}
    for r in read_csv(CONFIG / "entities" / "entity_master.csv"):
        out[r["entity_code"]] = Entity(
            code=r["entity_code"], name=r["entity_name"], short_name=r["short_name"],
            country=r["country_code"], currency=r["functional_currency"],
            erp=r["erp_system"], erp_company_code=r["erp_company_code"],
            bu=r["primary_business_unit"], parent=r["parent_entity_code"],
            ownership=float(r["ownership_pct"]), nci=float(r["nci_pct"]),
            entity_type=r["entity_type"],
            effective_from=_d(r["consolidation_effective_from"]),
            acquisition_date=_d(r["acquisition_date"]),
            is_elimination=r["is_elimination_entity"] == "TRUE")
    return out


def operating_entities() -> dict[str, Entity]:
    """Real legal entities only. Virtual elimination entities never reach a source system."""
    return {k: v for k, v in load_entities().items() if v.entity_type == "OPERATING"}


def load_group_coa() -> dict[str, dict[str, str]]:
    return {r["group_account"]: r for r in read_csv(CONFIG / "coa" / "group_coa.csv")}


def load_source_coa(erp: str) -> list[dict[str, str]]:
    return read_csv(CONFIG / "coa" / f"source_coa_{erp.lower()}.csv")


def load_departments() -> list[dict[str, str]]:
    return read_csv(CONFIG / "dimensions" / "department.csv")


def load_ic_matrix() -> list[dict[str, str]]:
    return read_csv(CONFIG / "ic" / "intercompany_matrix.csv")


def load_credit_agreement() -> dict[str, dict[str, str]]:
    return {r["term_id"]: r for r in read_csv(CONFIG / "debt" / "credit_agreement_terms.csv")}


# --------------------------------------------------------------------------- anchors
COLS = ["FY2023A", "FY2024A", "FY2025A", "FY2026B", "FY2026F"]
FY_OF_COL = {"FY2023A": 2023, "FY2024A": 2024, "FY2025A": 2025,
             "FY2026B": 2026, "FY2026F": 2026}
ACTUAL_COLS = ["FY2023A", "FY2024A", "FY2025A"]


def load_treasury_policy() -> dict[str, float]:
    """Board treasury policy and the facility's mechanical terms, by parameter id."""
    out: dict[str, float] = {}
    for r in read_csv(CONFIG / "debt" / "treasury_policy.csv"):
        try:
            out[r["policy_id"]] = float(r["value"])
        except ValueError:
            continue                      # conventions are text, not numbers
    return out


def load_anchor(name: str, key: str = "line_item") -> dict[str, dict[str, float]]:
    return {r[key]: {c: float(r[c]) for c in COLS}
            for r in read_csv(ANCHORS / f"anchor_{name}.csv")}


def load_opening_bs() -> dict[str, float]:
    return {r["line_item"]: float(r["amount_usd_m"])
            for r in read_csv(ANCHORS / "anchor_opening_balance_sheet.csv")}


def load_entity_revenue() -> dict[str, dict[str, float]]:
    return {r["entity_code"]: {c: float(r[c]) for c in COLS}
            for r in read_csv(ANCHORS / "anchor_by_entity.csv")}


def load_bu_anchor() -> dict[tuple[str, str], dict[str, float]]:
    return {(r["bu_code"], r["measure"]): {c: float(r[c]) for c in COLS}
            for r in read_csv(ANCHORS / "anchor_by_business_unit.csv")}


def load_ic_anchor() -> dict[str, dict[str, float]]:
    return {r["measure"]: {c: float(r[c]) for c in COLS}
            for r in read_csv(ANCHORS / "anchor_intercompany.csv")}


def load_addbacks() -> dict[str, dict[str, float]]:
    return {r["group_account"]: {c: float(r[c]) for c in COLS}
            for r in read_csv(ANCHORS / "anchor_addback_composition.csv")}


# --------------------------------------------------------------------------- helpers
MILLIONS = 1_000_000.0


def to_units(m: float) -> float:
    """Anchors are stated in USD millions; ledgers are in currency units."""
    return m * MILLIONS


def allocate_exact(total: float, weights: np.ndarray, decimals: int = 2) -> np.ndarray:
    """
    Split `total` across `weights` so the parts sum to `total` EXACTLY at `decimals`.

    Largest-remainder method.  Used everywhere an anchor is pushed down, so that no
    allocation ever leaks a rounding difference into the reconciliation.
    """
    weights = np.asarray(weights, dtype=float)
    if weights.size == 0:
        return weights
    if not np.isfinite(weights).all() or weights.sum() <= 0:
        weights = np.ones_like(weights)
    scale = 10 ** decimals
    exact = total * weights / weights.sum() * scale
    floor = np.floor(exact)
    remainder = int(round(total * scale - floor.sum()))
    if remainder:
        order = np.argsort(-(exact - floor), kind="stable")
        step = 1 if remainder > 0 else -1
        for i in range(abs(remainder)):
            floor[order[i % len(order)]] += step
    return floor / scale


def seasonal_shape(rng_: np.random.Generator, n: int, amplitude: float,
                   peak_month: int = 10, noise: float = 0.05) -> np.ndarray:
    """
    A 12-month seasonality shape summing to 1.0.

    Industrial businesses are not flat: activity dips in summer holidays and at the turn
    of the year, and peaks before year end.  `amplitude` controls how pronounced that is,
    `noise` adds month-to-month irregularity so the series does not look drawn with a ruler.
    """
    months = np.arange(n) % 12 + 1
    base = 1.0 + amplitude * np.cos(2 * np.pi * (months - peak_month) / 12.0)
    base *= 1.0 + noise * rng_.normal(size=n)
    base = np.clip(base, 0.35, None)
    return base / base.sum()


def month_workdays(p: Period) -> int:
    d = np.busday_count(p.start.isoformat(), (p.end + timedelta(days=1)).isoformat())
    return int(d)
