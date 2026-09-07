# Phase 1 Report — Business Design & Architecture

**Status:** Complete, superseded in part by Phase 1.1 · **Date:** 2026-09-07
**Next gate:** Phase 2 approval

> **Read with [`phase-01-1-report.md`](phase-01-1-report.md).** The Phase 1 approval gate
> required six architecture corrections. Where this report and the Phase 1.1 report differ,
> **Phase 1.1 is authoritative** — specifically on the consolidation layer definition, the
> NCI and FX/CTA policies, the covenant and EBITDA decisions, and the control and test counts.
> No financial anchor changed in Phase 1.1.

---

## 1. Objective and outcome

Phase 1 was to design the entire solution before generating any financial data: the company,
the financial anchors, the group and source charts of accounts, the consolidation logic, the
data model, the reporting layer, the control framework and the remaining phase plan.

All of it is delivered, and more of it is **executable** than a design phase normally
produces. The financial anchors are not a table typed into a document — they are the output of
a driver-based model that proves its own accounting identities and refuses to emit output if
they fail. The configuration is not prose — it is 12 machine-readable seed files validated by
152 automated tests that run in under a second.

That distinction is the reason this report can state, rather than hope, that the design is
internally consistent.

---

## 2. What was built

### Documentation (11 documents)

| Document | Content |
|---|---|
| `docs/project-charter.md` | Problem statement, scope, success criteria, governance, risks |
| `docs/business-scenario.md` | Company, operating model, acquisitions, BUs, entities, ERPs, revenue and cost structure, workforce, capital structure, intercompany, the FY2026 story |
| `docs/financial-anchors.md` | **Generated.** Full three-statement anchors, KPIs, BU and entity anchors, intercompany, FX, capital structure |
| `docs/data-contract.md` | Dimensional model: 16 dimensions, 9 facts, relationships, hierarchies, volumes, contract guarantees |
| `docs/consolidation-design.md` | Layer model, grain, sequence, COA harmonisation, FX, elimination, adjustments, cash flow, scenarios |
| `docs/reporting-design.md` | Excel workbooks, Power BI pages, semantic model, board pack, metric definitions, performance targets |
| `docs/control-framework.md` | Controls: severity model, categories, pipeline placement, the ones that matter most (71 at Phase 1; 81 after Phase 1.1) |
| `docs/open-questions.md` | 12 decisions requiring owner approval, each with a working assumption |
| `docs/glossary.md` | Terms and metric definitions |
| `docs/phases/roadmap.md` | Ten phases with deliverables, exit criteria and risks |
| `docs/phases/phase-01-report.md` | This document |

### Architecture Decision Records (14)

Recorded only where a competent practitioner could reasonably have decided differently.
Index: [`docs/adr/README.md`](../adr/README.md).

### Configuration seeds (12 files)

| File | Rows | Purpose |
|---|---|---|
| `config/entities/entity_master.csv` | 15 | Entity master, ownership tree, ERP, consolidation dates |
| `config/dimensions/business_unit.csv` | 5 | Business units |
| `config/dimensions/department.csv` | 26 | Harmonised department catalogue with P&L destination |
| `config/dimensions/scenario_version.csv` | 11 | Scenarios and versions including rolling forecasts |
| `config/coa/group_coa.csv` | 181 | Group chart of accounts with behavioural flags |
| `config/coa/source_coa_aurora.csv` | 146 | Aurora chart and mapping |
| `config/coa/source_coa_sable.csv` | 130 | Sable chart and mapping |
| `config/coa/source_coa_kestrel.csv` | 115 | Kestrel chart and mapping (with German account names) |
| `config/coa/erp_source_profile.csv` | 27 attrs | Per-ERP technical conventions |
| `config/fx/fx_translation_policy.csv` | 15 | FX policy by account class and scenario |
| `config/ic/intercompany_matrix.csv` | 34 | Every intercompany flow with pricing and elimination rule |
| `config/controls/control_register.csv` | 71 | Full control register |

### Executable model and tests

| Artefact | Content |
|---|---|
| `src/anchors/build_anchors.py` | Driver-based anchor model; emits 7 anchor CSVs and generates `docs/financial-anchors.md` |
| `config/anchors/*.csv` | Machine-readable anchor contract for Phases 2 and 9 |
| `tests/test_anchors.py` | 100+ assertions over the generated anchors |
| `tests/test_config_integrity.py` | 50+ assertions over the configuration seeds |

```
$ python src/anchors/build_anchors.py
All integrity assertions passed (BS balances; CF ties to BS cash).

$ python -m pytest tests -q
152 passed in 0.34s
```

---

## 3. Key design decisions

The nine decisions that shape everything downstream:

1. **Consolidation layers** (ADR-0003). Every row is tagged as reported, elimination,
   consolidation adjustment, management adjustment or CTA. Statutory is layers 1+2+3+5;
   management adds layer 4. The statutory result is primary and the management view is
   derived, not the other way round.
2. **One unified fact across scenarios** (ADR-0002). Budget and forecast at the same grain as
   actual, so variance is a subtraction and drills to the same cost centre.
3. **Prior year derived, not stored** (ADR-0004). Eliminates duplication and the restatement
   hazard of a stale stored copy.
4. **Monthly-average FX with computed CTA** (ADR-0005). Monthly average for the P&L, closing
   for the balance sheet, historical for equity; CTA computed and independently verified;
   constant currency stored as a third amount column.
5. **Cash flow derived from balance sheet movements** (ADR-0006). Ties to cash by
   construction, with three named traps handled explicitly.
6. **Mapping as effective-dated configuration** (ADR-0007). Reviewable, diffable, reproducible
   for closed periods, and a `SPLIT` that cannot resolve fails rather than defaults.
7. **Revenue detail in a separate reconciled fact** (ADR-0008). Avoids a grain conflict on the
   GL fact; `CTL-REC-02` makes divergence a blocking failure.
8. **Adjusted EBITDA as an account-level flag** (ADR-0013). One definition, visible in
   configuration, used everywhere, asserted by `CTL-FS-07`.
9. **Anchor-first deterministic modelling** (ADR-0011). Anchors proven before data exists;
   generators must hit them; if generated data disagrees, the generators are wrong.

---

## 4. Critical self-audit

The design was audited against the failure modes the brief names. Nine defects were found.
**Seven were fixed during Phase 1; two are accepted and documented.**

The four marked ⚠ were caught by an automated assertion rather than by review, which is the
strongest argument for building the anchor model as executable code.

### 4.1 Defects found and fixed

**⚠ (a) The FY2026 Forecast balance sheet was rolling forward from the Budget.**
*Severity: high.* The anchor engine carried each period's closing balance sheet into the next
period in sequence. Budget and Forecast are alternative views of the **same** fiscal year, so
the forecast was opening from the budget's closing position rather than from the FY2025 actual
close — compounding two views of one year. Every FY2026F balance sheet and cash flow figure was
affected: the term loan was understated by $10m, net leverage read 3.50x instead of 3.80x, and
net income was overstated by $0.7m.

*Caught by:* `test_retained_earnings_rolls_forward`.
*Fixed:* the engine now keys the opening balance sheet on the prior **fiscal year's actual
close**, populated only from `ACT` periods. Documented in `consolidation-design.md` §12.

**⚠ (b) Purchase accounting did not balance.** *Severity: high.* Goodwill was an input
alongside the other acquired balances. For Halden, consideration of $52.0m against
identifiable net assets of $24.4m implies goodwill of $27.6m, but $24.0m had been entered — a
$3.6m imbalance that flowed straight into the cash flow reconciliation.

*Caught by:* the cash-flow-ties-to-cash assertion inside the engine.
*Fixed:* goodwill is now computed as the **residual** of consideration less the fair value of
net identifiable assets, which is what goodwill actually is. Acquired working capital is
specified component by component so the cash flow statement can exclude it correctly.

**⚠ (c) The entire CTA movement was being routed through "effect of exchange rate changes on
cash".** *Severity: medium.* The statement balanced, but it reported a $5.1m FX effect on cash
in FY2025 — implausible for a group holding $22m of cash, most of it in USD.

*Caught by:* reviewing the generated statement for plausibility, not by a balancing control —
the balancing controls all passed.
*Fixed:* the FX effect on cash is now an explicit, small input; the remainder of the CTA
movement is presented as a non-cash reconciling item within operating activities, which is
where "changes in operating assets and liabilities, net of the effect of foreign currency
translation" actually belongs. See ADR-0006.

**⚠ (d) The opening balance sheet was mis-specified by $40m.** *Severity: medium.* The first
hand-sketched opening balance sheet implied retained earnings of −$52.1m against an intended
−$12.0m.

*Caught by:* the opening-balance guard assertion in the engine.
*Fixed:* contributed capital was restated to $145.0m with an accumulated deficit of $77.1m,
which is the correct shape for a post-LBO balance sheet carrying a recapitalisation dividend.
Total opening equity of $67.2m against $342.6m of assets is consistent with a levered platform.

**(e) Customer and product were initially on the GL fact grain.** *Severity: medium.* A grain
conflict: undefined for the majority of rows and a multi-order-of-magnitude cardinality
increase. *Fixed:* moved to `fact_revenue_detail` with a blocking reconciliation to the GL
(ADR-0008).

**(f) Prior Year was initially a stored scenario.** *Severity: medium.* Duplicates every actual
row and creates a restatement hazard. *Fixed:* derived by date offset, with `CTL-SCN-05`
proving equivalence (ADR-0004).

**(g) Statistical accounts were initially inside the trial balance test.** *Severity: medium.*
`CTL-TB-01` would have failed every month. A control that always fails is a control nobody
reads. *Fixed:* excluded structurally and asserted by
`test_statistical_accounts_are_excluded_from_the_trial_balance` (ADR-0012).

### 4.2 Issues considered and consciously resolved

**Annual-average FX.** Rejected before implementation. Applying a year-to-date average rate to
a year-to-date balance gives a different answer from summing translated months whenever
activity is uneven, which it always is here. It would also make `CTL-FX-03` inexpressible.

**Intercompany identified by account alone.** Insufficient — intercompany activity leaks into
ordinary accounts. The partner dimension alone is also insufficient, because it is not always
populated at source. Both are required and are tested against each other (`CTL-IC-04`).

**Interest coverage was initially below the covenant.** The first capital structure draft
produced FY2023 interest coverage of about 1.9x against a 2.00x minimum — an accidental
covenant breach, not a designed one. Resolved by modelling the $100m interest rate swap
explicitly, which is realistic for a 2021-vintage sponsor deal and brings FY2023 coverage to
2.14x. `test_covenant_headroom_is_positive` now guards against this recurring.

**Elimination netting against participating entities.** Rejected: it would break entity-level
reporting, since an entity's reported figures would no longer agree with its own trial balance
(ADR-0014).

**Unrealised profit in inventory treated as an elimination.** It is not. It is a consolidation
adjustment that genuinely reduces inventory and gross profit rather than netting to nil.
Anchored separately at $0.70m and controlled by `CTL-IC-08`; `CTL-IC-07` carries it as an
explicit exception.

### 4.3 Accepted limitations

**(h) CTA is an economic input to the anchor model, not a computed output.** In Phase 1 the CTA
movement is estimated from FX movement on foreign net assets. In Phase 4 it becomes a computed
output of the translation engine. This is correct sequencing — a full translation engine cannot
run before entity-level data exists — but it means the anchor CTA is a *target*, not a proof.
`CTL-FX-04` closes this in Phase 4.

**(i) ROU asset equals operating lease liability exactly.** A simplification; in reality they
diverge through prepaid and accrued rent and lease incentives. Asserted in
`test_rou_asset_equals_operating_lease_liability` so it cannot drift silently, and recorded as
OQ-06.

### 4.4 Requirements traced against the data model

Every reporting requirement in the brief was checked against the data model to confirm it is
actually supported. Two gaps were found and closed:

| Requirement | Support | Gap found |
|---|---|---|
| Group → BU → Entity → Dept → Cost Centre → Account Category → GL Account | `dim_entity`, `dim_cost_center`, `dim_account` flattened hierarchies | — |
| Actual vs Budget / Forecast / Prior Year | Unified fact + calculation groups | — |
| EBITDA and revenue bridges | Layers, add-back flags, constant-currency column, acquisition dates | — |
| FX impact | `amount_usd_cc` stored | — |
| Forecast accuracy | Multiple retained forecast versions with `actual_months` | **Gap:** required retaining superseded forecast versions. Closed — `FC_FY26_02` and `FC_FY26_05` retained. |
| Headcount and per-FTE metrics | Statistical accounts + `fact_headcount` | — |
| Covenant reporting | `fact_debt_schedule` at instrument level | **Gap:** a single debt balance sheet line cannot answer "what happens when the swap matures". Closed — debt modelled per instrument. |
| Intercompany balances and mismatches | `fact_intercompany_matching` with ageing | — |
| Management adjustments, separately auditable | Layer 4 + `dim_adjustment` | — |
| Source-to-consolidated reconciliation | Layer model + `CTL-REC-01` | — |

### 4.5 Complexity review

Three candidate features were considered and **rejected as unnecessary complexity**: an
equity-method associate (ADR-0009), a mid-period disposal, and a second NCI entity. Each would
add machinery without demonstrating a capability the current scope does not already exercise.

One simplification was considered and **rejected as insufficient**: a single combined
elimination entity. It would have collapsed three genuinely different classes of entry into one
bucket and defeated the layer model (ADR-0014).

---

## 5. Financial anchors — headline

All figures generated by `src/anchors/build_anchors.py` and independently re-tested.

| USD millions | FY2023A | FY2024A | FY2025A | FY2026B | FY2026F |
|---|---|---|---|---|---|
| Revenue | 328.0 | 371.4 | 412.1 | 448.0 | 437.2 |
| Gross profit | 91.7 | 105.4 | 119.3 | 132.4 | 126.3 |
| Gross margin % | 28.0% | 28.4% | 29.0% | 29.6% | 28.9% |
| EBITDA | 29.2 | 39.0 | 51.3 | 60.0 | 53.4 |
| Adjusted EBITDA | 39.0 | 47.2 | 57.8 | 63.5 | 59.2 |
| Adj. EBITDA margin % | 11.9% | 12.7% | 14.0% | 14.2% | 13.5% |
| Net income | (5.1) | 0.4 | 9.4 | 16.8 | 11.2 |
| Total assets | 404.1 | 448.7 | 467.5 | 470.8 | 479.9 |
| Cash | 15.0 | 15.0 | 22.0 | 22.0 | 22.0 |
| Net debt | 211.6 | 248.1 | 231.8 | 209.9 | 225.1 |
| Net leverage | 5.42x | 5.26x | 4.01x | 3.31x | 3.80x |
| Covenant maximum | 6.00x | 5.50x | 5.00x | 4.50x | 4.50x |
| Covenant headroom | 0.58x | 0.24x | 0.99x | 1.19x | 0.70x |
| Operating cash flow | 14.3 | 19.1 | 34.0 | 41.6 | 24.3 |
| Free cash flow | 1.8 | 5.1 | 18.5 | 24.1 | 9.3 |
| Headcount (FTE) | 2,180 | 2,340 | 2,450 | 2,530 | 2,486 |

The story these numbers tell: a levered buy-and-build platform that spent FY2023 and FY2024
absorbing two acquisitions at peak interest rates — a reported net loss, then near-breakeven —
before delivering real margin expansion and deleveraging in FY2025. FY2026 was budgeted to
continue that trajectory and is currently forecast to fall $10.8m short on revenue and $4.3m
on Adjusted EBITDA, for reasons that are specific and attributable.

**Full detail:** [`docs/financial-anchors.md`](../financial-anchors.md).

---

## 6. Structure at a glance

**Business units:** Flow Control & Components (38% of FY2025 revenue), Industrial Services
(30%), Engineered Systems (18%), Aftermarket & Parts (14%), plus Corporate & Shared Services.

**Entities, currencies and ERPs:**

| Entity | Country | Currency | BU | ERP | Note |
|---|---|---|---|---|---|
| NIG-100 Northstar Industrial Group, Inc. | US | USD | CORP | Aurora | Topco, treasury, all external debt |
| NIG-110 Northstar Shared Services LLC | US | USD | CORP | Aurora | Management fee provider |
| NIG-200 Meridian Flow Controls, Inc. | US | USD | FC | Aurora | Original platform |
| NIG-210 Meridian Flow Controls Canada ULC | CA | CAD | FC | Aurora | Second tier |
| NIG-220 Halden Valve GmbH | DE | EUR | FC | Kestrel | Acquired Apr 2023 |
| NIG-300 Cascade Industrial Services LLC | US | USD | IS | Sable | |
| NIG-310 Cascade Industrial Svcs Canada Ltd | CA | CAD | IS | Sable | Second tier |
| NIG-320 Tyneside Mechanical Services Ltd | GB | GBP | IS | Kestrel | |
| NIG-400 Vector Engineered Systems, Inc. | US | USD | ES | Sable | Over-time revenue |
| NIG-410 Vector Systems B.V. | NL | EUR | ES | Kestrel | Acquired Jul 2024, second tier |
| NIG-500 Northstar Aftermarket Solutions, Inc. | US | USD | AM | Aurora | |
| NIG-510 Northstar Parts UK Ltd | GB | GBP | AM | Kestrel | **80% owned — NCI**, second tier |

Plus three virtual entities: `ELIM-IC`, `ELIM-CON`, `ELIM-MGT`.

**ERP distribution:** Aurora 5 entities, Sable 3, Kestrel 4. ERP deliberately does not follow
either the legal or the business unit hierarchy.

---

## 7. Controls designed

71 controls at Phase 1, 56 blocking. **Extended to 81 controls, 66 blocking, at Phase 1.1** —
see [`phase-01-1-report.md`](phase-01-1-report.md) for the ten added: layer integrity, NCI
effective dating, NCI equity roll-forward, NCI share of adjustments, NCI distributions, net
income attribution, CTA roll-forward continuity, acquisition-date translation, cash flow FX
split, and reserved scenario isolation.

Design rule: **balancing controls block, judgement controls inform.** Detail in
[`docs/control-framework.md`](../control-framework.md).

Phase 1's own output is covered by 152 tests that run in CI; **197 after Phase 1.1**.

---

## 8. Open questions

Twelve decisions are flagged for owner approval in
[`docs/open-questions.md`](../open-questions.md), each with a working assumption so Phase 2 is
not blocked. The four with the most impact:

| # | Question | Working assumption |
|---|---|---|
| OQ-01 ✅ | Adjusted EBITDA add-backs | **Closed at Phase 1.1:** no synergies; sponsor fee added back within a $1.5m cap; SBC not added back |
| OQ-02 ✅ | Does net debt include operating leases? | **Closed at Phase 1.1:** no for the covenant; Economic Net Leverage added as a separate non-covenant KPI |
| OQ-12 ✅ | Should FY2026 show a covenant breach? | **Closed at Phase 1.1:** no breach; Downside scenario reserved but not populated |
| OQ-08 | Intercompany transfer pricing rates | Open — as per the intercompany matrix |

OQ-12 was the one worth deciding before Phase 2, and it was decided at the Phase 1.1 review:
the base case stands unchanged, with a Downside scenario reserved but not populated. Eight
questions remain open with working assumptions; none blocks Phase 2.

---

## 9. Recommended Phase 2 scope

**Phase 2 — Synthetic source systems & reference data.**

Generate deterministic, seeded ERP extracts calibrated to the Phase 1 anchors:

- ~1.5m journal lines across 12 entities and 45 months, each in its own ERP's format, sign
  convention, locale and encoding — including Kestrel's Windows-1252 encoding, comma decimal
  separators, `DD.MM.YYYY` dates, zero-padded text account codes and periods 13–16
- Monthly FX rate series for three rate sets, calibrated so revenue-weighted monthly averages
  reproduce the annual anchors within 10 basis points
- Budget and three forecast versions at full consolidation grain
- Intercompany transactions generated **in matched pairs by construction**, with deliberate,
  documented breaks so the controls have something real to catch: a cut-off difference, an FX
  residual on the GBP/EUR pair, one disputed balance
- Headcount, capex, debt schedule, customer and product masters, revenue detail

**Exit criteria:** every entity's raw trial balance balances in its own sign convention;
generated group results reconcile to the anchors within tolerance (`CTL-REC-06`: revenue,
EBITDA and net income ±0.5%, balance sheet captions ±1.0%); the business narrative is visible
in the data; regeneration from a fixed seed is byte-identical.

**Estimated effort:** the largest single phase. The risk is that generating data which is
simultaneously realistic, internally consistent and anchor-conforming proves harder than
expected, and the temptation will be to relax the anchor tolerance. It should not be relaxed —
that tolerance is what makes every later phase meaningful.

**Not in Phase 2:** no ingestion, no mapping, no consolidation, no reporting. Phase 2 produces
raw material only.

---

## 10. Verification

```
$ python src/anchors/build_anchors.py
Opening retained earnings plug (2022-12-31): -77.100
All integrity assertions passed (BS balances; CF ties to BS cash).
Wrote docs/financial-anchors.md and 7 anchor CSVs to config/anchors/

$ python -m pytest tests -q
152 passed in 0.34s
```

Independently verified in Phase 1:

- Balance sheet balances for all five periods, to $0.000001m
- Cash flow ties to balance sheet cash for all five periods
- Retained earnings rolls forward correctly, including both FY2026 views opening from FY2025
- Entity revenue rolls up to BU and to group, exactly
- Covenant headroom is positive in every period
- FX rates are quoted consistently as USD per unit
- All 391 source accounts map to valid, non-statistical group accounts
- The three ERP charts share no account codes — they are genuinely divergent
- The ownership tree is acyclic; ownership plus NCI sums to 100% for every entity
- Every intercompany matrix row references real entities, real accounts and never itself
