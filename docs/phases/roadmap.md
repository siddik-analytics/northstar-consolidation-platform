# Delivery Roadmap

Ten phases, each with a formal approval gate. **No phase begins without written approval of
the preceding phase.**

The brief suggested eight phases. This plan uses ten, because two of the suggested phases
each contained two genuinely separable pieces of work with different risk profiles:

- Source data generation is split from ingestion and harmonisation. Generating realistic ERP
  extracts and *consuming* them are different problems, and the second is where the
  chart-of-accounts risk lives.
- Reporting marts and the automated control suite are split from the consolidation engine.
  Controls only become meaningful once the data exists, and they should be built and proven
  before any reporting is layered on top.

| Phase | Name | Status |
|---|---|---|
| 1 | Business design & architecture | **Complete** |
| 1.1 | Architecture correction pass | **Complete — ready for Phase 2 approval** |
| 2 | Synthetic source systems & reference data | Not started |
| 3 | Ingestion, staging & COA harmonisation | Not started |
| 4 | Consolidation engine | Not started |
| 5 | Reporting marts & automated control suite | Not started |
| 6 | Excel FP&A and management reporting models | Not started |
| 7 | Power BI semantic model & report suite | Not started |
| 8 | Board reporting pack & commentary framework | Not started |
| 9 | QA, reconciliation & performance hardening | Not started |
| 10 | Documentation & portfolio packaging | Not started |

---

## Phase 1 — Business design & architecture ✅

Define the company, the financial anchors, the group and source charts of accounts, the
consolidation logic, the data model, the reporting design and the control framework — before
generating any data.

**Delivered:** 11 documents, 14 ADRs, 12 configuration seed files, an executable anchor model
and 152 automated tests. See [`phase-01-report.md`](phase-01-report.md).

---

## Phase 1.1 — Architecture correction pass ✅

Corrections required at the Phase 1 approval gate: the consolidation layer set given a single
canonical definition and propagated everywhere; the non-controlling interest and FX/CTA
policies completed; covenant and EBITDA decisions applied; a Downside scenario reserved.

**Delivered:** 3 new documents (NCI policy, FX/CTA policy, ADR-0015), 3 new configuration files
(layers, ownership history, credit agreement), 10 new controls, 45 new tests, 2 new anchor
outputs. No financial anchor changed. See [`phase-01-1-report.md`](phase-01-1-report.md).

---

## Phase 2 — Synthetic source systems & reference data

Generate the raw material: three ERPs' worth of extracts that look and behave like real
exports, calibrated to hit the Phase 1 anchors.

**Deliverables**
- Deterministic, seeded generators in `src/generators/`
- ~1.5m journal lines across 12 entities and 45 months, in each ERP's own format, sign
  convention, locale and encoding — including Kestrel's Windows-1252 encoding, comma decimals
  and periods 13–16
- Monthly FX rate series for three rate sets, calibrated so revenue-weighted monthly averages
  reproduce the annual anchors within 10 basis points
- Budget (`BUD_FY26_V1`) and three forecast versions at full consolidation grain
- Intercompany transactions generated **in matched pairs by construction**, with deliberate,
  documented breaks: cut-off differences, an FX residual on the GBP/EUR pair, and one
  disputed balance
- `fact_ownership_interest` for **every** entity and period, and `NIG-510` generated at 100%
  with pre- and post-acquisition reserves distinguishable (see `docs/nci-policy.md` §13)
- Acquisition-date spot rates and per-event historical equity rates (see
  `docs/fx-cta-policy.md` §8)
- Headcount, capex, debt schedule, customer and product master data
- Revenue detail reconciling to GL revenue accounts

**Exit criteria**
- Each entity's raw trial balance balances in local currency, in its own sign convention
- Generated group results reconcile to the Phase 1 anchors within tolerance (`CTL-REC-06`)
- Business narrative is visible in the data: margin expansion, deleveraging, the FY2026 miss
- Regeneration from a fixed seed is byte-identical

**Risks.** This is the phase most likely to consume more effort than expected. Generating data
that is simultaneously realistic, internally consistent and anchor-conforming is genuinely
hard — the temptation will be to relax the anchor tolerance. It should not be relaxed.

---

## Phase 3 — Ingestion, staging & COA harmonisation

Consume the extracts. This is where the chart-of-accounts risk is concentrated.

**Deliverables**
- `sql/00_staging/` — per-ERP ingestion with sign, locale, encoding and date normalisation
- Kestrel special-period handling (13–16 → December with an adjustment flag)
- Effective-dated mapping engine including the conditional split rule evaluator
- German total-cost-method reclassification with sign reversal
- `sql/10_dimensions/` — all conformed dimensions built from `config/`
- Controls `CTL-DQ-*`, `CTL-MAP-*`, `CTL-TB-01`, `CTL-TB-02`, `CTL-IC-04`, `CTL-IC-05`

**Exit criteria**
- Every source account mapped; zero suspense balances
- Trial balance balances before **and after** mapping, per entity, per period
- No conditional split falls through unresolved
- Gross margin by BU lands within the anchor band — the proof that the payroll splits worked

---

## Phase 4 — Consolidation engine

**Deliverables**
- FX translation: monthly average P&L, closing balance sheet, historical equity, computed CTA
- Constant-currency amount column
- Intercompany elimination by entity pair, including unrealised profit in inventory
- Investment elimination walking the full multi-tier ownership tree
- NCI allocation: income, equity, and the NCI share of CTA
- Purchase price allocation and acquired intangible amortisation
- Management adjustment layer with full metadata
- Cash flow derivation from balance sheet movements
- Controls `CTL-FX-*`, `CTL-IC-*`, `CTL-CON-*`, `CTL-FS-*`, `CTL-TB-03`, `CTL-TB-05`,
  `CTL-REC-01`, `CTL-REC-04`, `CTL-REC-05`

**Exit criteria**
- A = L + E at entity and group level, to $1
- Cash flow ties to balance sheet cash, to $1
- CTA agrees with the independent expectation within 0.5%
- All intercompany eliminates to nil per pair; unrealised profit correctly retained
- `CTL-REC-01` reconciliation produced automatically

---

## Phase 5 — Reporting marts & automated control suite

**Deliverables**
- `sql/40_marts/` — reporting-shaped marts for financial statements, variance, bridges,
  working capital, headcount, capex, debt and covenants
- Parquet exports for Excel and Power BI
- `sql/90_controls/` — the full control suite, executable as one command
- `fact_control_result` and a control history
- Pipeline orchestration with blocking-control enforcement
- Controls `CTL-SCN-*`, `CTL-BR-*`, `CTL-MAP-06`, `CTL-FS-07`, `CTL-FS-08`, `CTL-REC-02`,
  `CTL-REC-03`

**Exit criteria**
- One command rebuilds everything from raw in under five minutes
- All 81 controls execute and report; no blocking failure on any period
- No mart publishes from a period with a failed blocking control

---

## Phase 6 — Excel FP&A and management reporting models

**Deliverables**
- `Northstar_Management_Reporting_Pack.xlsx` (17 worksheets)
- `Northstar_Consolidation_Workbook.xlsx` (12 worksheets)
- `Northstar_Forecast_Model.xlsx` (14 worksheets)
- Power Query connections to the Parquet marts; Power Pivot models where needed

**Exit criteria**
- Every workbook refreshes from marts with no manual step
- The forecast model's three statements balance and tie inside the workbook
- No hard-coded number that is not a labelled assumption on `95_Assumptions`
- Print-ready formatting

---

## Phase 7 — Power BI semantic model & report suite

**Deliverables**
- `.pbip` project in TMDL/PBIR format, source-controlled as text
- Star-schema semantic model with explicit measures and two calculation groups
- Account-aware favourable/unfavourable variance logic
- Twelve report pages, two drill-through pages, one information page
- Row-level security by entity

**Exit criteria**
- Page render < 3 s cold, < 1 s warm
- Every page answers its stated question
- Figures agree with the Excel pack to the dollar
- Drill path works end to end: Group → BU → Entity → Department → Account Category → GL
  Account → journal line

---

## Phase 8 — Board reporting pack & commentary framework

**Deliverables**
- Quarterly board pack (paginated PDF) with the nine sections in `reporting-design.md` §5
- Structured commentary framework: materiality rule ($250k or 5%), variance decomposition
  supplied to the author, prior-period commentary surfaced for continuity
- Value-creation-plan tracking against the sponsor's thesis
- Forecast accuracy reporting by BU

**Exit criteria**
- Pack generates in under two minutes
- Every material variance has commentary; coverage is measured
- Commentary is author-written and specific. Generic filler is a defect, not a placeholder.

---

## Phase 9 — QA, reconciliation & performance hardening

**Deliverables**
- Full reconciliation of generated data back to the Phase 1 anchors (`CTL-REC-06`)
- End-to-end regression suite
- Performance profiling and tuning against every stated target
- Deferred controls from `control-framework.md` §9: journal anomaly detection, segregation of
  duties, row-level security testing, restatement detection
- Deliberate negative testing: inject a mapping error, an FX inversion, a duplicate load and an
  intercompany break, and **prove the controls catch each one**

**Exit criteria**
- All performance targets met
- Every control demonstrated to fire on an injected fault. A control that has never failed has
  never been tested.

---

## Phase 10 — Documentation & portfolio packaging

**Deliverables**
- Operations runbook, close calendar, troubleshooting guide
- Data dictionary generated from the model rather than written by hand
- Architecture diagrams
- Screenshots and portfolio assets in `docs/assets/`
- Executive summary of the engagement and its outcomes
- Handover pack

**Exit criteria**
- A competent successor can clone, build and operate the platform from the documentation alone
- Every success criterion in the project charter is demonstrably met
