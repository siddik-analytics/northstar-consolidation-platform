# Phase 2 Report — Synthetic Source Systems & Reference Data

**Status:** Complete · **Date:** 2026-09-07 · **Next gate:** Owner review before Phase 3

---

## 1. Completion status

Complete. Phase 2 generates the realistic, heterogeneous, reproducible source-system
environment that the consolidation platform exists to solve — **1,082,408 journal lines**
across 507 native ERP extracts in three genuinely different systems, plus eleven reference
and planning datasets, all reconciling to the approved anchors.

```
$ python -m src.generation.build
  journal_lines 1,082,408 | raw_files 507 | build_seconds 28.6
  dataset digest: f396de9021089d375750ce993c4503187e913e4f27427993ad1e104ebba9df13

$ python -m src.generation.validate
  57/57 controls passed

$ python -m src.generation.faults
  10 fault fixtures written; all 10 DETECTED

$ python -m pytest tests -q
  258 passed
```

No ingestion, mapping execution, consolidation, translation, elimination, Excel or Power BI
work was undertaken. Those remain Phases 3–7.

---

## 2. Files created and changed

### New — generation code (11 modules, `src/generation/`)
| Module | Purpose |
|---|---|
| `common.py` | Period spine, deterministic seeding, config loading, exact allocation |
| `fx.py` | Monthly rate series for three rate sets, anchored exactly |
| `model.py` | Economic model: pushes group anchors down to entity level |
| `ledger.py` | Annual entity income statement and year-end balance sheet targets |
| `series.py` | Monthly local-currency positions, treasury pooling, calibration |
| `mapping.py` | Reverse mapping and the expected-mapping manifest |
| `masters.py` | Cost centres, customers, products, workforce |
| `journals.py` | Balanced journal generation from entity positions |
| `erp.py` | Three native extract renderers |
| `datasets.py` | Plan, headcount, capex, fixed assets, debt, revenue detail |
| `targets.py` | The anchor bridge from consolidated to source layer |
| `validate.py` | 57 source controls, read back off disk |
| `faults.py` | Ten fault fixtures and their detectors |
| `build.py` | Orchestrator, manifest and checksums |

### New — documentation
`docs/source-system-design.md` · `docs/synthetic-data-methodology.md` ·
`docs/source-data-dictionary.md` · `docs/phases/phase-02-report.md`

### New — configuration and committed artefacts
`config/generation/expected_mapping_manifest.csv` (313 rows) ·
`config/anchors/phase02_source_layer_targets.csv` (35 rows) ·
`data/build_manifest.json` · `data/phase02_control_results.csv` ·
`data/faults/expected_results.{csv,json}` · `data/samples/` · nine reference CSVs

### New — tests
`tests/test_phase02_generation.py` — 59 tests.

### Changed — Phase 1 configuration, each disclosed in §9
`config/coa/source_coa_sable.csv` (+1 account) · `src/anchors/build_anchors.py`
(two exports added, no value changed) · `docs/data-contract.md` (directory naming) ·
`.gitignore` · `README.md` · `docs/phases/roadmap.md`

---

## 3. Generated row counts

| Dataset | Rows |
|---|---|
| **Journal lines** | **1,082,408** |
| — Aurora (5 entities) | 526,068 |
| — Sable (3 entities) | 371,224 |
| — Kestrel (4 entities) | 185,116 |
| Native extract files | 507 |
| Journals | 540,070 |
| Plan fact (budget + 3 forecast versions) | 26,124 |
| Revenue detail | 50,045 |
| Headcount fact | 20,973 |
| Fixed assets | 1,755 |
| Capital projects | 1,755 |
| Employees | 3,049 |
| Customers | 998 |
| Debt schedule | 595 |
| FX rates (monthly) | 544 |
| Products | 226 |
| Cost centres | 152 |
| FX historical rates | 36 |
| Expected-mapping manifest | 313 |

Entity-periods: **507** (12 entities × 44 months, less the pre-acquisition periods of
Halden Valve and Vector Systems B.V.). Median 1,685 lines per entity-period, ranging 535 to
7,895 — volume follows revenue rather than being constant.

---

## 4. Source ERP summary

| | Aurora | Sable | Kestrel |
|---|---|---|---|
| Entities | 5 | 3 | 4 |
| Journal lines | 526,068 | 371,224 | 185,116 |
| Source accounts | 146 | 131 | 115 |
| Account key | 4-digit numeric | 5-digit numeric | 8-char zero-padded **text** |
| Sign convention | one signed amount | natural sign per account | separate debit/credit columns |
| Encoding / delimiter | UTF-8 / comma | UTF-8 / comma | **Windows-1252 / semicolon** |
| Decimals / dates | `1234.56` / ISO | `1,234.56` / US | **`1.234,56` / `DD.MM.YYYY`** |
| Periods | 1–12 | 1–12 | **1–12 plus 13** |
| Conditional-split inversions | 27 | 28 | 47 |
| Substituted accounts | 1 | 8 | 14 |

The three charts share **no account code** (`P2-FMT-03`), and control `P2-SRC-03` proves the
three sign conventions are genuinely different *and* genuinely reversible by parsing all 507
raw files back and re-deriving a signed amount from each system's own rule. Detail:
[`source-system-design.md`](../source-system-design.md).

---

## 5. Financial reconciliation to anchors

Phase 2 generates **layer 1 only** — what each entity's own ledger says. The approved
anchors are the **consolidated** result. The two differ by intercompany gross-up and by the
Phase 4 constructs, so the comparison runs against a bridge derived deterministically from
the anchors ([`phase02_source_layer_targets.csv`](../../config/anchors/phase02_source_layer_targets.csv)).

### Income statement, FY2025 (USD m)

| | Consolidated anchor | + intercompany | = source target | Generated | Deviation |
|---|---|---|---|---|---|
| Revenue | 412.100 | 50.535 | 462.635 | 462.635 | **0.0000%** |
| Cost of sales | 292.755 | 39.800 | 332.555 | 332.555 | **0.0000%** |
| Operating expenses | 68.000 | 10.735 | 78.735 | 78.735 | **0.0000%** |

FY2023 and FY2024 reconcile to the same tolerance. Against a permitted ±0.5%, actual
deviation is zero — the anchors are pushed down with a largest-remainder split, so a
pushdown cannot leak a rounding difference.

### Balance sheet, year ends (USD m)

| Caption | FY2023 | FY2024 | FY2025 | Deviation |
|---|---|---|---|---|
| Cash | 15.000 | 15.000 | 22.000 | 0.0000% |
| Receivables | 55.715 | 61.052 | 65.484 | 0.0000% |
| Inventory (gross of unrealised profit) | 36.161 | 39.268 | 40.803 | 0.0000% |
| Payables | 29.775 | 34.984 | 40.103 | 0.0000% |
| Property, plant and equipment | 77.200 | 87.500 | 95.200 | 0.0000% |

Against a permitted ±1.0%.

### The business story survives in the data

External business unit revenue and gross margin, computed from the generated journals with
intercompany excluded:

| BU | Revenue $m | Anchor | Gross margin | Anchor |
|---|---|---|---|---|
| Flow Control & Components | 156.60 | 156.6 | 34.00% | 34.0% |
| Industrial Services | 123.60 | 123.6 | 22.00% | 22.0% |
| Engineered Systems | 74.20 | 74.2 | 19.00% | 19.0% |
| Aftermarket & Parts | 57.70 | 57.7 | 43.00% | 43.0% |
| **Group** | **412.10** | **412.1** | **28.96%** | **28.96%** |

### Other reconciliations

| Check | Result |
|---|---|
| Revenue detail to general ledger, per entity and period | exact (0.0000) |
| Intercompany pairs match in USD, 905 entity-pair-periods | exact (0.0000) |
| Headcount at Dec-2025 | 2,467 vs anchor 2,450 (0.69%, tolerance 5%) |
| Fixed asset register to capital project spend | exact |
| Debt schedule to anchored term loan balance | exact |
| Forecast actual months vs the Actual scenario | 0.01 (tolerance 0.05) |

---

## 6. Data quality and fault fixtures

Two ideas kept strictly apart. **`data/raw/` is the clean baseline and is never corrupted** —
it passes all 57 source controls. Each fault is a separate copy of only the file it touches,
in `data/faults/<id>/`, with `expected_results.json` naming the control that must catch it.

| ID | Fault | Expected control | Detected |
|---|---|---|---|
| F01 | Unmapped source account | `CTL-MAP-01` | ✅ |
| F02 | Intercompany amount mismatch | `CTL-IC-01` | ✅ |
| F03 | Missing FX rate | `CTL-FX-01` | ✅ |
| F04 | Duplicate journal identifier | `CTL-DQ-03` | ✅ |
| F05 | Invalid cost centre | `CTL-DQ-08` | ✅ |
| F06 | Malformed localised amount | `CTL-DQ-09` | ✅ |
| F07 | Posting date outside its period | `CTL-DQ-06` | ✅ |
| F08 | Payroll misclassified across gross margin | `CTL-MAP-04` | ✅ |
| F09 | Unbalanced journal | `CTL-TB-01` | ✅ |
| F10 | Posting before the acquisition date | `CTL-CON-02` | ✅ |

**F08 is the one worth understanding.** A production payroll line is re-tagged to an SGA
department. The journal balances, the trial balance closes, the file parses — every
arithmetic control passes, and only gross margin moves. It is the fault that a purely
balancing control framework cannot see, which is why the framework has business-reasonableness
controls at all.

**F02 was rebuilt during the phase.** The first version scaled both legs of the same journal
by 4.5%, which left the pair still matching — the fixture did not represent the fault it
claimed to. A genuine intercompany mismatch restates one *entity*: the buyer books a
different amount from the seller, both trial balances still close, and only a control testing
the entity **pair** finds it.

---

## 7. Deterministic build evidence

```
build 1: phase2_dataset_digest=f396de9021089d375750ce993c4503187e913e4f27427993ad1e104ebba9df13
build 2: phase2_dataset_digest=f396de9021089d375750ce993c4503187e913e4f27427993ad1e104ebba9df13
IDENTICAL
```

Every random draw comes from a generator seeded with `MASTER_SEED = 20260907` plus a stable
string key, so no stream depends on another and adding a stream cannot shift existing
numbers. `data/build_manifest.json` carries a SHA-256 for each of the 520 generated files;
`data/samples/build_digest.txt` carries one digest over all of them. Both are committed, so a
clean clone can verify a rebuild without holding the 166 MB of data.
`test_build_is_deterministic` re-runs the entire build and compares.

---

## 8. Test results

```
258 passed in 41s
```

| Module | Tests |
|---|---|
| `test_anchors.py` | 109 |
| `test_config_integrity.py` | 44 |
| `test_architecture_invariants.py` | 46 |
| `test_phase02_generation.py` | **59** |

Phase 2 tests split into those that need no generated data (configuration, the anchor bridge,
FX anchoring, the mapping manifest, the fault catalogue) and those over generated data, which
skip with a clear message if no build has been run.

---

## 9. Material defects discovered and fixed

Nine defects, found by the controls and by review. All fixed within Phase 2.

**(a) Liability captions allocated as debits.** `year_end_bs_usd` applied no sign when
splitting a caption across source accounts, so payables, accruals, contract liabilities, tax
payable and other long-term liabilities were all allocated as **debit** balances. Group cash,
being the residual, absorbed the entire error — it read **−$126m** against an anchor of $15m.
*Found by:* group cash implausibility. *Fixed:* explicit `CAPTION_SIGN` map.

**(b) Intercompany income and expense posted twice.** The generic income statement loop
posted every account in the entity position, and the intercompany block then posted the same
flows again with their partner attached. Cost of sales overshot its target by exactly the
intercompany volume ($29.3m in FY2023). *Found by:* `P2-ANC-COS`. *Fixed:* intercompany
accounts are excluded from the generic loop; the intercompany block is the only writer.

**(c) The forecast balance sheet rolled forward from the budget.** Carried over from Phase 1
and already fixed there; Phase 2's period chaining inherits the corrected rule.

**(d) Cash and retained earnings were interpolated like any other balance.** Both appeared in
the opening balance sheet but not in the year-end targets, so the interpolation drove them to
zero by December. *Found by:* the trial balance identity. *Fixed:* both are excluded from the
interpolated path — retained earnings rolls from net income, cash is the residual.

**(e) Opening balances were never posted.** Extracts contained only movements, so no reader
could derive a balance and every balance sheet control failed. *Fixed:* an
`OPENING_BALANCE` conversion journal in each entity's first period, with retained earnings as
the derived plug.

**(f) Legs were silently dropped when an ERP had no matching account.** `post()` skipped a leg
whose account could not be resolved, which unbalances the journal without any error.
Three cases existed: Sable had no affiliate-loan receivable, Kestrel no intercompany service
cost account. *Fixed:* the resolver now **raises** rather than skipping, and the two genuine
chart gaps are recorded as explicit substitutions.

**(g) Rounding residuals in multi-leg and closing journals.** Three-leg lease remeasurement
entries and the opening and closing journals derived their plug from unrounded values, then
rounded each leg, leaving up to six cents. *Fixed:* legs are rounded first and the residual
pushed onto the largest leg.

**(h) The workforce over-provisioned headcount by 21%.** Churn employees were added *on top*
of the ramp population rather than drawn from it, so every leaver inflated the active count
until they left. *Found by:* `P2-REC-02`. *Fixed:* churn is selected out of the ramp
population, with a replacement hired the following month.

**(i) The F02 fault fixture did not represent its own fault.** Covered in §6.

### Phase 1 configuration gap discovered

**The Sable chart had no investment-in-subsidiary account**, yet `NIG-300` and `NIG-400` are
both intermediate holding companies (holding `NIG-310` and `NIG-410`). This was an omission
in the Phase 1 chart, not a deliberate ERP difference. Added as
`SABLE 17500 Investment in Affiliates → 178100`, with the reason recorded in the row's own
notes. **Flagged rather than silently patched**, per the Phase 2 brief.

### Anchor exports added (no value changed)

Phase 2 needed two things the Phase 1 anchor model computed internally but did not export:
the **2022 opening balance sheet** (Phase 2 allocates it to entities as the starting ledger
position) and the **components of net interest** (needed to build the instrument-level debt
schedule). Both were added as exports to `build_anchors.py`.

`git diff` over the previously committed anchor CSVs confirms **no existing anchor value
changed** — only new rows and two new files. All 199 Phase 1/1.1 tests still pass.

---

## 10. Self-audit

Reviewed as though auditing another consultant's work, against the failure modes the brief
names.

| Risk | Finding |
|---|---|
| Accounting impossibilities | None. Every one of 540,070 journals balances to the cent; all 507 entity-periods close to zero, including when re-derived from the native extracts. |
| Duplicate grain | None (`P2-SRC-04`). |
| Invalid signs | Tested by re-parsing every raw file under its own ERP's rule (`P2-SRC-03`). |
| Hidden normalisation | Explicitly guarded: `P2-FMT-03` asserts the three charts share no account code; `P2-FMT-01/02` assert Kestrel's special periods and zero-padded keys survive. |
| Excessive randomness | 0.01% round-thousand postings, 1.63% weekend postings, 453,731 distinct amounts, lognormal transaction sizes, per-customer payment terms. |
| Broken ownership logic | `P2-CMP-02` — no entity posts before its consolidation effective date. Virtual elimination entities never produce an extract (`P2-REF-02`). |
| Headcount/expense inconsistency | Headcount within 0.69% of anchor; the headcount fact is derived from the employee master's own dates so the two cannot disagree. |
| Debt/interest inconsistency | Debt modelled per instrument; closing principal ties to the anchored balance. |
| CapEx/depreciation inconsistency | Fixed asset register ties exactly to project spend; assets carry in-service dates and lives so Phase 4 can roll depreciation forward. |
| Anchor drift | Zero. Every income statement and balance sheet check reconciles at 0.0000% deviation. |
| Scenario leakage | The reserved Downside scenario is registered but unpopulated (`P2-CMP-04`); forecast actual months equal the Actual scenario (`P2-SCN-01`). |
| Unreproducible output | Digest identical across rebuilds; verified by test. |

### Limitations accepted and disclosed

1. **One calibration exists.** Investment in subsidiaries is calibrated by −$4.2m/−$0.9m/−$8.9m
   against ~$415m (under 2.2%) so the layer-1 balance sheet reproduces the anchored cash
   position. It is economically meaningful — it makes the implied purchase-price allocation
   equal the anchored goodwill and intangibles — and it is recorded in the build manifest
   rather than buried.
2. **Unrealised intercompany profit has no income statement charge at source.** The anchor
   inventory target is grossed up for it, but no corresponding cost of sales relief is
   modelled, because the elimination is a Phase 4 layer-3 entry. The annual movement is
   ~$0.06m and is absorbed by the calibration above.
3. **Interim-month balances are interpolated**, not independently driven. Year ends are
   anchored exactly; the months between follow a linear path modulated by trailing activity.
   Real interim balances are lumpier.
4. **Contract accounting is simplified.** Over-time revenue posts to contract assets and is
   billed on, but there is no cost-to-cost percentage-of-completion engine behind it.
5. **No deferred tax at source**, consistent with OQ-05's effective-rate scope decision.

---

## 11. Open questions

No new open questions. The eight carried from Phase 1 (OQ-03, OQ-05 to OQ-11) are unchanged
and none blocked Phase 2. Two are worth restating because Phase 3 will meet them:

- **OQ-08 intercompany transfer pricing** — the generated data uses the approved rates
  (2.5% management fee, cost plus 10–12% on product, cost plus 5% on services, 6.0% on loans).
  Changing them means regenerating.
- **OQ-11 data volume** — 1.08m journal lines sits inside the approved 1.0–1.5m range.

---

## 12. Recommended Phase 3 scope

**Phase 3 — Ingestion, staging & COA harmonisation.** Consume what Phase 2 produced. This is
where the chart-of-accounts risk is concentrated.

- Per-ERP ingestion: sign normalisation for all three conventions, Windows-1252 decoding,
  comma-decimal and `DD.MM.YYYY` parsing, zero-padded account keys preserved as text
- Kestrel special-period handling (13 → December with an adjustment flag)
- The effective-dated mapping engine, including the conditional split rule evaluator
- German total-cost-method reclassification with sign reversal
- Conformed dimensions built from `config/`
- Controls `CTL-DQ-*`, `CTL-MAP-*`, `CTL-TB-01`, `CTL-TB-02`, `CTL-IC-04`, `CTL-IC-05`

**Phase 3 has an unusually precise acceptance test.** Every one of the 1,082,408 journal lines
carries the `expected_group_account` its mapping must produce, and
`config/generation/expected_mapping_manifest.csv` states the line attributes each conditional
split has to read. Phase 3 succeeds when the mapping engine reproduces that column exactly,
and when gross margin by business unit lands on the anchors — the proof the payroll splits
worked.

The ten fault fixtures then have to be run through the pipeline to show each control failing
where it should, which the Phase 2 detectors currently prove only in isolation.

---

## 13. Verification summary

| Exit gate | Status |
|---|---|
| 1. All source systems generated | ✅ 3 systems, 507 extracts, 1,082,408 lines |
| 2. Source master/reference data exists | ✅ 11 datasets |
| 3. Clean raw trial balances pass native validation | ✅ `P2-SRC-03`, 0 of 507 out of balance |
| 4. Aggregates reconcile to anchors | ✅ 0.0000% on P&L and balance sheet |
| 5. Customer/product revenue reconciles to GL | ✅ exact, per entity and period |
| 6. Headcount aligns with anchors | ✅ 0.69% |
| 7. Debt and CapEx internally coherent | ✅ both tie exactly |
| 8. FX data complete | ✅ `P2-CMP-05`, all currencies and periods |
| 9. Deterministic regeneration proven | ✅ identical digest |
| 10. Injected faults individually detectable | ✅ 10 of 10 |
| 11. Automated tests pass | ✅ 258 |
| 12. Documentation updated | ✅ 4 new documents, 3 updated |
| 13. Git working tree clean after regeneration | ✅ |
| 14. Phase 3 not started | ✅ |
