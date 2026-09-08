# The Phase 4 control framework

61 controls over the consolidation engine, all passing on the clean baseline.
[`control-framework.md`](control-framework.md) covers the source and pipeline controls of
Phases 2 and 3; this document covers Phase 4.

The register is committed at `config/controls/phase04_control_register.csv` and the results of
the last build at `data/phase04_control_results.csv`. A test fails if the two disagree about
which controls exist — a register listing a control the code does not run, or a control the
register does not describe, is how a control suite drifts into decoration.

---

## The design rule

> ### Controls iterate from the authority that requires the data, not from the data being tested.

This is the most important idea in the project and it was learned expensively — the same shape
of defect cost two separate phases before it was written down.

A control that walks the rows the engine produced and checks each one is only capable of
finding a **wrong** row. It is structurally incapable of finding a **missing** one, because a
missing row is not in the population it walks. And a missing row is the more dangerous defect:
nothing about the accounts looks unusual, the trial balance still closes, and some plug
absorbs the difference.

| Family | Iterates from | Not from |
|---|---|---|
| Ownership | `ref_ownership`, the ownership register | the entities that happen to have a parent |
| FX | the entity-periods that **need** a rate | the rate table |
| CTA | `ref_cta_expectation`, produced before the engine existed | the CTA the engine derived |
| Intercompany | the approved relationship population, **by pair** | the group's intercompany totals |
| Investment | `ref_investment_register` | the investments the ledgers contain |
| PPA and intangibles | `ref_acquisition`, `ref_ppa_intangible`, and the register for dates | the schedules that drove the postings |
| NCI | the non-controlling percentages in the ownership register | the entities that received an allocation |
| Unrealised profit | `ref_ic_inventory_transaction`, all 173 sales | the holdings table derived from them |
| Management adjustments | `ref_management_adjustment` | the adjustments that were posted |

Four Phase 4 controls were written the easy way, could not have failed, and were rewritten
during Phase 4A after fault fixtures exposed them. Those four are marked ★ below.

---

## Ownership — 6 controls

Population: `ref_ownership`.

| ID | Objective | Threshold | Sev |
|---|---|---|---|
| `P4-OWN-01` | no entity appears in its own ownership path | 0 cycles | blocking |
| `P4-OWN-02` | every consolidated entity has exactly one valid path to the ultimate parent | 0 | blocking |
| `P4-OWN-03` | no two register rows are effective for the same entity at the same time | 0 overlaps | blocking |
| `P4-OWN-04` | group % + NCI % = 1, and both are in [0, 1] | 0 invalid | blocking |
| `P4-OWN-05` | the ownership register and the investment register agree on parentage | 0 disagreements | blocking |
| `P4-OWN-06` ★ | second-tier holdings resolve through their own parent | derived from the register | blocking |

`P4-OWN-05` is the cross-register control. Each register is internally consistent on its own;
only the comparison between them finds a subsidiary consolidated on a relationship nobody paid
for, or an investment in something not consolidated.

`P4-OWN-06` originally asserted a hard-coded four second-tier entities. A control containing a
number that must be edited when the group changes is a control that will eventually be edited
to agree with whatever the engine produced. It now derives the expected population from the
register — entities held by an entity that is itself held by somebody.

**Failure implication:** an entity consolidated at the wrong percentage, or one tier too high.
Every total still balances; the split between group and minority is wrong.

## FX and CTA — 8 controls

Population: the entity-periods that require translation, and `ref_cta_expectation`.

| ID | Objective | Threshold | Sev |
|---|---|---|---|
| `P4-FX-01` | every currency and period an entity posted in has an average and a closing rate | 0 missing | blocking |
| `P4-FX-02` | every entity has a registered opening translation base (FX-P16) | 0 missing | blocking |
| `P4-FX-03` | no `HIST` equity account is translated at a closing rate (FX-P03) | 0 | blocking |
| `P4-FX-04` | derived CTA reproduces the independent expectation | every row within USD 1 | blocking |
| `P4-FX-05` | USD entities generate no CTA | 0.00 | blocking |
| `P4-FX-06` | the CTA roll-forward is continuous year to year | 0 discontinuities | blocking |
| `P4-FX-07` | the NCI share of the translation movement is the entity's own percentage | 0 | blocking |
| `P4-FX-08` | the FX effect on cash is distinct from CTA and smaller | both non-nil, distinct | blocking |

`P4-FX-01` iterates the entity-period population that **needs** a rate, taken from
`stg_entity_movement` — not the rates that happen to exist. `P4-FX-04` measured **243 of 243**
entity-periods agreeing, worst difference **0.000001 USD m**.

**Failure implication:** a plausible, balanced, entirely wrong set of translated statements.
Only the independent expectation can see it, which is the whole argument for having one.

## Intercompany — 5 controls

Population: `ref_ic_side`, the approved relationship population, matched **by entity pair**.

| ID | Objective | Threshold | Sev |
|---|---|---|---|
| `P4-IC-01` | every relationship nets, pair by pair | 0 unmatched, USD 1.00 per pair | blocking |
| `P4-IC-02` | the population is not empty | > 0 | blocking |
| `P4-IC-03` | consolidated intercompany balances are nil | USD 1.00 cumulative | blocking |
| `P4-IC-04` | consolidated intercompany income and expense are nil | USD 1.00 | blocking |
| `P4-IC-05` | every difference carries a classification | 0 unclassified | blocking |

Measured: 2,355 relationship-periods, all `MATCHED`; worst residual USD 0.19 on balances and
USD 0.38 on the consolidated flow total.

`P4-IC-02` looks trivial and is not: a pair reconciliation over no pairs passes perfectly, and
that is what a matching engine that has stopped working looks like.

**Failure implication:** group revenue and cost inflated by internal trade, or an entity
balance sheet carrying a receivable nobody owes. See
[`intercompany-elimination.md`](intercompany-elimination.md) for the F02 worked example.

## Investment — 3 controls

Population: `ref_investment_register`.

| ID | Objective | Threshold | Sev |
|---|---|---|---|
| `P4-INV-01` | every register relationship has an acquisition schedule | 0 missing | blocking |
| `P4-INV-02` | every investment eliminates in full, relationship by relationship | USD 0.01 | blocking |
| `P4-INV-03` ★ | every investment is eliminated in the month the **register** gives it | exact | blocking |

`P4-INV-03` previously measured the postings against the acquisition schedule that drove them.
A schedule saying the group owned something from January is perfectly self-consistent with
entries posted from January; only the register knows when the group actually bought it. It now
requires the elimination in the register's month exactly — early removes equity still outside
the group, late leaves an investment in a subsidiary already owned, and both balance.

## Goodwill and PPA — 4 controls

Population: `ref_acquisition`.

| ID | Objective | Threshold | Sev |
|---|---|---|---|
| `P4-PPA-01` | goodwill = consideration + NCI − fair value of identifiable net assets | USD 0.01, all 11 | blocking |
| `P4-PPA-02` | no negative goodwill | 0 | warning |
| `P4-PPA-03` | deferred tax follows the schedule's own rate | USD 0.01 | blocking |
| `P4-PPA-04` | every goodwill posting names its acquisition | 0 anonymous | blocking |

`P4-PPA-04` exists because goodwill that cannot be traced to an acquisition is a balance nobody
can explain and nobody can impair. Negative goodwill is a warning rather than a failure: a
bargain purchase is possible, but it is a disclosure, not a silent balance.

## Intangibles — 4 controls

Population: `ref_ppa_intangible`, with dates from the investment register.

| ID | Objective | Threshold | Sev |
|---|---|---|---|
| `P4-INT-01` | every tranche has an amortisation schedule | 0 missing | blocking |
| `P4-INT-02` ★ | amortisation never begins before the register's effective month | 0 | blocking |
| `P4-INT-03` | nothing amortises past its cost | 0 | blocking |
| `P4-INT-04` | gross − accumulated = net book value, every period | USD 0.01 | blocking |

## Non-controlling interests — 5 controls

Population: the non-controlling percentages in `dim_ownership_period`.

| ID | Objective | Threshold | Sev |
|---|---|---|---|
| `P4-NCI-01` | every entity with an NCI is allocated one | all of them | blocking |
| `P4-NCI-02` | the share uses the entity's own effective percentage | 0 | blocking |
| `P4-NCI-03` | attributed exactly once per entity per period | 0 duplicates | blocking |
| `P4-NCI-04` | the five-account roll-forward closes every year | USD 0.01 | blocking |
| `P4-NCI-05` | the NCI charge sits below tax and never inside EBITDA | 0 | blocking |

`P4-NCI-01` walks the register, so an entity the engine failed to allocate **fails** rather
than being absent from the results. `P4-NCI-05` protects the covenant calculation: Consolidated
EBITDA is defined on the group, not on the group's economic share.

## Unrealised profit — 4 controls

Population: `ref_ic_inventory_transaction`, all 173 intercompany sales.

| ID | Objective | Threshold | Sev |
|---|---|---|---|
| `P4-PUP-01` | the provision reproduces the independent expectation | USD 1.00 | blocking |
| `P4-PUP-02` ★ | every sale reaches the calculation at its transacted value | all 173 | blocking |
| `P4-PUP-03` | prior-period profit reverses as stock is sold on | > 0 releases | blocking |
| `P4-PUP-04` | each surviving layer carries its own margin | USD 0.01 | blocking |

`P4-PUP-02` previously counted the holdings table against the layers built from it — a
derivation compared with itself, which passes however many rows go missing from both. Fixture
F4-12 deleted a month of holdings and the control did not notice.

## Journals, layers and the two facts — 8 controls

| ID | Objective | Threshold | Sev |
|---|---|---|---|
| `P4-JNL-01` | every entry in layers 2–4 balances | USD 0.01 | blocking |
| `P4-LAY-01` | only layers 2–5 are posted here | 0 | blocking |
| `P4-LAY-02` | layers 1 and 5 together sum to zero every period | USD 0.01 | blocking |
| `P4-LAY-03` | no layer-4 row reaches the statutory basis | 0 | blocking |
| `P4-LAY-04` | the management basis contains every layer it should | 0 missing | blocking |
| `P4-LAY-05` | no source ledger carries a CTA account | 0 | blocking |
| `P4-FCT-01` | the journal fact and the financial fact reconcile | USD 0.01 | blocking |
| `P4-FCT-02` | the entity ledgers are never copied into the journal fact | 0 | blocking |

`P4-LAY-02` is how a single-sided layer is tested. Layer 5 does not balance alone by design —
it *is* the amount by which the translated trial balance misses zero — so the assertion is made
on layers 1 and 5 together. `P4-LAY-05` catches a source-layer CTA, which would be a plug the
balance sheet balanced around.

## Statements — 9 controls

| ID | Objective | Threshold | Sev |
|---|---|---|---|
| `P4-BS-01` | assets = liabilities + equity | USD 0.01, measured 0.00 | blocking |
| `P4-BS-02` | every balance sheet account maps to exactly one caption | 0 | blocking |
| `P4-BS-03` | no balance sheet account without a caption | 0 | blocking |
| `P4-BS-04` | no income-statement-only caption appears in the balance sheet | 0 | blocking |
| `P4-BS-05` | the period result appears exactly once in equity | exactly 1 | blocking |
| `P4-PL-01` | the income statement is internally consistent | USD 0.02 | blocking |
| `P4-CF-01` | the cash flow ties in every period | USD 0.01, measured 0.00 | blocking |
| `P4-CF-02` | closing cash ties to the balance sheet | USD 0.01, measured 0.00 | blocking |
| `P4-CF-03` | every balance sheet account has exactly one cash flow category | 0 | blocking |

Each of `P4-BS-02`, `P4-BS-03` and `P4-BS-05` exists because of a defect that balanced
perfectly while being wrong: an account in two captions is counted twice; an account with no
caption disappears from the statement while staying in the fact; a result line that excluded
the close counted every closed year twice.

`P4-CF-03` is the control that makes `P4-CF-01` meaningful. The cash flow ties **by
construction** if the categories partition the balance sheet, so the tie is not the interesting
assertion — the partition is. A mis-categorised account still ties while reporting the wrong
line.

## Statutory versus management — 2 controls

| ID | Objective | Threshold | Sev |
|---|---|---|---|
| `P4-BAS-01` | management − statutory = layer 4, for all 28 measure-years | all explained | blocking |
| `P4-BAS-02` | discloses that layer 4 is currently empty | disclosure | warning |

`P4-BAS-02` carries no pass condition. It reports what the approved register contains so that a
comparison of two identical columns is never mistaken for a proof that the two bases were kept
apart.

## Management adjustments — 3 controls

Population: `ref_management_adjustment`.

| ID | Objective | Threshold | Sev |
|---|---|---|---|
| `P4-MGT-01` | only approved adjustments are posted | posted = approved | blocking |
| `P4-MGT-02` | no adjustment is anonymous | 0 | blocking |
| `P4-MGT-03` | Adjusted and Covenant EBITDA are computed separately | reported | warning |

`P4-MGT-03` passes unconditionally by design — the two measures are not expected to be equal —
and it is the weakest control in the suite. It touches `rpt_ebitda_bridge` without testing
either figure in it, which is why defect **P4-D-02** survived: see
[`phase-04b-engine-findings.md`](phases/phase-04b-engine-findings.md).

---

## What the suite does not cover

Stated plainly, because a control register that implies completeness is worse than one that
admits its gaps:

* **No cross-artefact controls.** Nothing compares one reporting artefact with another. Two
  statements can disagree about the same measure and every control still passes — which is
  exactly what defect P4-D-02 is.
* **No control on `rpt_ebitda_bridge`'s figures.** `P4-MGT-03` reports on it without testing it.
* **No control that the balance sheet's result caption equals the period's result.** `P4-BS-05`
  requires the caption to appear once, not to be correct — defect P4-D-01.
* **Impairment is out of scope.** Goodwill is recognised and never tested for impairment; there
  is no impairment model in the platform.
* **Disposals are out of scope.** FX-P19 (CTA recycling on disposal) is implemented but has no
  population — there are no disposals in the window.
