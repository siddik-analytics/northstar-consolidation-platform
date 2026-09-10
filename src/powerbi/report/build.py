"""
Write the report: `powerbi/Northstar.Report/` in the enhanced (PBIR) format.

    python -m src.powerbi.report.build      writes the report folder only

`model.generate()` calls `generate()` so the whole project -- model and report -- comes from
one command and one set of declarations. The folder written is:

    Northstar.Report/
      definition.pbir                      binds to ../Northstar.SemanticModel
      definition/report.json               theme collection, settings
      definition/version.json
      definition/pages/pages.json          page order, the page that opens first
      definition/pages/<page>/page.json    size, filters, visual interactions
      definition/pages/<page>/visuals/<visual>/visual.json
      StaticResources/RegisteredResources/NorthstarIndustrial.json   the theme
      StaticResources/SharedResources/BaseThemes/Fluent2-CY26SU08.json  Desktop's base theme

Nothing in the report folder is edited by hand. A change is a change to `pages.py`,
`layout.py`, `theme.py` or `pbir.py`, and the folder is regenerated.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from .. import config as C
from . import pages as PAGES
from . import pbir as P
from . import theme as T

THEME_FILE = "NorthstarIndustrial.json"
BASE_THEME = "Fluent2-CY26SU08.json"
ASSETS = Path(__file__).with_name("assets")


def _write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_pages() -> list:
    P.MEASURES_TABLE = C.MEASURES_TABLE
    return [factory() for factory in PAGES.PAGES]


def generate(report_dir: Path | None = None) -> dict:
    """Write the report folder. Returns a summary for the manifest."""
    report_dir = report_dir or C.REPORT_DIR
    if report_dir.exists():
        shutil.rmtree(report_dir)
    definition = report_dir / "definition"
    _write(report_dir / "definition.pbir", {
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{C.PROJECT}.SemanticModel"}},
    })
    _write(definition / "report.json", P.report(THEME_FILE))
    _write(definition / "version.json", P.version())
    _write(report_dir / "StaticResources" / "RegisteredResources" / THEME_FILE, T.theme())
    base = report_dir / "StaticResources" / "SharedResources" / "BaseThemes" / BASE_THEME
    base.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ASSETS / BASE_THEME, base)

    pages = build_pages()
    _write(definition / "pages" / "pages.json",
           P.pages_index([pg.name for pg in pages], pages[0].name))
    visuals = 0
    for pg in pages:
        folder = definition / "pages" / pg.name
        _write(folder / "page.json", pg.page_json())
        for v in pg.visuals:
            _write(folder / "visuals" / v["name"] / "visual.json", v)
            visuals += 1
    return {"pages": len(pages), "visuals": visuals, "theme": THEME_FILE}


def main(argv: list[str]) -> int:
    summary = generate()
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
