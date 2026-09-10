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
| 2 | Synthetic source systems & reference data | **Complete** |
| 2.1 | Source data correction pass | **Complete** |
| 2.2 | Source-layer integrity pass | **Complete — ready for Phase 3 approval** |
| 3 | Ingestion, staging & COA harmonisation | **Complete — awaiting owner review** |
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
- Deterministic, seeded generators in `src/generation/`
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

**Delivered.** 1,082,408 journal lines across 507 native extracts in three systems, plus
eleven reference and planning datasets. Every income statement and balance sheet aggregate
reconciles to the anchor bridge at 0.0000% deviation — the tolerance was not relaxed, and
was not needed. 57 source controls pass, ten fault fixtures all fire, the build is
byte-identical on rebuild. Nine defects found and fixed, and one Phase 1 chart gap disclosed.
See [`phase-02-report.md`](phase-02-report.md).

---

## Phase 2.1 — Source data correction pass ✅

Corrections required at the Phase 2 approval gate: all four Kestrel special periods generated
with declared population rules; twelve balance sheet captions moved from interpolation to
economic drivers; the investment-at-cost calibration removed in favour of an investment
register; and the source detail Phase 4 needs to compute the unrealised-profit elimination
from evidence.

**Delivered:** 12 new controls, 26 new tests, 3 new generation modules, 4 new reference
datasets. No approved anchor changed. Two further defects found by the new guards — credit
captions starting the year as debits, and a group that ran a negative bank balance for 76
entity-months. See [`phase-02-1-report.md`](phase-02-1-report.md).

---

## Phase 2.2 — Source-layer integrity pass ✅

The two architecture issues left open at the Phase 2.1 gate, settled before the source data
was frozen.

**The measurement reserve is removed, not relocated.** `329100` existed because the Phase 2
anchor bridge derived a layer-1 target for every asset, every liability and every income
statement line — but not for equity, leaving the balance sheet one free variable that the
generator closed with a plug. The bridge now derives equity, contributed capital is held at
historical rates in each entity's own currency so a translation adjustment can actually arise,
and layer-1 cash lands on the anchor to the cent with nothing added to any ledger. The CTA is
computed from source balances and published as the expectation Phase 5's translation engine
will be tested against (ADR-0016 superseded by ADR-0017).

**The revolver pays for itself.** Utilisation is resolved to a daily balance on the borrowing
notice and collections sweep dates fixed in a shared treasury policy, and interest is built
from a base rate, a margin and a commitment fee that each trace to a clause. The Phase 1
average-drawn assumption, which the facility's own roll-forward contradicted, is superseded by
the derived average daily balance (ADR-0018).

**Delivered:** 2 new ADRs and 1 retired, 11 new controls, 34 new tests, 4 new reference
datasets, 1 new configuration register, 1 derivation tool. Two anchors narrowly revised with a
full quantification; revenue, EBITDA, cash, total assets, term debt and every working-capital
caption unchanged; no covenant breached. See
[`phase-02-2-report.md`](phase-02-2-report.md).

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

**Delivered.** A five-layer pipeline (raw → parsed → standardised → mapped → conformed) in
DuckDB SQL, with one adapter per source system rather than a generic parser. 1,080,782 lines
from 507 extracts in three encodings, three sign conventions, three date formats and three
period structures, normalised and harmonised to the group chart in about 55 seconds, with
full line-level lineage. The chart-of-accounts harmonisation engine is configuration-driven:
127 effective-dated rules in a validated language, reproducing the expected-mapping oracle at
**100.000000%** on every line the source system classified, with nothing unmapped and nothing
ambiguous. Gross margin by business unit reproduces the anchor exactly for all twelve
business-unit-years. 54 of 61 controls pass with **no blocking pipeline failure**; the other
seven are **four defects found in the frozen Phase 2 source layer**, reported and escalated
rather than patched. See [`phase-03-report.md`](phase-03-report.md).

---

## Phase 3.1 — Source defect remediation & clean-baseline gate ✅

**Deliverables**
- All four source defects corrected at the generation layer, not patched in the data
- The entire Phase 2 source baseline regenerated from the corrected code
- A formal row-population bridge: every ingested row with exactly one disposition
- 100.000000% mapping agreement over the whole population, with no exclusions
- A clean control baseline at both phases, with every source exception closed
- A source-diff manifest proving no unrelated economics moved

**Delivered.** The four defects are **closed**, not accepted. The journal writers that
discarded the attributes they had resolved now share one line resolver; the cost centre is
chosen to satisfy what a split requires rather than labelled afterwards, and the generator
refuses to post where no department can carry the cost; every intercompany balance is
decomposed by counterparty and settled counterparty by counterparty, so 100% of the position
is attributable to an entity pair and every pair nets to under USD 1.00 at closing rates; and
the tax true-up no longer moves a corporation tax payable into the VAT account.

Correcting them exposed five controls that were wrong rather than merely unlucky — most
sharply `P2-IC-01`, which tested only the intercompany lines that already carried a
counterparty and therefore could not fail. It is rewritten and split in two, and `P2-IC-02`
now tests the whole population.

**79 of 79** Phase 2 controls and **62 of 62** Phase 3 controls pass, with no source finding
outstanding. Mapping agreement is **100.000000%** across all 1,094,996 lines with zero
mismatches, zero unmapped, zero ambiguous and zero exclusions. Ten of ten fault fixtures are
handled as intended, with F02 explicitly `NOT_APPLICABLE_DEFERRED` to Phase 4's `CTL-IC-01`.
Revenue, gross profit, EBITDA, cash, the term loan and every working-capital caption are
unchanged; net income moves 0.48% in FY2025 through one causal chain that the report sets out
and `data/phase03_1_source_diff.json` evidences. See
[`phase-03-1-report.md`](phase-03-1-report.md).

---

## Phase 3.2 — Targeted source correction pass ✅

**Deliverables**
- The two defects the consolidation engine found in the frozen Phase 3.1 layer, corrected at
  the generation layer
- `P2-INV-01` redesigned around the authoritative population
- Regression against the Phase 4 engines already built

**Delivered.** Phase 4 stopped when its translation engine could not reproduce the CTA oracle
for one entity and its investment elimination found a register relationship that reached no
ledger. Both are corrected in the generator and the source regenerated: an entity consolidated
on the first day of the window now opens from the FY2022 closing anchor like every other
entity that opens there, and every investment the register requires reaches a ledger. The
opening journal now refuses to post when a counterparty decomposition does not sum to the
balance it decomposes, which makes the second class of defect impossible for every account.

`P2-INV-01` is rebuilt around the register rather than the ledger — the same control-design
defect Phase 3.1 found in `P2-IC-01`, and the second time it has cost a phase. **80 of 80**
Phase 2 controls and **62 of 62** Phase 3 controls pass; CTA now agrees with the oracle for
**243 of 243** entity-periods; the intercompany elimination is unchanged; no headline anchor
moved. See [`phase-03-2-report.md`](phase-03-2-report.md).

---

## Phase 4 — Consolidation engine ✅

**Complete.** The accounting engine is frozen at `4847d64`: five layers, FX translation with a
derived CTA, pair-level intercompany elimination, investment elimination and PPA, NCI,
unrealised profit, the management layer and the three consolidated statements. With the Phase
4C reporting corrections: **72 of 72** controls passing, **23 of 23** fault fixtures handled as
intended, a balance sheet that balances at 0.00 in all 48 months and a cash flow that ties at
0.00 in all 48. See [`phase-04-report.md`](phase-04-report.md).

**Original deliverables**
- FX translation: monthly average P&L, closing balance sheet, historical equity, computed
  CTA — tested against `data/reference/cta_expectation.csv`, the per-entity, per-month
  expectation Phase 2.2 derived from source balances before the engine existed (`CTL-FX-12`)
- Constant-currency amount column
- Intercompany elimination by entity pair, including unrealised profit in inventory --
  unblocked by Phase 3.1: every intercompany balance now names its counterparty and the
  pairs net to under USD 1.00 at closing rates
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

## Phase 4A — Consolidation proof and control gate ✅

**Deliverables**
- The P3-D-07 owner decision applied: the entity ledger supersedes the Phase 1 NCI estimate
- A cash flow that ties in every period, with CTA and the effect of exchange rates on cash
  kept apart
- The statutory and management bases proved to differ by layer 4 and by nothing else
- The full Phase 4 control suite, and fault fixtures for it
- F02, deferred by Phase 3, put through the Phase 4 elimination engine

**Delivered.** `NCI_INCOME` is now derived by `tools/derive_nci_anchor.py` rather than typed
in, converging at iteration 1 with a difference of 0.000000, and the roll-forward closes every
year — so P3-D-07 is closed by decision (ADR-0025, `SX-010`) with neither the transfer price
moved nor the engine scaled.

The cash flow ties at **0.00 in all 48 periods** and closing cash ties to the balance sheet at
**0.00**. Two defects were found getting there: the translation accounts sit in the operating
bucket in the approved chart, so excluding them from financing alone counted the translation
twice; and the year-end close carries a few cents of translation that excluding both its sides
stranded. The second is now presented as its own line, computed from the close entry rather
than derived as whatever makes the statement tie — which let the 0.10 USD tolerance an earlier
draft carried be **removed** rather than kept.

**61 of 61** Phase 4 controls pass and **19 of 19** fault fixtures are handled as intended,
with no accidental detections. F02 is caught by `P4-IC-01`, the pair reconciliation that owns
it, after a full pipeline and consolidation run. Four controls that could not have failed were
found by fixtures and rewritten to iterate from the authority that requires the data; one
non-deterministic artefact and one ignored configuration field were found by the self-audit.
See [`phase-04a-proof-gate.md`](phase-04a-proof-gate.md).

---

## Phase 4B — Consolidation documentation & release gate ✅

**Deliverables**
- The as-built documentation package: engine, FX, intercompany, investments and PPA, NCI,
  unrealised profit, management adjustments, the statements, the control framework, fault
  testing, lineage and reproducibility
- The formal Phase 4 report
- A cross-document consistency audit
- No change to accounting code or economics

**Delivered.** Twelve documents written or rewritten and the Phase 4 report completed, with
every figure taken from the built warehouse rather than restated from memory. The full
regression was re-run unchanged afterwards — 80/80, 62/62, 10/10, 61/61, 19/19, 421 tests, the
same build id and a clean tree — because documentation work must not change financial results.

The pass found **two defects in Phase 4 reporting artefacts**, both by comparing what one
artefact says with what another says about the same figure. Neither was corrected, per the
brief. See [`phase-04b-engine-findings.md`](phase-04b-engine-findings.md).

---

## Phase 4C — Reporting integrity & cross-artefact control gate ✅

**Deliverables**
- P4-D-01 and P4-D-02 corrected
- A permanent cross-artefact control family
- Fault fixtures proving it detects reporting divergence
- A written NULL / empty-population policy, enforced
- A contract for every Phase 4 reporting artefact

**Delivered.** The balance sheet's result caption is now the fiscal year to date excluding the
close, agreeing with the income statement in all 48 months and at all four year ends; total
equity did not move. The EBITDA bridge excludes the close and coalesces every component, so it
agrees with the income statement exactly and Covenant EBITDA is a number in every year rather
than NULL.

Eleven `P4-XAR-*` controls implement the second design rule — *different artefacts expressing
the same financial measure must reconcile to one authoritative definition* — each with at least
one side recomputed from `fact_financials`. `P4-XAR-11` failed on its first run and found a
**third** instance of the same close defect, in `rpt_layer_bridge` (P4-D-03).

Four fixtures prove the family detects reporting divergence; `F4-XAR-01` breaks the equity
presentation while the balance sheet still balances and **no accounting control fires**. The
NULL policy — *no population means zero, never NULL* — is enforced by a lint test after
seventeen un-coalesced aggregates were found and fixed. See
[`phase-04c-reporting-integrity.md`](phase-04c-reporting-integrity.md).

---

## Phase 5 — Reporting marts & Excel management reporting ✅

**Complete.** Nineteen governed reporting marts over the frozen consolidation, and a sixteen-tab
Excel management reporting workbook built on them as code. Every figure in the workbook is a
lookup into a mart; the workbook computes variance, subtotals and display logic and no
accounting policy.

**36 of 36** mart controls pass and **17 of 17** workbook reconciliations agree with the marts,
with zero layout findings. The consolidation is untouched: source digest, consolidation build id
and all fifteen consolidation artefacts are byte-identical.

The visual review found eleven defects that no programmatic check would have caught, including
a covenant leverage computed on a fiscal-year EBITDA for a year in progress — which reported
7.38x against a 4.50x limit — and a **breach stamped on two dates the credit agreement never
tests**. Both are corrected; the group is compliant at every test date with 0.29 turns of
headroom. See [`phase-05-report.md`](phase-05-report.md).

---

## Phase 5.1 — Upstream dimensional-integrity correction ✅

**Complete, awaiting rebaseline review.** Phase 6A's semantic model needed a unique key for the
`Capital Project` dimension and `project_id` was not one: 1,846 capital projects carried 395
identifiers, because the sequence restarted inside each asset class. Escalated as **P6-D-01**
rather than worked around in DAX; the owner approved correcting the generator.

The identifier now carries the grain that makes a project distinct
(`CP-{entity}-{period}-{asset_class}-{sequence}`), the source layer was regenerated and Phases
2 to 5 rebuilt. **No money moved:** 297,296 rows compared across sixteen grains at a required
difference of `0.00`, and zero numeric differences across 615,262 workbook cells.

The larger fix is the framework. All **61** keyed objects in the platform are now declared in
`src/integrity/registry.py` and proved by one generic engine — **229 controls, 9 fault
fixtures** — with `P7-REG-01` failing whenever a keyed table exists that the registry has never
heard of. It found a second gap on its first run (**P7-D-01**, `PY_DERIVED` used as a version
code with no row in the version master), reported and quarantined rather than fixed.

The framework found a second defect on its first run: **P7-D-01**, `PY_DERIVED` used as a
version code by 12,516 mart rows with no row in any version master. Reported rather than fixed
at the time, and closed in the follow-on pass -- Prior Year now has a governed derived version
in the master, the hand-written `ref_default_version` union is gone, and fourteen `P7-VER`
controls with nine fixtures govern scenario and version integrity. The framework finishes at
**249/249 with nothing quarantined**, and again no money moved: 325,000 rows compared across
eighteen grains at `0.00`, including Prior Year isolated on its own.

Phase 6A remains **not resumed**; its WIP is preserved on `wip/phase-06a-semantic-model` and
must be rebased onto this baseline, updating both its Capital Project key and its
scenario/version assumptions. See
[`phase-05-1-key-integrity.md`](phase-05-1-key-integrity.md),
[`phase-05-1-scenario-integrity.md`](phase-05-1-scenario-integrity.md),
[ADR-0026](../adr/0026-a-declared-key-is-a-contract.md) and
[ADR-0027](../adr/0027-a-derived-version-is-still-a-governed-version.md).

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
- Every implemented control executes and reports; no blocking failure on any period
- No mart publishes from a period with a failed blocking control

---

## Phase 5.2 — Excel executive design and visual polish ✅

**Owner-approved and frozen.** A design pass over the approved workbook: no finance logic,
no reporting definitions, presentation only.

Rendering all sixteen sheets through Excel's own PDF writer and looking at them found that **all
seventeen charts had no axes** — `openpyxl` deletes an axis whose `delete` is unset — and that
**all 26 chart series started at the header row**, plotting a phantom zero and shifting every bar
chart by one category. Neither is visible in XML, a formula audit or a reconciliation.

Also corrected: charts straddling page breaks, hollow negative bars, twelve repeated
finance-lease rows burying 96% of the debt, a control summary that stopped at Phase 5, two
negative-number conventions on the flagship sheet, and an empty half-page on the P&L.

**No reported financial value changed**; 17/17 reconciliations still pass. See
[`phase-05-2-visual-polish.md`](phase-05-2-visual-polish.md).

**Phase 5.2A** added the secondary colour: navy plus muted industrial copper, as a system with
five distinct jobs rather than a single accent. Owner-approved; the workbook is frozen from
here. See [`phase-05-2a-copper-correction.md`](phase-05-2a-copper-correction.md).

---

## Phase 6A — Power BI semantic model ✅

**Complete, awaiting review.** A governed star schema over the Phase 5 marts: 28 tables, 89
measures, 31 active and 5 deliberately inactive relationships, generated from two declarations
into both a PBIP/TMDL project and a TMSL deployment.

Validated by **running it**. Power BI Desktop will not open a PBIP from the command line here,
but the Analysis Services instance it runs accepts TMSL over XMLA, so the model is deployed
there and its own DAX executed. That found three classes of defect no amount of reading TMDL
would have: a relationship on a column that does not exist, every statement measure summing
both reporting bases and reporting twice the truth, and four measures that do not parse.

**49/49 semantic controls, 10/10 fault fixtures**, 19 reconciliations to the marts and 8 to the
Excel workbook, all on real DAX. Reproducible: two clean generations, identical project digest.

This phase was interrupted twice by upstream defects -- P6-D-01 and P7-D-01 -- and resumed only
after both contracts were corrected and rebaselined. See
[`phase-06a-report.md`](phase-06a-report.md).

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
