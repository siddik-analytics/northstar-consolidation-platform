# Phase 2.1 Report — Source Data Correction Pass

**Status:** Complete · **Date:** 2026-09-07 · **Next gate:** Phase 3 approval

Corrections required at the Phase 2 approval gate. Scope was limited to the four items
raised. **No approved financial anchor was changed** — `config/anchors/` and
`docs/financial-anchors.md` are byte-identical to commit `03aa6bd`.

---

## 1. Summary

| # | Correction required | Outcome |
|---|---|---|
| 1 | Kestrel special periods 13–16 | ✅ All four generated with a defined accounting purpose, a declared population rule and a real posting calendar. Periods 14 and 16 are genuinely conditional |
| 2 | Monthly balance sheet realism | ✅ Interpolation replaced with economic drivers for twelve captions; a managed revolver added; two structural bugs and one silent modelling error found and fixed by the new guards |
| 3 | Investment in subsidiaries | ✅ Calibration removed entirely. Balances now step on acquisition dates from an investment register and reconcile in every month |
| 4 | Unrealised intercompany profit support | ✅ Transaction and FIFO-layer holdings datasets retained. Phase 2 performs no elimination |

**Tests: 258 → 284.** **Controls: 57 → 69.** **Group accounts: 189 → 190.** **ADRs: 15 → 16.**

Two defects were found *because of* this pass rather than being on the list: payables and
other credit captions started each year as debits, and the group ran a negative bank balance
in 76 entity-months. Both are fixed and both now have controls.

---

## 2. Kestrel special periods 13–16

Phase 1 specified four special periods; Phase 2.0 generated only period 13. Rather than
revise the architecture down to one, all four are now generated, because all four are real: a
German ledger does not close once. `config/coa/kestrel_special_periods.csv` declares each one
as configuration — purpose, who posts it, its timing, its entry nature and its population
rule — and the generator implements those rules.

| Period | German | Purpose | Population | Generated |
|---|---|---|---|---|
| **13** | *Abschlussbuchungen* | Statutory close into `00071500 Jahresergebnis` | Every Kestrel company-year | 542 lines, **11 of 11** |
| **14** | *Prueferbuchungen* | Audit reclassifications | Only where a finding arose | 30 lines, **5 of 11** |
| **15** | *Steuerbuchungen* | Tax true-up on filing: corporate income tax versus trade tax | Every **filed** year | 44 lines, **11 of 11** |
| **16** | *Konzernanpassungen* | HGB provisions reclassified to group categories | Only above group financial control's reporting threshold | 16 lines, **4 of 11** |

Three properties matter and are tested:

- **Periods 14–16 are reclassifications, not restatements** (`P2-FMT-09`). Each entry moves an
  amount within one anchored caption, so the year's result and every anchored subtotal are
  unchanged. That is correct rather than convenient: the group's reported result *is* the
  approved anchor, so the generated ledger is the audited outturn. A pre-audit ledger that
  differed would need an unaudited scenario, which is out of scope.
- **Unfiled years carry nothing** (`P2-FMT-08`). FY2026 is neither audited nor filed at the
  reporting date, so it has no period 14 and no period 15.
- **Conditional periods must be conditional** (`P2-FMT-07`). An audit finding at every entity
  every year would be as unrealistic as none at all.

No use case was invented to create rows. Period 16 deliberately excludes the operating lease
right-of-use asset — the Kestrel entities do not recognise it locally, so there is nothing to
reclassify, and Phase 3 raises it as a staging top-side entry instead.

---

## 3. Monthly balance sheet generation

Phase 2.0 interpolated interim balances between anchored year ends. Twelve captions are now
generated from the economics that move them — an ageing profile for receivables and payables,
a purchases-less-consumption path for inventory, real payday and quarterly settlement
calendars for accruals, staggered annual renewals for prepayments, lumpy project completions
for PP&E, and an instrument schedule for term debt. Each path is then scaled by a single
factor per year so **December lands exactly on the anchored balance**: drivers supply the
shape, the approved anchor supplies the level.

Measured by `linearity` (0.0 = a perfect straight line):

| Caption | Mean | Worst |
|---|---|---|
| Trade receivables `120100` | 0.653 | 0.254 |
| Allowance `120200` | 0.659 | 0.254 |
| Inventory `130100/200/300` | 0.474–0.501 | 0.090 |
| Trade payables `210100/200` | 0.607 | 0.186 |
| Accrued payroll `215100` | 0.677 | 0.427 |
| Accrued bonus `215200` | 0.859 | 0.846 |
| Accrued interest `216100` | 0.793 | 0.760 |
| Tax payable `218100` | 0.804 | 0.687 |
| Prepayments `140100` | 0.828 | 0.697 |

Against **0.000 for every one of them in Phase 2.0**. Control `P2-BR-04` fails the build if
any series scores below 0.02.

The objective was not volatility. Every path is deterministic and economically explainable:
accrued bonus accretes and is paid in March; accrued interest accretes and settles quarterly
in arrears; prepayments step at four staggered renewal dates and release a twelfth a month.
Accumulated depreciation and scheduled term amortisation are **excluded** from the linearity
test, because a stable asset base depreciated straight-line and a term loan on a fixed
schedule are genuinely near-linear, and demanding curvature of them would be demanding noise.

### 3.1 Three defects the rewrite exposed

**Credit captions started the year as debits.** The drivers produce magnitudes, so a credit
caption received a negative scaling factor which, blended against the prior year's factor,
crossed zero mid-year. Group payables ran from **+$18.5m in January to −$25.6m in December**.
Paths are now oriented to the sign of the caption before scaling.

**Accrued interest was $1,119m in January.** Interest settled on the quarter end, so December
sat at a trough and the factor needed to reach the anchor was 744×. Interest now settles in
arrears in the month after each interest period, so a quarter's accrual is always outstanding
at the balance sheet date — which is both realistic and anchorable. The same fault was then
found in prepayments, whose every policy expired in December.

Both were caught by a new guard rather than by inspection: **the build now fails if a driver
path's December point falls below 20% of the path's own average magnitude.** That is a
modelling error in the driver, not something to scale away.

**Entities accrued interest on debt they did not have.** The caption pushdown gave shared
services and other non-borrowing entities an accrued interest balance with no charge to
explain it. Accounts are now restricted to the entities that can hold them, with the
caption's share renormalised across the remaining accounts.

### 3.2 The revolving facility

Pooling redistributes cash; it does not create liquidity. Phase 2.0 left **76 entity-months
with a negative bank balance**, with the group as a whole $20.9m overdrawn in March 2023.

The revolver is now generated as the group's liquidity instrument: drawn against the position
the balanced ledgers actually produce, targeting a minimum operating balance that moves with
trading activity, requested in round half-millions and repaid in blocks only once there is a
worthwhile surplus — so the balance is sticky, as a real facility is. **December is set to the
approved year-end anchor**, so every anchored balance is untouched, and drawings never exceed
the $60m commitment (`P2-BR-05`).

**Result: 0 entity-months negative** (`P2-BR-01`), with group cash oscillating between $9.2m
and $28.9m across the 44 months.

One consequence is disclosed rather than smoothed away. The anchor model prices revolver
interest off an average-drawn assumption of $15.0m / $12.0m / $5.0m; the generated path
averages $6.7m / $23.9m / $11.6m, because the generated working-capital profile and the July
2024 acquisition demand liquidity on a different intra-year rhythm. Reconciling them would
mean re-opening an approved anchor's interest assumption. **The year-end drawn balances —
which are the anchored balance sheet figures — tie exactly.** Flagged for Phase 3.

---

## 4. Investment in subsidiaries

The Phase 2.0 calibration is **removed**, not reduced. `src/generation/series.py::calibrate`
and the `investment_calibration_usd_m` manifest field are gone.

`config/entities/investment_register.csv` now records the eleven ownership events in the
group's history — platform acquisition, formation, carve-out, second-tier holdings acquired
with their parent, and the one 80% acquisition that creates the group's only NCI. Each row
carries the event date, the consolidation effective date, ownership acquired and cumulative,
the consideration in transaction currency and USD, and a note explaining the transaction.

A balance is therefore the sum of the considerations actually paid, and it **steps on
acquisition dates**. Phase 2.0 interpolated it, which spread the $52m Halden acquisition
evenly across twelve months and left the balance unexplainable in all but December. Every
holding entity is USD-functional and the register carries USD cost, so no translation is
involved and the path needs no anchor scaling: it is already the answer.

`data/reference/investment_rollforward.csv` (463 rows) presents this as a monthly
roll-forward per parent and subsidiary in the form Phase 4's investment elimination consumes.
`P2-INV-01` reconciles **every ledger balance in every month** to it; `P2-INV-02` asserts
every register event has a consideration and an event type.

One date deserves a note: the Northstar Parts UK acquisition **completed on 31 December 2022**,
so its investment and the resulting NCI sit in the group's opening balance sheet while results
consolidate from 1 January 2023. `event_date` and `consolidation_effective_date` are separate
columns for exactly this reason.

### 4.1 Where the residual went instead — ADR-0016 · **SUPERSEDED BY PHASE 2.2**

> **This section is superseded.** The reviewer rejected the measurement reserve as a
> permanent source-layer design, and was right: the residual was not a measurement effect
> to be disclosed but the consequence of an anchor bridge that derived a layer-1 target for
> everything except equity. Phase 2.2 derived that target, held contributed capital at
> historical rates so a translation adjustment could arise, and removed `329100` entirely.
> The residual is nil, not small. See [`phase-02-2-report.md`](phase-02-2-report.md) and
> ADR-0017.

Removing the plug exposed what it had been hiding. Every caption other than cash is pinned to
an anchor and retained earnings rolls from locally-measured net income; together these
over-determine the balance sheet, and a difference remains.

It cannot be closed by source construction — a subsidiary's opening equity is the residual of
its own opening balance sheet, so raising a parent's contributed capital raises the
subsidiary's equity by the same amount and the two cancel at group level. What would close it
is re-deriving the anchored CTA from the generated ledgers, which changes an approved anchor
and was explicitly out of scope.

Letting it fall into cash was rejected: cash is the one group balance that is externally
verifiable, and a shortfall there also causes the revolver to draw against a gap that does not
exist. So it is posted where it belongs and named for what it is — **`329100 Group reporting
measurement reserve`**, a holding-company equity reserve struck at each year end, disclosed
line by line in `data/reference/translation_difference.csv` alongside the CTA the generated
ledgers independently imply, and capped by `P2-RES-01` at 2% of layer-1 total assets.

| Year | Layer-1 cash | Anchor cash | Variance | Reserve | % of layer-1 assets |
|---|---|---|---|---|---|
| 2023 | $15.000m | $15.000m | **0.000** | $4.238m | 0.56% |
| 2024 | $15.000m | $15.000m | **0.000** | $0.918m | 0.11% |
| 2025 | $22.000m | $22.000m | **0.000** | $8.932m | 1.03% |

Phase 4 removes the reserve and replaces it with a computed CTA. It is never a consolidation
input, and CTL-FX-04's prohibition on CTA as a plug is unaffected — that control governs the
consolidation engine, and this is a source-layer reserve the engine discards.

---

## 5. Unrealised intercompany profit support

**Phase 2 performs no elimination** (`test_phase_2_does_not_perform_the_elimination`). It
retains the detail Phase 4 needs to compute one from evidence.

Four intercompany goods flows carry stock still on hand at the buyer. The business design
justifies exactly these and no more: the flow business sells finished goods to Canada and
spare parts to both aftermarket entities, and the German valve business sells components into
the US flow business. The population was not expanded to create complexity.

- `ic_inventory_transactions.csv` (173 rows) — seller, buyer, transfer price in both
  currencies and USD, seller cost, IC gross profit, margin, category, period, quantity, and
  the buyer's inventory account.
- `ic_inventory_holdings.csv` (470 rows) — **one row per surviving FIFO purchase layer** per
  month end: the transaction period it came from, months held, percentage and quantity still
  unconsumed, and the value and unrealised profit remaining.

Layer detail rather than a monthly total, so Phase 4 can eliminate at the margin actually
earned on each layer instead of a blended assumption. Goods are consumed first-in-first-out
over each flow's months-on-hand, so a closing holding is a function of recent purchases rather
than a percentage of the balance. Implied unrealised profit tracks the anchored PUP within
**4.4%** (`P2-ICP-02`, threshold 10%). Source inventory is carried gross of PUP, which the
anchor bridge already reflects.

---

## 6. Files changed

**New — configuration (2):** `config/coa/kestrel_special_periods.csv`,
`config/entities/investment_register.csv`.

**New — code (3):** `src/generation/bsdrivers.py` (driver paths, the year-end anchor and its
guards, the revolver), `src/generation/investments.py` (register, roll-forward),
`src/generation/translation.py` (generated CTA, reserve disclosure).

**New — reference data (4):** `investment_rollforward.csv`, `translation_difference.csv`,
`ic_inventory_transactions.csv`, `ic_inventory_holdings.csv`.

**New — documentation (2):** `docs/adr/0016-source-layer-measurement-reserve.md`, this report.

**New — tests (1):** `tests/test_phase02_1_corrections.py`, 26 tests.

**Amended — code (6):** `series.py` (driver dispatch, revolver, measurement reserve;
`calibrate` removed), `ledger.py` (investments from the register, account bearer
restrictions), `journals.py` (special periods 14–16), `erp.py` (special period routing),
`datasets.py` (IC inventory), `validate.py` (12 new controls), `build.py`.

**Amended — configuration (3):** `group_coa.csv` (+`329100`), `source_coa_aurora.csv`
(+`3250`), `expected_mapping_manifest.csv`.

**Amended — documentation (4):** `synthetic-data-methodology.md` (§3.4–3.8 rewritten; the
"one calibration, disclosed" section deleted), `source-system-design.md` (new §5.1),
`source-data-dictionary.md` (§9a–9c), `docs/adr/README.md`.

---

## 7. Regression

| Check | Result |
|---|---|
| All Phase 2 data regenerated | ✅ 1,081,954 journal lines, 525 files |
| Phase 1 / 1.1 tests | ✅ pass, no anchor changed |
| Full test suite | ✅ **284 passed** (258 → 284) |
| Phase 2 controls | ✅ **69/69 pass** (57 → 69) |
| Injected fault fixtures | ✅ **10/10 detected** |
| Deterministic rebuild | ✅ digest `ebf75d63…` identical across consecutive builds |
| Approved anchors unchanged | ✅ `config/anchors/` and `docs/financial-anchors.md` byte-identical to `03aa6bd` |
| Clean baseline uncontaminated | ✅ fault variants confined to `data/faults/<id>/` |

### New controls (12)

`P2-FMT-06` all four special periods populated · `P2-FMT-07` conditional periods are
conditional · `P2-FMT-08` unfiled years carry none · `P2-FMT-09` special periods do not move
the result · `P2-BR-04` interim balances are driver-generated · `P2-BR-05` revolver within
commitment · `P2-INV-01` investments reconcile to the register · `P2-INV-02` every register
event is explained · `P2-ICP-01` IC inventory detail supports a PUP calculation · `P2-ICP-02`
implied PUP tracks the anchor · `P2-RES-01` measurement reserve immaterial · `P2-RES-02` cash
carries none of the difference.

---

## 8. Carried into Phase 3 — **all three closed in Phase 2.2**

1. ~~**Generated revolver utilisation versus the anchor's interest assumption** (§3.2). Year-end
   balances tie; average drawn does not. Closing it needs an approved anchor re-opened.~~
   **Closed.** The assumption was a defect, provable from the facility's own roll-forward
   before any generated data is consulted. Utilisation is now resolved to a daily balance and
   the average drawn anchor is derived from it (ADR-0018).
2. ~~**`329100` must be handled explicitly** by Phase 3 mapping and Phase 4 consolidation.~~
   **Closed.** The account is removed from every chart, from the mapping manifest and from the
   generator. There is nothing for Phase 3 to handle.
3. ~~**Generated CTA versus anchored CTA** — cumulative $1.44m / −$1.47m / $3.15m against
   $0.00m / −$5.30m / $3.50m.~~ **Closed.** The generated figure was itself understated,
   because contributed capital was retranslated onto a USD target each year and could not
   generate an adjustment. With capital frozen at historical rates the layer-1 CTA is
   $1.54m / −$2.70m / $5.04m, and the anchored roll-forward is derived from it (ADR-0017).

See [`phase-02-2-report.md`](phase-02-2-report.md).
