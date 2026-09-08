# The Chart-of-Accounts Harmonisation Engine

The core Phase 3 deliverable. Three source charts, 392 source accounts, one group chart of
188, and a set of conditional rules that a lookup table cannot express.

See ADR-0007 (mapping as effective-dated configuration) and ADR-0020 (the rule language).

---

## 1. The problem a lookup cannot solve

Aurora books **all** payroll to one account, `6100 Salaries and Wages`, whether the labour is
direct production, indirect operations or SG&A. Gross margin is therefore not derivable from
the Aurora account code at all — the department segment is mandatory:

```
6100  →  515100  Direct labour - production          D100
      →  515200  Direct labour - field and project   D200 D205 D300 D305 D310
      →  520100  Overhead - indirect labour          D105 D110 D115 D120 D210 D215
      →  610100  Salaries and wages                  everything else
```

Get it wrong and every balancing control still passes. The trial balance sums to zero, the
statements tie, the eliminations net — and gross margin moves by three points. That is why
`P3-REC-06` exists (§6) and why fault fixture F08 tests exactly this.

### Where the accepted values are a set

An approved rule frequently accepts several values, not one. Kestrel's temporary-staff
account reaches cost of sales from a `PRODUCTION`, `FIELD` **or** `PROJECT` cost centre. The
generator has to satisfy the same contract from the other side, so the manifest records the
accepted **set** and the posting declares whichever member the entity actually has. Naming
one of them forced a services entity with no manufacturing to declare `PRODUCTION`, which is
half of what defect P2-D-02 was.

The other half was a wrong value in a lookup: `D210 Equipment & Fleet` and `D215 Field Safety
& Compliance` were classified as `FIELD` when they are support departments, which the
approved Aurora split had always said by grouping them with the other indirect-operations
departments. `SAB-60700-10` was expressed on the department **function** because, under the
wrong classification, the function happened to select exactly the department set the chart
enumerates. It no longer does, so the rule is expressed on the department set the chart
actually names. A rule written on a proxy for its criterion breaks silently when the proxy
stops holding.

F08 is also the reason `P3-REC-06` is set at one basis point rather than the 0.05 percentage
points it started at. The fixture moves eight payroll postings across the line *consistently* —
the line attributes and the cost centre agree with each other, so the posting looks correct
from every direction — and shifts group gross margin by 0.047pp. Under the original tolerance
it was invisible. The clean pipeline reproduces every business unit's margin at exactly
0.000000, so a tolerance here has nothing legitimate to absorb and any slack above zero is
blindness.

Kestrel has the same problem for a different reason: a German nature-of-expense chart
classifies by *what was bought*, not *why*, so `00091000 Loehne und Gehaelter` carries the
same four-way split and it is the cost centre that resolves it.

---

## 2. What the engine supports

| Mapping | Meaning | Where the decision lives | Count |
|---|---|---|---|
| `DIRECT` | one source account, one group account | the approved source chart | 314 accounts |
| `MERGE` | several source accounts collapse into one group account | the approved source chart | 25 accounts |
| `SPLIT` | one source account maps differently depending on the individual posting | `config/mapping/mapping_rules.csv` | 51 accounts, 125 rules |
| `DERIVED` | a presentation reclassification, because the local ledger reports on a different basis | `config/mapping/mapping_rules.csv` | 2 accounts, 2 rules |

Conditions may test:

**Context fields** — native or dimension-resolved: `erp_system`, `entity_code`, `bu_code`,
`country_code`, `source_account`, `dept_code`, `cost_center_code`, `dept_function`,
`partner_entity_code`, `source_currency`, `document_type`, `source_event_type`.

**Line attributes** — what the posting itself declares, parsed out of the source system's own
attribute field: `asset_class`, `instrument_type`, `partner_bu`, `maturity_months`,
`product_group`, `income_type`, `presentation`, `advisor_type`, `expense_subtype`,
`cost_type`, `accrual_type`, `vendor_category`, `tax_jurisdiction`, `revaluation_flag`,
`reimbursable_type`, `project_code`, `cost_center_function`, `dept_function`, `dept_code`.

A field outside those two lists is rejected when the rule set loads and the build stops.

---

## 3. The rule language

```
condition   := clause { ' AND ' clause }
clause      := 'TRUE'
             | field op literal
             | field 'IN' '(' literal { ',' literal } ')'
             | field 'NOT IN' '(' literal { ',' literal } ')'
             | field 'IS NULL' | field 'IS NOT NULL'
op          := '=' | '<>' | '<=' | '>=' | '<' | '>'
literal     := "'" text "'" | number
```

Conditions are **parsed and re-emitted** as SQL, never interpolated. A literal cannot carry a
predicate, a field cannot name a subquery, and a numeric comparison on a text attribute goes
through `TRY_CAST` so that a non-numeric value fails to match rather than failing the build.

A worked example, `config/mapping/mapping_rules.csv`:

| rule_id | source_account | priority | condition | target | class |
|---|---|---|---|---|---|
| `AUR-6100-10` | 6100 | 10 | `dept_code IN ('D100')` | 515100 | SPLIT_BRANCH |
| `AUR-6100-20` | 6100 | 20 | `dept_code IN ('D200','D205','D300','D305','D310')` | 515200 | SPLIT_BRANCH |
| `AUR-6100-30` | 6100 | 30 | `dept_code IN ('D105','D110','D115','D120','D210','D215')` | 520100 | SPLIT_BRANCH |
| `AUR-6100-99` | 6100 | 999 | `TRUE` | 610100 | SPLIT_DEFAULT |

Each row also carries its **basis** — the chart narrative it was authored from — and, where
the two differ, a note saying why (ADR-0020 §"Where the prose and the mapping contract
differ").

### Field resolution is attribute-first

Where a posting declares its own classification, the source system is stating something about
that line, so the declared attribute wins and the posted dimension is the fallback:

```
dept_function = coalesce(attr dept_function, attr cost_center_function,
                         cost centre's function, department's function)
dept_code     = coalesce(attr dept_code, the posted department segment)
```

`P3-MAP-12` reports every line where the two disagree. There are 5,710 — source defect
P2-D-02, reported and not patched.

---

## 4. How a line is resolved

```
                    ┌── the source account is not in the ERP's chart ──→ UNMAPPED_ACCOUNT
                    │
                    ├── no mapping row effective at the posting date ──→ OUT_OF_EFFECT
                    │
a standardised line ┼── entity or cost centre does not resolve ────────→ INVALID_DIMENSION
                    │
                    ├── more than one non-default branch matched ──────→ AMBIGUOUS
                    │
                    ├── a DERIVED rule fired ──────────────────────────→ MAPPED_DERIVED
                    ├── a SPLIT_BRANCH fired ──────────────────────────→ MAPPED_SPLIT
                    ├── the SPLIT_DEFAULT fired ───────────────────────→ MAPPED_SPLIT_DEFAULT
                    ├── a conditional account matched nothing ─────────→ UNMAPPED_NO_RULE
                    ├── the chart says MERGE ──────────────────────────→ MAPPED_MERGE
                    └── otherwise ─────────────────────────────────────→ MAPPED_DIRECT
```

Every line ends with exactly one status. **Nothing is defaulted silently**: a split's default
branch is a declared rule with a rule id, not an `else` in code, and `P3-MAP-06` fails the
build if a conditional account has none.

### Ambiguity is an exception, not something priority resolves

If two non-default branches match, the line is `AMBIGUOUS` and blocks. Taking the
higher-priority match would make two overlapping rules look like one working rule until
somebody checked.

### The exception file

Blocking statuses are written to `data/10_staging/exceptions/mapping_exceptions.csv` with
what an investigator actually needs:

`mapping_status` · `erp_system` · `entity_code` · `source_account` · `source_account_name` ·
`mapping_type` · `fiscal_year` · `accounting_period` · `line_count` ·
`absolute_amount_local` · `source_currency` · an example file, journal, attribute string,
department, cost centre and function · `candidate_rules` · `resolution_guidance`

On the clean baseline it has **no rows**.

---

## 5. The German total-cost-method reclassification

Kestrel reports on the *Gesamtkostenverfahren*. Two accounts sit **above** the revenue line
as part of `Gesamtleistung`:

```
Umsatzerlöse                       1,000
+ Bestandsveränderung  00081000       50     ← movement in finished goods
+ Aktivierte Eigenleistungen 00081200 20     ← own work capitalised
= Gesamtleistung                   1,070
− Materialaufwand                   (600)
− Personalaufwand                   (300)
```

Under the group's cost-of-sales presentation both belong **inside cost of sales**:

```
Revenue                            1,000
− Cost of sales                     (880)   = 600 + 300 − 50 − 20
= Gross profit                        120
```

**What reverses is the caption, not the number.** A credit stays a credit; what changes is
that it stops adding to *Gesamtleistung* and starts reducing cost of sales. In a
debit-positive signed model that happens automatically once the amount lands on a cost-of-sales
account, which is why:

- the mapped trial balance still sums to zero (`P3-TB-03`) — no amount moved;
- net income is unchanged — the reclassification is within the P&L;
- gross margin becomes economically correct — which it is not if the items stay in revenue;
- and the source presentation stays visible: the line keeps `00081000`, its German name
  *Bestandsveraenderung*, `is_presentation_reclass = TRUE` and
  `presentation_reclass_type = 'GKV_TO_UKV'`.

`P3-MAP-10` proves every one of these postings reaches cost of sales and none is left in the
revenue block; `P3-MAP-11` proves each is flagged and traceable. This is CTL-MAP-08.

Leaving them in revenue would overstate both revenue and gross margin for the three Kestrel
entities, and every balancing control would still pass.

---

## 6. Acceptance

Two different questions, answered separately.

### Did the engine produce the right answer?

Phase 2 recorded, for every generated journal line, the group account a Phase 3 mapping is
expected to produce. That expectation is an **oracle**: `reconcile.py` reads it to grade the
engine, and no transformation stage may. `test_the_manifest_is_an_oracle_and_never_an_input`
inspects the stage modules and asserts the separation, because a perfect score against a file
the engine can read would mean nothing.

| Population | Lines | Exact matches | Agreement |
|---|---|---|---|
| **Classifiable at source** | 1,013,640 | 1,013,640 | **100.000000%** |
| Not classifiable at source | 67,142 | 66,976 | 99.752763% |
| All lines | 1,080,782 | 1,080,616 | 99.984641% |

A line is *classifiable at source* when its account maps unconditionally, or when the posting
declares at least one of the attributes its account's rule set reads. A line that is not
carries nothing the engine could have used, so the split resolves to the account's declared
default branch. All 166 disagreements are in that second population and every one of them is
source defect P2-D-01 — see `docs/phases/phase-03-report.md` §12.

Unmapped: **0**. Ambiguous: **0**.

### Do the mapped numbers mean anything?

A mapping can be wrong and still balance, so the mapped result is reconciled to the approved
anchors at the level where such an error shows. See
[`source-to-group-reconciliation.md`](source-to-group-reconciliation.md).

---

## 7. Group accounts with no source

`rpt_group_account_coverage` answers CTL-MAP-06: which group accounts received nothing, and
whether that is expected.

| Status | Meaning |
|---|---|
| `POSTED` | received postings |
| `CREATED_BY_TRANSLATION` | the 33x CTA block: created at layer 5, correctly empty here |
| `CREATED_BY_CONSOLIDATION` | goodwill, acquired intangibles, PPA deferred tax, the 34x NCI block, the NCI income allocation |
| `STATISTICAL_NOT_IN_LEDGER` | statistical accounts, outside the trial balance by design |
| `MAPPED_BUT_UNUSED` | a source account maps here and never posted in the period |
| `NO_SOURCE_ACCOUNT_MAPS_HERE` | nothing in any source chart reaches it |

The distinction is the point: an account that is empty because translation creates it is not
the same problem as an account a source chart maps to and never fills.
