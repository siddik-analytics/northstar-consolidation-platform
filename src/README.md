# Source Code

| Package | Phase | Purpose |
|---|---|---|
| `anchors/` | 1 | The driver-based financial anchor model. Emits `config/anchors/*.csv` and generates `docs/financial-anchors.md`. Self-asserting: refuses to emit output if the balance sheet does not balance or the cash flow does not tie. |
| `generators/` | 2 | Deterministic, seeded synthetic source system generators — one per ERP, plus FX, headcount, capex, debt and master data |
| `pipeline/` | 3–5 | Orchestration: runs the SQL layers in order and enforces blocking controls |
| `common/` | 3+ | Shared utilities: config loading, DuckDB connection, logging, control execution |

Python is used for orchestration, generation and anything genuinely procedural. Accounting
logic lives in SQL, where a finance professional can read it (ADR-0001).
