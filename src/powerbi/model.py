"""
Generate the Power BI project: TMDL semantic model plus the PBIP shell.

The model is **authored as code**, the same way the Excel workbook is, and for the same
reason: a semantic model kept only as a `.pbix` is a binary nobody can review, diff or
regenerate. Here every table, column, relationship, measure, format string and description is
produced from `config.py` and `measures.py`, so a change to the model is a change to a Python
declaration and shows up in a diff as one.

## Determinism

Power BI writes a `lineageTag` GUID on every object. Left to Desktop those are random, and two
generations of an identical model would differ in every file. They are derived here from a
UUID5 over the object's own name, so the same model always produces the same tags and the
project is byte-reproducible.

The one machine-specific value is the `DataFolder` parameter, which has to be an absolute path
for Desktop to resolve it. It is written from the repository location at generation time and
`P6-SEM-08` checks that it points at this repository's published marts.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import duckdb

from . import config as C
from .measures import MEASURES, PERIOD_BASIS_ROWS

#: A fixed namespace, so a lineage tag is a function of the object's name and nothing else.
NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

TYPE_MAP = {
    "BIGINT": ("int64", "Int64.Type"), "INTEGER": ("int64", "Int64.Type"),
    "HUGEINT": ("int64", "Int64.Type"), "SMALLINT": ("int64", "Int64.Type"),
    "DOUBLE": ("double", "Number.Type"), "FLOAT": ("double", "Number.Type"),
    "BOOLEAN": ("boolean", "Logical.Type"),
    "DATE": ("dateTime", "Date.Type"), "TIMESTAMP": ("dateTime", "DateTime.Type"),
    "VARCHAR": ("string", "Text.Type"),
}


def tag(*parts: str) -> str:
    return str(uuid.uuid5(NAMESPACE, "|".join(parts)))


def _dtype(duck_type: str) -> tuple[str, str]:
    base = duck_type.split("(")[0].upper()
    if base.startswith("DECIMAL"):
        return "decimal", "Currency.Type"
    return TYPE_MAP.get(base, ("string", "Text.Type"))


def publish_dimensions(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """
    Write the semantic dimension tables the marts do not publish.

    They are conformance only -- selections of dimensions the warehouse already holds -- and
    they go to their own folder so the Phase 5 marts stay frozen and their manifest digest
    does not move.
    """
    C.SEMANTIC_DIR.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name, sql in C.SEMANTIC_DIMENSIONS:
        con.execute(f"CREATE OR REPLACE TABLE {name} AS "
                    + sql.format(report_period=C.REPORT_PERIOD))
        out = C.SEMANTIC_DIR / f"{name}.parquet"
        con.execute(f"COPY (SELECT * FROM {name} ORDER BY ALL) TO '{out.as_posix()}' "
                    f"(FORMAT PARQUET, COMPRESSION ZSTD)")
        counts[name] = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]

    # The disconnected period-basis dimension. Published like every other table rather than
    # created as a calculated table, so the model has no calculated tables at all.
    rows = ", ".join(f"('{code}', '{name}', {order})"
                     for code, name, order in PERIOD_BASIS_ROWS)
    con.execute(f"""
        CREATE OR REPLACE TABLE dim_semantic_period_basis AS
        SELECT * FROM (VALUES {rows}) AS t(basis_code, basis_name, sort_order)
    """)
    out = C.SEMANTIC_DIR / "dim_semantic_period_basis.parquet"
    con.execute(f"COPY (SELECT * FROM dim_semantic_period_basis ORDER BY ALL) "
                f"TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    counts["dim_semantic_period_basis"] = len(PERIOD_BASIS_ROWS)
    return counts


def _columns(con, table: str) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in con.execute(f"DESCRIBE {table}").fetchall()]


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _description_lines(text: str, indent: str) -> list[str]:
    """TMDL descriptions are triple-slash comment lines above the object."""
    words, line, out = text.split(), "", []
    for word in words:
        if len(line) + len(word) + 1 > 92:
            out.append(f"{indent}/// {line}")
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(f"{indent}/// {line}")
    return out


def _table_tmdl(con, spec: dict) -> str:
    name, source = spec["name"], spec["source"]
    folder = "35_semantic" if spec["folder"] == "semantic" else "30_marts"
    lines: list[str] = []
    lines += _description_lines(spec["description"], "")
    lines.append(f"table '{name}'")
    lines.append(f"\tlineageTag: {tag('table', name)}")
    lines.append("")

    for column, duck_type in _columns(con, source):
        data_type, _ = _dtype(duck_type)
        hidden = column in spec["hide"]
        is_key = column in spec["key"] and spec["kind"] == "dimension" and len(spec["key"]) == 1
        lines.append(f"\tcolumn {column}")
        lines.append(f"\t\tdataType: {data_type}")
        if hidden:
            lines.append("\t\tisHidden")
        if is_key:
            lines.append("\t\tisKey")
        lines.append(f"\t\tlineageTag: {tag('column', name, column)}")
        # Numeric columns on a fact are summed by the measure layer, never by a report
        # dropping a column onto a visual: an implicit total is a definition nobody wrote.
        lines.append("\t\tsummarizeBy: none")
        lines.append(f"\t\tsourceColumn: {column}")
        if column in spec.get("sort", {}):
            lines.append(f"\t\tsortByColumn: {spec['sort'][column]}")
        if data_type == "dateTime":
            lines.append('\t\tformatString: yyyy-mm-dd')
        lines.append("")
        lines.append("\t\tannotation SummarizationSetBy = Automatic")
        lines.append("")

    lines.append(f"\tpartition '{name}' = m")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource =")
    lines.append("\t\t\t\tlet")
    lines.append(f'\t\t\t\t    Source = Parquet.Document(File.Contents('
                 f'DataFolder & "\\{folder}\\{source}.parquet"))')
    lines.append("\t\t\t\tin")
    lines.append("\t\t\t\t    Source")
    lines.append("")
    lines.append("\tannotation PBI_ResultType = Table")
    lines.append("")
    return "\n".join(lines)


def _measures_tmdl() -> str:
    """
    Every measure lives on one table.

    Scattering measures across the tables they happen to read is the default and it is wrong:
    a reader looking for `Covenant Headroom` should not have to know which fact it came from,
    and moving a measure between tables changes nothing about it except where people look.
    """
    lines = ["/// Every measure in the model. Measures are grouped by display folder, not by",
             "/// the table they read, so a report author finds them by what they mean.",
             "table Measures",
             f"\tlineageTag: {tag('table', 'Measures')}",
             ""]
    for name, expression, fmt, folder, description in MEASURES:
        lines += _description_lines(description, "\t")
        lines.append(f"\tmeasure '{name}' =")
        for row in expression.split("\n"):
            lines.append(f"\t\t\t{row}" if row else "")
        if fmt:
            lines.append(f'\t\tformatString: {fmt}')
        lines.append(f"\t\tlineageTag: {tag('measure', name)}")
        lines.append(f"\t\tdisplayFolder: {folder}")
        lines.append("")

    # A measures-only table needs one hidden column to exist at all.
    lines += ["\tcolumn _placeholder",
              "\t\tisHidden",
              "\t\tdataType: int64",
              f"\t\tlineageTag: {tag('column', 'Measures', '_placeholder')}",
              "\t\tsummarizeBy: none",
              "\t\tsourceColumn: _placeholder",
              "",
              "\t\tannotation SummarizationSetBy = Automatic",
              "",
              "\tpartition Measures = m",
              "\t\tmode: import",
              "\t\tsource =",
              "\t\t\t\tlet",
              "\t\t\t\t    Source = #table(type table [_placeholder = Int64.Type], {})",
              "\t\t\t\tin",
              "\t\t\t\t    Source",
              "",
              "\tannotation PBI_ResultType = Table",
              ""]
    return "\n".join(lines)


def _relationships_tmdl() -> str:
    lines: list[str] = []
    for from_table, from_col, to_table, to_col in C.RELATIONSHIPS:
        rid = tag("rel", from_table, from_col, to_table, to_col)
        lines.append(f"relationship {rid}")
        lines.append(f"\tfromColumn: '{from_table}'.{from_col}")
        lines.append(f"\ttoColumn: '{to_table}'.{to_col}")
        lines.append("")
    for from_table, from_col, to_table, to_col, why in C.INACTIVE_RELATIONSHIPS:
        rid = tag("rel", from_table, from_col, to_table, to_col)
        lines += _description_lines(why, "")
        lines.append(f"relationship {rid}")
        lines.append("\tisActive: false")
        lines.append(f"\tfromColumn: '{from_table}'.{from_col}")
        lines.append(f"\ttoColumn: '{to_table}'.{to_col}")
        lines.append("")
    return "\n".join(lines)


def _model_tmdl() -> str:
    order = json.dumps([t["name"] for t in C.TABLES] + ["Period Basis", "Measures"])
    return "\n".join([
        "model Model",
        "\tculture: en-GB",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: en-GB",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        f"\tannotation PBI_QueryOrder = {order}",
        "",
        "\tannotation PBI_ProTooling = [\"DevMode\"]",
        "",
        "ref table 'Period Basis'",
        *[f"ref table '{t['name']}'" for t in C.TABLES],
        "ref table Measures",
        "",
        "ref cultureInfo en-GB",
        "",
    ])


def _period_basis_tmdl(con) -> str:
    spec = dict(name="Period Basis", source="dim_semantic_period_basis", folder="semantic",
                kind="dimension", key=("basis_code",), sort={"basis_name": "sort_order"},
                hide=("sort_order",),
                description="Month, year to date or full year. DISCONNECTED on purpose: it is "
                            "read by the statement measures to choose which governed column "
                            "to aggregate, and it filters no fact. Relating it to anything "
                            "would filter rows, which is not what it is for.")
    return _table_tmdl(con, spec)


def generate(con: duckdb.DuckDBPyConnection) -> dict:
    """Write the whole PBIP project. Returns a small summary for the manifest."""
    # Clear only what this generator owns. `powerbi/` itself holds committed files that are
    # not generated, so removing the whole folder would delete work that is not ours.
    for owned in (C.MODEL_DIR, C.REPORT_DIR):
        if owned.exists():
            shutil.rmtree(owned)
    definition = C.MODEL_DIR / "definition"
    (definition / "tables").mkdir(parents=True, exist_ok=True)
    (definition / "cultures").mkdir(parents=True, exist_ok=True)
    C.REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- the .pbip shell
    (C.PBIP_DIR / f"{C.PROJECT}.pbip").write_text(json.dumps({
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{C.PROJECT}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    }, indent=2) + "\n", encoding="utf-8")

    (C.MODEL_DIR / "definition.pbism").write_text(json.dumps({
        "version": "4.2", "settings": {},
    }, indent=2) + "\n", encoding="utf-8")

    (C.REPORT_DIR / "definition.pbir").write_text(json.dumps({
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{C.PROJECT}.SemanticModel"}},
    }, indent=2) + "\n", encoding="utf-8")

    # A single technical page. Phase 6A validates a semantic model; the report pages are
    # Phase 6B, and building them now would be building on an unapproved model.
    (C.REPORT_DIR / "report.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/"
                   "definition/report/1.0.0/schema.json",
        "themeCollection": {},
        "sections": [{
            "name": "TechnicalValidation",
            "displayName": "Technical validation",
            "ordinal": 0, "width": 1280, "height": 720,
            "visualContainers": [],
        }],
        "config": json.dumps({"version": "5.43", "themeCollection": {}}),
        "layoutOptimization": 0,
    }, indent=2) + "\n", encoding="utf-8")

    # ---------------------------------------------------------------- the model
    (definition / "database.tmdl").write_text(
        "database\n\tcompatibilityLevel: 1567\n", encoding="utf-8")
    (definition / "model.tmdl").write_text(_model_tmdl(), encoding="utf-8")
    (definition / "relationships.tmdl").write_text(_relationships_tmdl(), encoding="utf-8")
    (definition / "cultures" / "en-GB.tmdl").write_text(
        "cultureInfo en-GB\n\n\tlinguisticMetadata =\n\t\t\t{\n"
        '\t\t\t  "Version": "1.0.0",\n\t\t\t  "Language": "en-GB"\n\t\t\t}\n'
        "\n\t\tcontentType: json\n", encoding="utf-8")

    # the DataFolder parameter: the one machine-specific value in the project
    data_folder = str(C.DATA.resolve()).replace("\\", "\\\\")
    (definition / "expressions.tmdl").write_text("\n".join([
        "/// The folder holding the published reporting marts and semantic dimensions. This is",
        "/// the only absolute path in the project. It is written from the repository location",
        "/// when the model is generated, and `P6-SEM-08` checks it still points at this",
        "/// repository's published data.",
        f'expression DataFolder = "{data_folder}" meta '
        '[IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
        f"\tlineageTag: {tag('expression', 'DataFolder')}",
        "",
        "\tannotation PBI_NavigationStepName = Navigation",
        "",
        "\tannotation PBI_ResultType = Text",
        "",
    ]), encoding="utf-8")

    tables = 0
    for spec in C.TABLES:
        (definition / "tables" / f"{spec['name']}.tmdl").write_text(
            _table_tmdl(con, spec), encoding="utf-8")
        tables += 1
    (definition / "tables" / "Period Basis.tmdl").write_text(
        _period_basis_tmdl(con), encoding="utf-8")
    (definition / "tables" / "Measures.tmdl").write_text(_measures_tmdl(), encoding="utf-8")
    tables += 2

    return {
        "tables": tables,
        "measures": len(MEASURES),
        "relationships": len(C.RELATIONSHIPS),
        "inactive_relationships": len(C.INACTIVE_RELATIONSHIPS),
    }
