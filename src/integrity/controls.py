"""
The declared-key and declared-grain control suite.

    python -m src.integrity.controls

One generic engine, executed over the whole registry, over the full population. No object
gets a bespoke check, because a bespoke check is a check someone has to remember to write --
and the reason P6-D-01 survived four phases is that nobody remembered to write one for
`fact_capex_project`.

Five families:

``P7-REG``  the registry itself is complete and honest
``P7-KEY``  every declared key is unique over its whole population
``P7-NUL``  no key column is null
``P7-REF``  every declared foreign key resolves
``P7-CPX``  the capital project chain, end to end, at the grain the business reads
``P7-VER``  scenario and version governance, including the derived-version policy
``P7-RPR``  lineage identifiers identify content, not a checkout

The control ids carry the object name rather than a sequence number, so a failure says what
broke without a lookup, and inserting a registry entry does not renumber the suite.
"""

from __future__ import annotations

import csv
import json
import pathlib
import sys
from pathlib import Path

import duckdb

from .registry import KEYLESS, OUT_OF_SCOPE, REFERENCES, REGISTRY

ROOT = Path(__file__).resolve().parents[2]
DUCKDB_PATH = ROOT / "data" / "20_warehouse" / "northstar.duckdb"
CONTROL_RESULTS = ROOT / "data" / "phase07_key_control_results.csv"

#: The prefixes that mark an object as carrying a business key and therefore in scope.
IN_SCOPE_PREFIXES = ("dim_", "fact_", "mart_", "ref_")


class Result(list):
    def add(self, cid, name, severity, status, measured="", threshold="", detail=""):
        self.append(dict(control_id=cid, control_name=name, severity=severity, status=status,
                         measured=str(measured), threshold=str(threshold), detail=detail))

    def ok(self, cid, name, severity, condition, measured, threshold, detail=""):
        self.add(cid, name, severity, "PASS" if condition else "FAIL", measured, threshold,
                 detail)

    @property
    def failed(self):
        return [r for r in self if r["status"] == "FAIL" and r["severity"] == "BLOCKING"]


def _one(con, sql):
    row = con.execute(sql).fetchone()
    return row[0] if row and row[0] is not None else 0


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'main' AND table_type = 'BASE TABLE'""").fetchall()}


def _columns(con, table: str) -> set[str]:
    return {r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()}


# --------------------------------------------------------------------------- P7-REG
def _registry_completeness(con, r: Result) -> None:
    """
    The registry must name every keyed object in the warehouse.

    This is the control that makes the rest of the suite mean something. Without it a new
    table can be added, joined on and reported from while the framework happily reports
    green over the objects it happens to know about.
    """
    present = _tables(con)
    in_scope = {t for t in present
                if t.startswith(IN_SCOPE_PREFIXES)
                and not any(t.startswith(p) for p in OUT_OF_SCOPE)}
    declared = {d.object for d in REGISTRY}

    undeclared = sorted(in_scope - declared - set(KEYLESS))
    r.ok("P7-REG-01", "Every keyed object in the warehouse is declared in the registry",
         "BLOCKING", not undeclared, len(undeclared), 0,
         f"undeclared: {', '.join(undeclared)}" if undeclared
         else f"{len(in_scope)} objects in scope, all declared")

    missing = sorted(declared - present)
    r.ok("P7-REG-02", "Every registry entry names an object that exists", "BLOCKING",
         not missing, len(missing), 0,
         f"declared but absent: {', '.join(missing)}" if missing
         else f"{len(declared)} declarations, all resolve")

    # A declared key naming a column the object does not have is a contract nobody can honour.
    bad: list[str] = []
    for d in REGISTRY:
        if d.object not in present:
            continue
        cols = _columns(con, d.object)
        for column in d.key:
            if column not in cols:
                bad.append(f"{d.object}.{column}")
    r.ok("P7-REG-03", "Every declared key column exists on its object", "BLOCKING",
         not bad, len(bad), 0, f"missing columns: {', '.join(bad)}" if bad else "")

    # A keyless declaration is a waiver, and a waiver with no reason is not a waiver.
    unexplained = sorted(k for k, why in KEYLESS.items() if not why.strip())
    r.ok("P7-REG-04", "Every keyless waiver carries a reason", "BLOCKING",
         not unexplained, len(unexplained), 0,
         f"{len(KEYLESS)} waivers" if KEYLESS else "no waivers in force")


# --------------------------------------------------------------------------- P7-KEY / P7-NUL
def _keys(con, r: Result) -> None:
    present = _tables(con)
    for d in REGISTRY:
        if d.object not in present:
            continue                      # already failed as P7-REG-02
        key = ", ".join(d.key)
        rows, distinct = con.execute(f"""
            SELECT count(*), (SELECT count(*) FROM (SELECT DISTINCT {key} FROM {d.object}))
            FROM {d.object}""").fetchone()
        dupes = rows - distinct
        r.ok(f"P7-KEY-{d.object}",
             f"{d.object} is unique on its declared key ({key})",
             "BLOCKING", dupes == 0, f"{dupes} duplicate rows", 0,
             f"{rows:,} rows, {distinct:,} distinct keys; owner {d.owner}; "
             f"authority {d.source}")

        # A key column may be null only where the registry names it and says why. Testing
        # only the columns outside that set is what keeps the permission a contract rather
        # than a blanket amnesty over the whole key.
        must_not_be_null = [c for c in d.key if c not in d.nullable]
        if must_not_be_null:
            nulls = _one(con, f"""
                SELECT count(*) FROM {d.object}
                WHERE {' OR '.join(f'{c} IS NULL' for c in must_not_be_null)}""")
        else:
            nulls = 0
        permitted = (f"; null permitted in {', '.join(d.nullable)} -- {d.nulls}"
                     if d.nullable else "")
        r.ok(f"P7-NUL-{d.object}",
             f"{d.object} has no null in an unpermitted key column",
             "BLOCKING", nulls == 0, nulls, 0,
             f"{len(must_not_be_null)} of {len(d.key)} key columns must never be null"
             + permitted)

        # A permission with no reason, or a reason with no permission, is not a declaration.
        coherent = ((d.nulls == "FORBIDDEN") == (not d.nullable)) and (
            not d.nullable or len(d.nulls.strip()) > 20)
        r.ok(f"P7-NUL-{d.object}-declared",
             f"{d.object} states a reason for every nullable key column", "BLOCKING",
             coherent, "coherent" if coherent else "incoherent", "coherent",
             "a nullable key column needs a reason a reviewer would accept")


# --------------------------------------------------------------------------- P7-REF
def _references(con, r: Result) -> None:
    present = _tables(con)
    for ref in REFERENCES:
        if ref.child not in present or ref.parent not in present:
            continue
        on = " AND ".join(f"c.{a} IS NOT DISTINCT FROM p.{b}"
                          for a, b in zip(ref.child_key, ref.parent_key))
        not_null = " AND ".join(f"c.{a} IS NOT NULL" for a in ref.child_key)
        orphans = _one(con, f"""
            SELECT count(*) FROM {ref.child} c
            WHERE {not_null}
              AND NOT EXISTS (SELECT 1 FROM {ref.parent} p WHERE {on})""")
        cols = ", ".join(ref.child_key)
        cid = f"P7-REF-{ref.child}->{ref.parent}"
        name = f"{ref.child}.({cols}) resolves in {ref.parent}"
        detail = f"owner {ref.owner}" + (f"; {ref.note}" if ref.note else "")

        if orphans == 0:
            r.add(cid, name, "BLOCKING", "PASS", 0, 0, detail)
        elif ref.accepted and orphans == ref.accepted:
            # The known open finding, unchanged. Recorded, not forgiven.
            r.add(cid, name, "BLOCKING", "SOURCE_FINDING", orphans,
                  f"{ref.accepted} accepted ({ref.defect})",
                  f"{detail}. Open finding {ref.defect}, unchanged at {ref.accepted} rows.")
        elif ref.accepted:
            r.add(cid, name, "BLOCKING", "FAIL", orphans, f"{ref.accepted} accepted",
                  f"{detail}. This is "
                  + ("MORE" if orphans > ref.accepted else "FEWER")
                  + f" than the {ref.accepted} rows accepted as {ref.defect}: "
                  + ("something new is wrong." if orphans > ref.accepted
                     else "the defect may have been fixed and the acceptance retired."))
        else:
            r.add(cid, name, "BLOCKING", "FAIL", orphans, 0, detail)


# --------------------------------------------------------------------------- P7-CPX
def _capital_projects(con, r: Result) -> None:
    """
    Capital Project -> CapEx fact -> Fixed Asset, proved end to end.

    P6-D-01's real damage was here: a fixed asset could not name the project that bought it,
    because five projects answered to the same identifier. Uniqueness alone does not prove
    the chain -- an identifier can be unique and still describe the wrong thing -- so each
    link is tested on the attributes that have to agree, and then on the money.
    """
    rows, ids = con.execute(
        "SELECT count(*), count(DISTINCT project_id) FROM fact_capex_project").fetchone()
    r.ok("P7-CPX-01", "Every capital project row carries its own project identifier",
         "BLOCKING", rows == ids, f"{rows:,} rows / {ids:,} ids", "equal",
         "the P6-D-01 condition, stated as an identity rather than a naming convention")

    orphan_assets = _one(con, """
        SELECT count(*) FROM ref_fixed_asset f
        WHERE NOT EXISTS (SELECT 1 FROM fact_capex_project p
                          WHERE p.project_id = f.project_id)""")
    r.ok("P7-CPX-02", "Every fixed asset resolves to a capital project", "BLOCKING",
         orphan_assets == 0, orphan_assets, 0)

    # An identifier that resolves to more than one definition of the thing it names.
    ambiguous = _one(con, """
        SELECT count(*) FROM (
            SELECT project_id FROM fact_capex_project
            GROUP BY project_id
            HAVING count(DISTINCT project_name) > 1 OR count(DISTINCT asset_class) > 1
                OR count(DISTINCT entity_code) > 1 OR count(DISTINCT period_key) > 1
                OR count(DISTINCT bu_code) > 1)""")
    r.ok("P7-CPX-03", "No project identifier resolves to two different project definitions",
         "BLOCKING", ambiguous == 0, ambiguous, 0,
         "the exact P6-D-01 symptom: one id, five names, five asset classes")

    class_disagreement = _one(con, """
        SELECT count(*) FROM ref_fixed_asset f
        JOIN fact_capex_project p USING (project_id)
        WHERE f.asset_class <> p.asset_class""")
    r.ok("P7-CPX-04", "A fixed asset agrees with its project on asset class", "BLOCKING",
         class_disagreement == 0, class_disagreement, 0,
         "policy: an asset created by a project belongs to that project's class")

    entity_disagreement = _one(con, """
        SELECT count(*) FROM ref_fixed_asset f
        JOIN fact_capex_project p USING (project_id)
        WHERE f.entity_code <> p.entity_code""")
    r.ok("P7-CPX-05", "A fixed asset agrees with its project on owning entity", "BLOCKING",
         entity_disagreement == 0, entity_disagreement, 0)

    period_disagreement = _one(con, """
        SELECT count(*) FROM ref_fixed_asset f
        JOIN fact_capex_project p USING (project_id)
        WHERE CAST(strftime(f.acquisition_date, '%Y%m') AS INTEGER) <> p.period_key""")
    r.ok("P7-CPX-06", "A fixed asset is acquired in its project's period", "BLOCKING",
         period_disagreement == 0, period_disagreement, 0,
         "an asset capitalised outside the month its project spent the money would break the "
         "capex-to-depreciation reconciliation")

    # The money. Asset cost is the project's spend, project by project.
    worst = _one(con, """
        SELECT coalesce(max(abs(d)), 0) FROM (
            SELECT round(sum(f.cost_local) - min(p.spend_local), 2) AS d
            FROM ref_fixed_asset f JOIN fact_capex_project p USING (project_id)
            GROUP BY f.project_id)""")
    r.ok("P7-CPX-07", "Fixed asset cost reconciles to project spend, project by project",
         "BLOCKING", worst == 0, f"{worst:.2f}", "0.00",
         "identifier integrity is only worth having if the amounts follow the identifier")

    unbuilt = _one(con, """
        SELECT count(*) FROM fact_capex_project p
        WHERE NOT EXISTS (SELECT 1 FROM ref_fixed_asset f
                          WHERE f.project_id = p.project_id)""")
    r.ok("P7-CPX-08", "Every capital project created at least one asset", "BLOCKING",
         unbuilt == 0, unbuilt, 0)

    mart_rows, mart_ids = con.execute(
        "SELECT count(*), count(DISTINCT project_id) FROM mart_capex").fetchone()
    r.ok("P7-CPX-09", "The CapEx mart carries the corrected key through to reporting",
         "BLOCKING", mart_rows == mart_ids, f"{mart_rows:,} rows / {mart_ids:,} ids", "equal",
         "this is the grain the Power BI CapEx fact and Capital Project dimension declare")


# --------------------------------------------------------------------------- P7-VER
def _versions(con, r: Result) -> None:
    """
    Scenario and version governance.

    P7-D-01: `PY_DERIVED` was used as a version code by 12,516 mart rows and by every
    prior-year comparator, while existing in no version master at all. It worked because
    nothing ever asked a version to resolve -- the same shape as P6-D-01, one dimension over.

    The rule these controls hold is that **a figure being derived is not a reason to leave its
    identity ungoverned**. A derived version is still a version: it has a row, a scenario, a
    policy, and a stated derivation. What it does not have is stored data, and that distinction
    is what is tested here rather than assumed.
    """
    # ---------------------------------------------------------------- referential integrity
    # Iterated from the facts that carry a version, so a fact nobody thought about fails here
    # rather than being silently out of scope.
    carriers = [(t, c) for t, c in (
        ("fact_plan", "version_code"), ("fact_financials", "version_code"),
        ("fact_trial_balance", "version_code"), ("fact_consol_journal", "version_code"),
        ("mart_financial_ytd", "version_code"), ("mart_financial_monthly", "version_code"),
        ("mart_business_unit", "version_code"), ("mart_entity_performance", "version_code"),
        ("mart_variance", "base_version"), ("mart_variance", "comparator_version"),
        ("ref_default_version", "version_code"),
    ) if t in _tables(con)]
    unresolved = 0
    detail = []
    for table, column in carriers:
        n = _one(con, f"""
            SELECT count(*) FROM {table} c WHERE c.{column} IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM dim_version v
                              WHERE v.version_code = c.{column})""")
        unresolved += n
        if n:
            detail.append(f"{table}.{column}={n}")
    r.ok("P7-VER-01", "Every version code in every fact and mart resolves to the version master",
         "BLOCKING", unresolved == 0, unresolved, 0,
         "; ".join(detail) if detail
         else f"{len(carriers)} version-bearing columns, all resolve")

    # ---------------------------------------------------------------- scenario compatibility
    # A version's scenario must exist, and its type must be the type its scenario declares.
    # Existence alone would let a Budget version sit under the Forecast scenario.
    incompatible = _one(con, """
        SELECT count(*) FROM dim_version v
        LEFT JOIN dim_scenario s USING (scenario_code)
        WHERE s.scenario_code IS NULL OR v.scenario_type <> s.scenario_type""")
    r.ok("P7-VER-02", "Every version is permitted for the scenario it belongs to", "BLOCKING",
         incompatible == 0, incompatible, 0,
         "the version's type must be the type its scenario declares, not merely a scenario "
         "that happens to exist")

    # A fact row's scenario and version must agree with the master, not just each exist.
    mismatched = _one(con, """
        SELECT count(*) FROM mart_financial_ytd m
        JOIN dim_version v ON v.version_code = m.version_code
        WHERE m.scenario_code <> v.scenario_code""")
    r.ok("P7-VER-03", "Every reporting row's scenario matches its version's scenario",
         "BLOCKING", mismatched == 0, mismatched, 0,
         "a row claiming scenario FC on a Budget version would reconcile perfectly and report "
         "the wrong thing")

    # ---------------------------------------------------------------- default uniqueness
    bad_defaults = _one(con, """
        SELECT count(*) FROM (
            SELECT s.scenario_code, count(*) FILTER (WHERE v.is_default) AS n
            FROM dim_scenario s JOIN dim_version v USING (scenario_code)
            WHERE NOT s.is_reserved AND NOT v.is_reserved
            GROUP BY s.scenario_code HAVING count(*) FILTER (WHERE v.is_default) <> 1)""")
    r.ok("P7-VER-04", "Each reportable scenario has exactly one default version", "BLOCKING",
         bad_defaults == 0, bad_defaults, 0,
         "three forecasts are retained and only the current one is the default; a superseded "
         "forecast presented as the forecast is an error nobody would notice")

    # ---------------------------------------------------------------- one authority
    # The defaults a report uses must BE the governed defaults, not a list assembled beside
    # them. `ref_default_version` used to union Prior Year in by hand because PY_DERIVED had
    # no version row to be the default of.
    off_book = _one(con, """
        SELECT count(*) FROM (
            SELECT scenario_code, version_code FROM ref_default_version
            EXCEPT
            SELECT scenario_code, version_code FROM dim_version
            WHERE is_default AND NOT is_reserved)""")
    r.ok("P7-VER-05", "No default version exists outside the governed version master",
         "BLOCKING", off_book == 0, off_book, 0,
         "one authoritative source for version membership; a second definition is a second "
         "answer waiting to disagree")

    # ---------------------------------------------------------------- derived-version policy
    derived = [row[0] for row in con.execute(
        "SELECT version_code FROM dim_version WHERE scenario_type = 'DERIVED'").fetchall()]
    r.ok("P7-VER-06", "Prior Year is a governed derived version, not an absent one", "BLOCKING",
         "PY_DERIVED" in derived, ", ".join(derived) or "none", "PY_DERIVED",
         "the P7-D-01 condition, stated as membership rather than as a convention")

    # A derived version is derived. It must not be loaded from anywhere.
    loaded = _one(con, """
        SELECT count(*) FROM fact_plan p JOIN dim_version v USING (version_code)
        WHERE v.scenario_type = 'DERIVED'""") + _one(con, """
        SELECT count(*) FROM fact_financials f JOIN dim_version v USING (version_code)
        WHERE v.scenario_type = 'DERIVED'""")
    r.ok("P7-VER-07", "A derived version carries no source-loaded rows", "BLOCKING",
         loaded == 0, loaded, 0,
         "Prior Year is a view of Actual. A stored PY row would be a second copy of a figure "
         "that is supposed to have one source, free to drift from it")

    unlocked = _one(con, """
        SELECT count(*) FROM dim_version
        WHERE scenario_type = 'DERIVED' AND NOT is_locked""")
    r.ok("P7-VER-08", "A derived version is locked against editing", "BLOCKING",
         unlocked == 0, unlocked, 0,
         "a derived figure that can be edited is no longer derived")

    orphan_derived = _one(con, """
        SELECT count(*) FROM dim_version v JOIN dim_scenario s USING (scenario_code)
        WHERE v.scenario_type = 'DERIVED'
          AND (s.derived_from_scenario_code IS NULL
               OR NOT EXISTS (SELECT 1 FROM dim_scenario p
                              WHERE p.scenario_code = s.derived_from_scenario_code))""")
    r.ok("P7-VER-09", "A derived version names the scenario it derives from, and it exists",
         "BLOCKING", orphan_derived == 0, orphan_derived, 0,
         "a derivation with no stated source is an assertion")

    # The derivation itself: Prior Year IS Actual, twelve months earlier. Recomputed from the
    # Actual rows rather than compared with another prior-year calculation.
    worst = _one(con, """
        SELECT coalesce(max(abs(py.ytd_usd - act.ytd_usd)), 0)
        FROM mart_financial_ytd py
        JOIN mart_financial_ytd act
          ON act.version_code = 'ACTUAL' AND act.period_key = py.period_key - 100
         AND act.basis = py.basis AND act.entity_code = py.entity_code
         AND act.bu_code = py.bu_code AND act.measure_code = py.measure_code
        WHERE py.version_code = 'PY_DERIVED'""")
    r.ok("P7-VER-10", "Prior Year equals Actual twelve months earlier, to the cent", "BLOCKING",
         worst == 0, f"{worst:.2f}", "0.00",
         "the derivation stated in the master, proved against the Actual it claims to be")

    missing_py = _one(con, """
        SELECT count(*) FROM mart_financial_ytd act
        WHERE act.version_code = 'ACTUAL' AND act.period_key < 202600
          AND NOT EXISTS (
              SELECT 1 FROM mart_financial_ytd py
              WHERE py.version_code = 'PY_DERIVED' AND py.period_key = act.period_key + 100
                AND py.basis = act.basis AND py.entity_code = act.entity_code
                AND py.bu_code = act.bu_code AND py.measure_code = act.measure_code)""")
    r.ok("P7-VER-11", "Every Actual month has its prior-year row a year later", "BLOCKING",
         missing_py == 0, missing_py, 0,
         "iterated from Actual, not from Prior Year: a PY row the derivation failed to build "
         "is invisible to a control that iterates PY")

    # ---------------------------------------------------------------- reserved scenarios
    reserved_leak = _one(con, """
        SELECT count(*) FROM dim_report_scenario d
        WHERE EXISTS (SELECT 1 FROM dim_scenario s
                      WHERE s.scenario_code = d.scenario_code AND s.is_reserved)
           OR EXISTS (SELECT 1 FROM dim_version v
                      WHERE v.version_code = d.version_code AND v.is_reserved)""")
    r.ok("P7-VER-12", "No reserved scenario or version is reportable", "BLOCKING",
         reserved_leak == 0, reserved_leak, 0,
         "a placeholder in configuration must not become reportable by being configured; "
         "Downside stays reserved until it is approved and populated")

    reserved_data = _one(con, """
        SELECT count(*) FROM mart_financial_ytd m JOIN dim_version v USING (version_code)
        WHERE v.is_reserved""")
    r.ok("P7-VER-13", "No reserved version carries reporting data", "BLOCKING",
         reserved_data == 0, reserved_data, 0,
         "reserved means unpopulated, and an empty report that looks like a real one is worse "
         "than no report")

    # ---------------------------------------------------------------- no blank members
    # Every version a report can select must be nameable. A code with no name is the blank
    # member a semantic model would otherwise invent.
    blank = _one(con, """
        SELECT count(*) FROM dim_report_scenario
        WHERE version_code IS NULL OR trim(coalesce(version_name, '')) = ''
           OR scenario_code IS NULL OR trim(coalesce(scenario_name, '')) = ''""")
    r.ok("P7-VER-14", "Every reportable version and scenario is named", "BLOCKING",
         blank == 0, blank, 0,
         "an unnamed member becomes a blank in every downstream report")


# --------------------------------------------------------------------------- P7-RPR
def _reproducibility(r: Result) -> None:
    """
    Lineage identifiers must identify content, not a checkout.

    P6-D-02: every phase hashed the raw bytes of its declared inputs, so a build id changed
    when git rewrote a line ending. A rebase demonstrated it -- the ids moved while not one
    byte of content did, and the form that reproduced each committed id turned out to be a
    per-file mixture of CRLF and LF.

    A unit test alone would not have caught the *next* phase quietly writing its own hasher,
    so this runs with the rest of the control suite and iterates the phases rather than a list
    somebody has to remember to extend.
    """
    import tempfile

    from src import lineage
    from src.lineage.digest import UnknownFileType

    phases = []
    try:
        from src.consol.run import BUILD_INPUTS as P4, build_id as id4
        from src.marts.run import BUILD_INPUTS as P5, build_id as id5
        from src.pipeline.run import BUILD_INPUTS as P3, build_id as id3
        from src.powerbi.run import BUILD_INPUTS as P6, build_id as id6
        phases = [("phase03", P3, id3, "src/pipeline/run.py"),
                  ("phase04", P4, id4, "src/consol/run.py"),
                  ("phase05", P5, id5, "src/marts/run.py"),
                  ("phase06a", P6, id6, "src/powerbi/run.py")]
    except ImportError as exc:                                   # pragma: no cover
        r.add("P7-RPR-01", "The phase build ids are importable", "BLOCKING", "FAIL",
              str(exc), "importable")
        return

    # ---- equivalent text, three encodings, one id
    sample = "code,name\n400100,Product revenue\n\n500100,Cost of sales  \n"
    with tempfile.TemporaryDirectory() as tmp:
        ids = set()
        for label, newline in (("lf", "\n"), ("crlf", "\r\n"), ("cr", "\r")):
            path = pathlib.Path(tmp) / label / "a.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(sample.replace("\n", newline).encode("utf-8"))
            ids.add(lineage.build_id([path]))
        # and a real content change must still move it
        changed = pathlib.Path(tmp) / "lf" / "b.csv"
        changed.write_bytes(sample.replace("400100", "400200").encode("utf-8"))
        moved = lineage.build_id([changed]) != lineage.build_id(
            [pathlib.Path(tmp) / "lf" / "a.csv"])
    r.ok("P7-RPR-01", "LF, CRLF and CR text produce one canonical build id", "BLOCKING",
         len(ids) == 1 and moved, f"{len(ids)} distinct ids, content change moves it: {moved}",
         "1 distinct id, True",
         "the P6-D-02 condition. The second half matters as much as the first: a hash that "
         "stopped noticing real changes would be a worse defect than the one it replaced")

    # ---- no phase writes its own hasher
    bypassed = []
    for name, _inputs, _fn, module in phases:
        source = (ROOT / module).read_text(encoding="utf-8")
        start = source.index("def build_id(")
        end = source.index("\ndef ", start + 1)
        body = source[start:end]
        if "lineage.build_id" not in body or "read_bytes" in body:
            bypassed.append(module)
    r.ok("P7-RPR-02", "No phase computes a build id outside the shared canonical hasher",
         "BLOCKING", not bypassed, "; ".join(bypassed) or 0, 0,
         "four subtly different implementations was the shape of the original defect")

    # ---- every declared input has a declared type
    undeclared = []
    for name, inputs, _fn, _module in phases:
        for path in inputs:
            try:
                lineage.is_text(pathlib.Path(path))
            except UnknownFileType:
                undeclared.append(f"{name}:{pathlib.Path(path).name}")
    r.ok("P7-RPR-03", "Every declared build input has a declared text or binary type",
         "BLOCKING", not undeclared, "; ".join(undeclared) or 0, 0,
         "guessing whether a file is text is how a build id becomes environment-dependent")

    # ---- the committed manifests reproduce
    drifted = []
    for name, _inputs, fn, _module in phases:
        manifest = ROOT / "data" / f"{name}_manifest.json"
        if not manifest.exists():
            continue
        recorded = json.loads(manifest.read_text(encoding="utf-8")).get("build_id")
        if recorded != fn():
            drifted.append(f"{name}: {recorded} vs {fn()}")
    r.ok("P7-RPR-04", "Every committed manifest reproduces its build id in this working tree",
         "BLOCKING", not drifted, "; ".join(drifted) or 0, 0,
         "recomputed from the declared inputs as they stand, so a checkout that changed them "
         "fails here rather than at the next rebuild")

    # ---- the byte digest is still a byte digest
    with tempfile.TemporaryDirectory() as tmp:
        lf = pathlib.Path(tmp) / "a.csv"
        crlf = pathlib.Path(tmp) / "b.csv"
        lf.write_bytes(b"x,y\n1,2\n")
        crlf.write_bytes(b"x,y\r\n1,2\r\n")
        distinct = lineage.exact_digest(lf) != lineage.exact_digest(crlf)
    r.ok("P7-RPR-05", "The exact artefact digest still answers byte identity", "BLOCKING",
         distinct, f"line endings distinguishable: {distinct}", "True",
         "a build id and an artefact digest answer different questions, and redefining the "
         "second as the first would destroy the ability to prove a rebuild is byte-identical")


def run(con: duckdb.DuckDBPyConnection) -> Result:
    r = Result()
    _registry_completeness(con, r)
    _keys(con, r)
    _references(con, r)
    _capital_projects(con, r)
    _versions(con, r)
    _reproducibility(r)
    return r


def write(res: Result) -> None:
    CONTROL_RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(CONTROL_RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys()))
        w.writeheader()
        w.writerows(res)


def report(res: Result) -> None:
    for row in res:
        if row["status"] != "PASS":
            print(f"  {row['status']:6} {row['control_id']:52} {row['control_name']}")
            print(f"         measured {row['measured']} vs {row['threshold']}"
                  f" -- {row['detail']}")
    families: dict[str, list[int]] = {}
    for row in res:
        fam = row["control_id"].split("-")[1]
        seen = families.setdefault(fam, [0, 0])
        seen[0] += 1
        seen[1] += row["status"] == "PASS"
    for fam, (total, passed) in sorted(families.items()):
        print(f"  P7-{fam:4} {passed:>4}/{total:<4} passed")
    findings = [r for r in res if r["status"] == "SOURCE_FINDING"]
    for row in findings:
        print(f"  FINDING {row['control_id']}: {row['detail']}")
    print(f"{sum(r['status'] == 'PASS' for r in res)}/{len(res)} key and grain controls "
          f"passed, {len(findings)} open findings, {len(res.failed)} blocking failures")


def main(argv: list[str]) -> int:
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    res = run(con)
    con.close()
    if "--no-write" not in argv:
        write(res)
    report(res)
    return 1 if res.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
