# Ingestion Design

How three deliberately different ERP extracts become one controlled finance data model, and
what is guaranteed at each step.

Phase 3 performs **no consolidation**: no elimination, no translation, no adjustment layer,
no consolidated statement. Everything it produces is layer 1 — entity as reported, in the
entity's own functional currency.

---

## 1. The layers

Named after what has happened to the data, not after where it sits (ADR-0019).

| Layer | What it is | Conventions | Written to |
|---|---|---|---|
| **raw** | the frozen Phase 2 native extracts | each source system's own | never written by this pipeline |
| **parsed** | typed, with every native column preserved verbatim beside it | still each system's own: its sign, its periods, its keys | `data/10_staging/01_parsed/` |
| **standardised** | one canonical journal-line model | debit-positive, canonical periods, conformed dimension keys | `data/10_staging/02_standardised/` |
| **mapped** | group account attached, with the rule that produced it and a status | group chart of accounts | `data/10_staging/03_mapped/` |
| **conformed** | the finance data model: facts, dimensions, validation views | the data contract | `data/10_staging/04_conformed/` and DuckDB |

The point of the naming is that a question has one place to be answered. *Is this a locale
problem or a mapping problem?* — look at the layer the number first goes wrong in.

```
data/raw/{aurora,sable,kestrel}/*.csv        507 files, 1,080,782 lines
        │  src/pipeline/adapters.py           one adapter per source system
        ▼
parsed_aurora / parsed_sable / parsed_kestrel
        │  src/pipeline/standardise.py        sign · period · dimensions · attributes
        ▼
stg_standardised                              1,080,782 rows, one canonical shape
        │  src/pipeline/harmonise.py          config-driven rule engine
        ▼
stg_mapped_enriched                           + group_account, mapping_status, rule id
        │  src/pipeline/conform.py            + subledgers.py, dimensions.py
        ▼
fact_journal_line · fact_trial_balance · 12 conformed dimensions · validation views
```

Run it with `python -m src.pipeline.run`. Controls alone: `python -m src.pipeline.controls`.

---

## 2. The source adapters

There is no generic parser. A generic parser would have to *guess* at each system's
conventions, and a guess about a comma is a guess about a thousand.

### Aurora — modern cloud ERP

| | |
|---|---|
| Encoding / delimiter | UTF-8, comma |
| Dates | ISO `2024-11-26` |
| Amounts | one signed amount, credits negative |
| Account key | four digits, read and kept as **text** |
| Entity key | `SUBSIDIARY` is the group entity code |
| Fiscal year | **absent.** Derived from the posting date |
| Cost centre | **absent.** The extract carries a department segment (`DEPT-D500`); a cost centre is resolved from entity + department |
| Trap | `AMOUNT_USD_SYSTEM` is translated on Aurora's own deliberately stale rate table. Carried for lineage, read by nothing (CTL-FX-06) |

### Sable — project ERP

| | |
|---|---|
| Encoding / delimiter | UTF-8, comma |
| Dates | US `11/28/2024` |
| Amounts | the account's **natural sign**, with US thousands separators |
| Account key | five digits, text |
| Entity key | `COMPANY` is the ERP company code (`CAS-US`), resolved through the entity master |
| Dimensions | a pipe-delimited string: `entity|department|project|partner` |
| Trap | a signed value exists only once the account's normal balance is known. It is taken from the **approved chart**, never from the extract's own `NORMALBALANCE` column — and the two are then compared (control `P3-TB-01`) |

### Kestrel — legacy European ERP

| | |
|---|---|
| Encoding / delimiter | Windows-1252, semicolon |
| Dates | German `16.12.2024` |
| Amounts | separate positive `SOLL` and `HABEN` columns, German notation: point thousands, comma decimal |
| Account key | **zero-padded eight characters**, text, always |
| Entity key | `BUKRS` is the company code |
| Periods | 1–16 |
| Cost centre | `KOSTL`, carried natively |
| Trap | `DMBTR_KONZERN_EUR` is a legacy group-currency column inherited from Halden's pre-acquisition parent. Carried for lineage, read by nothing (CTL-FX-06) |

`P3-ING-07` proves the eight-character keys keep their leading zeros and that none has been
coerced to a number at any stage. A key silently narrowed to `12000` cannot be joined back to
`00012000`, and nothing else in the pipeline would notice.

### The numeric grammar

Each adapter knows its system's number format, so each adapter can also state it as a
grammar. `P3-ING-13` validates every raw amount string against an anchored regular expression
**before it is cast**:

| ERP | Grammar | Accepts | Rejects |
|---|---|---|---|
| Aurora | `-?[0-9]+(\.[0-9]{1,2})?` — no grouping at all | `-4218.50` | `4,218.50`, `4218,50` |
| Sable | `-?[0-9]{1,3}(,[0-9]{3})*(\.[0-9]{1,2})?` | `1,306,803.00` | `1.306.803,00` |
| Kestrel | `-?[0-9]{1,3}(\.[0-9]{3})*(,[0-9]{1,2})?` | `13.068,03`, `218,50` | `13.068.03`, `4218,50` |

Each is exactly what its system emits, not a superset. Kestrel always writes its grouping
separator, so an ungrouped `4218,50` is a corruption in its own right — a lost point rather
than a lost thousand — and the grammar says so.

This exists because a malformed amount is not a null. `13.068,03` mistyped as `13.068.03`
parses cleanly — as 1,306,803, a hundredfold overstatement — and if both legs of the entry are
affected it still balances. Completeness and null controls are structurally blind to it. The
grammar is the only place the error is visible, and it is visible at the point of entry rather
than three layers downstream as an inexplicable variance.

The clean source layer has **zero** non-conforming amounts across all 1,080,782 lines, so the
control's threshold is its natural one.

---

## 3. Sign normalisation

The canonical convention is stated **once**, in `src/pipeline/config.py`:

> `signed_local_amount` is **DEBIT-POSITIVE**. An asset or an expense carries a positive
> balance; a liability, equity item or revenue carries a negative one. A trial balance sums
> to zero.

Each adapter is responsible for recovering it from its own system:

| System | Recovery |
|---|---|
| Aurora | already signed; used as given |
| Kestrel | `SOLL − HABEN` |
| Sable | `AMOUNT × (+1 if the chart says the account is debit-normal, else −1)` |

Nothing infers a sign from how a statement is presented. `P3-TB-06` then proves no class was
inverted, testing the **closing balance** of a balance sheet account and the **year's total**
for an income statement account — because a balance sheet account's movement in a year is
legitimately either way round while its balance is not. Contra accounts and genuinely
bidirectional accounts (an intercompany current account is a receivable one month and a
payable the next) are **named** and excluded, never inferred.

This is also where money stops being a float. Every source amount is exact to the cent, and
a parallel `SUM` over `DOUBLE` adds its partial results in whatever order the threads happen
to finish in — so the same ledger can total to a different last bit from one run to the next.
The standardised layer casts to `DECIMAL(18,2)` (ADR-0022), at the same point it commits to a
sign; the parsed layer above keeps whatever the file said.

---

## 4. Period normalisation

Three concepts, kept apart rather than collapsed:

| Field | Meaning | Range |
|---|---|---|
| `accounting_period` | what the source system posted to | 1–12, or 13–16 at Kestrel |
| `management_period` | the calendar month a reader sees | always 1–12 |
| `special_period_type` | what a 13–16 posting *is* | four named types |

| Period | German | Type | Reports in |
|---|---|---|---|
| 13 | *Abschlussbuchungen* | `STATUTORY_CLOSE` | December |
| 14 | *Prueferbuchungen* | `AUDIT_ADJUSTMENT` | December |
| 15 | *Steuerbuchungen* | `TAX_ADJUSTMENT` | December |
| 16 | *Konzernanpassungen* | `GROUP_REPORTING_ADJUSTMENT` | December |

A special period is part of the December close, so its management period is 12 and
`is_adjustment_period` is true. Keeping the two apart is the only thing that stops a
thirteenth month appearing in a chart (`P3-ING-11`) while keeping the adjustment identifiable
all the way through (`P3-ING-10`, CTL-DQ-07).

`P3-ING-06` separately proves that a posting date parses **and** falls inside its own
accounting period — special periods excepted, since they carry a December date by design.

---

## 5. Lineage

Every conformed row carries what is needed to get back to the extract:

`erp_system` · `source_file` · `source_row_ordinal` · `source_entity_key` ·
`source_account` · `source_account_name` · `source_period_raw` · `source_native_amount` ·
`source_normal_balance_declared` · `source_line_attributes` · `source_translated_amount` ·
`journal_id` · `document_id` · `line_number` · `source_event_type` · `source_description` ·
`ingest_build_id`

The declared grain is `(erp_system, source_file, journal_id, line_number)`, condensed into
`line_uid` and **enforced** (`P3-ING-08`, `test_the_conformed_fact_holds_its_declared_grain`).

`source_row_ordinal` is the row's position within its file under that ERP's own line key —
not a byte offset, which is not reproducible under a parallel scan. `P3-ING-09` proves it runs
1..N in every file, so a dropped row is visible.

---

## 6. The group adjustment boundary

The architecture distinguishes three things a single "adjustment" column would blur:

| | What it is | Where it lives | Who writes it |
|---|---|---|---|
| a source posting | something an entity's own ledger says | `fact_journal_line`, layer 1 | ingestion |
| a mapping reclassification | the same amount under a different group caption | `fact_journal_line`, with `mapping_rule_id` and `is_presentation_reclass` | the mapping engine |
| a group adjustment | an amount that exists only on consolidation | `stg_group_adjustment`, layer 3 or 4 | the consolidation engine, in Phase 4 |

`stg_group_adjustment` is created with its full schema and is **empty by design**.
`P3-ADJ-01` fails the build if Phase 3 ever writes to it, and `P3-ADJ-02` proves the pipeline
produces layer 1 and nothing else.

The worked example is the operating lease right-of-use asset. The Kestrel entities do not
recognise one in their local books, so Kestrel's special period 16 has nothing to reclassify.
The group figure is carried entirely by the other entities, so nothing is in fact missing —
but if a later phase needs to raise a top-side entry, this is the table, at the consolidation
layer, posted by the consolidation engine, never by ingestion.

---

## 7. Determinism and performance

Every stage is a deterministic function of the frozen source layer and the committed
configuration. The build id is the SHA-256 of the Phase 2 dataset digest plus the mapping
configuration, the four charts and the entity master — **not** a timestamp, because a clock
value in a committed manifest leaves the working tree dirty after every run and destroys the
reproducibility it was meant to record. Wall-clock duration is printed and never written.

The transformation path is DuckDB SQL end to end. There is no row-by-row Python: the
mapping engine evaluates every rule in a single pass by joining the ledger to the rule set on
(ERP, source account) and evaluating one `CASE` over the rule id, so a line only ever
evaluates the handful of branches that belong to its own account.

| Stage | Seconds |
|---|---|
| parsed | ~22 |
| dimensions | ~0.2 |
| standardised | ~21 |
| mapped | ~43 |
| subledgers | ~3 |
| conformed | ~9 |
| reconciliation and acceptance | ~11 |
| **total** | **~110 s for 1.08m lines on a laptop** |

The 61 controls run separately against the built warehouse and take about 2.4 s.

`data/phase03_manifest.json` records the build id, the frozen source digest, every row count,
the mapping acceptance result and a SHA-256 per artefact.
