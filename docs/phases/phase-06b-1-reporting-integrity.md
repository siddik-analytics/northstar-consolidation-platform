# Phase 6B.1 — final reporting integrity corrections

**Status:** complete — **awaiting owner final visual review**
**Baseline:** `2fe00ee` (Phase 6B reviewed and approved bar two corrections); Excel frozen at
`bf847b4327526a39`, untouched
**Docs:** [Phase 6B](phase-06b-report.md) · [the report](../powerbi-report.md) ·
[semantic model](../powerbi-semantic-model.md) · [controls](../powerbi-controls.md#phase-6b1-p6b1) ·
[defect register](../defect-register.md) · [lessons §18](../architecture-lessons.md) ·
[screenshots](../assets/phase-06b/MANIFEST.md)

---

## 1. The two corrections

| | before | after |
|---|---|---|
| **P6B-D-06** | `Account[fs_caption_l2]` sorted by `sort_order`, an account-grain key: one caption, several keys; the report avoided the column | every reportable level carries a key **at its own grain**, derived from the governed chart order; the P&L account detail is the full caption → sub-caption → account hierarchy |
| **Layer bridge** | annual, from `mart_consolidation_bridge`: FY2026 read 29.2m beside a YTD headline of 28.1m | the bridge at month grain, on the governed period basis and the reporting close: the YTD bridge at Aug 2026 sums to 28,100,907.83, the YTD Statutory EBITDA, exactly |

Nothing else changed: no redesign, no palette change, no new analytical visual (the page lost
one), no Excel change.

## 2. The hierarchy and its sort architecture

`dim_semantic_account` now publishes, beside every account:

| column | grain | derivation |
|---|---|---|
| `fs_caption_l1` · `fs_caption_l1_sort` | level-1 caption | the smallest account `sort_order` beneath the caption |
| `fs_caption_l2` · `fs_caption_l2_sort` | level-2 caption | the smallest account `sort_order` beneath the caption |
| `account_name` · `sort_order` | account | the chart's own order, as Phase 3 governs it |

A caption therefore sits exactly where its first account sits on the governed chart, so
the order is the statement's own (Cash and cash equivalents first on the balance sheet,
Product revenue first on the income statement), nothing is alphabetical, and a caption maps
to one key **by construction** rather than by whichever account happened to come first.

One thing the chart does that the derivation had to respect: three level-2 labels are reused
under more than one level-1 caption — *Intercompany balances* under four, *Non-controlling
interests* and *Operating lease liabilities* under two. Those are different hierarchy
nodes with one label, and a label that names two nodes cannot have one key. Each such node
is qualified with its level-1 caption (*Intercompany balances (current assets)*), so the
label, too, names exactly one node. No account moved and no amount changed.

The same control found the same fault in two more places the moment it ran: `Scenario
[scenario_name]` sorted by a version-grain key (four names, six keys), and `Balance Sheet
[caption]` where *Intercompany balances* spans ASSET and LIABILITY. Both are restated in the
semantic layer (`dim_semantic_scenario` with a scenario-grain key; `fact_semantic_balance_sheet`
with the spanning caption qualified); the Phase 5 marts are untouched.

## 3. Hierarchy acceptance

| proof | evidence |
|---|---|
| every level-1 caption → one key; every level-2 caption → one key | 12 captions, 12 keys; 61 captions, 61 keys (`P6B1-HS-01`, `P6B1-HS-02`) |
| no duplicate caused by sort metadata | the engine groups 61 level-2 captions once each: 0 duplicates (`P6B1-HS-03`) |
| statement order, no alphabetical fallback | level-1 order by key equals the chart's; level-2 captions contiguous under their level-1; the alphabetical order is not the rendered one (`P6B1-HS-02`) |
| account drill intact | 175 accounts resolve beneath their captions in the engine (`P6B1-HS-03`); the P&L account detail expands Revenue → Product revenue, Service revenue, Project revenue, Other revenue, Revenue deductions, Intercompany revenue natively (`assets/phase-06b/final/02_pnl_performance_expanded.png`) |
| P&L and balance sheet render correctly natively | `assets/phase-06b-1/hierarchy_lab_is_bs.png`: both statements' level-1 and level-2 captions in Desktop, in statement order, each once |
| permanent control | `P6B1-HS-01…03`; fixture `F6B1-01` gives *Accrued liabilities* two keys and `P6B1-HS-01` fails |

## 4. The layer bridge

`fact_semantic_layer_bridge` is the consolidation bridge at month grain — `rpt_layer_bridge`'s
definitions unchanged (EBITDA accounts, the year-end close excluded as P4-D-03 requires),
grouped by layer and period instead of layer and fiscal year. `P6B1-BR-01` proves every
layer and fiscal year of it sums to `mart_consolidation_bridge`, which stays as Phase 5
published it (the workbook reads it).

`[Layer EBITDA]` and `[Layer Net Income]` read that fact on the governed period basis —
the month, the fiscal year to the month, or the fiscal year — and are blank after the
reporting close, exactly as the statement measures are. `[Layer Entries]` is a count over the
months in context and says so.

The Consolidation & Controls page now carries the period and basis slicers the headline
follows, and the bridge's title is the governed `[Consolidation Bridge Title]`: *Year to
date consolidation bridge — Aug 2026*. It cannot go stale and it cannot claim a scope it
does not have. The annual entries matrix is gone (it was the only annual figure on the
page, and the owner's rule is that two scopes never sit together without an explicit
distinction); the count remains a governed measure.

## 5. Bridge reconciliation, Aug 2026

Statutory layers 1 + 2 + 3 + 5 against the governed consolidated measure, in the engine:

| basis | Layer EBITDA | Statutory EBITDA | Δ | Layer Net Income | Net Income | Δ |
|---|---|---|---|---|---|---|
| MTD | 3,625,944.61 | 3,625,944.59 | 0.02 | (78,300.81) | (78,300.83) | 0.02 |
| **YTD** | **28,100,907.83** | **28,100,907.83** | **0.00** | (939,022.79) | (939,022.82) | 0.03 |
| FY | 29,202,425.43 | 29,202,425.43 | 0.00 | (2,238,063.11) | (2,238,063.14) | 0.03 |

The cents are rounding at different grains (the bridge rounds each layer-month, the mart
each entity-month); the tolerance is the platform's 0.05. Sep–Dec 2026 read blank on every
basis (`P6B1-BR-08`). The FY figure at Aug 2026 is the same 29.2m the annual bridge showed —
and the same figure the headline gives on the FY basis — so the earlier mismatch was scope,
never arithmetic.

## 6. Controls and fixtures

`P6B1`: 12 controls in three families, all passing; 3 fixtures, 3/3 detected by the control
named for each. The table is in [`powerbi-controls.md`](../powerbi-controls.md#phase-6b1-p6b1).
The family has its own register so the Phase 6A register the frozen workbook reads keeps its
68 rows.

## 7. Native validation

Desktop 2.157.1354.0: the corrected project opened through its own dialog and refreshed
(the refresh automation now presses again when Desktop swallows the first press after an
open); all ten pages rendered with zero visual errors; navigation 10/10; the unit slicer
narrows; the Actual line ends at the close; the rendered cards equal the engine. The bridge
title reads *Year to date consolidation bridge — Aug 2026* and its bars sum to 28.1m.

## 8. Regression

Every upstream suite, the semantic, report and 6B.1 families, the integrity framework, the
reproducibility check and 586 tests pass. **The committed workbook is untouched at
`bf847b4327526a39`.** One consequence is reported rather than hidden: the three semantic
publications are declared in the key and grain registry, as the framework requires, and the
registry's control count therefore grew from 295 to 304 — a count the workbook's Cover and
sheet 13 read. A *rebuild* of the workbook would move exactly those four count cells
(`tools/workbook_diff.py`: 4 numeric, 0 text, 0 financial) and its digest, so the
reproducibility test that compares a rebuild with the frozen digest fails until the owner
either accepts a control-count refresh, as at Phase 6A.2 and 6A.3, or keeps the workbook
frozen as it is. Nothing was decided here.

## 9. What moved in the sealed model

The definition digest moved (three sort declarations, one table source and key, one
relationship, three measures rewritten, one measure added) and with it the Phase 6A build
id — an owner-approved correction to the sealed model, recorded here. The project digest
moved with the report.

## 10. Remaining limitations

* `[Layer Entries]` is a plain count over the months in context; no visual shows it now.
* The bridge's month-grain fact is a Phase 6 publication derived from the consolidated
  fact; the Phase 5 annual mart is unchanged and still what the workbook's sheet 13 reads.
* Qualified level-2 labels (*Intercompany balances (current assets)*) are a semantic-layer
  presentation; the Phase 3 chart of accounts keeps its plain labels.
