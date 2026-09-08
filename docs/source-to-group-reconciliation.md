# Source-to-Group Reconciliation

The evidence that the mapping worked. A mapping can be wrong and still balance, so
"everything ties" is not a result — these are the specific reconciliations that would break
if it did not.

Everything below is **layer 1**: entity as reported, both legs of every intercompany
transaction present, nothing eliminated, nothing consolidated. These are **not** financial
statements and are named `vw_validation_*` and `rec_*` so that they cannot be mistaken for
one. The USD figures are produced by applying the approved monthly average rates (income
statement) and closing rates (balance sheet) for comparison only: no cumulative translation
adjustment is computed, nothing is posted, and no translated fact is stored. Translation is
Phase 4's work (ADR-0005).

Machine-readable output: `data/phase03_reconciliation.csv`.

---

## 1. Mapping acceptance

Phase 2 recorded, per line, the group account a Phase 3 mapping should produce. That file is
an **oracle**: it is read by the acceptance test and by nothing in the pipeline
(ADR-0020, `test_the_manifest_is_an_oracle_and_never_an_input`).

| Population | Lines | Exact matches | Mismatches | Agreement |
|---|---|---|---|---|
| **Classifiable at source** | 1,013,640 | 1,013,640 | 0 | **100.000000%** |
| Not classifiable at source | 67,142 | 66,976 | 166 | 99.752763% |
| **All lines** | 1,080,782 | 1,080,616 | 166 | 99.984641% |

| | |
|---|---|
| Unmapped | **0** |
| Ambiguous | **0** |
| Invalid dimension | **0** |
| Out of effect | **0** |

Every one of the 166 disagreements is in the second population, where the source system
supplied no attribute the rule could read. All 166 are source defect **P2-D-01** — see
`docs/phases/phase-03-report.md` §12. Detail: `data/phase03_mapping_acceptance.csv`.

---

## 2. Group income statement

Against `config/anchors/phase02_source_layer_targets.csv`, which is the approved consolidated
anchor bridged to what the sum of the source ledgers must say — intercompany grossed up,
Phase 4 constructs removed. Tolerance 0.5%, unchanged from Phase 2 and not relaxed.

| USD m | FY2023 | FY2024 | FY2025 |
|---|---|---|---|
| **Revenue** mapped | 365.780 | 415.774 | 462.635 |
| target | 365.780 | 415.774 | 462.635 |
| deviation | **0.000000%** | **0.000000%** | **0.000000%** |
| **Cost of sales** mapped | 265.560 | 300.726 | 332.555 |
| target | 265.560 | 300.726 | 332.555 |
| deviation | **0.000000%** | **0.000000%** | **0.000000%** |
| **Operating expense** mapped | 70.980 | 76.074 | 78.735 |
| target | 70.980 | 76.074 | 78.735 |
| deviation | **0.000000%** | **0.000000%** | **0.000000%** |

---

## 3. Gross margin by business unit — the control that matters

This is the reconciliation that catches a mapping which is wrong but still balances. Move
production payroll from cost of sales into SG&A and every trial balance still sums to zero,
every statement still ties, every elimination still nets — and the margin moves. Fault
fixture F08 does exactly that, and this is the control that finds it.

Computed on **external** revenue and cost, which is the basis the business-unit anchor is
stated on.

| FY | BU | Revenue mapped / target | Gross profit mapped / target | Margin mapped / target | Variance |
|---|---|---|---|---|---|
| 2023 | FC | 124.000 / 124.000 | 40.300 / 40.300 | 32.500% / 32.500% | **0.000000** |
| 2023 | IS | 101.500 / 101.500 | 21.315 / 21.315 | 21.000% / 21.000% | **0.000000** |
| 2023 | ES | 55.000 / 55.000 | 10.175 / 10.175 | 18.500% / 18.500% | **0.000000** |
| 2023 | AM | 47.500 / 47.500 | 19.950 / 19.950 | 42.000% / 42.000% | **0.000000** |
| 2024 | FC | 141.000 / 141.000 | 47.094 / 47.094 | 33.400% / 33.400% | **0.000000** |
| 2024 | IS | 113.000 / 113.000 | 24.408 / 24.408 | 21.600% / 21.600% | **0.000000** |
| 2024 | ES | 65.400 / 65.400 | 11.772 / 11.772 | 18.000% / 18.000% | **0.000000** |
| 2024 | AM | 52.000 / 52.000 | 22.100 / 22.100 | 42.500% / 42.500% | **0.000000** |
| 2025 | FC | 156.600 / 156.600 | 53.244 / 53.244 | 34.000% / 34.000% | **0.000000** |
| 2025 | IS | 123.600 / 123.600 | 27.192 / 27.192 | 22.000% / 22.000% | **0.000000** |
| 2025 | ES | 74.200 / 74.200 | 14.098 / 14.098 | 19.000% / 19.000% | **0.000000** |
| 2025 | AM | 57.700 / 57.700 | 24.811 / 24.811 | 43.000% / 43.000% | **0.000000** |

Twelve business-unit-years, exact. `P3-REC-06` fails above **0.01** percentage points — one
basis point.

The threshold started at 0.05pp and was tightened here, because the original was the defect.
F08 re-tags eight payroll postings from a production department to an SGA one *consistently*:
the line attributes and the cost centre agree with each other, so nothing in the posting looks
wrong and no dimensional control can object. It moves group gross margin by 0.047104pp — under
0.05, and therefore invisible.

A tolerance is supposed to absorb something. This one has nothing to absorb: the mapping is
deterministic, the target is the source data itself, and every clean business-unit-year comes
out at exactly 0.000000. Any slack above zero is pure blindness. One basis point sits a factor of five below the fault it must
catch and many orders of magnitude above floating-point noise on figures of this size.

---

## 4. External revenue by entity

Against `config/anchors/anchor_by_entity.csv`, eleven operating entities × three years.

**Worst variance: 0.000000 USD m.** `P3-REC-07`.

---

## 5. Balance sheet, at closing rates

Two comparisons, because they answer different questions. `mapped` is what the pipeline
produced; `oracle` is the same balance built from the group account Phase 2 said each line
should carry. Where the two agree, the **mapping** is right and any remaining variance
against the anchor is a property of the source data.

| FY2025, USD m | mapped | oracle | mapping variance | target | variance vs target |
|---|---|---|---|---|---|
| cash | 22.000 | 22.000 | 0.000 | 22.000 | (0.000) |
| trade receivables | 65.479 | 65.479 | 0.000 | 65.484 | (0.006) |
| inventory | 40.803 | 40.803 | 0.000 | 40.803 | (0.000) |
| property, plant and equipment | 95.200 | 95.200 | 0.000 | 95.200 | 0.000 |
| trade payables | 40.103 | 40.103 | 0.000 | 40.103 | 0.000 |
| revolving credit facility | 19.518 | 19.518 | 0.000 | 19.518 | 0.000 |
| term loan, gross | 226.600 | 226.600 | 0.000 | 226.600 | 0.000 |
| **contract assets** | 6.567 | 8.901 | **(2.334)** | 8.901 | (2.334) |
| **prepayments** | 10.576 | 8.242 | **2.334** | 8.242 | 2.334 |
| accrued liabilities | 22.792 | 22.792 | 0.000 | 22.666 | 0.126 |
| income taxes payable | 2.347 | 2.347 | 0.000 | 2.473 | (0.126) |

Two findings, both in the source layer and both reported rather than patched:

- **contract assets / prepayments** — the only captions where the pipeline differs from the
  oracle. Seven Kestrel postings to `00017000 Aktive Rechnungsabgrenzung` carry no
  `accrual_type`, so the split resolves to its default branch and $2.33m sits in prepayments
  instead of contract assets. Source defect **P2-D-01** (`P3-REC-03`).
- **accrued liabilities / income taxes payable** — mapping variance **nil**: the pipeline and
  the oracle agree exactly. The variance is against the *anchor*, and it is caused by Kestrel
  special period 15 moving $0.126m from `218100` to `219100`, which crosses an anchored
  caption boundary. Source defect **P2-D-04** (`P3-REC-11` reports it; the balance sheet
  control excludes the four captions and holds every other one to 1.0%).

Every other caption reconciles exactly. `P3-REC-04` covers them at the approved 1.0%
tolerance.

---

## 6. Revenue detail to the general ledger

ADR-0008 keeps customer and product detail in its own fact at a finer grain than the GL, and
the whole point of that decision is that the two tie. Customer and product columns are **not**
pushed into the journal-line fact — the customer reference stays on the line for lineage, the
measures do not.

Reconciled at entity × period, 507 combinations.

**Worst variance: 0.00 local currency.** `P3-REC-05`.

---

## 7. Trial balances

| Control | What it proves | Worst | Threshold |
|---|---|---|---|
| `P3-TB-01` | the native trial balance closes in each ERP's own convention, re-derived from the parsed layer | 0.0000 | 0.02 |
| `P3-TB-02` | it still closes after sign normalisation | 0.0000 | 0.02 |
| `P3-TB-03` | it still closes after mapping | 0.0000 | 0.02 |
| `P3-TB-05` | mapping changed no amount, line for line | 0.000000 | 0.005 |
| `P3-REC-01` | source amounts survive standardisation, by absolute value per ERP | 0.0000 | 0.01 |
| `P3-REC-08` | `fact_trial_balance` ties to `fact_journal_line` | 0.0000 | 0.02 |

The aggregate is built **from** the detail rather than alongside it, so the last of these
cannot silently drift.

---

## 8. Planning data

| | |
|---|---|
| Versions conformed | `BUD_FY26_V1`, `FC_FY26_02`, `FC_FY26_05`, `FC_FY26_08` |
| Superseded forecasts | retained — a forecast that has been replaced is still the forecast that was approved at the time |
| Reserved Downside `DS_FY26_STRESS` | **0 rows** (CTL-SCN-06) |
| Prior Year | **not materialised** — derived by date offset from Actual (ADR-0004) |

`P3-REC-09` and `P3-REC-10`.
