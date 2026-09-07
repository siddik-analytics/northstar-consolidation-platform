"""
Controlled fault fixtures.

The clean baseline in `data/raw/` is never corrupted.  Each fault is a *separate copy* of
the one or two files it affects, written to `data/faults/<fault_id>/`, together with an
expected-results manifest naming the control that must catch it.

This keeps two ideas apart, which the brief is explicit about:

    clean baseline data      must pass every applicable source control
    injected-fault variants  must make one named control fail, and only that one

A control that has never failed has never been tested.

    python -m src.generation.faults
"""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .common import FAULTS, RAW, REFERENCE, write_csv


@dataclass
class Fault:
    fault_id: str
    name: str
    category: str
    expected_control: str
    phase_detected: int
    description: str
    detector: str


CATALOGUE = [
    Fault("F01", "Unmapped source account", "MAPPING", "CTL-MAP-01", 3,
          "A posting carries a source account that does not exist in the Aurora chart, so "
          "the mapping engine has nothing to map it to. It must land in suspense and block "
          "the close, never default into other expenses.",
          "source account not present in the ERP chart of accounts"),
    Fault("F02", "Intercompany amount mismatch", "INTERCOMPANY", "CTL-IC-01", 4,
          "The buying entity restates a management fee by 4.5% while the selling entity "
          "does not. Both trial balances still close, so only a control that tests the "
          "entity PAIR -- rather than the aggregate -- can find it.",
          "entity-pair intercompany balance does not net to zero"),
    Fault("F03", "Missing FX rate", "FX", "CTL-FX-01", 4,
          "The closing rate for one currency and period is absent from the rate file. "
          "Translation must fail rather than silently apply zero or carry a stale rate.",
          "currency-period-rate-type absent from the rate table"),
    Fault("F04", "Duplicate journal identifier", "DATA_QUALITY", "CTL-DQ-03", 3,
          "A journal is present twice in the same extract, as happens when a period is "
          "loaded twice. It doubles the entity's result while still balancing.",
          "duplicate (entity, journal_id, line_number)"),
    Fault("F05", "Invalid cost centre", "DATA_QUALITY", "CTL-DQ-08", 3,
          "A posting references a cost centre that is not in the master, which would "
          "otherwise become an orphan dimension key.",
          "cost centre not present in the cost centre master"),
    Fault("F06", "Malformed localised amount", "DATA_QUALITY", "CTL-DQ-09", 3,
          "A Kestrel amount is written with a period decimal separator instead of a comma. "
          "Parsed under the German locale, 1.234,56 becomes 1.23456 -- a thousand-fold "
          "error that still looks like a number.",
          "amount does not parse under the declared locale"),
    Fault("F07", "Posting date outside its period", "DATA_QUALITY", "CTL-DQ-06", 3,
          "A line is stamped with a posting date in a different month from the fiscal "
          "period it is filed under.",
          "posting date month does not match the fiscal period"),
    Fault("F08", "Payroll misclassified across the gross margin line", "MAPPING",
          "CTL-MAP-04", 3,
          "A direct production payroll posting carries an SGA department, so Aurora's "
          "conditional split resolves it to operating expense instead of cost of sales. "
          "Every balancing control still passes; only gross margin moves.",
          "payroll line whose department contradicts its cost centre function"),
    Fault("F09", "Unbalanced journal", "TRIAL_BALANCE", "CTL-TB-01", 3,
          "One leg of a two-sided entry is removed, so the entity's trial balance no "
          "longer closes to zero.",
          "journal whose lines do not sum to zero"),
    Fault("F10", "Posting before the consolidation effective date", "CONSOLIDATION",
          "CTL-CON-02", 4,
          "Halden Valve posts a period before its 1 April 2023 acquisition date, which "
          "would overstate FY2023 and corrupt the organic growth bridge.",
          "period earlier than the entity's consolidation effective date"),
]


def _read(path: Path, enc="utf-8", delim=","):
    with open(path, newline="", encoding=enc) as f:
        rows = list(csv.reader(f, delimiter=delim))
    return rows[0], rows[1:]


def _write(path: Path, header, rows, enc="utf-8", delim=","):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding=enc, errors="replace") as f:
        w = csv.writer(f, delimiter=delim, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _pick(subdir: str, contains: str = "") -> Path:
    files = sorted((RAW / subdir).glob("*.csv"))
    if contains:
        files = [f for f in files if contains in f.name] or files
    return files[len(files) // 2]


def inject() -> list[dict]:
    if not (RAW / "aurora").exists():
        raise SystemExit("run `python -m src.generation.build` first")
    if FAULTS.exists():
        shutil.rmtree(FAULTS)
    out: list[dict] = []

    def record(f: Fault, path: Path, detail: str, affected: int):
        out.append(dict(fault_id=f.fault_id, name=f.name, category=f.category,
                        expected_control=f.expected_control,
                        phase_detected=f.phase_detected, detector=f.detector,
                        variant_file=path.relative_to(FAULTS).as_posix(),
                        affected_rows=affected, description=f.description, detail=detail))

    cat = {f.fault_id: f for f in CATALOGUE}

    # F01 unmapped source account -------------------------------------------
    src = _pick("aurora", "NIG200")
    h, rows = _read(src)
    i = h.index("ACCOUNT")
    target = next(r for r in rows if r[i] == "6100")
    target[i] = "6199"
    p = FAULTS / "F01" / src.name
    _write(p, h, rows)
    record(cat["F01"], p, "Aurora account 6100 changed to 6199, which is not in the chart", 1)

    # F02 intercompany amount mismatch --------------------------------------
    # A genuine mismatch restates one ENTITY, not one leg: the buyer books a different
    # amount from the seller. Both entities still balance internally, so only a
    # pair-level control finds it.
    src2 = _pick("aurora", "NIG200")
    h, rows = _read(src2)
    ia, ip = h.index("AMOUNT"), h.index("SUBSIDIARY_PARTNER")
    n = 0
    for r in rows:
        if r[ip] == "NIG-110":
            r[ia] = f"{float(r[ia]) * 1.045:.2f}"
            n += 1
    p = FAULTS / "F02" / src2.name
    _write(p, h, rows)
    record(cat["F02"], p,
           "the buyer restates the management fee by 4.5%; its own trial balance still "
           "closes, but the entity pair no longer eliminates", n)

    # F03 missing FX rate ----------------------------------------------------
    h, rows = _read(REFERENCE / "fx_rates_monthly.csv")
    ic, ipk, irt = h.index("currency_code"), h.index("period_key"), h.index("rate_type")
    kept = [r for r in rows
            if not (r[ic] == "EUR" and r[ipk] == "202411" and r[irt] == "CLOSE")]
    p = FAULTS / "F03" / "fx_rates_monthly.csv"
    _write(p, h, kept)
    record(cat["F03"], p, "EUR closing rate for 2024-11 removed", len(rows) - len(kept))

    # F04 duplicate journal --------------------------------------------------
    src4 = _pick("sable", "CAS-US")
    h, rows = _read(src4)
    ij = h.index("JOURNALID")
    jid = rows[len(rows) // 2][ij]
    dup = [list(r) for r in rows if r[ij] == jid]
    p = FAULTS / "F04" / src4.name
    _write(p, h, rows + dup)
    record(cat["F04"], p, f"journal {jid} present twice", len(dup))

    # F05 invalid cost centre ------------------------------------------------
    src5 = _pick("kestrel", "1000")
    h, rows = _read(src5, "cp1252", ";")
    ik = h.index("KOSTL")
    for r in rows[:3]:
        r[ik] = "999-999"
    p = FAULTS / "F05" / src5.name
    _write(p, h, rows, "cp1252", ";")
    record(cat["F05"], p, "cost centre 999-999 does not exist in the master", 3)

    # F06 malformed localised amount -----------------------------------------
    h, rows = _read(src5, "cp1252", ";")
    isoll = h.index("SOLL")
    n = 0
    for r in rows:
        if r[isoll] and "," in r[isoll] and n < 4:
            r[isoll] = r[isoll].replace(".", "").replace(",", ".")
            n += 1
    p = FAULTS / "F06" / src5.name
    _write(p, h, rows, "cp1252", ";")
    record(cat["F06"], p, "German comma decimal replaced by a period separator", n)

    # F07 posting date outside its period ------------------------------------
    h, rows = _read(src)
    idt = h.index("TRANDATE")
    for r in rows[:2]:
        r[idt] = r[idt][:8] + "01"
        r[idt] = f"{int(r[idt][:4])}-{int(r[idt][5:7]) % 12 + 1:02d}-01"
    p = FAULTS / "F07" / src.name
    _write(p, h, rows)
    record(cat["F07"], p, "posting date moved into the following month", 2)

    # F08 payroll misclassified across the gross margin line ------------------
    h, rows = _read(src)
    ia, idep, iattr = h.index("ACCOUNT"), h.index("DEPARTMENT"), h.index("LINE_ATTRIBUTES")
    n = 0
    for r in rows:
        if r[ia] == "6100" and "PRODUCTION" in r[iattr] and n < 8:
            r[idep] = "DEPT-D500"
            r[iattr] = r[iattr].replace("dept_function=PRODUCTION", "dept_function=SGA")
            n += 1
    p = FAULTS / "F08" / src.name
    _write(p, h, rows)
    record(cat["F08"], p,
           "production payroll re-tagged to an SGA department; gross margin moves, "
           "every balancing control still passes", n)

    # F09 unbalanced journal --------------------------------------------------
    h, rows = _read(src)
    ij = h.index("JOURNAL_ID")
    jid = rows[len(rows) // 3][ij]
    kept = [r for r in rows if r[ij] != jid] + [r for r in rows if r[ij] == jid][:1]
    p = FAULTS / "F09" / src.name
    _write(p, h, kept)
    record(cat["F09"], p, f"one leg of journal {jid} removed", 1)

    # F10 posting before the consolidation effective date ---------------------
    hal = sorted((RAW / "kestrel").glob("KESTREL_BSEG_1000_*.csv"))[0]
    h, rows = _read(hal, "cp1252", ";")
    early = [list(r) for r in rows[:5]]
    for r in early:
        r[h.index("GJAHR")], r[h.index("MONAT")] = "2023", "2"
        r[h.index("BUDAT")] = "15.02.2023"
    p = FAULTS / "F10" / hal.name
    _write(p, h, rows + early, "cp1252", ";")
    record(cat["F10"], p,
           "Halden Valve posts February 2023, before its 1 April 2023 acquisition", 5)

    manifest = FAULTS / "expected_results.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    write_csv(FAULTS / "expected_results.csv",
              ["fault_id", "name", "category", "expected_control", "phase_detected",
               "variant_file", "affected_rows", "detector", "detail"],
              [[r["fault_id"], r["name"], r["category"], r["expected_control"],
                r["phase_detected"], r["variant_file"], r["affected_rows"],
                r["detector"], r["detail"]] for r in out])
    return out


# --------------------------------------------------------------------------- detection
def detect(fault_id: str) -> bool:
    """Does the fault variant actually trip its detector? Used by the Phase 2 tests."""
    from .common import operating_entities, load_source_coa, read_csv
    base = FAULTS / fault_id
    files = sorted(base.glob("*.csv"))
    if not files:
        return False
    path = files[0]
    kestrel = "KESTREL" in path.name
    enc, delim = ("cp1252", ";") if kestrel else ("utf-8", ",")
    if fault_id == "F03":
        enc, delim = "utf-8", ","
    h, rows = _read(path, enc, delim)
    idx = {c: i for i, c in enumerate(h)}

    if fault_id == "F01":
        valid = {r["source_account"] for r in load_source_coa("aurora")}
        return any(r[idx["ACCOUNT"]] not in valid for r in rows)
    if fault_id == "F02":
        # Both files still balance, so compare the gross intercompany volume, not the net
        clean = _pick("aurora", "NIG200")
        hc, rc = _read(clean)
        ic_, ia_ = hc.index("SUBSIDIARY_PARTNER"), hc.index("AMOUNT")
        tot_c = sum(abs(float(r[ia_])) for r in rc if r[ic_] == "NIG-110")
        tot_f = sum(abs(float(r[idx["AMOUNT"]])) for r in rows
                    if r[idx["SUBSIDIARY_PARTNER"]] == "NIG-110")
        net_f = sum(float(r[idx["AMOUNT"]]) for r in rows
                    if r[idx["SUBSIDIARY_PARTNER"]] == "NIG-110")
        # the restated entity must still balance internally -- that is what makes it hard
        return abs(tot_f - tot_c) > 1.0 and abs(net_f) < 1.0
    if fault_id == "F03":
        keys = {(r[idx["currency_code"]], r[idx["period_key"]], r[idx["rate_type"]])
                for r in rows}
        return ("EUR", "202411", "CLOSE") not in keys
    if fault_id == "F04":
        seen = set()
        for r in rows:
            k = (r[idx["JOURNALID"]], r[idx["LINENUM"]])
            if k in seen:
                return True
            seen.add(k)
        return False
    if fault_id == "F05":
        valid = {c["cost_center_code"] for c in read_csv(REFERENCE / "cost_centres.csv")}
        return any(r[idx["KOSTL"]] not in valid for r in rows)
    if fault_id == "F06":
        # A German-locale amount must not contain a period used as a decimal point
        for r in rows:
            v = r[idx["SOLL"]]
            if v and "," not in v and "." in v:
                return True
        return False
    if fault_id == "F07":
        pk = int(path.stem.split("_")[-1])
        return any(int(r[idx["TRANDATE"]][5:7]) != pk % 100 for r in rows)
    if fault_id == "F08":
        return any(r[idx["ACCOUNT"]] == "6100" and "dept_function=SGA" in r[idx["LINE_ATTRIBUTES"]]
                   and r[idx["DEPARTMENT"]] == "DEPT-D500" for r in rows)
    if fault_id == "F09":
        bal: dict[str, float] = {}
        for r in rows:
            bal[r[idx["JOURNAL_ID"]]] = bal.get(r[idx["JOURNAL_ID"]], 0.0) \
                + float(r[idx["AMOUNT"]])
        return any(abs(v) > 0.011 for v in bal.values())
    if fault_id == "F10":
        ents = operating_entities()
        eff = ents["NIG-220"].effective_from
        return any(int(r[idx["GJAHR"]]) * 100 + int(r[idx["MONAT"]])
                   < eff.year * 100 + eff.month for r in rows)
    return False


if __name__ == "__main__":
    faults = inject()
    print(f"{len(faults)} fault fixtures written to data/faults/")
    ok = True
    for f in faults:
        fired = detect(f["fault_id"])
        ok &= fired
        print(f"  {f['fault_id']}  {'DETECTED' if fired else 'NOT DETECTED':13} "
              f"{f['expected_control']:12} {f['name']}")
    raise SystemExit(0 if ok else 1)
