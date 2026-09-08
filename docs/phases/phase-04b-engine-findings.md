# Phase 4B — defects found in the Phase 4 engine by documentation work

> **Both defects are CLOSED in Phase 4C**, together with a third of the same kind that the
> new controls found on their first run. See
> [`phase-04c-reporting-integrity.md`](phase-04c-reporting-integrity.md). This document is kept
> as the record of what was found and why nothing was corrected here.

Two defects were found while writing the Phase 4B documentation package. Both are in **Phase 4
reporting artefacts**. Neither was corrected in Phase 4B: that brief is documentation and
release-readiness only, and it requires that a genuine defect be reported rather than silently
fixed under cover of documentation.

Both were found the same way — by writing down what an artefact contains and comparing it with
what another artefact says about the same thing. Neither is caught by any of the 61 controls,
and that absence is itself part of each finding.

| | Defect | Artefact | Measurement wrong? | Controls affected | Status |
|---|---|---|---|---|---|
| **P4-D-01** | prior years' unclosed consolidation result presented as the current period's result | `rpt_balance_sheet` | no — classification within equity | none | **CLOSED 4C** |
| **P4-D-02** | statutory EBITDA computed including the year-end close; Covenant EBITDA voided by a NULL | `rpt_ebitda_bridge` | **yes** | none | **CLOSED 4C** |
| **P4-D-03** | the same close defect in a third artefact, found by `P4-XAR-11` on its first run | `rpt_layer_bridge` | **yes** | none | **CLOSED 4C** |

---

## P4-D-01 — "Result for the period" accumulates prior years' consolidation adjustments

**Status:** **CLOSED in Phase 4C.**

### What it is

The consolidated balance sheet's equity section carries a caption **"Result for the period"**.
At 31 December 2025 it shows **USD 19.869m** as a debit — a loss of 19.869m.

The consolidated income statement for FY2025 reports net income attributable to the parent of
**+7.046m**, a profit. A reader comparing the two statements cannot reconcile them.

| Caption at 31 Dec, USD m | 2023 | 2024 | 2025 |
|---|---|---|---|
| Result for the period (as presented) | 6.100 | 12.963 | 19.869 |
| Net income attributable to parent, that year | (6.795) | (1.072) | 7.046 |

### Root cause

The caption is the cumulative balance of every income statement account **including the
year-end close**. That construction is correct in intent — the close reverses each year's
result into retained earnings, so what is left is the result not yet closed — and it is what
makes the balance sheet balance.

But it is only complete for layer 1. Decomposed at 31 December 2025:

| | USD m |
|---|---|
| Layer 1, after its own year-end close | (0.187) |
| Layer 3, consolidation adjustments — **never closed by any entity ledger** | 20.055 |
| | **19.868** |

The layer-3 balance is three years of accumulated PPA amortisation (20.024), unrealised profit
(0.714) and NCI attribution (0.682 credit). No entity closes them, because they do not exist in
any entity's books, so they accumulate in the "result" caption instead of rolling into
consolidated retained earnings the way a group's prior-year consolidation adjustments should.

The consequence is a misclassification **within** equity. The layer-3 result of FY2023 and
FY2024 — 6.140 + 6.885 = **13.025 USD m** — belongs in consolidated retained earnings by
31 December 2025 and is instead still sitting in the current-period caption:

| At 31 Dec 2025, USD m | As presented | Where it belongs |
|---|---|---|
| Retained earnings | 57.832 (deficit) | 70.857 (deficit) |
| Result for the period | 19.869 | 6.844 — FY2025's own layer-3 result of 7.031, less the layer-1 close residual |
| **Total equity** | **93.340** | **93.340** |

A stricter reading goes further: the December period-end is *after* the year-end close, so at
that date the caption should hold only what has not been closed at all, and FY2025's own
layer-3 result belongs in retained earnings too. Which of the two is right is a presentation
policy question, and it is the owner's to settle — but under either reading the figure
currently presented is not the result for the period.

### Why the balancing controls miss it

Because nothing is out of balance. Total equity is right, assets equal liabilities plus equity
at 0.00 in all 48 periods, every layer control passes, the cash flow ties, and no anchor moves.
The defect is entirely in how one correct total is split across two captions, and no structural
identity can see a split.

`P4-BS-05` requires the result caption to appear exactly once — which it does. It does not, and
cannot without new information, assert that the amount in it is the *period's* result.

### What a fix would involve

Rolling prior years' layer-3 result into consolidated retained earnings at each year end — the
consolidation equivalent of the close that the entity ledgers perform on their own books. That
is a change to `src/consol/statements.py` and possibly a new layer-3 closing entry, plus a
control asserting that the result caption equals the year-to-date result attributable to the
parent. It is an accounting-presentation change and belongs to the owner, not to a
documentation phase.

---

## P4-D-02 — the EBITDA bridge is wrong in three of four years, and Covenant EBITDA is NULL

**Status:** **CLOSED in Phase 4C.**

### What it is

`rpt_ebitda_bridge` and `rpt_income_statement` disagree about Adjusted EBITDA:

| USD m | FY2023 | FY2024 | FY2025 | FY2026 |
|---|---|---|---|---|
| Statutory EBITDA per `rpt_income_statement` | 28.705 | 38.891 | 51.250 | 29.202 |
| Statutory EBITDA per `rpt_ebitda_bridge` | **(0.535)** | **(0.083)** | **(0.095)** | 29.202 |
| Adjusted EBITDA per `rpt_income_statement` | 38.505 | 47.091 | 57.750 | 33.013 |
| Adjusted EBITDA per `rpt_ebitda_bridge` | **(0.535)** | **(0.083)** | **(0.095)** | 33.013 |
| Covenant EBITDA per `rpt_ebitda_bridge` | **NULL** | **NULL** | **NULL** | **NULL** |

### Root cause, in three parts

**1. The close is not excluded.** `mgmt.ebitda_bridges()` reads `vw_statutory_fact` without the
`counts_in_result` predicate, so each year's income statement accounts are summed *including*
the year-end close that reverses them. The year therefore nets to approximately nil and what
remains is the layer-3 unrealised-profit charge that no ledger closes. FY2026 is right only
because it has not been closed yet — eight actual months with no year end.

This is the same defect that was found and fixed in `rpt_income_statement` and
`rpt_balance_sheet` during Phase 4. It was not fixed here because nothing compared the two
artefacts until this documentation was written.

**2. A nil `FILTER` voids the row.** `covenant_ebitda_usd` is computed as an arithmetic
expression containing `sum(amount_usd) FILTER (WHERE group_account IN ('740100','740200'))`.
No entity ever posts to those accounts, so the aggregate is NULL, and one NULL anywhere in the
expression makes the whole result NULL. Every year's Covenant EBITDA is therefore NULL rather
than "the same as Adjusted EBITDA plus a nil add-back".

This is also a repeat: the identical `FILTER`-yields-NULL fault voided gross profit and net
income in `rpt_income_statement` during Phase 4 and was fixed there by coalescing every
measure at the point it is built. `mgmt.py` was not given the same treatment.

**3. The covenant FX add-back has no population.** Accounts `740100` and `740200` (realised and
unrealised foreign exchange) exist in the chart and are never posted to by any entity. The
credit agreement's CA-030 add-back is therefore structurally nil in the modelled window. That
is a source-layer observation rather than an engine defect, but it is what exposed fault (2),
and it should be stated rather than left as a silent NULL — a covenant add-back that is nil
because there is nothing to add back is a different statement from one that is nil because the
calculation failed.

### Why the controls miss it

There is no control on `rpt_ebitda_bridge` at all. `P4-MGT-03` touches it, but only to report
how many years show Adjusted and Covenant EBITDA as equal — and it is a `WARNING` that passes
unconditionally, by design, because the two measures are *not expected* to be equal. It never
tests either figure against anything.

The `P4-PL-01` control tests the internal consistency of `rpt_income_statement` — revenue less
cost of sales equals gross profit, EBITDA less D&A equals EBIT — but it stops at that artefact.
Nothing cross-checks one reporting artefact against another, which is exactly the gap that let
two statements disagree about the same measure.

### What a fix would involve

* apply `counts_in_result` in `mgmt.ebitda_bridges()`, as `rpt_income_statement` already does;
* `coalesce` every aggregate where it is built, as `rpt_income_statement` already does;
* add a control asserting that `rpt_ebitda_bridge.statutory_ebitda_usd` equals
  `rpt_income_statement`'s EBITDA for the same year, and that Covenant EBITDA is non-null —
  a cross-artefact control, which the suite currently has none of;
* add a fault fixture that breaks one artefact and requires the other to disagree.

The third item is the substantive one. Both faults are repeats of faults already found and
fixed elsewhere in the same phase, in an artefact nothing was checking. A control family that
compares reporting artefacts with each other would have caught both on the day they were
written.

---

## Assessment

Neither defect touches the accounting engine: no journal, no layer, no elimination, no
translation, no attribution and no statement identity is affected. Both are in the presentation
and analytics artefacts built on top of a consolidation that remains proved —
61/61 controls, 19/19 fixtures, balance sheet 0.00, cash flow 0.00, 421 tests.

But `rpt_ebitda_bridge` produces figures a lender would be shown, and it produces them wrongly.
Phase 4 should not be signed off as complete until it is corrected, and the correction is an
engineering change that this documentation phase was explicitly told not to make.
