# Control Framework

**The design register: 87 controls across 10 categories**, in
[`config/controls/control_register.csv`](../config/controls/control_register.csv). This
document explains the design.

**What is implemented and running, as at Phase 4B:**

| | Controls | Register | Results |
|---|---|---|---|
| Phase 2 — generated source | **80** | `src/generation/validate.py` | `data/phase02_control_results.csv` |
| Phase 3 — ingestion and mapping | **62** | `src/pipeline/controls.py` | `data/phase03_control_results.csv` |
| Phase 4 — consolidation | **61** | [`config/controls/phase04_control_register.csv`](../config/controls/phase04_control_register.csv) | `data/phase04_control_results.csv` |

The Phase 4 suite has its own document — [`consolidation-controls.md`](consolidation-controls.md)
— because it introduced the design rule that now governs all of them: **controls iterate from
the authority that requires the data, not from the data being tested.** The design register's
`CTL-*` identifiers map onto the implemented `P2-*`, `P3-*` and `P4-*` controls; where a design
control was split or reshaped in implementation, the implemented control names the `CTL-*` it
descends from.

## 1. Why this exists

The CFO's stated problem is not that the numbers are wrong. It is that **nobody can prove
they are right**. Month-end takes four days, intercompany is reconciled by email, and when
the board asks where a number came from the honest answer is "a spreadsheet".

A control framework fixes that by making correctness a property of the pipeline rather than
a property of the person who happened to build this month's file. The design targets are:

1. **Every material failure mode has a named control.** If something can go wrong silently,
   there is a control that makes it go wrong loudly.
2. **Blocking controls actually block.** A failed blocking control stops the pipeline. It
   does not produce a warning that gets ignored for six months.
3. **Control results are data.** Stored in `fact_control_result`, so status can be trended
   and the close can be shown to be improving.
4. **Every control names an owner and a remediation.** A control that fails and tells nobody
   what to do is an alarm without a fire exit.

## 2. Severity model

| Severity | Count | Behaviour |
|---|---|---|
| `BLOCKING` | 66 | Pipeline halts. Nothing downstream is published. The period does not close. |
| `WARNING` | 13 | Pipeline continues; the exception is reported and requires explicit acknowledgement before sign-off. |
| `INFO` | 2 | Reported for trend and insight; no action required. |

The ratio is deliberate. Most of these controls test an identity — a trial balance balances
or it does not, an elimination nets to nil or it does not — and an identity that fails is
not a matter of degree. Warnings are reserved for **plausibility** tests, where the right
answer genuinely depends on judgement: a gross margin eight points off trend might be a
mapping defect or might be a genuinely unusual month, and only a human can tell.

An over-use of `WARNING` is how control frameworks die. If half the controls warn every
month, people stop reading them, and the one that mattered gets lost in the noise.

## 3. Categories

| Category | Controls | Phase | What it protects |
|---|---|---|---|
| `DATA_QUALITY` | 10 | 3–4 | The extract arrived, parsed, and was not loaded twice |
| `MAPPING` | 8 | 3 | Every source account reached the right group account |
| `TRIAL_BALANCE` | 5 | 3–4 | Debits equal credits at every stage of transformation |
| `FIN_STATEMENT` | 9 | 4–5 | The three statements are internally consistent and tie to each other |
| `FX` | 11 | 3–5 | Translation is correct, CTA rolls forward, and is derived rather than plugged |
| `INTERCOMPANY` | 8 | 3–4 | Intercompany activity is identified, matched and eliminated |
| `CONSOLIDATION` | 13 | 4 | Layers, scope, ownership, NCI and adjustments are right |
| `SCENARIO` | 6 | 5 | Budget and forecast are complete, locked, comparable and isolated |
| `RECONCILIATION` | 6 | 4–9 | Every figure traces back to its source |
| `REASONABLENESS` | 5 | 4–8 | The numbers make business sense, not just arithmetic sense |

## 4. Control points in the pipeline

```
  RAW EXTRACT ──► CTL-DQ-01..03, 09, 10        file received, parses, no duplicates
        │
  NORMALISE ────► CTL-DQ-05, CTL-TB-01         signs correct, entity TB balances
        │
  MAP ──────────► CTL-MAP-01..08, CTL-TB-02    everything mapped, still balances
        │
  TRANSLATE ────► CTL-FX-01..11, CTL-TB-03     rates complete, CTA rolls forward, balances in USD
        │
  ELIMINATE ────► CTL-IC-01..08                IC matched, eliminations balance
        │
  CONSOLIDATE ──► CTL-CON-01..13               layers, scope, ownership, NCI, adjustments
        │
  DERIVE CF ────► CTL-FS-01..08                statements tie to each other
        │
  PUBLISH ──────► CTL-SCN-*, CTL-REC-*, CTL-BR-*  completeness, traceability, sense
```

Controls run **at the point of the transformation they protect**, not in a batch at the end.
A trial balance failure detected at ingestion costs minutes to fix; the same failure
detected after consolidation costs a day of bisecting.

## 5. The controls that matter most

Eighty-one controls is a lot to hold in your head. These eleven are the ones that would
catch the failures that actually damage credibility.

### `CTL-TB-01` — Entity trial balance balances
The most fundamental control there is. Sum of all signed amounts across non-statistical
accounts equals zero, per entity, per period, in local currency. If this fails, the extract
is incomplete or the sign convention for that ERP is wrong. With three different sign
conventions in play, this is not theoretical.

### `CTL-FS-03` — Cash flow reconciles to the balance sheet
Net change in cash per the cash flow statement equals the movement in balance sheet cash.
Because the statement is derived from balance sheet movements, this holds by construction —
*provided* every movement is categorised into exactly one cash flow line. A break means an
account movement is either missing from the statement or double-counted, which is why
`CTL-FS-04` (every balance sheet account has a cash flow category) exists alongside it.

### `CTL-FX-04` — CTA is derived and explainable
The engine's CTA is compared to an independent expectation:

```
opening net assets × Δ(closing rate)  +  current year result × (closing − average rate)
```

CTA entered as a plug is the classic way a consolidation hides a translation defect: the
balance sheet balances, so nobody looks, and the error sits in equity indefinitely. This
control makes plugging impossible.

### `CTL-FX-12` — CTA reproduces the source-layer expectation

`CTL-FX-04` compares the engine's CTA to a formula. `CTL-FX-12` compares it to a **number
produced before the engine existed**, from the source ledgers alone:
`data/reference/cta_expectation.csv`, one row per foreign entity and month, carrying opening
net assets in local currency, the three rates applied, the result, and the movement each
component generates. It references no group target, which is the whole point — a consolidation
engine tested against a figure derived from its own output tests nothing.

The group figure bridges to it by adding the retranslation of goodwill and acquired
intangibles, which exist in no source ledger, and deducting the non-controlling interest's
share and the movement in unrealised intercompany profit. Phase 2.2 derived the approved CTA
anchor from that bridge, superseding the provisional Phase 1 target (ADR-0017).

### `CTL-CON-14` — No residual or balancing account in any layer

The control is written against an **idea**, not an account number. No account in any chart,
and no posting in any layer, may exist to absorb a difference between a computed result and an
expected one. Equity must close on its own roll-forward: opening, plus the result, plus
contributions, less distributions, plus the computed CTA.

It exists because the project made the same mistake twice. Phase 2.0 absorbed a residual into
investment at cost, which left investment balances unexplainable. Phase 2.1 moved it to a
named, capped, disclosed equity reserve — better, but still a balance whose only purpose was
to make the model agree. Phase 2.2 found the real cause: the anchor bridge derived a layer-1
target for every asset, every liability and every income statement line, but not for equity, so
the balance sheet had one free variable. Deriving that target removed the residual entirely
(ADR-0016 superseded by ADR-0017). A control that catches a class of defect the project has
already committed twice is worth more than one that catches a hypothetical.

### `CTL-FS-10` — Facility charge supported by the daily drawn balance

Two identities, both of which a revolving facility must satisfy:

```
opening drawn + drawings - repayments                  = closing drawn
average daily drawn x (base rate + margin)
    + commitment fee on the average daily undrawn      = the recorded charge
```

Interest accrues on a daily balance, not a month-end one, so the second identity needs an
intra-month position — which is why `config/debt/treasury_policy.csv` fixes the borrowing
notice date and the collections sweep date as policy rather than leaving them implicit. An
average-drawn assumption that the facility's own roll-forward contradicts misstates the
interest cost and the covenant coverage ratio at the same time, and neither the balance sheet
nor the cash flow statement will notice. See ADR-0018.

### `CTL-DQ-11` — Source lineage complete and unique

Every conformed financial row carries the source system, the file, its ordinal within that
file, the source account and account name as the system spelled them, the native amount
*before* sign normalisation, the source period as posted, the journal and document
identifiers and the line number. The declared grain — ERP, file, journal, line — is unique,
and the ordinal runs 1..N within every file with no gap.

Two different failures are covered. A row that cannot be walked back to a byte range in a
named file cannot be defended in an audit, however correct it is. And a gap in the ordinal is
a dropped row, which no total will reveal because the total was computed after the row went
missing.

### `CTL-MAP-09` — Mapping rule set integrity

The rule set is validated before any data is mapped: every conditional account declares
exactly one default branch, every condition parses and names only permitted fields, every
target exists in the group chart and is not statistical, identifiers are unique, and every
rule is effective-dated.

A split with no default branch is a silent fall-through waiting for a posting that does not
match. A condition naming an unvalidated field is arbitrary code sitting in a configuration
file, where no control can reach it — which is the failure ADR-0007 and ADR-0020 exist to
prevent, arriving by a different door.

### `CTL-DQ-09` — Numeric and date parsing

Strengthened in Phase 3. It originally asked for zero nulls after parsing, and a fault
fixture proved that insufficient: a German `13.068,03` written as `13.068.03` is not null,
not blank and not non-numeric. It casts cleanly to 1,306,803 — a hundredfold overstatement —
and if both legs of the entry are affected it still balances, so the trial balance controls
are blind to it too.

The control now requires every raw amount string to conform to **its own ERP's numeric
grammar before it is cast**, as an anchored expression per system, each exactly what that
system emits rather than a permissive superset. Phase 3 implements it as `P3-ING-13`.

### `CTL-IC-04` — Intercompany partner always populated

Enforced from Phase 2 as `P2-IC-02` and from Phase 3 as `P3-DIM-08`, and worth reading as a
lesson rather than a rule.

The Phase 2 implementation tested the intercompany lines **that already carried a partner**.
It could not fail. A filter that removes exactly the rows a control exists to find is not a
subtle bug, and it ran green through two phase gates over a population in which 63% of the
intercompany balance position could not be attributed to an entity pair at all — the defect
that would have blocked the Phase 4 elimination engine.

A control is now required to state the population it measures, and to measure the whole of
it. Where a legitimate exclusion exists it is named and justified in the control itself: the
year-end close is excluded here because it sweeps the entire income statement into retained
earnings in one entry, so its lines are a position rather than a transaction with any one
counterparty.

### `CTL-IC-01` and `CTL-IC-02` — what matches at which rate

Also split apart in Phase 3.1, because one control was doing both jobs and doing neither
correctly. A **balance** matches its mirror at the **closing** rate, and it is the cumulative
balance that must match, not the month's movement. A **flow** matches at the **average** rate
of the month it was recorded in. Testing movements at average rates for every intercompany
line regardless of statement is two errors, and they cancelled only because the balance sheet
legs carried no counterparty and were silently excluded.

Investments in subsidiaries are intercompany but **not reciprocal** — a holding eliminates
against the subsidiary's equity, not against a mirror balance in the subsidiary's books — so
they are excluded from the pair test and reconciled to the investment register by
`P2-INV-01` instead.

### `CTL-DQ-12` — Population bridge complete

Every ingested financial row carries exactly one disposition in each of three partitions:
what kind of posting it is, what the harmonisation engine did with it, and whether the oracle
graded it. Each partition sums to the ingested row count.

Two things this catches that nothing else does. A row that falls out between two stages
leaves no trace in any total — the trial balance still closes, because a dropped balanced
journal is still balanced. And a difference between two population counts that nobody can
name is the same failure wearing a tidier number: Phase 3 reported 1,080,782 ingested against
1,013,640 graded and the difference turned out to be a measurement defect, not an exclusion.

Dispositions that must be nil are stated at nil rather than omitted. A category missing from
a bridge reads as a category nobody thought to look for.

### `CTL-CON-03` — Investment elimination, and where a control's population comes from

`P2-INV-01` reconciles the investments the ledgers hold to the approved investment register.
It used to walk the **ledger's** balances and look each one up in the register, so an
investment the register required and no ledger held was never looked at — and when exactly
that happened, USD 16.9m disappeared from an opening balance sheet while the trial balance
still closed, because the missing asset only made the retained-earnings plug smaller
(P3-D-06).

That is the second time this shape has cost a phase. `P2-IC-01` iterated the intercompany
lines that already carried a counterparty; `P2-INV-01` iterated the investments the ledger
already held. Both were written by somebody who knew what the answer should be and checked
that the data agreed with itself, and agreeing with itself was never in doubt.

**A control's population comes from the authority that requires the data, never from the data
itself.** The register says which investments must exist; the flow matrix says which
intercompany relationships must exist; the FX policy says which translation bases must exist.
`P2-INV-01` now starts from the register and reports missing, unexpected, wrong parent, wrong
subsidiary, wrong amount, wrong effective date and duplicate relationship separately, over the
463 relationship-periods the register requires.

### `CTL-FX-10` — the opening translation base, recomputed rather than trusted

`P2-FX-04` recomputes every entity's opening translation base from the rule its opening
balance sheet is built with, and compares it with what the generator registered. It exists
because those two were produced by different parts of the generator and disagreed for one
entity: the balance sheet was stated at the FY2022 closing anchor and registered at the
January 2023 close (P3-D-05). Nothing balanced differently — the 2.1% difference simply became
CTA, which no self-consistency check can see and only an independent recomputation catches.

### The source exception register

A control that fails because of a defect in data the team does not own is a different animal
from a control that fails because the pipeline is wrong, and treating them the same destroys
one of them. Downgrade the first to a warning and it stops being read; leave it failing and
the build is red every day until nobody looks.

`config/controls/source_exception_register.csv` quarantines the first kind. Each accepted
finding records the **population it was accepted at**, and the control compares against that
baseline:

| Measured | Outcome |
|---|---|
| nil | `PASS` — the source was corrected |
| equal to the accepted population | `SOURCE_FINDING` — the known defect, unchanged |
| **more** than accepted | **`FAIL`** — something new is wrong |
| fewer than accepted | **`FAIL`** — retire the exception, it is stale |

All seven entries are `CLOSED` at an accepted population of nil as at Phase 3.1: the four
defects they excepted were corrected at the generation layer rather than accepted. A closed
exception is **not** a deleted one. The register still names the defect, so a recurrence
fails the control instead of reappearing as an accepted finding, and each entry records the
phase that closed it and the code that corrected it.

The third row is the one that earns the register. Without it, a *new* break of exactly the
same shape as an accepted one hides inside it and no control ever moves. Each entry also
carries an expiry — the phase at which the underlying defect is expected to be corrected — so
an exception cannot quietly become permanent.

### `CTL-CON-09` — Consolidation layer integrity
Every fact row carries a `layer_id` from the defined set of five. This is a small control
guarding a large hole: because both the statutory and the management view are defined by
*explicit* layer membership (`1,2,3,5` and `1,2,3,4,5`), a row with an undefined or null layer
belongs to **neither**. It is silently excluded from both, and the statements still balance
without it — so no other control in the framework notices. The layer set is closed at five and
`dim_layer` is built from a single configuration file.

### `CTL-FX-09` — CTA roll-forward continuity
Closing CTA equals opening plus movement plus any amount recycled on disposal, and each
period's closing CTA is the next period's opening, per entity, with no unexplained step. A
discontinuity means either that a closed period has been restated or that the engine
recomputed CTA from scratch instead of rolling it forward. Both are defects, and both are
invisible without this control because a recomputed CTA still balances the balance sheet.

### `CTL-CON-11` — NCI equity roll-forward
Closing NCI equals opening, plus share of result, less dividends, plus the share of the
translation adjustment, plus ownership changes. The component most often omitted is the **NCI
share of the CTA movement**: allocating 100% of a partially owned subsidiary's translation
movement to group equity overstates group equity and understates NCI by the same amount, and
because both sit inside total equity the balance sheet still balances. Only a control looking
for it specifically will find it.

### `CTL-IC-01` / `CTL-IC-02` — Intercompany eliminates to nil
Balances and P&L, per entity pair, per account, per period. Not tested in aggregate — a
$2m receivable from one entity and a $2m payable to a different one net to zero in
aggregate while being completely wrong.

### `CTL-IC-08` — Unrealised profit in inventory
The elimination most often missed, because it requires knowing what proportion of closing
inventory was bought internally — which the GL alone does not carry. Omitting it overstates
consolidated inventory and gross profit. FY2025 anchor: $0.70m.

### `CTL-CON-02` — Consolidation scope respects effective dates
No entity contributes results before its acquisition date. Consolidating Halden from January
2023 rather than April would overstate FY2023 revenue by roughly $6m and quietly corrupt
every organic-growth comparison thereafter.

### `CTL-REC-01` — Source-to-consolidated reconciliation
A single statement reconciling the sum of source trial balances to the consolidated result,
with mapping, translation, eliminations, consolidation adjustments and management
adjustments as separate named lines. This is the answer to "where did this number come
from?", produced every period whether or not anyone asks.

### `CTL-BR-01` — Gross margin within a plausible band
The only control here that catches a **mapping** error rather than an arithmetic one. If
Aurora's payroll split sends direct labour to SG&A, every balancing control still passes —
the trial balance balances, the statements tie, eliminations net — because the error is a
reclassification *within* the P&L. Only a business-sense check catches it. This is why
reasonableness controls exist at all.

## 6. Reasonableness controls and their limits

Balancing controls prove arithmetic consistency. They cannot prove the numbers mean
anything. The five reasonableness controls (`CTL-BR-*`) test gross margin, revenue per FTE,
opposite-sign balances, working capital days and forecast accuracy against trailing
averages.

They are all `WARNING` or `INFO`, never `BLOCKING`, because a genuinely unusual month is a
business event rather than a defect. A large turnaround campaign legitimately moves
Industrial Services gross margin several points. Blocking the close for it would train
people to override the control, and an override that becomes routine is worse than no
control.

The rule is: **balancing controls block, judgement controls inform**.

## 7. Governance

| Aspect | Approach |
|---|---|
| Ownership | Every control names an accountable role, not a person — roles survive staff changes |
| Execution | Automatically, on every pipeline run. No manual controls in the critical path. |
| Evidence | Every result written to `fact_control_result` with measured value, threshold, timestamp and run ID |
| Exceptions | A blocking failure can only be overridden by the Group Financial Controller, with a recorded reason. The override is itself an audit record. |
| Trending | Control pass rates and close duration trended over time |
| Review | The register is reviewed quarterly. New failure modes get new controls. |
| Change control | The register is version-controlled and validated in CI by `tests/test_config_integrity.py` |

## 8. Controls on the Phase 1 deliverables themselves

The control framework applies to this phase too. Phase 1 ships with 152 automated tests:

| Test module | Coverage |
|---|---|
| `tests/test_anchors.py` | Every accounting identity in the anchor model: statement subtotals, balance sheet balancing, cash flow tying to cash, retained earnings roll-forward, KPI derivation, covenant headroom, entity-to-BU-to-group roll-up, FX quotation direction, and the business-narrative assertions (margin expands, leverage falls, forecast is below budget) |
| `tests/test_config_integrity.py` | Chart-of-accounts structure and flag consistency, mapping validity, ERP chart divergence, entity tree integrity and acyclicity, ownership sums, intercompany matrix referential integrity, control register well-formedness, scenario/version consistency |

Four of these tests earned their place by catching real defects — three during Phase 1 and one
during the Phase 1.1 correction pass. See `docs/phases/phase-01-report.md` §4 and
`docs/phases/phase-01-1-report.md`.

`test_config_integrity.py` additionally enforces the architectural invariants introduced at
Phase 1.1: the consolidation layer set is closed at five and agrees across the configuration,
the statutory and management formulas and every documentation reference; ownership plus NCI
sums to 100% in the effective-dated register with no overlapping or missing date ranges; the
NCI equity roll-forward accounts and the CTA roll-forward accounts both exist and are complete;
and every add-back account named in the credit agreement is flagged in the group chart.

## 9. Deferred to later phases

Some controls cannot be meaningfully specified until the data exists. These are recorded now
so they are not forgotten:

| Control area | Phase | Note |
|---|---|---|
| Journal-level anomaly detection | 9 | Round-dollar postings, weekend entries, unusual preparers |
| Segregation of duties on adjustments | 9 | Preparer ≠ approver, enforced rather than documented |
| Access and row-level security testing | 9 | Verify a BU role cannot see other entities |
| Close-cycle timing controls | 9 | Actual close duration against the target of five working days |
| Restatement detection | 5 | Alert when a closed period's figures change between runs |
| Covenant breach, waiver and equity cure reporting | 8 | Exercised by the reserved Downside scenario (`DS_FY26_STRESS`), not by the base dataset |
