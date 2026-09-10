"""
Deploy the semantic model to a live Analysis Services engine, and validate it there.

The `P6-XAR` controls have to compare what **Power BI** reports against what the marts hold.
A comparison where both sides are things I wrote is not evidence, so the Power BI side has to
come from the real engine evaluating the real DAX.

Power BI Desktop will not open a PBIP project from the command line on this machine -- `.pbip`
has no file association and the Store build does not forward the argument -- but the Analysis
Services instance Desktop runs behind itself **does** accept TMSL over XMLA, which is how
external tabular tools have always driven it. So the model is deployed to that instance and
queried there.

The TMSL is emitted from `config.TABLES`, `config.RELATIONSHIPS` and `measures.MEASURES` --
the same declarations that produce the TMDL, and the reason the two cannot disagree. What is
validated here is therefore the model the PBIP project describes, not a convenient subset of
it: every table, every relationship, every measure, loaded and evaluated by the engine that
will run the reports.
"""

from __future__ import annotations

import json

from . import config as C
from . import dax
from . import model
from .measures import MEASURES, PERIOD_BASIS_ROWS

DATABASE = "NorthstarSemanticValidation"

TYPE_MAP = {
    "BIGINT": "int64", "INTEGER": "int64", "HUGEINT": "int64", "SMALLINT": "int64",
    "DOUBLE": "double", "FLOAT": "double", "BOOLEAN": "boolean",
    "DATE": "dateTime", "TIMESTAMP": "dateTime", "VARCHAR": "string",
}


def _dtype(duck_type: str) -> str:
    base = duck_type.split("(")[0].upper()
    if base.startswith("DECIMAL"):
        return "decimal"
    return TYPE_MAP.get(base, "string")


def _columns(con, table: str) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in con.execute(f"DESCRIBE {table}").fetchall()]


def _m_partition(name: str, folder: str, source: str) -> dict:
    path = (C.DATA / folder / f"{source}.parquet").as_posix().replace("/", "\\")
    return {
        "name": name,
        "mode": "import",
        "source": {
            "type": "m",
            "expression": [
                "let",
                f'    Source = Parquet.Document(File.Contents("{path}"))',
                "in",
                "    Source",
            ],
        },
    }


def _table(con, spec: dict) -> dict:
    folder = "35_semantic" if spec["folder"] == "semantic" else "30_marts"
    columns = []
    for column, duck_type in _columns(con, spec["source"]):
        col = {
            "name": column,
            "dataType": _dtype(duck_type),
            "sourceColumn": column,
            "summarizeBy": "none",
        }
        if column in spec["hide"]:
            col["isHidden"] = True
        if column in spec.get("sort", {}):
            col["sortByColumn"] = spec["sort"][column]
        columns.append(col)

    for column, expression in spec.get("calculated", {}).items():
        columns.append({
            "name": column, "dataType": "string", "type": "calculated",
            "expression": expression, "isHidden": True, "summarizeBy": "none",
        })

    table = {
        "name": spec["name"],
        "description": spec["description"],
        "columns": columns,
        "partitions": [_m_partition(spec["name"], folder, spec["source"])],
    }

    hierarchies = []
    for hier_name, levels in spec.get("hierarchies", {}).items():
        hierarchies.append({
            "name": hier_name,
            "levels": [
                {"name": level.replace("_", " ").capitalize(), "ordinal": i, "column": level}
                for i, level in enumerate(levels)
            ],
        })
    if hierarchies:
        table["hierarchies"] = hierarchies
    return table


def _measures_table() -> dict:
    return {
        "name": C.MEASURES_TABLE,
        "description": "Every measure in the model, grouped by what it means rather than by "
                       "the table it reads.",
        "columns": [{"name": "_placeholder", "dataType": "int64", "isHidden": True,
                     "sourceColumn": "_placeholder", "summarizeBy": "none"}],
        "partitions": [{
            "name": C.MEASURES_TABLE, "mode": "import",
            "source": {"type": "m", "expression": [
                "let",
                "    Source = #table(type table [_placeholder = Int64.Type], {})",
                "in",
                "    Source",
            ]},
        }],
        "measures": [
            {
                "name": name,
                "expression": expression.split("\n"),
                "displayFolder": folder,
                "description": description,
                **({"formatString": fmt} if fmt else {}),
            }
            for name, expression, fmt, folder, description in MEASURES
        ],
    }


def _period_basis_table() -> dict:
    rows = ", ".join(f'{{"{code}", "{name}", {order}}}'
                     for code, name, order in PERIOD_BASIS_ROWS)
    return {
        "name": "Period Basis",
        "description": "Month, year to date or full year. DISCONNECTED on purpose: it is read "
                       "by the statement measures to choose which governed column to "
                       "aggregate, and it filters no fact.",
        "columns": [
            {"name": "basis_code", "dataType": "string", "sourceColumn": "basis_code",
             "summarizeBy": "none"},
            {"name": "basis_name", "dataType": "string", "sourceColumn": "basis_name",
             "summarizeBy": "none", "sortByColumn": "sort_order"},
            {"name": "sort_order", "dataType": "int64", "sourceColumn": "sort_order",
             "summarizeBy": "none", "isHidden": True},
        ],
        "partitions": [{
            "name": "Period Basis", "mode": "import",
            "source": {"type": "m", "expression": [
                "let",
                "    Source = #table(type table [basis_code = Text.Type, "
                "basis_name = Text.Type, sort_order = Int64.Type],",
                f"        {{{rows}}})",
                "in",
                "    Source",
            ]},
        }],
    }


def _relationships() -> list[dict]:
    out = []
    for from_table, from_col, to_table, to_col in C.RELATIONSHIPS:
        out.append({
            "name": f"{from_table}_{from_col}_to_{to_table}_{to_col}",
            "fromTable": from_table, "fromColumn": from_col,
            "toTable": to_table, "toColumn": to_col,
            "crossFilteringBehavior": "oneDirection",
        })
    for from_table, from_col, to_table, to_col, why in C.INACTIVE_RELATIONSHIPS:
        out.append({
            "name": f"{from_table}_{from_col}_to_{to_table}_{to_col}_inactive",
            "fromTable": from_table, "fromColumn": from_col,
            "toTable": to_table, "toColumn": to_col,
            "crossFilteringBehavior": "oneDirection",
            "isActive": False,
            # The same annotation the TMDL carries, so the two forms of the model hold the
            # same metadata and P6-PBIP-04 can compare them.
            "annotations": [{"name": model.RATIONALE_ANNOTATION,
                             "value": model._one_line(why)}],
        })
    return out


def build_tmsl(con) -> dict:
    tables = [_table(con, spec) for spec in C.TABLES]
    tables.append(_period_basis_table())
    tables.append(_measures_table())
    return {
        "createOrReplace": {
            "object": {"database": DATABASE},
            "database": {
                "name": DATABASE,
                "compatibilityLevel": 1567,
                "model": {
                    "culture": "en-GB",
                    "defaultPowerBIDataSourceVersion": "powerBI_V3",
                    "annotations": [{"name": "__PBI_TimeIntelligenceEnabled", "value": "0"}],
                    "tables": tables,
                    "relationships": _relationships(),
                },
            },
        }
    }


def deploy(con) -> tuple[bool, str]:
    """Create the model on the live instance and load it. Returns (ok, message)."""
    ready, why = dax.available()
    if not ready:
        return False, why
    tmsl = build_tmsl(con)
    conn, _ = dax.connect()
    cmd = conn.CreateCommand()
    cmd.CommandText = json.dumps(tmsl)
    try:
        cmd.ExecuteNonQuery()
    except Exception as exc:
        return False, f"TMSL createOrReplace failed: {exc.__class__.__name__}: {exc}"

    refresh = {"refresh": {"type": "full",
                           "objects": [{"database": DATABASE}]}}
    cmd = conn.CreateCommand()
    cmd.CommandText = json.dumps(refresh)
    try:
        cmd.ExecuteNonQuery()
    except Exception as exc:
        return False, f"refresh failed: {exc.__class__.__name__}: {exc}"
    # The model that now exists is not the one the cached connection is pointed at.
    dax.reset()
    return True, f"deployed and refreshed {DATABASE}"


def drop(_con=None) -> None:
    conn, _ = dax.connect()
    if conn is None:
        return
    cmd = conn.CreateCommand()
    cmd.CommandText = json.dumps({"delete": {"object": {"database": DATABASE}}})
    try:
        cmd.ExecuteNonQuery()
    except Exception:
        pass
