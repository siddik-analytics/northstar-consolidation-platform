# Control Framework

**71 controls across 10 categories.** The full machine-readable register is
[`config/controls/control_register.csv`](../config/controls/control_register.csv); this
document explains the design.

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
| `BLOCKING` | 56 | Pipeline halts. Nothing downstream is published. The period does not close. |
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
| `FIN_STATEMENT` | 8 | 4–5 | The three statements are internally consistent and tie to each other |
| `FX` | 8 | 3–5 | Translation is correct and CTA is derived rather than plugged |
| `INTERCOMPANY` | 8 | 3–4 | Intercompany activity is identified, matched and eliminated |
| `CONSOLIDATION` | 8 | 4 | Scope, ownership, NCI and adjustments are right |
| `SCENARIO` | 5 | 5 | Budget and forecast are complete, locked and comparable |
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
  TRANSLATE ────► CTL-FX-01..07, CTL-TB-03     rates complete, CTA derived, balances in USD
        │
  ELIMINATE ────► CTL-IC-01..08                IC matched, eliminations balance
        │
  CONSOLIDATE ──► CTL-CON-01..08               scope, ownership, NCI, adjustments
        │
  DERIVE CF ────► CTL-FS-01..08                statements tie to each other
        │
  PUBLISH ──────► CTL-SCN-*, CTL-REC-*, CTL-BR-*  completeness, traceability, sense
```

Controls run **at the point of the transformation they protect**, not in a batch at the end.
A trial balance failure detected at ingestion costs minutes to fix; the same failure
detected after consolidation costs a day of bisecting.

## 5. The controls that matter most

Seventy-one controls is a lot to hold in your head. These eight are the ones that would
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

Three of these tests earned their place during Phase 1 by catching real defects — see
`docs/phases/phase-01-report.md` §4.

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
