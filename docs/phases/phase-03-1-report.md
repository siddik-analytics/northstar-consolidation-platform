# Phase 3.1 Report — Source Defect Remediation & Clean-Baseline Gate

**Status:** Complete · **Date:** 2026-09-07 · **Next gate:** Phase 4 approval

Phase 3 found four defects in the frozen Phase 2 source layer and, correctly, did not touch
them. The freeze was reopened for this pass and for one purpose: to correct those four
defects at the generation layer, regenerate, and prove that nothing else moved.

All four are **CLOSED**. Not accepted, not deferred, not excepted — corrected in the code
that produces the data, with the raw extracts regenerated from it. No generated file was
edited by hand.

---

## 1. Summary

| | |
|---|---|
| Source defects | **4 raised, 4 closed** |
| Source exceptions outstanding | **0** |
| Phase 2 controls | **79 of 79 pass** (was 77 of 77; two intercompany controls added) |
| Phase 3 controls | **62 of 62 pass** (was 54 of 61 with 7 source findings) |
| Mapping agreement, **all** lines | **100.000000%** (1,094,996 of 1,094,996) |
| Mismatches · unmapped · ambiguous · invalid dimension | **0 · 0 · 0 · 0** |
| Source-defect exclusions | **0** |
| Population bridge residue | **0** in all three partitions |
| Group income statement vs target | **0.000000%**, all three years |
| Gross margin by business unit | **exact**, all twelve business-unit-years |
| Fault fixtures | **10 of 10 handled as intended** |
| Tests | 357 → **390** |
| Anchors moved | 15 of 34 headline measures, all downstream of one input |
| Anchors unchanged | Revenue, gross profit, EBITDA, adjusted EBITDA, cash, term loan, every working-capital caption, both intercompany anchors |

---

## 2. P2-D-01 — journals written without the attributes their mapping rule reads

**Affected population.** 166 journal lines across three ERPs and sixteen source accounts:
158 year-end-close lines at 12 entities, 5 Kestrel period-14 audit adjustments at 4 entities,
3 opening-balance lines at 3 entities.

**Financial amount affected.** USD 2.33m misclassified between two balance sheet captions —
26% of contract assets at FY2025 — plus USD 69.8m of local-currency close and conversion
postings that resolved to a default branch rather than to a derived one. The close lines
affected no reported figure because the close is excluded from every result measure by
design; the contract-asset misclassification affected the balance sheet directly.

**Root cause.** `opening_balance`, `year_end_close` and `special_period_adjustments` each
resolved the source account **and the attributes the mapping contract requires**, then wrote
an empty string into the attribute field and discarded them (`src, _req = resolved`). Only
`post()` — the ordinary-transaction path — wrote them.

**Why it is a source-generation defect and not a transformation defect.** The approved
mapping contract states, per source account, which line attribute a conditional split must
read. The engine did the only defensible thing with a posting that carries none of them:
resolve it to the account's declared default branch. The mapping was right; the extract did
not contain what the contract said it would.

**Generator responsible.** `src/generation/journals.py`.

**Correction.** One line resolver, `JournalGenerator._resolve`, returns the source account,
the cost centre, the department, the function and the attribute string, and **every** journal
type goes through it — the conversion journal, the statutory close, the special-period
adjustments and ordinary transactions alike. There is now no path that can resolve the
attributes and then not write them.

**Downstream effect.** Mapping agreement across all lines rises from 99.984641% to
100.000000%. Contract assets and prepayments reproduce the source-layer target exactly at
every caption-year. No account class carries an inverted sign at any entity.

**Regression tests.** `test_no_journal_writer_discards_the_attributes_it_resolved` (the
writers cannot resolve the account themselves any more),
`test_every_posting_to_a_conditional_account_carries_what_its_rule_reads`,
`test_the_conversion_and_close_journals_are_not_a_blind_spot` (measured over those journal
types on their own, with a guard that the population is not empty — a test that passes
because it found nothing to test is the same blind spot again),
`test_the_accrual_that_moved_2m_between_two_captions_is_classified`.

---

## 3. P2-D-02 — a posting's declared classification contradicted its cost centre

**Affected population.** 5,710 journal lines, 0.53% of the ledger: 4,419 Kestrel and 1,291
Sable, in thirteen distinct combinations.

**Financial amount affected.** USD 51.1m of local-currency postings carried a classification
the cost-centre dimension did not corroborate. **No reported figure was wrong** — the mapping
contract names the declared attribute as authoritative and the engine resolved
attribute-first — so what was lost was corroboration, not accuracy.

**Root cause.** Three compounding causes, and the third is the interesting one.

1. `_cost_centre` chose a cost centre from the account's departments and only then applied
   the split's required function to the line attribute. For `dept_function` it re-picked a
   department only if a matching one existed among that account's own; for
   `cost_center_function` it did not re-pick at all; for `dept_code` there was no handling.
2. `SPLIT_INVERSE` named **one** accepted value where the approved rule accepts a set.
   Kestrel's temporary-staff account reaches cost of sales from a `PRODUCTION`, `FIELD` **or**
   `PROJECT` cost centre; the generator asked for `PRODUCTION`, so a services entity with no
   manufacturing had to declare a function it does not have.
3. **`D210 Equipment & Fleet` and `D215 Field Safety & Compliance` were classified as
   `FIELD`.** They support field operations; they do not deliver them. The department master
   calls both `INDIRECT`, their descriptions say so, and the approved Aurora split groups
   them with the other indirect-operations departments (`D105, D110, D115, D120, D210, D215
   → 520100`) rather than with the billable crews (`D200, D205 → 515200`). One wrong word in
   a lookup table put every industrial-services posting on the wrong side of a distinction
   that gross margin depends on.

**Why it is a source-generation defect.** The whole basis of the material mapping problem
(ADR-0007, CTL-MAP-04) is that the department or cost-centre segment carries what the account
code cannot. A free-text assignment field that contradicts the cost centre it sits in would
be a finding in any real implementation, and it makes the dimension useless as a check on the
mapping.

**Generators and configuration responsible.** `src/generation/journals.py`,
`src/generation/mapping.py`, `src/generation/masters.py`,
`config/dimensions/department.csv`, `config/mapping/mapping_rules.csv`.

**Correction.**

- The requirement now **drives** the choice of cost centre instead of being stamped on after
  it, and the attributes are read back off the cost centre actually chosen, so the two views
  of a posting cannot disagree by construction.
- Where no department at the entity can satisfy the requirement, the generator **refuses to
  post** rather than applying a label the cost centre denies. That refusal found three
  further inconsistencies that had been invisible: the transformation programme department
  was marked CORP-only while the approved add-back allocation puts 45% of its cost at four
  operating entities; the field-safety department was marked IS-only while an
  engineered-systems entity commissions on customer sites; and a substituted posting was
  looking up the departments of the account the chart does not have rather than the one it
  is actually classified as.
- A split requirement may name **every** value its rule accepts, and the generator posts to
  whichever member the entity actually has.
- `D210` and `D215` are `INDIRECT_OPS`.
- `SAB-60700-10` is expressed on `dept_code`, as the approved chart states it, rather than on
  a function that used to be a proxy for the same set and no longer is.

**Downstream effect.** Zero contradicting lines. Gross margin by business unit still
reproduces the anchor exactly for all twelve business-unit-years — the classification the
cost centre now corroborates is the classification the mapping always produced.

**Regression tests.** `test_the_cost_centre_is_chosen_to_satisfy_the_split_not_labelled_afterwards`,
`test_a_cost_centre_that_cannot_satisfy_the_requirement_is_refused`,
`test_a_split_requirement_may_name_every_value_its_rule_accepts`,
`test_the_support_departments_are_not_labelled_as_delivery`,
`test_every_department_a_conditional_account_may_use_exists_somewhere`,
`test_no_posting_declares_one_classification_and_sits_in_another`.

---

## 4. P2-D-03 — intercompany postings did not carry the counterparty

This was the Phase 4 blocker.

**Affected population.** 5,248 postings: 4,628 on the intercompany trade current account,
375 on the group treasury current account, 243 on the intercompany loan accounts, 2 others.
The investment-in-subsidiary postings were a further gap the original analysis did not name.

**Financial amount affected.** At 31 December 2025 the intercompany receivable and payable
position was **(24.284)m local in total, of which only (8.913)m — 37% — was attributable to
an entity pair**. The intercompany *result* elimination would have worked, because the
invoice legs carried partners. The intercompany **balance sheet** elimination by pair would
not have.

**Root cause.** Four distinct causes, all with the same shape: a balance that is by
definition owed to somebody, recorded without saying who.

1. **The settlement leg.** Stage 3 cleared each balance sheet account to its target as one
   net figure against cash, with `partner=""`. The invoice that created the balance named the
   counterparty; the receipt that cleared it did not.
2. **The treasury current account.** The cash pool has exactly one counterparty on each side
   and always has had — the operating entity's current account is with Topco and Topco's is
   with that operating entity. Nothing recorded it.
3. **The loan accounts.** Every loan in the register is made by Topco, so a borrower's
   payable has one counterparty and Topco's receivable divides between the borrowers in
   proportion to their notionals. Both were true by construction; the postings did not say so.
4. **Investments in subsidiaries.** The register names the subsidiary for every holding. The
   consideration posting did not.

Correcting these surfaced two further defects that no control could previously see, because
a balance nobody could attribute to a pair could not be compared with its mirror:

5. **The trade current account did not net pairwise.** The anchored group intercompany
   balance was allocated to entities by each entity's *share of intercompany turnover*. Every
   entity got the right total and no pair got a matching number: in May 2025 one entity's
   receivable from another and that other's payable to it were 10% apart.
6. **A pair carried a balance before both sides were in the group.** The flow matrix is
   settled a year at a time, so a company acquired in April was carrying balances with its
   new sister companies from January — one side of a pair that the other side could not have.

**Why it is a source-generation defect.** `CTL-IC-04`, approved in Phase 1, requires every
posting to an intercompany account to carry a valid partner. In a real ERP, clearing an
intercompany receivable references the specific counterparty; that is how the balance is
attributable, and it is how the elimination engine matches it.

**Why Phase 2 did not catch it.** `P2-IC-01` filtered to lines that **already had** a
partner. A control that tests only the population that satisfies it cannot fail. That is not
a detail of implementation, it is the reason a blocking control ran green for two phases over
data it was written to reject.

**Generators responsible.** `src/generation/journals.py`, `src/generation/ledger.py`,
`src/generation/series.py`, `src/generation/build.py`, `src/generation/validate.py`.

**Correction.**

- `IC_BALANCE_ACCOUNTS` names the seven accounts whose balance is by definition owed to or by
  another group entity. Each is settled **counterparty by counterparty** in its own stage,
  and the per-counterparty residuals sum to the account residual, so cash is unchanged.
  Anything left unattributed on such an account raises rather than posting a nameless plug.
- The anchored group intercompany balance is allocated **flow by flow** rather than entity by
  entity. An entity's total is the sum of its own flows either way — so no entity balance and
  no anchor moves — but a flow has one seller and one buyer, so both sides of a pair now read
  the same USD figure. The **pair** is the unit that runs from what it owed at the last year
  end to what the anchor says it will owe at this one, and each side translates it at its own
  closing rate.
- A pair has no balance before both sides are in the group.
- The loan and investment balances are decomposed from their own registers month by month,
  so the lender never carries a balance with a borrower that is not yet in the group.
- The opening balance journal brings intercompany positions forward one counterparty at a
  time. A balance carried in as a single unattributed figure is exactly as useless to the
  elimination engine as an unattributed settlement.
- `P2-IC-01` is split in two and both are stated correctly: a **balance** matches its mirror
  at the **closing** rate and it is the cumulative balance that must match, not the month's
  movement (`CTL-IC-01`); a **flow** matches at the **average** rate of the month it was
  recorded in (`CTL-IC-02`). The old control tested movements at average rates for every
  intercompany line regardless of statement — two errors that cancelled only because the
  balance sheet legs carried no counterparty and were silently excluded.
- New `P2-IC-02` tests the **whole** intercompany population for a counterparty, not the
  subset that already has one.

**Downstream effect.** **100%** of the intercompany position is attributable to an entity
pair. Every pair nets to under USD 1.00 at closing rates in every period, and every flow to
under USD 1.00 at average rates. Investments in subsidiaries are excluded from the pair test
as non-reciprocal — a holding eliminates against the subsidiary's equity, not against a
mirror balance — and are reconciled to the investment register by `P2-INV-01` instead.

**Regression tests.** `test_every_intercompany_balance_account_is_settled_by_counterparty`,
`test_a_partnerless_residual_on_an_intercompany_account_is_an_error`,
`test_no_intercompany_posting_lacks_a_counterparty`,
`test_no_posting_names_itself_as_its_own_counterparty`,
`test_the_whole_intercompany_position_is_attributable_to_a_pair`,
`test_an_entity_carries_no_balance_with_a_company_that_is_not_yet_in_the_group`.

---

## 5. P2-D-04 — a special period crossed an anchored balance sheet caption

**Affected population.** The period-15 tax true-up at the Kestrel entities, FY2023 to FY2025.

**Financial amount affected.** USD 0.028m, 0.039m and 0.126m — 5.1% of income taxes payable
at FY2025.

**Root cause.** The balance sheet leg of the true-up was `218100 Income taxes payable →
219100 Other taxes payable`. `219100` is the **VAT** account: it is an accrued liability, not
an income tax, and it belongs to a different anchored caption. The entry was documented as a
reallocation between corporation tax and trade tax, and trade tax is an income tax.

**Why it is a source-generation defect.** Phase 2.1 states that special periods 14–16
"reclassify within one anchored caption, so the year's result and every anchored subtotal are
unchanged", and `P2-FMT-09` tests it — for the **result**, and not for balance sheet
captions. The rule was right and the entry broke it.

**Generator responsible.** `src/generation/journals.py`,
`SPECIAL_PERIOD_ADJUSTMENTS[15]`.

**Correction.** The balance sheet leg is removed. A true-up between Körperschaftsteuer and
Gewerbesteuer reallocates the **charge**; the amount owed to the tax authority does not
change, and because both are income taxes payable at group level the payable is not
reclassified either. The entry is a pure income statement reclassification and now says so.

**Downstream effect.** Both captions reproduce the source-layer target. Special periods 14
and 16 still carry balance sheet legs, so Phase 3's handling of balance sheet postings in a
thirteenth-to-sixteenth period is still exercised.

**Regression tests.** `test_no_special_period_adjustment_crosses_an_anchored_caption` — every
leg of every special-period entry, at the level that is actually anchored: the second caption
level on the balance sheet, where income taxes payable and accrued liabilities are separate
figures, and the first on the income statement, where total tax is anchored but current tax
and other tax within it are not. `test_the_tax_true_up_has_no_balance_sheet_leg`.
`test_special_periods_still_reach_the_ledger` guards against the correction quietly emptying
them.

---

## 6. The row-population bridge

| Bridge | Disposition | Lines | Absolute amount, local |
|---|---|---:|---:|
| `CHARACTER` | `OPENING_BALANCE` | 274 | 1,288,100,667.36 |
| `CHARACTER` | `OPERATIONAL` | 1,093,022 | 17,978,663,470.20 |
| `CHARACTER` | `SPECIAL_PERIOD_AUDIT_ADJUSTMENT` | 30 | 61,820.10 |
| `CHARACTER` | `SPECIAL_PERIOD_GROUP_REPORTING_ADJUSTMENT` | 16 | 145,962.08 |
| `CHARACTER` | `SPECIAL_PERIOD_STATUTORY_CLOSE` | 542 | 430,378,092.32 |
| `CHARACTER` | `SPECIAL_PERIOD_TAX_ADJUSTMENT` | 22 | 304,136.76 |
| `CHARACTER` | `YEAR_END_CLOSE` | 1,090 | 2,414,261,927.00 |
| `MAPPING` | `AMBIGUOUS` | 0 | 0.00 |
| `MAPPING` | `INVALID_DIMENSION` | 0 | 0.00 |
| `MAPPING` | `MAPPED_DERIVED` | 613 | 495,078.38 |
| `MAPPING` | `MAPPED_DIRECT` | 1,008,862 | 19,761,700,826.91 |
| `MAPPING` | `MAPPED_SPLIT` | 46,940 | 1,462,025,990.22 |
| `MAPPING` | `MAPPED_SPLIT_DEFAULT` | 38,581 | 887,694,180.31 |
| `MAPPING` | `OUT_OF_EFFECT` | 0 | 0.00 |
| `MAPPING` | `UNMAPPED_ACCOUNT` | 0 | 0.00 |
| `MAPPING` | `UNMAPPED_NO_RULE` | 0 | 0.00 |
| `ORACLE` | `GRADED_AGREES` | 1,094,996 | 22,111,916,075.82 |
| `ORACLE` | `GRADED_DISAGREES` | 0 | 0.00 |
| `ORACLE` | `GRADED_NOT_CLASSIFIABLE_AT_SOURCE` | 0 | 0.00 |
| `ORACLE` | `NOT_GRADED` | 0 | 0.00 |

**Ingested: 1,094,996.** `CHARACTER` sums to 1,094,996 (residue 0). `MAPPING` sums to 1,094,996 (residue 0). `ORACLE` sums to 1,094,996 (residue 0).

Three partitions of the same population. Each sums to the ingested row count with **zero
residue**, and `P3-REC-12` (`CTL-DQ-12`) fails the build on any residue in any of them.
Dispositions that must be nil are stated at nil rather than omitted: a category missing from
a bridge reads as a category nobody thought to look for.

### The 67,142-row difference, explained

Phase 3 reported 1,080,782 ingested rows and 1,013,640 graded against the expected-mapping
oracle. The difference was never an exclusion — **every** row was graded, and the reported
agreement across all rows was 99.984641%. The second figure was a *sub-measure*,
`classifiable_at_source`, introduced to isolate P2-D-01: of the lines posting to a conditional
account, how many carried what their account's rules read.

That sub-measure was **wrong**, and 67,142 of the 67,246 rows it excluded should never have
been in it. It tested `attr_<field>` — the declared line-attribute string — for every field a
rule reads. But a rule field like `dept_code` is a **context field**: the standardised layer
resolves it as `coalesce(attr_dept_code, source_department_key)`, and Aurora states a
posting's department in its department segment rather than in the attribute string. Aurora's
payroll and purchase-invoice lines were therefore marked unclassifiable while being, in fact,
classifiable and correctly classified.

The measure now runs against the column the rule actually evaluates — `resolve_field` is the
authority for which column that is, and the acceptance module now calls it instead of
hard-coding a prefix. The remaining 208 rows it then found were a real, smaller instance of
the same defect as P2-D-01: Sable's restructuring account and Aurora's intercompany notes
account are conditional, and the generator posted to them without stating the `cost_type` or
the `maturity_months` the rules read. Both now state it.

**Result: 1,094,996 ingested, 1,094,996 graded, 1,094,996 classifiable at source, 1,094,996
agreeing.** The two agreement measures are the same number because there is nothing left for
them to differ about.

---

## 7. Mapping hard gate

| | |
|---|---|
| Lines graded | **1,094,996** |
| Expected mapping agreement | **100.000000%** |
| Mismatches | **0** |
| Unmapped | **0** |
| Ambiguous | **0** |
| Invalid dimension keys | **0** |
| Source-defect exclusions | **0** |
| Accepted shortfall | **none** |

The expected-mapping manifest remains a test oracle.
`test_the_manifest_is_an_oracle_and_never_an_input` asserts that no transformation stage
reads it, the manifest file, or the Phase 2 journal mirror — only the acceptance grader does.

---

## 8. The clean control baseline

**Phase 2: 79 of 79 pass.** Two controls added (`P2-IC-02`, `P2-IC-03`) and one rewritten
(`P2-IC-01`).

**Phase 3: 62 of 62 pass.** One control added (`P3-REC-12`).

Every one of the seven previously non-PASS results was reviewed against the four categories
the gate requires:

| Control | Was | Category | Disposition |
|---|---|---|---|
| `P3-TB-06` | SOURCE_FINDING, 7 account-entity-years | **A — a real defect** | P2-D-01 corrected; contract assets no longer carry an inverted balance. **PASS** |
| `P3-MAP-04` | SOURCE_FINDING, 166 lines | **A — a real defect** | P2-D-01 corrected. **PASS at 100.000000%** |
| `P3-MAP-12` | SOURCE_FINDING, 5,710 lines | **A — a real defect** | P2-D-02 corrected; zero contradictions. **PASS** |
| `P3-MAP-13` | SOURCE_FINDING, 166 lines | **A — a real defect** | P2-D-01 corrected. **PASS** |
| `P3-DIM-08` | SOURCE_FINDING, 5,248 lines | **A — a real defect, and a Phase 4 blocker** | P2-D-03 corrected; every intercompany posting names its counterparty. **PASS** |
| `P3-REC-03` | SOURCE_FINDING, 6 caption-years | **A — a real defect** | P2-D-01 corrected. **PASS** |
| `P3-REC-11` | SOURCE_FINDING, 6 caption-years | **A — a real defect** | P2-D-04 corrected. **PASS** |

All seven were category A. None was an intentional design exception, none was inapplicable at
Phase 3, and none was an incorrectly designed control — although fixing them exposed three
controls that *were* incorrectly designed and two that were incorrectly scoped:

| Control | What was wrong with it |
|---|---|
| `P2-IC-01` | tested only the lines that already carried a partner, so the population it was written to reject was invisible to it; and tested monthly *movements* at *average* rates for balance sheet accounts, where a *balance* must match at the *closing* rate |
| `P2-INV-01` | correct, but it was the only thing standing between an unattributed investment holding and the elimination engine; `P2-IC-02` now covers the population it does not |
| `P3-MAP-12` | reported a NULL amount when it found nothing, and crashed rather than passing. A control that cannot express "nil" is not finished |
| acceptance measure | tested the declared attribute rather than the field the rule evaluates (§6) |
| `SAB-60700-10` | expressed on a function that was a proxy for a department set and stopped being one when the department master was corrected |

**No threshold was loosened.** Every threshold in this pass moved in one direction: `P2-IC-01`
gained a second control and a stricter basis, `P2-IC-02` widened a population from a subset to
the whole, `P3-REC-12` is new and at zero, and the acceptance measure went from excluding
67,246 rows to excluding none.

### The source exception register

All seven entries are `CLOSED` at an accepted population of **nil**, each recording the phase
that closed it and the code that corrected it. A closed exception is not a deleted one: the
register still names the defect, so if it recurs the control **fails** rather than
reappearing as an accepted finding. `test_a_recurrence_of_a_closed_defect_fails_rather_than_passing`
asserts exactly that.

---

## 9. Fault fixtures

| Fault | What it is | Intended control | Phase 3 family | Fired | Outcome |
|---|---|---|---|---|---|
| `F01` | Unmapped source account | `CTL-MAP-01` | `P3-MAP` | `P3-MAP-01`, `P3-MAP-03`, `P3-MAP-04`, `P3-MAP-08` | **DETECTED** |
| `F02` | Intercompany amount mismatch | `CTL-IC-01` | — | — | **NOT APPLICABLE** — deferred |
| `F03` | Missing FX rate | `CTL-FX-01` | `P3-DIM` | `P3-DIM-10` | **DETECTED** |
| `F04` | Duplicate journal identifier | `CTL-DQ-03` | `P3-ING` | `P3-ING-02`, `P3-ING-08` | **DETECTED** |
| `F05` | Invalid cost centre | `CTL-DQ-08` | `P3-DIM` | `P3-DIM-02` | **DETECTED** |
| `F06` | Malformed localised amount | `CTL-DQ-09` | `P3-ING` | `P3-ING-13` | **DETECTED** |
| `F07` | Posting date outside its period | `CTL-DQ-06` | `P3-ING` | `P3-ING-06` | **DETECTED** |
| `F08` | Payroll misclassified across the gross margin line | `CTL-MAP-04` | `P3-REC` | `P3-REC-06` | **DETECTED** |
| `F09` | Unbalanced journal | `CTL-TB-01` | `P3-TB` | `P3-TB-01`, `P3-TB-02`, `P3-TB-03` | **DETECTED** |
| `F10` | Posting before the consolidation effective date | `CTL-CON-02` | `P3-CMP` | `P3-CMP-02` | **DETECTED** |

**9 of 10 faults are detected in Phase 3 by the control family that is supposed to catch them. The tenth, F02, is not applicable at this phase and is deferred to a named Phase 4 control. 10 of 10 handled as intended, and none detected only by accident.**

### F02 — reviewed, and confirmed NOT APPLICABLE to Phase 3

The fixture alters one side of an intercompany pair. Detecting it requires comparing the two
sides, and the pair is only assembled by the Phase 4 elimination engine — there is no Phase 3
artefact in which both sides meet. Every Phase 3 control is **correct** to pass on it: the
file parses, the journal balances, the account maps, the dimension resolves and the trial
balance closes, because a one-sided intercompany difference is a valid posting at the entity
that made it. Claiming detection here would mean a control had fired for a reason it does not
own.

- **Fixture retained unchanged**, with its expected-failure manifest.
- **Classified `NOT_APPLICABLE_DEFERRED`**, an explicit status rather than a silent pass, and
  the harness treats a control firing on it as an `ACCIDENTAL_DETECTION` defect.
- **The Phase 4 control that must detect it is `CTL-IC-01`** — intercompany balances
  eliminate to nil, tolerance USD 1.00 per entity pair — named in the fault result row.
- Phase 3.1 makes that detection possible where it previously was not: P2-IC-01 now proves
  the clean source nets to under USD 1.00 for every pair and period, so the fixture's
  one-sided difference is orders of magnitude above the threshold it will be measured
  against. Before this pass, 63% of the position could not be attributed to a pair at all
  and `CTL-IC-01` would have had nothing to measure.

---

## 10. Source freeze integrity

`data/phase03_1_source_diff.json`, produced by `tools/source_diff_manifest.py`, is the
evidence. It enumerates every file under `src/generation`, `config`, `data/reference` and
`tools` that differs from the Phase 2.2 freeze at commit `20355b2`, and every headline anchor
before and after.

### Anchors that did not move

**Revenue · Cost of sales · Gross profit · EBITDA · Adjusted EBITDA · Operating expenses ·
EBIT · Cash · Term loan B · Trade receivables · Inventory · Trade payables · Contract assets ·
Prepayments · Accrued liabilities · Income taxes payable · Total assets · Intercompany AR/AP ·
Intercompany loans** — identical to the sixth decimal in all three years.

### Anchors that moved, and why

One input moved, and everything else follows from it.

```
intercompany balances are now built pair by pair, and a pair has no balance
before both sides are in the group
        ↓
the monthly intercompany positions change, and cash is the residual of the
balanced entity journals
        ↓
the group's intra-year liquidity need changes, and the revolver is drawn
against exactly that
        ↓
average daily drawn falls:  FY2023 17.318 → 14.829   FY2024 26.347 → 23.902
                            FY2025 22.820 → 22.099
        ↓
revolver interest falls and the commitment fee on the larger undrawn balance
rises (ADR-0018: the charge is priced off the daily utilisation model, so it
follows the model rather than being assumed)
        ↓
net interest falls → profit before tax rises → tax rises → net income rises
        ↓
retained earnings rise → total equity rises → the year-end facility balance
falls → net debt falls → leverage improves
```

| Measure | FY2023 | FY2024 | FY2025 |
|---|---|---|---|
| Average daily drawn | 17.318 → **14.829** | 26.347 → **23.902** | 22.820 → **22.099** |
| Revolver interest | 1.550 → **1.327** | 2.490 → **2.259** | 1.905 → **1.845** |
| Commitment fee | 0.213 → **0.226** | 0.168 → **0.180** | 0.186 → **0.190** |
| Net interest | 18.435 → **18.224** | 21.985 → **21.767** | 21.046 → **20.989** |
| Tax | 0.809 → **0.771** | (0.226) → **(0.106)** | 3.363 → **3.379** |
| **Net income** | (5.304) → **(5.055)** | (0.185) → **(0.087)** | 8.437 → **8.477** |
| Revolver drawn at year end | 16.237 → **15.989** | 24.867 → **24.519** | 19.518 → **19.132** |
| Retained earnings | (82.584) → **(82.335)** | (83.049) → **(82.702)** | (74.972) → **(74.585)** |
| Total equity | 85.574 → **85.823** | 81.754 → **82.101** | 99.192 → **99.578** |
| Net debt | 212.706 → **212.457** | 249.136 → **248.788** | 234.969 → **234.583** |
| Net leverage | 5.448× → **5.442×** | 5.281× → **5.274×** | 4.062× → **4.055×** |

FY2025 net income moves by **USD 0.040m, 0.48%**. Every covenant retains headroom and the
direction of every movement is favourable, which is a consequence and not a design: less
revolver drawn is less interest.

**CTA and NCI moved in the sixth decimal.** Both are derived from the generated entity
balances (ADR-0017), and correcting the intercompany positions moved those balances a little.
The largest movement in any year is USD 2.2 thousand of CTA against a movement of USD 7.7m —
0.03%. Restated rather than absorbed into a wider tolerance, because the point of the
assertion is that the figure is derived and reproducible.

**No unrelated anchor was touched.** The three derived inputs — `CTA_MOVEMENT`, `NCI_FX`,
`RCF_AVG_DRAWN` — were re-derived to a fixed point by `tools/derive_anchor_inputs.py`, which
converged in five iterations; nothing was entered by hand.

### Files changed

**Generator (7):** `journals.py` (all four defects), `mapping.py` (the accepted values of a
split), `masters.py` (the function of a department), `ledger.py` and `series.py` (intercompany
by counterparty), `build.py` (passing the opening decomposition), `validate.py` (the controls
that failed to catch them).

**Configuration (5):** `config/dimensions/department.csv` (D210/D215 function, D910 and D215
applicability), `config/mapping/mapping_rules.csv` (one rule expressed on the department set
the chart names), `config/controls/control_register.csv` (+CTL-DQ-12),
`config/controls/source_exception_register.csv` (all seven closed),
`config/anchors/*` (re-derived).

**Pipeline (5):** `reconcile.py` (the acceptance measure and the population bridge),
`controls.py` (P3-REC-12, and a control that could not express nil), `conform.py`,
`faults.py` (F02), `run.py`.

`test_phase_3_itself_changed_no_generator_module` asserts against git that Phase 3 changed
nothing, and `test_phase_3_1_changed_the_generator_only_where_the_defects_were` asserts that
every module Phase 3.1 moved is one the defect analysis named.

---

## 11. Financial reconciliation

### Group income statement, against the Phase 2 source-layer targets

| FY | Revenue | Cost of sales | Operating expenses | Worst deviation |
|---|---|---|---|---|
| 2023 | 328.000 / 328.000 | 236.260 / 236.260 | 62.500 / 62.500 | **0.000000%** |
| 2024 | 371.400 / 371.400 | 266.026 / 266.026 | 66.400 / 66.400 | **0.000000%** |
| 2025 | 462.635 / 462.635 | 332.555 / 332.555 | 78.735 / 78.735 | **0.000000%** |

Group revenue and cost of sales here include the intercompany legs, which is the basis the
source-layer target is stated on; both legs of every intercompany transaction are present
because this is layer 1 and nothing has been eliminated.

### Gross margin by business unit

Twelve business-unit-years. Mapped margin equals target margin at **0.000000** percentage
points in every one. `P3-REC-06` fails above 0.01pp — one basis point.

### External revenue by entity

Eleven operating entities × three years. Worst deviation **0.000000%**.

### Balance sheet, at closing rates

Worst deviation **0.008817%**, on trade receivables at FY2025 — USD 5.8 thousand on USD
65.5m. It is a translation artefact of the comparison, not a mapping difference: the
validation view translates a cumulative local balance at a single closing rate while the
anchor allocation was built at each year's own rate, so a caption whose entity mix shifts
through the year carries a small difference. FX translation is Phase 4's work (ADR-0005) and
this view is explicitly not it. Every other caption-year is inside 0.0001%.

The previous worst was **0.285480** — 28.5% — on contract assets, which was P2-D-01.

### Trial balances

| Proof | Worst | Threshold |
|---|---|---|
| native trial balance closes in each ERP's own convention | 0.0000 | 0.02 |
| still closes after sign normalisation | 0.0000 | 0.02 |
| still closes after mapping | 0.0000 | 0.02 |
| mapping changed no amount, line for line | 0.000000 | 0.005 |
| `fact_trial_balance` ties to `fact_journal_line` | 0.0000 | 0.02 |

### Intercompany

| Proof | Worst | Threshold |
|---|---|---|
| pairs match at the closing rate, every pair and period (`P2-IC-01`) | USD 0.1742 | 1.00 USD |
| flows match at the average rate (`P2-IC-03`) | USD 0.0165 | 1.00 USD |
| every intercompany posting names its counterparty (`P2-IC-02`) | 0 missing, 0 self-referencing | 0, 0 |
| investments reconcile to the register (`P2-INV-01`) | USD 0.0000 | 1.00 USD |

---

## 12. Determinism and reproducibility

A clean clone runs the whole chain:

```bash
python src/anchors/build_anchors.py     # anchors
python -m src.generation.build          # the source layer
python -m src.generation.validate       # 79 source controls
python -m src.generation.faults         # inject and detect the fault fixtures
python -m src.pipeline.run              # ingest -> conform -> 62 controls
python -m src.pipeline.faults           # the fixtures through the real pipeline
python -m pytest tests -q
```

| Evidence | Result |
|---|---|
| Phase 3 build id | `c073afea58cf0a5e` |
| Source layer digest | `375b1d81aa857d91…` |
| Artefacts checksummed in the manifest | 25 |
| Two **full** rebuilds, anchors onward | identical checksums on every committed artefact |
| Working tree after a full rebuild | **clean** |
| Phase 2 build | 20.8 s |
| Phase 3 pipeline | 43.1 s for 1,094,996 lines |
| Phase 3 controls | 2.4 s |
| Test suite | 33 s, **390 passed** |

Money is `DECIMAL(18,2)` from the standardised layer onward and every artefact is written in
a total order (ADR-0022), so the second run is byte-identical rather than merely equal.

One reproducibility hazard was found and closed in this pass. The fault fixtures are cut from
the raw extracts by a **separate** step, and regenerating the source without regenerating them
leaves every variant differing from the baseline in ways the fault did not cause — which
reads as ten detections and is ten pieces of noise. `src/pipeline/faults.py` now refuses to
run against fixtures older than the extracts they were cut from.


---

## 13. What this pass changed about how the platform is tested

Four lessons, recorded because each of them let a defect through a control that existed to
catch it.

**A control must be measured over the population it is about.** `P2-IC-01` tested the lines
that already carried a counterparty. It could not fail. This is not a subtle bug — it is a
filter that removes exactly the rows the control exists to find — and it survived two phase
gates. `P2-IC-02` now tests the whole intercompany population, and
`test_the_conversion_and_close_journals_are_not_a_blind_spot` asserts a non-empty population
before asserting anything about it.

**A measure must read the column the rule reads.** The acceptance sub-measure tested the
declared attribute where the rule evaluates a resolved field, and reported 67,246 correctly
classified rows as unclassifiable. It now calls `resolve_field`, the same function the rule
compiler calls, so the two cannot diverge again.

**A generator that cannot satisfy a contract should stop, not improvise.** The old
`_cost_centre` applied the required label whether or not the cost centre could carry it.
Raising instead found three inconsistencies between the approved economics and the department
master that had been silently absorbed for two phases.

**A fixture is only a fixture while it is cut from the current source.** The fault variants
are copies of raw extracts with one thing wrong in them, made by a step separate from the
source build. Regenerating the source without regenerating them turned every variant into a
different dataset, and the sweep reported nine detections that were nothing of the kind — the
most dangerous possible failure mode for a control-testing harness, because it looks like
success. The sweep now refuses to run against fixtures older than the extracts.

---

## 14. Limitations and open questions

1. **Two rule branches still never fire** on the current data — Sable `40900` reimbursables
   and Kestrel `00081200` own work capitalised. They are authored from the approved charts and
   are correct; they are simply unexercised.
2. **`stg_group_adjustment` is still empty and untested in anger.** Its schema is declared and
   `P3-ADJ-01` proves Phase 3 writes nothing to it, but no entry has passed through it.
3. **`ref_cta_expectation` remains a control input only.** It is what Phase 5's translation
   engine will be tested against (CTL-FX-12) and must never be joined into a reporting
   measure.
4. **The validation views translate at approved rates for comparison only.** They are views,
   not facts, and produce no CTA — but they are the first place a rate is applied to a ledger
   amount, and Phase 4 must not mistake them for a translation engine. The 0.0088% trade
   receivable deviation in §11 is a property of that comparison, not of the data.
5. **The intercompany trade current account interpolates between year ends.** Both sides of a
   pair now interpolate the *same* USD figure, so the pair matches at every closing rate, but
   the monthly path itself is an interpolation and not a driven one. That is documented rather
   than hidden, and it is unchanged in kind from the Phase 2 design.

---

## 15. Recommended Phase 4 scope

Unchanged from the Phase 3 report except that **item 1 is now done**. In dependency order:

1. **FX translation and the CTA.** Monthly average for the income statement, closing rate for
   the balance sheet, historical rates for equity from `ref_fx_rate_historical` (FX-P03), CTA
   computed to layer 5 and tested against `ref_cta_expectation` (CTL-FX-04, CTL-FX-12,
   ADR-0017). CTA must never be entered as a plug, and `P3-BR-03` has already proved there is
   no source-layer reserve for it to hide in.
2. **Intercompany elimination by entity pair**, layer 2. No longer blocked: 100% of the
   position is attributable, every pair nets to under USD 1.00 at closing rates, and
   `CTL-IC-01` has something to measure. Fault fixture F02 is the acceptance test for it.
3. **Investment elimination** across the full ownership tree, from `ref_investment_register`
   and `ref_investment_rollforward`, layer 3. Every holding now names its subsidiary.
4. **Purchase price allocation and acquired intangible amortisation**, layer 3.
5. **NCI allocation** — income, equity and the NCI share of CTA — from `ref_ownership`,
   layer 3.
6. **Unrealised profit in inventory**, from `ref_ic_inventory_holding`'s FIFO layers, layer 3.
7. **The management adjustment layer**, layer 4, raised through `stg_group_adjustment`.
8. **Cash flow derived from balance sheet movements** (ADR-0006).

Phase 4 should not touch `src/generation/` or `src/pipeline/` other than to consume their
output.

---

**Phase 3.1 is complete.** All four source defects are closed at the generation layer, the
source layer is regenerated from code, every ingested row has an explicit disposition, the
mapping gate is met at 100.000000% with no exclusions, and both control baselines are clean.
