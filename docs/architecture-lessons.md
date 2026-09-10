# Architecture lessons

Fourteen defects found across Phases 2 to 6 that a balancing control could not have caught, and
the design change each one produced.

They share a shape. Every one of them **balanced**. The trial balance closed, the journal
summed to zero, the statement footed, and the number was wrong. That is the failure mode this
platform is built against, because it is the failure mode that survives a review: a reviewer
checks that it balances, it does, and the review ends.

The last two did not even need the number to be wrong. They balanced, footed, tied and
reconciled — and still could not say which project bought which asset, or what version half the
reporting rows belonged to.

Each entry: **symptom → root cause → why ordinary controls miss it → permanent fix**.

---

## 1. The measurement reserve — a residual with a name

**Symptom.** The consolidated balance sheet balanced because a "source-layer measurement
reserve" in equity absorbed whatever was left over.

**Root cause.** The layer-1 equity bridge did not reconstruct group equity from its components,
so the difference was posted to a reserve. The reserve was documented, disclosed, and still a
plug.

**Why controls miss it.** They cannot. A plug guarantees the balancing control passes — that is
its purpose. Every control was green precisely *because* the defect existed.

**Permanent fix.** [ADR-0016](adr/0016-source-layer-measurement-reserve.md) was **superseded by
[ADR-0017](adr/0017-layer-1-equity-bridge-and-derived-cta.md)**: equity is reconstructed from
contributed capital, retained earnings, the result and a **derived** CTA, and the reserve was
deleted. A named residual is still a residual; the fix is to compute the thing the residual was
standing in for.

## 2. Historical equity retranslated

**Symptom.** CTA drifted from the independent expectation.

**Root cause.** Contributed capital was being retranslated at each period's closing rate.
Share capital does not change because a spot rate moved.

**Why controls miss it.** The balance sheet still balances — the difference goes into CTA,
which is a residual and absorbs anything handed to it. The only way to see it is to derive CTA
independently and compare.

**Permanent fix.** Translation is driven by `dim_account.fx_method` rather than by a code list,
and `P4-FX-03` asserts no `HIST` account is ever translated at a closing rate. Fixture F4-05
injects it.

## 3. Revolver interest on a plausible average balance

**Symptom.** Interest expense was internally consistent and did not match the debt schedule.

**Root cause.** Interest was priced off an assumed average utilisation rather than off actual
daily drawings.

**Why controls miss it.** Interest computed from an assumption is arithmetically perfect. There
is nothing internally inconsistent about it. It is wrong only against a fact that the model did
not hold.

**Permanent fix.** [ADR-0018](adr/0018-revolver-utilisation-and-interest.md) — a daily
utilisation model generates the drawings, and interest is computed from them. The lesson
generalises: a derived figure should be derived from the thing it depends on, not from a
summary of it.

## 4. An investment relationship that existed everywhere except the ledger

**Symptom.** The consolidation engine found a register relationship with nothing to eliminate:
NIG-500's USD 16.9m investment in NIG-510 was in the register, in the roll-forward, and in no
ledger.

**Root cause.** The opening-balance decomposition filtered on entities live at the opening date
under a consolidated view, where the balance carries what the *parent* held.

**Why controls miss it.** `P2-INV-01` iterated the **investments the ledgers contained**. Every
investment that existed was correct, so the control passed while an entire relationship was
missing. A control built that way can only find a wrong row; it is structurally incapable of
finding a missing one — and the trial balance still closed because the retained-earnings plug
absorbed the 16.9m.

**Permanent fix.** `P2-INV-01` was rebuilt to iterate the **register** — all 463
relationship-periods — classifying each as present, missing, wrong amount, wrong relationship,
duplicated or early. And a general assertion was added to the generator: a decomposition must
sum to the balance it decomposes, which makes the whole class impossible rather than this
instance.

## 5. The wrong opening rate for an entity on the window boundary

**Symptom.** CTA agreed with the independent expectation for 242 of 243 entity-periods.

**Root cause.** `historical_rates()` selected with `period_key < 202301`. An entity effective
**on** 1 January 2023 matched nothing and fell through to January's closing rate, 1.23412,
instead of the FY2022 anchor, 1.2083.

**Why controls miss it.** The opening balance sheet balanced at the wrong rate exactly as well
as it would have at the right one. One entity, one period, every structural control green.

**Permanent fix.** The boundary is expressed as a **date** and is **inclusive**:
`if eff <= WINDOW_OPENS`. A boundary written as `<` over an integer period key cannot express
"on the boundary", and the entity sitting exactly on it is the one nobody tests.

## 6. Controls that iterate the data instead of the authority

**Symptom.** Two separate phases lost to the same shape of defect — `P2-IC-01` walked the
intercompany lines that already carried a counterparty; `P2-INV-01` walked the investments the
ledgers already held. Neither could fail.

**Root cause.** The control's population was the output being tested rather than the record
that requires the output to exist.

**Why controls miss it.** They *are* the thing that misses it. This is a defect in control
design, and no amount of running them finds it. Only a fixture that removes a required row
does — which is why Phase 4A found four more of them by running nineteen deliberately broken
builds.

**Permanent fix.** The rule was written down and applied to every Phase 4 control:

> **Controls iterate from the authority that requires the data, not from the data being
> tested.**

Ownership register → ownership paths. Investment register → ledger investments. IC relationship
population → pair reconciliation. FX policy → required rates. IC transaction population → PUP
completeness.

## 7. A balance sheet caption presented twice

**Symptom.** The consolidated balance sheet was out by 41.6m, then 12.9m, then balanced.

**Root cause.** Three separate faults in one artefact: the period-result line excluded the
year-end close, so every closed year was counted twice; the dense caption spine resolved
`account_class` and `sort_order` **per period**, so a caption whose accounts moved in different
months appeared under two sort orders and was summed twice; and captions with no movement in a
month were dropped, so the running sum lost them.

**Why controls miss it.** The first two produce a balance sheet that is out — those were
visible. The third does not: a caption dropped from the running sum takes its balance with it
and the statement still foots, just with goodwill missing from December.

**Permanent fix.** The caption spine is resolved **once** for the whole statement, densified
across every month, and keyed by caption **and account class**. `P4-BS-02`, `P4-BS-03` and
`P4-BS-05` each guard one of the three.

## 8. NCI attributed from an intercompany elimination

**Symptom.** The minority's share of result came out five times the approved anchor, in the
wrong direction.

**Root cause.** The attribution base included layer 2. An intercompany elimination removes a
matched pair and changes group profit by nothing; attributing the buyer's half to the buyer
without the seller's half to the seller handed NIG-510 its purchases for free — its own result
of USD (0.78)m became +4.71m.

**Why controls miss it.** Nothing is out of balance. The elimination is correct; the
*attribution* of half of it is not, and total equity is unchanged either way. Only a comparison
against an independently formed expectation shows it.

**Permanent fix.** The base is layer 3 only, tested by
`tests/test_phase04a_proof_gate.py::test_the_nci_base_excludes_intercompany_eliminations`. The
episode also exposed that the approved anchor itself had never been derived — see
[ADR-0025](adr/0025-the-entity-ledger-supersedes-the-phase-1-nci-estimate.md) and
[`nci.md`](nci.md).

## 9. Translation counted twice in the cash flow

**Symptom.** The cash flow missed by 13.95m, then 2.07m, then 3.56m, then 0.08.

**Root cause.** The cumulative translation accounts carry `cash_flow_category = 'OP_NONCASH'`
in the approved chart. Excluding them from financing alone left them inside operating, so the
translation was removed once and counted once. The final 0.08 was different: the year-end close
carries a few cents of translation that the trial balance absorbs into CTA, and excluding both
sides of the close stranded it.

**Why controls miss it.** A cash flow derived from balance sheet movements ties **by
construction** whenever the categories partition the balance sheet. The tie is not evidence.
Only a control on the partition itself, and a separate one distinguishing the FX effect on cash
from CTA, can see a mis-categorisation.

**Permanent fix.** Translation accounts are mapped to a synthetic `CTA` bucket so they leave
every category; the close's translation is a **presented line computed from the close entry
itself**, not derived as the difference between the two sides of the statement. `P4-CF-03`
tests the partition and `P4-FX-08` tests the distinction. A 0.10 USD tolerance introduced for
the residual was removed once the residual was explained — a tolerance is what you use when you
do not yet understand something, not a place to leave it.

## 10. A SQL aggregate that returned whichever row it saw first

**Symptom.** Two builds of identical data produced different bytes for
`rpt_balance_sheet.parquet`.

**Root cause.** `Intercompany balances` is deliberately the caption for both the receivables and
the payables, and the caption spine collapsed the two to one row with
`any_value(account_class)`.

**Why controls miss it.** Every value it returns is a *valid* value. Nothing is out of balance
and no accounting control can object. Only comparing two builds of the same inputs finds it.

**Permanent fix.** The class is part of the caption key, so the caption is presented under each
class it belongs to — which is how a balance sheet presents receivables and payables anyway.
Every remaining arbitrary-row aggregate in the engine was replaced with `min()`, and a test
fails if one returns. [ADR-0022](adr/0022-money-is-decimal-and-artefacts-are-totally-ordered.md)
is the reason this is a test and not a preference: a build whose bytes move between runs of
identical data cannot be used as evidence of anything.

## 11. Three artefacts disagreeing about the same measure

**Symptom.** The balance sheet presented USD 19.869m as "the result for the period" while the
income statement reported a 7.046m profit for the same year. The EBITDA bridge reported
statutory EBITDA of (0.535)m for a year in which the income statement reported 28.705m. The
layer bridge showed the group's net income arriving almost entirely from the consolidation
layers.

**Root cause.** Two faults, each repeated across artefacts. The year-end close was included in
income statement measures in three artefacts, which nets a fiscal year to approximately nil.
And a `FILTER` matching nothing yielded NULL, voiding the whole Covenant EBITDA expression.
Both had already been found and fixed in `rpt_income_statement` during Phase 4 — and nothing
carried the fix to the artefacts nobody was comparing it against.

**Why controls miss it.** All 61 accounting controls passed throughout. Nothing was out of
balance: total equity was right, the balance sheet balanced at 0.00, the cash flow tied at
0.00, and every layer, elimination and roll-forward control was green. The defects were
entirely in the reporting layer, and **no control compared one artefact with another**. A
control suite that only tests the accounting cannot see a reporting error, however large.

**Permanent fix.** A second design rule, and a control family that implements it:

> **Different artefacts expressing the same financial measure must reconcile to one
> authoritative definition.**

Eleven `P4-XAR-*` controls, each with at least one side recomputed from `fact_financials` and
never both sides from the same reporting calculation. `P4-XAR-11` found the third instance on
its first run. Plus a written NULL policy — *a component with no population contributes zero,
never NULL* — enforced by a lint test, because that same fault has now caused three separate
defects here.

---

## 12. A business key that was never a key

**Symptom.** `project_id` identified 1,846 capital projects with 395 values. Five different
capital programmes in the same entity-month — buildings, plant, vehicles, IT, leasehold — all
answered to `CP-200-202505-01`. A fixed asset could not name the project that bought it.

**Root cause.** The generator took the sequence number from the inner loop that splits one
asset class into parts, while the outer loop walked the asset classes, so the sequence
restarted at `-01` for every class.

**Why controls miss it.** This is the sharpest example in the list, because the mechanism is
different from all the others. It is not that the defect *balanced*. It is that **every join
still worked**. `ref_fixed_asset` joined `fact_capex_project` and returned rows — five times
too many — and no control compared the row count before the join with the row count after it.
The only checks in range were a `NOT NULL` test, which a colliding key passes comfortably, and
two grain controls pointed at the two financial marts. Four phases, 250 controls and 42 fault
fixtures passed over it. No amount was ever wrong, so no reconciliation could see it.

It was found by Power BI, which needed a unique key for a dimension and asked the only question
nobody had thought to ask: *is this actually unique?*

**Permanent fix.** [ADR-0026](adr/0026-a-declared-key-is-a-contract.md), and a third design
rule:

> **A declared key is a contract, not a naming convention. Its uniqueness must be proved over
> its authoritative population.**

The identifier now carries the grain that makes a project distinct
(`CP-{entity}-{period}-{asset_class}-{sequence}`), and — the part that generalises — all 61
keyed objects in the platform are declared in `src/integrity/registry.py` and proved by one
generic engine: 229 controls, 9 fault fixtures, and `P7-REG-01` failing whenever a keyed table
exists that the registry has never heard of. Six of those 61 keys turned out to need a column
the obvious guess omitted, which is the same mistake in miniature, six more times.

The framework found a further gap on its first run (`PY_DERIVED` used as a version code with no
row in the version master), which is the usual sign that a control family was worth building.

---

## 13. A version code that resolved to nothing

**Symptom.** `PY_DERIVED` was the version code on 12,516 rows of `mart_financial_ytd` and on
every prior-year comparator in `mart_variance`. It existed in no version master. `PY` *was* a
first-class scenario; its version simply had no row.

**Root cause.** A sound decision, followed by a step that does not follow from it. Prior Year is
derived from Actual at *t − 12* and stored nowhere, so it cannot drift (ADR-0004). Because the
**data** is not stored, the **identity** was never registered — and those are different
questions. `dim_report_scenario` admitted a version only if rows existed carrying its code,
which is the right test for a stored version and the wrong test for a derived one.

**Why controls miss it.** The same reason as item 12, one dimension over: every query still
returned rows. A version code that resolves to nothing does not fail a join, it just never
appears in a dimension nobody was joining it to. And there was a **workaround already in the
code** — `ref_default_version` unioned the PY default in by hand, with a comment — which is
usually the clearest available signal that something is wrong and the easiest thing in the world
to read past.

**Permanent fix.** [ADR-0027](adr/0027-a-derived-version-is-still-a-governed-version.md):

> **Deriving a figure is not a reason to leave its identity ungoverned.** Where a number comes
> from and whether the thing has a governed identity are separate questions.

`PY_DERIVED` is now a governed derived version in the master — typed `DERIVED`, locked, never
source-loaded, naming what it derives from. Fourteen `P7-VER` controls and nine fixtures hold
it, including a pair worth copying: `P7-VER-10` proves every Prior Year row is the right Actual,
and `P7-VER-11` proves no Actual month is *missing* its Prior Year. One iterates PY, the other
iterates Actual, because a row the derivation never built is invisible to a control that
iterates the output.

The `UNION ALL` is gone and `P7-VER-05` fails if a default ever appears outside the master
again.

---

## 14. A digest that answered the wrong question

**Symptom.** Rebasing a branch moved every build id in the platform. Not one byte of file
*content* had changed.

**Root cause.** `build_id()` hashed raw bytes, and git rewrites line endings on checkout. The
form that reproduced each committed id turned out to be a per-file mixture of CRLF and LF, so
the ids were identifying which files had last been authored on Windows.

**Why controls miss it.** Every control that could have seen it was measuring money, and no
money was involved. The reproducibility tests *did* fail — eventually — but only because a
rebase happened to change the working tree; on any machine where the files were never
re-checked-out, they passed indefinitely while the claim they were making was false. A control
that passes for the wrong reason is indistinguishable from one that works.

**Permanent fix.** [ADR-0028](adr/0028-lineage-ids-hash-content-artefact-digests-hash-bytes.md),
and a distinction the platform had never drawn:

> **A lineage id answers "is this the same input" and hashes canonical content. An artefact
> digest answers "is this the same file" and hashes bytes. They are not interchangeable.**

One shared hasher, and `P7-RPR-02` reads the source of every phase's `build_id` to fail the
next one that quietly writes its own.

---

## 15. A model the engine ran and Desktop would not open

**Symptom.** The Phase 6A semantic model passed 49 controls on real DAX against the real
engine, 19 reconciliations to the marts and 8 to Excel, and 10 fault fixtures. Power BI Desktop
refused to open the project it described: first *"Property 'description' is unknown"*, then
*"Unsupported Table name "Measures""*.

**Root cause.** Two things the engine does not check. TMDL maps a `///` comment to a
`Description` property, and a relationship has none — but TMSL carries no comments, so the
deployment never had one. Desktop reserves the table name `Measures` — but Analysis Services
reserves nothing, so the deployment loaded it. The emitter produced two forms from one
declaration and they could not disagree about a definition; they were never asked whether they
agreed about *validity*.

**Why controls miss it.** Every control was pointed at the engine, and the engine was right.
The report said, accurately, that the Desktop file-open path had not been exercised — and
recorded it as a limitation of the environment rather than as a missing control surface. A
limitation is something you cannot test. This was something nobody had tested.

**Permanent fix.** `src/powerbi/desktop.py` opens the generated `.pbip` in Desktop through
Desktop's own Open dialog, reads back the loaded title or the refusal, refreshes natively, and
counts what Desktop loaded. `P6-PBIP-01` … `P6-PBIP-04` hold it; `F6-PBIP-01` and
`F6-PBIP-02` re-emit each defect and record that the engine still accepts it while the
project controls and Desktop refuse it.

> **Native file-format validation and semantic-engine validation are separate control
> surfaces. Passing one does not prove the other.**

---

## What these have in common

**A plug makes controls pass.** Items 1 and 4 both had a residual absorbing the defect, and in
both cases the balancing control was green *because* of it. Any account whose purpose is to
absorb a difference is a place where a defect can live indefinitely.

**Self-consistency is not correctness.** Items 2, 3, 5, 8 and 9 were all internally consistent.
Each needed an **independently produced expectation** — the CTA oracle, the debt schedule, the
NCI anchor, the cash flow partition — computed from different inputs by different code, and
read only by the control.

**A control's population is a design decision.** Item 6 is the general case of item 4, and the
reason four more instances were found in Phase 4A. If a control iterates the output, it can
only find wrong rows. Missing rows are invisible, and missing rows are worse.

**A control suite tests what it was pointed at.** Item 11 is the general case: 61 controls
proved the accounting and none of them looked at whether the reports agreed with it. Every
control family has a blind spot shaped exactly like the thing it was not asked about, and the
only way to find it is to break something deliberately and see whether anything objects.

**Determinism is an accounting property.** Item 10 has no accounting consequence at all, and it
would still have made every artefact unusable as evidence. If a rebuild can differ, nothing
built on it can be relied upon.

**A join that returns rows is not a join that is right.** Items 12 and 13 are the two defects
here that never made a number wrong. Every control that could have seen them was measuring
amounts, and the amounts were correct — the identity was not. Structure needs its own controls,
because a platform that only checks its arithmetic will believe anything its keys tell it.

**A workaround is a defect somebody already found.** Item 13 had a hand-written `UNION ALL`
sitting in the mart build with a comment beside it. Nobody had written it for fun; it was there
because the governed dimension was missing a row, and the quickest way past that was to add the
row by hand at the point of use. Code that routes around its own data model is worth reading as
a report of a defect rather than as an implementation detail.

**A control family earns its keep by finding the next one.** The framework built for item 12
found item 13 within a day of existing — different dimension, different cause, same shape.

**Ask what a check is actually asserting.** Item 14 is the only defect here that involved no
data at all. The digests were computed correctly, compared correctly and reported correctly;
they were simply digests of the wrong thing. A measurement can be precise, repeatable and
entirely beside the point.
