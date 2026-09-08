# ADR-0019: Five ingestion layers, ERP-specific adapters, and line-level lineage

- **Status:** Accepted
- **Date:** 2026-09-07
- **Phase:** 3
- **Related:** ADR-0001 (DuckDB), ADR-0003 (consolidation layers), ADR-0007 (mapping as
  effective-dated configuration), ADR-0020 (the mapping rule language), CTL-DQ-01 to
  CTL-DQ-10, CTL-FX-06

## Context

Three source systems have to become one finance data model. They differ in encoding,
delimiter, numeric notation, date format, account-key typing, sign convention, period
structure and dimensionality — Aurora carries no cost centre and no fiscal year, Sable
carries amounts at each account's natural sign, Kestrel carries separate positive debit and
credit columns in German notation with fiscal periods running to sixteen.

Two shapes were available. A single generic parser with per-system options, or a set of
deliberate adapters. And within the transformation, a single "load and map" step, or an
explicit chain of layers.

## Decision

**Five layers, named after what has happened to the data rather than after where it sits.**

```
raw            the frozen Phase 2 native extracts. Never written by this pipeline
parsed         typed, with every native column preserved verbatim alongside. Still in each
               system's own conventions: its sign, its periods, its account keys
standardised   one canonical journal-line model. Sign, period and dimension normalised
mapped         group account attached, with the rule that produced it and a status
conformed      the finance data model: facts, dimensions and the validation views
```

The value of naming the layers this way is that a question has one place to be answered. "Is
this a locale problem or a mapping problem?" is settled by looking at which layer the number
first goes wrong in.

**One adapter per source system, and no generic parser.** Each adapter states its system's
conventions as data — encoding, delimiter, line key, native columns, the typed derivations,
and the field no downstream stage may read. A generic parser would have had to *guess* at
each of those, and a guess about a comma is a guess about a thousand.

**The parsed layer keeps every native column verbatim.** Not a subset, not a rename: the
extract as it was, alongside the typed derivations. A reviewer asking "what did the file
actually say" gets an answer without going back to the file.

**Lineage is carried on every row, not reconstructed on demand.** Every conformed row keeps
the source system, the file, its ordinal within that file, the source account and account
name as the system spelled them, the native amount before sign normalisation, the source
period as posted, the source attribute string, the journal and document identifiers, and the
line number. The declared grain is `(erp_system, source_file, journal_id, line_number)` and
it is enforced, not asserted.

`source_row_ordinal` is defined as the row's position within its file **under that ERP's own
line key**, not as a byte offset. A byte offset is not reproducible under a parallel scan;
an ordinal under a declared key is, and `P3-ING-09` proves it is dense from 1 to N in every
file.

**Amounts stay in the entity's functional currency.** The conformed fact has no USD column.
Translation is Phase 4's work (ADR-0005), and a USD column here would be an invitation to
translate twice. The reconciliation views convert at approved average rates for comparison
against the anchors, are named `vw_validation_*`, and are views rather than facts so that
nothing can join to them by accident.

**A source system's own translated amount is carried for lineage and read by nothing.**
Aurora ships `AMOUNT_USD_SYSTEM` from a deliberately stale internal rate table; Kestrel ships
`DMBTR_KONZERN_EUR` from its pre-acquisition parent's group currency. Both are on the
journal-line fact and on no aggregate, and `P3-ING-12` fails the build if one appears in
`fact_trial_balance` (CTL-FX-06).

## Alternatives considered

**One parser with a configuration table of dialect options.** Rejected. The differences are
not dialect options — Sable's sign cannot be recovered without joining the chart of accounts,
and Kestrel's period 13 is not a month. A configuration table would have grown a column per
special case until it was an adapter with worse names.

**Aggregate at ingestion, to entity × account × period.** Rejected, and it is the tempting
one: it would cut the fact from 1.08m rows to 42k and every reconciliation in this phase
would still pass. It also makes a mapping untraceable to the posting that produced it, an
elimination unmatchable to its document, and "why is this number here" unanswerable. The
aggregate exists — `fact_trial_balance` — but it is built **from** the detail, so the two
cannot disagree.

**Map straight from raw.** Rejected. It merges two failure modes that need to stay apart: a
number that is wrong because it was read wrongly, and a number that is wrong because it was
classified wrongly.

## Consequences

- A reviewer can walk any conformed row back to the byte range of a named file.
- 1,080,782 journal lines move through five layers in under a minute on a laptop, in DuckDB
  SQL, with no row-by-row Python in the transformation path.
- The layers are materialised as Parquet, so an intermediate can be inspected without
  re-running the pipeline, and the whole chain is a deterministic function of the frozen
  source layer plus committed configuration.
- The parsed layer roughly doubles the storage of the ledger, because it holds the native
  columns as text as well as typed. That is the price of being able to answer the question,
  and it is paid in a directory that is regenerated rather than committed.
