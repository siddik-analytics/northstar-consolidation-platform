"""
Investment in subsidiaries: an explainable roll-forward, not a residual.

Every investment balance answers four questions by construction:

    which parent owns it        parent_entity
    which subsidiary            subsidiary_entity
    when was it acquired        event_date, and the period it first appears
    why is the balance this     consideration paid, at cost, per the register

Source: `config/entities/investment_register.csv`.  Nothing here is calibrated or plugged.
All parents are USD-functional, so investments are held at USD cost and never retranslated.

The roll-forward this module emits is the fixture the Phase 4 investment elimination is
built against: for each parent, subsidiary and period it states cost, ownership and the
non-controlling share.
"""

from __future__ import annotations

from datetime import date

from .common import CONFIG, REFERENCE, build_periods, read_csv, write_csv


def load_register() -> list[dict]:
    rows = read_csv(CONFIG / "entities" / "investment_register.csv")
    for r in rows:
        r["_date"] = date.fromisoformat(r["event_date"])
        r["_usd"] = float(r["consideration_usd_m"])
        r["_own"] = float(r["ownership_pct_acquired"])
    return rows


def investments_at(as_of: date) -> dict[tuple[str, str], float]:
    """Cumulative cost by (parent, subsidiary) in USD millions at a given date."""
    out: dict[tuple[str, str], float] = {}
    for r in load_register():
        if r["_date"] <= as_of:
            key = (r["parent_entity"], r["subsidiary_entity"])
            out[key] = out.get(key, 0.0) + r["_usd"]
    return out


def total_at(as_of: date) -> float:
    return sum(investments_at(as_of).values())


def by_parent(as_of: date) -> dict[str, float]:
    out: dict[str, float] = {}
    for (parent, _sub), amt in investments_at(as_of).items():
        out[parent] = out.get(parent, 0.0) + amt
    return out


def build_rollforward() -> list[dict]:
    """One row per parent x subsidiary x period, with movements and ownership."""
    register = load_register()
    periods = build_periods((2023, 1), (2026, 8))
    pairs = sorted({(r["parent_entity"], r["subsidiary_entity"]) for r in register})
    rows: list[dict] = []
    for parent, sub in pairs:
        events = sorted([r for r in register
                         if r["parent_entity"] == parent and r["subsidiary_entity"] == sub],
                        key=lambda r: r["_date"])
        balance = 0.0
        own = 0.0
        for p in periods:
            additions = sum(r["_usd"] for r in events
                            if p.start <= r["_date"] <= p.end)
            acquired_own = sum(r["_own"] for r in events if p.start <= r["_date"] <= p.end)
            before = sum(r["_usd"] for r in events if r["_date"] < p.start)
            if p.period_key == periods[0].period_key:
                balance = before
                own = sum(r["_own"] for r in events if r["_date"] < p.start)
            opening = balance
            balance = opening + additions
            own += acquired_own
            if balance == 0.0:
                continue
            event = next((r for r in events if p.start <= r["_date"] <= p.end), None)
            rows.append(dict(
                parent_entity=parent, subsidiary_entity=sub, period_key=p.period_key,
                opening_cost_usd=round(opening * 1e6, 2),
                additions_usd=round(additions * 1e6, 2),
                disposals_usd=0.0,
                closing_cost_usd=round(balance * 1e6, 2),
                ownership_pct=round(own, 4),
                nci_pct=round(1.0 - own, 4),
                carrying_currency="USD",
                event_type=event["event_type"] if event else "NONE",
                investment_id=event["investment_id"] if event else "",
                first_consolidated_period=min(
                    r["_date"].year * 100 + r["_date"].month for r in events)))
    return rows


def write_reference() -> int:
    rows = build_rollforward()
    write_csv(REFERENCE / "investment_rollforward.csv", list(rows[0]),
              [list(r.values()) for r in rows])
    return len(rows)
