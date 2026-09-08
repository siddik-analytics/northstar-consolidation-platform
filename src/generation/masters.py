"""Source-system master and reference data: cost centres, customers, products, employees."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from .common import (ACTUAL_PERIODS, REFERENCE, load_departments, operating_entities,
                     rng, stable_id, write_csv)
from .model import EconomicModel

# Department function drives the conditional payroll splits in every source chart.
DEPT_FUNCTION = {
    "D100": "PRODUCTION", "D105": "INDIRECT_OPS", "D110": "INDIRECT_OPS",
    "D115": "INDIRECT_OPS", "D120": "INDIRECT_OPS",
    # D210 and D215 support field operations, they do not deliver them: the department
    # master calls both INDIRECT and the approved Aurora split rule groups them with the
    # other indirect-operations departments (D105, D110, D115, D120 -> 520100) rather than
    # with the billable crews (D200, D205 -> 515200). Calling them FIELD here made every
    # posting at an industrial-services entity declare a delivery function while sitting
    # in a support cost centre, which was the bulk of defect P2-D-02.
    "D200": "FIELD", "D205": "FIELD",
    "D210": "INDIRECT_OPS", "D215": "INDIRECT_OPS",
    "D300": "PROJECT", "D305": "PROJECT", "D310": "PROJECT",
    "D400": "SGA", "D405": "SGA", "D410": "SGA", "D415": "SGA",
    "D500": "SGA", "D505": "SGA", "D510": "SGA", "D515": "SGA", "D520": "SGA",
    "D525": "SGA", "D900": "SGA", "D905": "SGA", "D910": "SGA", "D950": "SGA",
}
# Which departments may carry a given group account. The first entry that exists at the
# entity is used, so the required dept_function for each conditional split is satisfied.
ACCOUNT_DEPTS = {
    # Revenue is owned by the commercial function, or by the delivering operation where
    # the business unit has no separate sales team.
    "410100": ["D400", "D100"], "410200": ["D400", "D100"], "415100": ["D410", "D400"],
    "420100": ["D400", "D200"], "420200": ["D410", "D400"], "420300": ["D415", "D400"],
    "425100": ["D305", "D400"], "425200": ["D305", "D400"],
    "430100": ["D120", "D400"], "435100": ["D400"],
    "440100": ["D410", "D400"], "440200": ["D410", "D400"],
    "490100": ["D400"], "490200": ["D400"], "490300": ["D500"], "490400": ["D500"],
    "515100": ["D100"], "515200": ["D200", "D205", "D300", "D305", "D310"],
    "515300": ["D100", "D200", "D300"],
    "520100": ["D105", "D110", "D115", "D210", "D215"],
    "520200": ["D100"], "520300": ["D115", "D120", "D210", "D200"],
    "520400": ["D210", "D200", "D205"],
    "510100": ["D115", "D100"], "510200": ["D115", "D120"], "510300": ["D100", "D200", "D300"],
    "525100": ["D120", "D115"], "525200": ["D120"], "530100": ["D110", "D115"],
    "530200": ["D110"], "535100": ["D305", "D300"],
    "590100": ["D115", "D120"], "590200": ["D200", "D300"],
    "610100": ["D500", "D505", "D510", "D400", "D950"], "610200": ["D505"],
    "610300": ["D505"], "610400": ["D500", "D900"], "610500": ["D900"],
    "610600": ["D500", "D510"], "610700": ["D505"], "610800": ["D505"],
    "620100": ["D525"], "620200": ["D525"], "620300": ["D525"], "620400": ["D525"],
    "630100": ["D500"], "630200": ["D515", "D500"], "630300": ["D500", "D950"],
    "630400": ["D900"],
    "640100": ["D405"], "640200": ["D405"], "640300": ["D400"], "640400": ["D500"],
    "650100": ["D510"], "650200": ["D510"], "650300": ["D510"],
    "660100": ["D400", "D500"], "660200": ["D400", "D200"],
    "670100": ["D500", "D950"], "670200": ["D500"], "670300": ["D950"], "670400": ["D950"],
    "680100": ["D505"], "680200": ["D525"], "680300": ["D905"], "680400": ["D910"],
    "680600": ["D515"], "680700": ["D505"],
    "695100": ["D500"], "695200": ["D500"], "695300": ["D500"],
    "710100": ["D950"], "720200": ["D950"],
}
DEFAULT_DEPT = "D950"

CUSTOMER_PREFIX = ["Ashford", "Baytown", "Cedar Ridge", "Delta Point", "Eastgate", "Foxbridge",
                   "Granville", "Harlow", "Ironside", "Juniper", "Kestrel Bay", "Larkfield",
                   "Meridian Park", "Northbrook", "Oakfield", "Pinehurst", "Quarry Hill",
                   "Redmond", "Stonebridge", "Thornbury", "Upton", "Vale", "Westmoor",
                   "Yarrow", "Zenith"]
CUSTOMER_CORE = ["Chemicals", "Refining", "Energy", "Water", "Petrochemical", "Industrial",
                 "Processing", "Utilities", "Minerals", "Foods", "Paper", "Metals"]
CUSTOMER_SUFFIX = ["Corporation", "LLC", "Inc.", "Group", "Holdings", "Ltd.", "GmbH", "B.V.",
                   "plc", "Partners", "Works", "Industries"]
SECTORS = ["Chemicals", "Refining & Petrochemical", "Power Generation", "Water Treatment",
           "Food & Beverage", "Pulp & Paper", "Mining & Minerals", "Pharmaceutical",
           "General Industrial"]
JOB_FAMILIES = [
    ("PROD", "Production & Assembly", 62_000, "PRODUCTION"),
    ("FIELD", "Field Service Technician", 78_000, "FIELD"),
    ("ENGR", "Engineering", 104_000, "PROJECT"),
    ("PROJ", "Project Management", 112_000, "PROJECT"),
    ("QUAL", "Quality & HSE", 76_000, "INDIRECT_OPS"),
    ("SUPPLY", "Supply Chain & Warehouse", 64_000, "INDIRECT_OPS"),
    ("SALES", "Sales & Commercial", 98_000, "SGA"),
    ("FIN", "Finance", 96_000, "SGA"),
    ("HR", "Human Resources", 84_000, "SGA"),
    ("IT", "Information Technology", 106_000, "SGA"),
    ("EXEC", "Executive & Leadership", 205_000, "SGA"),
    ("ADMIN", "Administration", 58_000, "SGA"),
]
COUNTRY_PAY_INDEX = {"US": 1.00, "CA": 0.88, "GB": 0.82, "DE": 0.90, "NL": 0.92}


def build_cost_centres() -> list[dict]:
    ents = operating_entities()
    depts = {d["department_code"]: d for d in load_departments()}
    rows = []
    for code, e in sorted(ents.items()):
        num = code.split("-")[1]
        for dcode, d in depts.items():
            applies = d["applies_to_bu"].split(";")
            if e.bu not in applies:
                continue
            g = rng("cc", code, dcode)
            rows.append(dict(
                entity_code=code, cost_center_code=f"{num}-{dcode[1:]}",
                cost_center_name=f"{e.short_name} {d['department_name']}",
                department_code=dcode, department_name=d["department_name"],
                function_group=d["function_group"], dept_function=DEPT_FUNCTION[dcode],
                cost_type=d["cost_type"], pl_destination=d["pl_destination"],
                bu_code=e.bu, is_headcount_bearing=d["headcount_bearing"],
                erp_system=e.erp,
                manager_id=f"MGR-{stable_id(code, dcode, width=6)}",
                is_active="TRUE"))
    return rows


def build_customers(model: EconomicModel) -> list[dict]:
    """~1,150 customers with a realistic concentration curve and named parent groups."""
    rows, seen = [], set()
    g = rng("customers")
    n_groups = 260
    groups = []
    for i in range(n_groups):
        name = (f"{CUSTOMER_PREFIX[i % len(CUSTOMER_PREFIX)]} "
                f"{CUSTOMER_CORE[(i * 7) % len(CUSTOMER_CORE)]} "
                f"{CUSTOMER_SUFFIX[(i * 5) % len(CUSTOMER_SUFFIX)]}")
        groups.append((f"CG{i + 1:04d}", name))
    ents = operating_entities()
    countries = {"NIG-200": "US", "NIG-500": "US", "NIG-300": "US", "NIG-400": "US",
                 "NIG-210": "CA", "NIG-310": "CA", "NIG-320": "GB", "NIG-510": "GB",
                 "NIG-220": "DE", "NIG-410": "NL"}
    # Pareto weights: the largest customers take a disproportionate share
    weights = 1.0 / np.arange(1, n_groups + 1) ** 0.85
    for ecode in [c for c in countries]:
        n = int(60 + 90 * model.rev_anchor[ecode]["FY2025A"] / 92.0)
        gi = g.choice(n_groups, size=n, replace=True, p=weights / weights.sum())
        for j, idx in enumerate(gi):
            gcode, gname = groups[idx]
            cust = f"C{ecode[-3:]}{j + 1:04d}"
            if cust in seen:
                continue
            seen.add(cust)
            first = date(2019, 1, 1) + timedelta(days=int(g.integers(0, 2400)))
            rows.append(dict(
                customer_code=cust, customer_name=f"{gname} - {ecode[-3:]} {j + 1:03d}",
                customer_group_code=gcode, customer_group_name=gname,
                industry_sector=SECTORS[int(g.integers(0, len(SECTORS)))],
                country_code=countries[ecode], billing_entity=ecode,
                channel="DIRECT" if g.random() < 0.78 else "DISTRIBUTOR",
                payment_terms_days=int(g.choice([30, 30, 45, 45, 60, 60, 75, 90])),
                first_order_date=first.isoformat(),
                is_key_account="TRUE" if idx < 25 else "FALSE", is_active="TRUE"))
    return rows


def build_products() -> list[dict]:
    fam = {
        "FC": [("Centrifugal Pumps", "PUMP"), ("Control Valves", "VALVE"),
               ("Flow Instrumentation", "INSTR"), ("Actuators", "ACT")],
        "IS": [("Field Mechanical Services", "FMS"), ("Rotating Equipment", "ROT"),
               ("Turnaround Services", "TAR"), ("Inspection & Testing", "INSP")],
        "ES": [("Engineered Skid Packages", "SKID"), ("Automation & Controls", "AUTO"),
               ("Systems Integration", "SI")],
        "AM": [("Pump Spares", "PSPARE"), ("Valve Spares", "VSPARE"),
               ("Seals & Consumables", "SEAL"), ("Repair Kits", "KIT")],
    }
    rev_type = {"FC": "PRODUCT", "IS": "SERVICE", "ES": "PROJECT", "AM": "PARTS"}
    recog = {"FC": "POINT_IN_TIME", "IS": "OVER_TIME", "ES": "OVER_TIME", "AM": "POINT_IN_TIME"}
    margin = {"FC": 0.34, "IS": 0.22, "ES": 0.19, "AM": 0.43}
    rows = []
    for bu, families in fam.items():
        for fname, fcode in families:
            g = rng("product", bu, fcode)
            for line in range(1, 6):
                for variant in range(1, int(g.integers(3, 6))):
                    code = f"{fcode}-{line}{variant:02d}"
                    rows.append(dict(
                        product_code=code,
                        product_name=f"{fname} Series {line}00 Model {variant:02d}",
                        product_family=fname, product_family_code=fcode,
                        product_line=f"{fcode}-{line}00", bu_code=bu,
                        revenue_type=rev_type[bu], recognition_method=recog[bu],
                        is_aftermarket="TRUE" if bu == "AM" else "FALSE",
                        standard_margin_pct=round(margin[bu] * float(g.uniform(0.88, 1.14)), 4),
                        is_active="TRUE"))
    return rows


def build_employees(model: EconomicModel) -> list[dict]:
    """
    A synthetic workforce that tracks the approved headcount anchors month by month.

    Hire dates are assigned so the active population follows the anchored ramp from FY2023
    to FY2026 rather than being drawn at random, and a churn population is added in
    hire/leave pairs so attrition is visible without disturbing the net count.

    Identities are entirely synthetic: employees carry an opaque identifier and no name, so
    the dataset cannot be mistaken for, or reverse-engineered into, real personal data.
    """
    ents = operating_entities()
    cc_by_entity: dict[str, list[dict]] = {}
    for cc in build_cost_centres():
        if cc["is_headcount_bearing"] == "TRUE":
            cc_by_entity.setdefault(cc["entity_code"], []).append(cc)

    hc = {c: model.entity_headcount_weight(c)
          for c in ("FY2023A", "FY2024A", "FY2025A", "FY2026F")}
    months = list(ACTUAL_PERIODS)
    rows = []
    for code, e in sorted(ents.items()):
        ccs = cc_by_entity.get(code, [])
        anchors = [hc["FY2023A"].get(code, 0.0), hc["FY2024A"].get(code, 0.0),
                   hc["FY2025A"].get(code, 0.0), hc["FY2026F"].get(code, 0.0)]
        if not ccs or max(anchors) <= 0:
            continue
        g = rng("employees", code)
        ramp = []
        for p_ in months:
            yi = min(max(p_.year - 2023, 0), 2)
            ramp.append(anchors[yi] + (anchors[yi + 1] - anchors[yi]) * p_.month / 12.0)
        churn = int(round(max(ramp) * 0.20))

        def make(i, hire, term):
            cc = ccs[int(g.integers(0, len(ccs)))]
            fam = [j for j in JOB_FAMILIES if j[3] == cc["dept_function"]] or JOB_FAMILIES
            jf = fam[int(g.integers(0, len(fam)))]
            band = float(np.clip(g.normal(1.0, 0.18), 0.55, 1.9))
            part_time = g.random() < 0.06
            eligible = jf[0] in ("EXEC", "SALES", "FIN", "IT", "PROJ")
            return dict(
                employee_id=f"E{stable_id(code, i, width=8)}",
                entity_code=code, cost_center_code=cc["cost_center_code"],
                department_code=cc["department_code"], bu_code=e.bu,
                country_code=e.country, currency_code=e.currency,
                job_family_code=jf[0], job_family_name=jf[1],
                employment_status="TERMINATED" if term else "ACTIVE",
                employment_type="PART_TIME" if part_time else "FULL_TIME",
                fte=round(float(g.choice([0.5, 0.6, 0.8])), 2) if part_time else 1.0,
                hire_date=hire.isoformat(),
                termination_date=term.isoformat() if term else "",
                annual_base_salary_local=round(
                    jf[2] * COUNTRY_PAY_INDEX[e.country] * band, 2),
                benefits_rate_pct=round(float(g.uniform(0.16, 0.27)), 4),
                bonus_eligible="TRUE" if eligible else "FALSE",
                bonus_target_pct=round(float(g.uniform(0.05, 0.35)), 4) if eligible else 0.0)

        base_count = int(round(ramp[0]))
        for i in range(base_count):
            hire = e.effective_from - timedelta(days=int(g.integers(200, 3000)))
            rows.append(make(i, hire, None))
        idx = base_count
        for m, p_ in enumerate(months):
            need = int(round(ramp[m])) - idx
            for _ in range(max(need, 0)):
                hire = max(p_.start + timedelta(days=int(g.integers(0, p_.days))),
                           e.effective_from)
                rows.append(make(idx, hire, None))
                idx += 1
        # Churn comes OUT of the ramp population: some of the people already hired leave,
        # and each is replaced the following month.  Adding leavers on top of the ramp
        # would inflate the active count against the anchor.
        ramp_rows = [r for r in rows if r["entity_code"] == code]
        if ramp_rows and churn:
            picks = g.choice(len(ramp_rows), size=min(churn, len(ramp_rows)), replace=False)
            for pick in picks:
                emp = ramp_rows[int(pick)]
                hired = date.fromisoformat(emp["hire_date"])
                cand = [m for m, p_ in enumerate(months)
                        if p_.end > hired and m < len(months) - 2]
                if not cand:
                    continue
                m = int(cand[int(g.integers(0, len(cand)))])
                emp["termination_date"] = months[m].end.isoformat()
                emp["employment_status"] = "TERMINATED"
                repl = months[m + 1].start + timedelta(days=int(g.integers(0, 20)))
                rows.append(make(idx, repl, None))
                idx += 1
    return rows


def write_all(model: EconomicModel) -> dict[str, int]:
    cc = build_cost_centres()
    write_csv(REFERENCE / "cost_centres.csv", list(cc[0]), [list(r.values()) for r in cc])
    cust = build_customers(model)
    write_csv(REFERENCE / "customers.csv", list(cust[0]), [list(r.values()) for r in cust])
    prod = build_products()
    write_csv(REFERENCE / "products.csv", list(prod[0]), [list(r.values()) for r in prod])
    emp = build_employees(model)
    write_csv(REFERENCE / "employees.csv", list(emp[0]), [list(r.values()) for r in emp])
    return {"cost_centres": len(cc), "customers": len(cust), "products": len(prod),
            "employees": len(emp)}
