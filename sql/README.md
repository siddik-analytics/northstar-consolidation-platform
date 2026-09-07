# SQL Transformation Layer

Built in Phases 3–5. Scripts are numbered by pipeline stage and run in order.

| Directory | Phase | Contents |
|---|---|---|
| `00_staging/` | 3 | Per-ERP ingestion: sign, locale, encoding, date and account-code normalisation |
| `10_dimensions/` | 3 | Conformed dimensions built from `config/` |
| `20_facts/` | 3 | Mapped, un-consolidated facts |
| `30_consolidation/` | 4 | FX translation, CTA, elimination, NCI, adjustments, cash flow derivation |
| `40_marts/` | 5 | Reporting-shaped marts for Excel and Power BI |
| `90_controls/` | 3–5 | The 71-control suite, executable as one command |

Conventions: one concern per file, named `<nn>_<verb>_<subject>.sql`. Standard SQL wherever
DuckDB-specific syntax is avoidable, so a later port to a server warehouse stays cheap
(ADR-0001). Every script is idempotent — re-running a period replaces it rather than
appending.
