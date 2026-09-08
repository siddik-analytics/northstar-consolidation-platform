# Phase 4 — Group consolidation engine

Formal completion report for the consolidation engine, covering Phase 4, the Phase 4A proof
gate and the Phase 4B documentation and release gate.

**Engine frozen at `4847d64`.** Source layer `fd7afb8f…`, consolidation build
`78e406e139662392`.

> **Phase 4 is not signed off.** Two defects in Phase 4 reporting artefacts were found during
> the Phase 4B documentation pass and, per the Phase 4B brief, reported rather than corrected.
> See §21 and [`phase-04b-engine-findings.md`](phase-04b-engine-findings.md).

---

## 1. Scope

Twelve entity ledgers, three ERPs, four currencies, 48 months, into one consolidated group in
USD — with FX translation and a derived CTA, intercompany elimination, investment elimination,
purchase price allocation, acquired intangible amortisation, non-controlling interests,
unrealised profit in inventory, a management adjustment layer, the three consolidated
statements, a full control suite and complete audit lineage.

Delivered across three gates:

| | | |
|---|---|---|
| Phase 4 | the engines | `c55d441`, `5a1c254`, `f2fa9df` |
| Phase 4A | proof and control gate | `4847d64` |
| Phase 4B | documentation and release gate | this pass |

Phase 4 stopped twice to report upstream defects rather than repairing data inside the
consolidation engine. Both stops were approved, corrected at the generator in Phase 3.2, and
the engine resumed on a corrected source layer.

## 2. Architecture

Five layers ([ADR-0003](../adr/0003-consolidation-layer-model.md)), two reconciled facts
([ADR-0024](../adr/0024-two-reconciled-consolidation-facts.md)), two reporting bases selected
at the architecture level:

```
Statutory  = Layer 1 + Layer 2 + Layer 3 + Layer 5
Management = Statutory + Layer 4
```

Full description: [`consolidation-engine.md`](../consolidation-engine.md).

## 3. Journal counts by layer

| Layer | Process | Entries | Legs |
|---|---|---|---|
| 2 `IC_ELIM` | intercompany elimination | 2,203 | 4,406 |
| 3 `CONSOL_ADJ` | investment elimination | 11 | 67 |
| | PPA amortisation | 657 | 1,314 |
| | unrealised profit | 177 | 354 |
| | NCI result | 48 | 96 |
| | NCI dividends | 3 | 6 |
| | opening CTA reclassification | 1 | 2 |
| 4 `MGMT_ADJ` | management adjustments | 0 | 0 |
| 5 `FX_CTA` | translation adjustment | 243 | 287 |
| | | **3,343** | **6,532** |

Layer 1 contributes 44,584 translated rows from the frozen conformed layer.
`fact_financials` holds **48,202** rows.

## 4. FX translation and CTA

Six of twelve entities are non-USD. Translation is driven by `dim_account.fx_method`; CTA is
the residual of the translated trial balance and is never plugged.

| | |
|---|---|
| Entity-periods translated | 507 |
| CTA reproduces the independent expectation | **243 of 243**, worst 0.000001 USD m |
| USD entities' CTA | 0.00 |
| Cumulative CTA at 31 Dec 2025 | (0.283) USD m group, (0.110) USD m NCI share |
| Layers 1 + 5 sum to zero | 0.00 in all 48 periods |

Detail: [`fx-translation.md`](../fx-translation.md).

## 5. Intercompany elimination

Matched by entity pair on account **sets**, never at group total.

| | |
|---|---|
| Ordered entity pairs | 34 |
| Relationship-periods matched | 2,355 — all `MATCHED` |
| Balance positions matched | 1,409 periods, USD 8,866.7m gross |
| Flow positions matched | 946 periods, USD 175.7m gross |
| Worst residual | USD 0.19 (balances), USD 0.01 (flows) |
| Unmatched, unclassified | 0 |

Detail: [`intercompany-elimination.md`](../intercompany-elimination.md).

## 6. F02 — the deferral closed

The one-sided intercompany fixture Phase 3 deferred runs through the full pipeline **and** the
Phase 4 elimination engine and is detected by **`P4-IC-01`**, the pair reconciliation that owns
it. Detection by an unrelated control would not have closed the deferral, and the harness
records that case separately as a control-design defect.

## 7. Investments and purchase price allocation

Eleven relationships, eliminated relationship by relationship — never at aggregate group level,
because a group-level elimination cannot express a second-tier holding.

| | |
|---|---|
| Register relationships | 11, all with an acquisition schedule |
| Investment eliminated | USD 451.2m, in full, worst residual 0.00 |
| Goodwill derived | **USD 140.697m** across 11 bridges |
| Goodwill plugged | none — `P4-PPA-01` recomputes every bridge |
| Deferred tax on fair value uplift | USD 20.397m |

Detail and the full bridge: [`investment-and-ppa.md`](../investment-and-ppa.md).

## 8. Acquired intangibles

| | |
|---|---|
| Tranches | 18 |
| Gross fair value recognised | USD 72.5m |
| Net book value at 31 Dec 2025 | **USD 52.476m** |
| Amortisation legs | 1,314 |
| Amortisation begins | the month the register gives, not the start of the year |

## 9. Non-controlling interests

One non-controlling interest in the group: 20% of NIG-510, held by its founding management.
Consolidated at 100% with separate presentation, attributed on a **layer-3** base.

| USD | FY2023 | FY2024 | FY2025 | FY2026 |
|---|---|---|---|---|
| Opening | — | 2,673,319 | 2,404,987 | 2,158,052 |
| Share of result | (197,389) | (218,966) | (265,949) | (179,968) |
| Distributions | — | (30,000) | (40,000) | (50,000) |
| Share of translation | 70,708 | (19,366) | 59,014 | 16,923 |
| Recognised at acquisition | 2,800,000 | — | — | — |
| **Closing** | **2,673,319** | **2,404,987** | **2,158,052** | **1,945,008** |

The Phase 1 NCI earnings anchor was superseded by owner decision at the Phase 4A gate: the
generated entity ledger and the approved transfer-pricing economics are the authority
([ADR-0025](../adr/0025-the-entity-ledger-supersedes-the-phase-1-nci-estimate.md), `SX-010`).
The anchor is now derived by `tools/derive_nci_anchor.py`, converged at iteration 1 with a
difference of 0.000000. Detail: [`nci.md`](../nci.md).

## 10. Unrealised profit in inventory

FIFO surviving layers, each at its own margin, posted as the movement in the provision so the
release is automatic.

| | |
|---|---|
| Eligible transactions | 173 |
| Surviving layers computed | 470 |
| Provision at 31 Dec 2023 / 2024 / 2025 | USD 535,382 / 618,793 / 713,755 |
| Reproduces the independent expectation | worst USD 0.02 |
| Release periods observed | 56 |

Detail: [`unrealised-profit-in-inventory.md`](../unrealised-profit-in-inventory.md).

## 11. Management adjustments

**Layer 4 is empty.** Both approved adjustments are nil-amount presentation reclassifications,
so the management basis is numerically identical to the statutory basis. `P4-BAS-02` discloses
this rather than letting a table of zeros look like a proof, and no amount was invented.

The framework is proved by two fixtures instead: `F4-MGT-LEAK` posts a real layer-4 amount
(96 legs, 8 measure-years moved, statutory unmoved) and `F4-17` proves a DRAFT adjustment
reaches no layer at all. Detail: [`management-adjustments.md`](../management-adjustments.md).

## 12. Statutory versus management

All **28 measure-years** — revenue, gross profit, EBITDA, EBIT, net income, total assets and
total equity, over four years — differ by layer 4 and by nothing else (`P4-BAS-01`), and the
statutory basis contains zero layer-4 rows (`P4-LAY-03`).

## 13. Consolidated income statement

| USD m | FY2023 | FY2024 | FY2025 | FY2026 (8m) |
|---|---|---|---|---|
| Revenue | 328.000 | 371.400 | 412.100 | 278.981 |
| Gross profit | 91.205 | 105.291 | 119.250 | 77.082 |
| EBITDA | 28.705 | 38.891 | 51.250 | 29.202 |
| Adjusted EBITDA | 38.505 | 47.091 | 57.750 | 33.013 |
| EBIT | 13.403 | 21.470 | 32.748 | 14.174 |
| Net income | (6.992) | (1.291) | 6.780 | (2.238) |
| Attributable to NCI | (0.197) | (0.219) | (0.266) | (0.180) |
| **Attributable to the parent** | **(6.795)** | **(1.072)** | **7.046** | **(2.058)** |

## 14. Consolidated balance sheet

**Assets = Liabilities + Equity in all 48 months, residual exactly 0.00.**

At 31 December 2025: total assets USD 465.390m, liabilities USD 372.048m, equity USD 93.340m —
including goodwill 140.697, acquired intangibles net 52.476, CTA (0.283) and non-controlling
interests 2.158. Investments in subsidiaries and intercompany balances both eliminate to nil
and are presented rather than suppressed.

## 15. Consolidated cash flow

**Opening + operating + investing + financing + FX on cash = closing, difference exactly 0.00
in all 48 periods.** Closing cash ties to the balance sheet at 0.00 in all 48 periods.

| USD m | FY2023 | FY2024 | FY2025 | FY2026 (8m) |
|---|---|---|---|---|
| Operating | (61.541) | 13.128 | 26.130 | (7.478) |
| Investing | (313.616) | (47.909) | (13.019) | (1.956) |
| Financing | 390.057 | 34.981 | (6.355) | 1.961 |
| FX effect on cash | 0.100 | (0.199) | 0.244 | 0.053 |
| Closing cash | 15.000 | 15.000 | 22.000 | 14.580 |

No cash residual, no FX plug, and CTA is not used as the FX effect on cash (`P4-FX-08`).

## 16. Controls

**61 controls, 61 passing, 0 source findings, 0 blocking failures.** Register committed at
`config/controls/phase04_control_register.csv`; a test fails if register and code disagree.

| Family | Count | Family | Count |
|---|---|---|---|
| Ownership | 6 | Unrealised profit | 4 |
| FX and CTA | 8 | Journals, layers, the two facts | 8 |
| Intercompany | 5 | Statements | 9 |
| Investment | 3 | Statutory vs management | 2 |
| Goodwill and PPA | 4 | Management adjustments | 3 |
| Intangibles | 4 | NCI | 5 |

Detail: [`consolidation-controls.md`](../consolidation-controls.md).

## 17. Fault fixtures

**19 of 19 handled as intended, 0 accidental detections.** Every fixture corrupts an input the
engine consumes and runs a full consolidation. Four controls that could not have failed were
exposed by fixtures and rewritten: `P4-PUP-02`, `P4-INV-03`, `P4-INT-02`, `P4-OWN-06`.

Detail: [`fault-testing.md`](../fault-testing.md).

## 18. Defects found and fixed

**Upstream, escalated rather than repaired downstream** — the engine stopped twice:

| | | Outcome |
|---|---|---|
| P3-D-05 | an entity effective *on* the window boundary got January's closing rate | fixed at the generator (Phase 3.2), CTA 242/243 → **243/243** |
| P3-D-06 | a register investment relationship reached no ledger; USD 16.9m absorbed by a retained-earnings plug | fixed at the generator (Phase 3.2), plus a general assertion that a decomposition sums to its balance |
| P3-D-07 | the Phase 1 NCI earnings anchor contradicted by the entity ledger | closed by owner decision (ADR-0025); anchor now derived |

**Inside Phase 4, found and fixed within the phase:** the balance sheet's triple presentation
defect (41.6m → 12.9m → 0.00); the NCI attribution base including layer 2 (5× the anchor); the
cash flow's double-counted translation and stranded close (13.95m → 0.00); one
non-deterministic artefact; one configuration field the engine ignored; two dangling
documentation references.

**Found in Phase 4B and NOT fixed** — see §21.

Architectural analysis of all of these: [`architecture-lessons.md`](../architecture-lessons.md).

## 19. Performance

| Stage | Seconds |
|---|---|
| ownership | 0.03 |
| translate | 0.32 |
| eliminate | 0.12 |
| investments | 0.05 |
| nci · pup · cta · mgmt | 0.05 |
| statements | 0.51 |
| **consolidation total** | **1.2** |
| 61 controls | 0.3 |
| 19 fault fixtures (19 full consolidations) | 45 |
| full chain from a clean checkout | ≈ 210 |

A month-end close that took four days in the spreadsheet is a 1.2-second rebuild with 61
controls attached.

## 20. Determinism

| | |
|---|---|
| Consecutive rebuilds compared | 3 |
| Build id | `78e406e139662392`, identical each time |
| Artefacts byte-identical | **15 of 15** |
| Source digest after regeneration | `fd7afb8f…`, unchanged |
| Working tree after full rebuild | **clean** |

Detail: [`reproducibility.md`](../reproducibility.md).

## 21. Limitations and open items

**Open defects — Phase 4 cannot be signed off until these are decided:**

| | | Impact |
|---|---|---|
| **P4-D-01** | `rpt_balance_sheet`'s "Result for the period" accumulates prior years' unclosed consolidation result — USD 19.869m at Dec 2025 against a FY2025 parent result of 7.046m | classification within equity; total equity correct; no control affected |
| **P4-D-02** | `rpt_ebitda_bridge` computes statutory EBITDA including the year-end close (three of four years wrong) and returns NULL Covenant EBITDA in every year | the artefact is unusable; `rpt_income_statement` is correct and the two disagree |

Both are in reporting artefacts, not in the accounting engine. Neither is caught by any of the
61 controls, and both were found by writing this documentation and comparing artefacts with
each other. Full analysis: [`phase-04b-engine-findings.md`](phase-04b-engine-findings.md).

**Scope limitations, by design:**

* **No impairment model.** Goodwill is recognised and never tested for impairment.
* **No disposals.** FX-P19 (CTA recycling on disposal) is implemented with no population.
* **Layer 4 is empty**, so the management basis is proved structurally and by fixture rather
  than from production data.
* **No cross-artefact controls.** Nothing compares one reporting artefact with another — the
  gap that let P4-D-02 survive.
* **Actual scenario only** is consolidated in full. Budget and Forecast share the grain, the
  engine and the layers but are not exercised end to end.
* **The covenant FX add-back has no population** — accounts 740100/740200 are never posted to,
  so CA-030 is structurally nil in the modelled window.

## 22. Recommendation for Phase 5

Two items first, before any new phase:

1. **Decide P4-D-01 and P4-D-02** and correct them in a short Phase 4C, with a **cross-artefact
   control family** and fault fixtures for it. Both defects are repeats of faults already fixed
   elsewhere in the same phase, in an artefact nothing was checking; the control family is the
   substantive fix, not the two one-line corrections.

Then, per [`roadmap.md`](roadmap.md):

2. **Phase 5 — reporting marts and the automated control suite.** Reporting-shaped marts over
   `fact_financials` for the statements, variance, bridges, working capital, headcount, capex,
   debt and covenants; Parquet exports; the full control suite executable as one command. This
   is the right next dependency: the Excel and Power BI phases both consume the marts, and
   building either directly against the consolidation fact would put presentation logic in two
   places.

The Excel FP&A model (Phase 6) follows the marts, and Power BI (Phase 7) follows Excel — the
metric definitions are settled once, in the marts, rather than re-derived in each tool.
