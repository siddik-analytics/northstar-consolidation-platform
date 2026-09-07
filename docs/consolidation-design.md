# Consolidation Design

How twelve legal entities, on three ERP systems, in four currencies, become one set of
group financial statements — and how every step of that journey can be traced backwards.

## 1. Design principles

1. **Nothing is netted before it is understood.** Every transformation between the source
   trial balance and the consolidated result is a separately identifiable, separately
   reportable layer. The reconciliation from "what the ERPs said" to "what the board sees"
   is a standing output, not an investigation.
2. **Consolidation is deterministic and repeatable.** Given the same source data and the
   same configuration, the engine produces byte-identical output. There are no manual
   spreadsheet steps in the critical path.
3. **Adjustments are data, not code.** Eliminations, consolidation entries and management
   adjustments are rows with identifiers, owners, approvers and narratives — never a
   hard-coded `CASE` statement.
4. **Statutory and management views are separated at the architecture level**, not by
   filtering at report time. A management normalisation can never accidentally change the
   reported result.
5. **CTA is computed, never plugged.** If the translation engine's CTA disagrees with an
   independent expectation, the engine is wrong and the period does not close.

## 2. The consolidation layer model

Every row in `fact_financials` carries a `layer_id`. The layer determines which reporting
basis the row belongs to. This is the single most important structural decision in the
platform (ADR-0003).

**There are exactly five layers.** The canonical, machine-readable definition is
[`config/dimensions/consolidation_layer.csv`](../config/dimensions/consolidation_layer.csv);
`dim_layer` is built from it, and every document below is derived from the same file. No
other layer exists, and a fact row carrying any other `layer_id` is rejected by
`CTL-CON-09`.

| # | Code | Name | Posting source | Posted to | Statutory | Management | Balances alone |
|---|---|---|---|---|---|---|---|
| **1** | `REPORTED` | Entity Reported | Source ERP extract | Real legal entities | ✅ | ✅ | ✅ |
| **2** | `IC_ELIM` | Intercompany Eliminations | Elimination engine | `ELIM-IC` | ✅ | ✅ | ✅ |
| **3** | `CONSOL_ADJ` | Consolidation Adjustments | Consolidation engine | `ELIM-CON` | ✅ | ✅ | ✅ |
| **4** | `MGMT_ADJ` | Management Adjustments | Manual, approved | `ELIM-MGT` | ❌ | ✅ | ✅ |
| **5** | `FX_CTA` | Translation Adjustment | Translation engine | Real legal entities | ✅ | ✅ | ❌ |

```
Consolidated (statutory)  =  L1 + L2 + L3 + L5          layer_id IN (1,2,3,5)
Management view           =  L1 + L2 + L3 + L5 + L4      layer_id IN (1,2,3,4,5)
```

**What each layer contains**

| # | Contents |
|---|---|
| 1 | Source trial balances from Aurora, Sable and Kestrel — sign- and locale-normalised, mapped to the group chart of accounts, translated into USD. The only layer originating outside the platform. |
| 2 | Elimination of intercompany revenue, cost of sales, management fees, royalties, interest, receivables, payables and loans, generated from matched entity pairs. |
| 3 | Investment-in-subsidiary elimination across the full ownership tree, purchase price allocation and acquired intangible amortisation, NCI allocation of profit and equity, and unrealised profit in inventory. Statutory entries that **change** the consolidated result rather than netting to nil. |
| 4 | Normalisations, reclassifications and pro-forma presentation entries prepared and approved by finance. **Excluded from the statutory result.** |
| 5 | The cumulative translation adjustment. Posted to the **real foreign entity** it belongs to, not to a virtual entity, because entity-level CTA is a genuine reporting requirement. |

**Two properties that are easy to get wrong**

*Why layer 5 does not balance independently.* Layers 2, 3 and 4 are self-balancing sets of
journal entries — debits equal credits within each layer for every period. Layer 5 is not: it
is the balancing entry that makes the **translated** layer-1 trial balance sum to zero. Testing
it for independent balance would fail every period. `CTL-IC-06` and `CTL-CON-07` therefore
apply to layers 2–4 only, and `CTL-TB-03` covers layers 1 and 5 together.

*Why layer 5 is posted to real entities.* Every other consolidation entry goes to a virtual
entity so that entity-level reported figures still agree with the entity's own trial balance
(ADR-0014). CTA is the exception: it is an attribute of a specific foreign operation, and
"what is Halden's CTA?" is a question the group needs to answer. Posting it to `ELIM-CON`
would make it unattributable.

Layer 4 exists because the alternative is worse. In most hand-built consolidations,
"management adjustments" are made inside the consolidated numbers and then backed out for
statutory reporting — which means the statutory number is derived by subtraction from a
management number, and nobody can be certain what was removed. Here the statutory result is
the primary number and the management view is the derived one. The direction of derivation
matters: it is far easier to defend a management view built on top of an audited base than
an audited base reconstructed out of a management view.

Control `CTL-CON-06` asserts that the statutory result excludes layer 4 entirely.

## 3. Consolidation grain

`fact_financials` is stored at **one row per**:

```
entity × group account × cost centre × intercompany partner × period (month)
        × scenario × version × layer
```

Everything above this grain is an aggregation and everything below it lives in
`fact_journal_line` (actuals only) or a dedicated detail fact.

**Why monthly and not daily.** Consolidation is a monthly process. Budget and forecast do
not exist at a daily grain, so a daily consolidation fact would be empty for two of the
three scenarios and would multiply the row count by thirty for no analytical gain.
Transaction-level traceability is preserved in `fact_journal_line`, which drills through
from any consolidated figure.

**Why customer and product are not on this grain.** Attaching customer and product to the
GL fact would multiply its cardinality by several orders of magnitude while remaining
undefined for the overwhelming majority of rows — there is no customer dimension on an
accrued audit fee. Revenue and cost-of-sales analytics live in `fact_revenue_detail`, which
is reconciled to the GL revenue accounts by control `CTL-REC-02`. See ADR-0008.

## 4. Consolidation sequence

The engine runs in a strict order. Each step is idempotent and each has its own controls.

```
  1. INGEST      Load raw ERP extracts to staging, preserving source values verbatim
  2. NORMALISE   Apply per-ERP sign, locale, date and account-code conventions
  3. VALIDATE    CTL-DQ-*, CTL-TB-01: does each entity's own trial balance balance?
  4. MAP         Apply effective-dated group COA mapping, including conditional splits
  5. VALIDATE    CTL-MAP-*, CTL-TB-02: does it still balance after mapping?
  6. TRANSLATE   Local -> USD per the FX policy; derive CTA; build the constant-currency column
  7. VALIDATE    CTL-FX-*, CTL-TB-03: does it balance in USD, and is CTA explainable?
  8. ELIMINATE   Intercompany eliminations to ELIM-IC
  9. CONSOLIDATE Investment eliminations, NCI, PPA, unrealised profit to ELIM-CON
 10. ADJUST      Management adjustments to ELIM-MGT (management view only)
 11. DERIVE      Cash flow statement from balance sheet movements
 12. VALIDATE    CTL-FS-*, CTL-IC-*, CTL-CON-*, CTL-REC-*: full statement integrity
 13. PUBLISH     Reporting marts, only if no BLOCKING control has failed
```

A blocking control failure stops the pipeline at that step. Nothing downstream is
published from a period that has not passed its controls — the alternative is a board pack
built on a trial balance that does not balance, which is how consolidations lose credibility.

## 5. Chart-of-accounts harmonisation

### 5.1 The group chart

The group chart of accounts ([`config/coa/group_coa.csv`](../config/coa/group_coa.csv))
has 181 accounts (72 balance sheet, 96 income statement, 13 statistical) across a
six-digit numbering scheme where the leading digit encodes the
statement section:

| Block | Section | Notes |
|---|---|---|
| `1xxxxx` | Assets | |
| `2xxxxx` | Liabilities | |
| `3xxxxx` | Equity | |
| `4xxxxx` | Revenue | `49xxxx` reserved for intercompany revenue |
| `5xxxxx` | Cost of sales | `59xxxx` reserved for intercompany cost of sales |
| `6xxxxx` | Operating expenses | `68xxxx` non-recurring add-backs, `69xxxx` intercompany |
| `7xxxxx` | D&A, impairment and non-operating | `79xxxx` intercompany financing |
| `8xxxxx` | Income tax | |
| `9xxxxx` | Statistical | Excluded from the trial balance entirely |

Each account carries the attributes the engine needs to behave correctly without special
cases: `fx_method`, `cash_flow_category`, `is_intercompany`, `is_ebitda`,
`is_ebitda_addback`, `is_statistical` and `include_in_tb_balance`. Reporting hierarchies
are flattened onto the account rather than held as a parent-child structure (ADR-0010).

Two decisions worth stating explicitly:

**Statistical accounts are in the same fact table but outside the trial balance.** Headcount,
billable hours, bookings and backlog live in `9xxxxx` accounts so that they share the same
entity, cost centre, period and scenario dimensionality as financial data — which is what
makes revenue-per-FTE and utilisation trivially computable. They are excluded from every
debits-equals-credits test. Including them would make the fundamental control fail every
month, and a control that always fails is a control nobody reads. See ADR-0012.

**Non-recurring costs sit inside operating expenses, flagged as add-backs.** Restructuring,
transaction costs and the ERP programme are genuinely operating costs and belong above
EBITDA in the reported statements. Adjusted EBITDA is then reported EBITDA plus the sum of
accounts where `is_ebitda_addback = TRUE`. This makes the add-back list a visible,
reviewable data attribute instead of a formula buried in a spreadsheet. See ADR-0013.

### 5.2 Mapping architecture

Mappings are **effective-dated configuration**, not code (ADR-0007):

```
source_account + erp_system + effective_from  ->  group_account
                                              +  mapping_type
                                              +  mapping_rule (for conditional splits)
```

Four mapping types:

| Type | Meaning | Example |
|---|---|---|
| `DIRECT` | One source account to one group account | Aurora `1100` → `120100` Trade receivables |
| `MERGE` | Several source accounts to one group account | Aurora `1010`, `1015`, `1020` → `110100` Cash |
| `SPLIT` | One source account to several group accounts, resolved by another attribute | Aurora `6100` Salaries → direct labour or SG&A, by department |
| `DERIVED` | Requires a transformation beyond a code substitution | Kestrel `00081000` inventory movement → cost of sales, with sign reversal |

Mappings are never edited retrospectively. A change creates a new effective-dated row, so a
closed period always re-computes to the same answer (`CTL-MAP-07`).

### 5.3 The three mappings that actually matter

Most of the 391 source accounts map one-to-one and are uninteresting. These three are
where a consolidation goes wrong:

**(a) Payroll that spans the gross margin line.** Aurora `6100` and Kestrel `00091000` book
all wages to a single account irrespective of function. Whether a given dollar is direct
labour (cost of sales) or SG&A (operating expense) is determined only by the department or
cost centre. Consequences if handled badly:

- Defaulting everything to SG&A moves roughly $60m of FY2025 cost below gross profit,
  inflating group gross margin from 29.0% to about 43% and making EBITDA unchanged but
  every margin metric meaningless.
- Defaulting everything to cost of sales does the reverse.

The rule is explicit in the mapping file, and `CTL-MAP-04` fails the load if any line falls
through it without resolving. There is no default.

**(b) The German total-cost-method presentation.** Kestrel entities report on the
*Gesamtkostenverfahren*, where `00081000` (change in finished goods inventory) and
`00081200` (own work capitalised) appear **above the revenue line**. Under the group's
cost-of-sales presentation both belong in cost of sales, with a sign reversal. Leaving them
in revenue overstates both revenue and gross profit for three of twelve entities.
Enforced by `CTL-MAP-08`.

**(c) Affiliate interest buried in third-party interest.** Kestrel `00100000` mixes both.
Intercompany interest that is not routed to `795200` is never eliminated, which overstates
consolidated net interest and — because interest coverage is a tested covenant — reports a
covenant ratio that is wrong in the direction that matters. Enforced by `CTL-IC-05`.

### 5.4 Unmapped accounts

Unmapped source accounts are **never** defaulted into a catch-all "other expenses" account.
They are posted to a suspense account, reported by `CTL-MAP-01` as a blocking failure, and
the period does not close until they are mapped. A catch-all default is worse than a
failure because it produces a plausible-looking number that is quietly wrong.

## 6. FX translation

Full policy: [`config/fx/fx_translation_policy.csv`](../config/fx/fx_translation_policy.csv)
(22 rules). Rationale: [ADR-0005](adr/0005-fx-translation-method.md).

**The complete translation policy — including the acquisition-date basis, the deterministic
CTA roll-forward, the NCI share of the translation movement, and the split of the FX effect
between cash and non-cash in the cash flow statement — is specified in
[`docs/fx-cta-policy.md`](fx-cta-policy.md).** The summary below covers the method; that
document is authoritative on the detail.

### 6.1 Method

The group applies the **current rate method** to all foreign operations. No entity operates
in a hyperinflationary economy and each entity's functional currency is its local currency,
so the temporal method is not in scope.

| Item | Rate | Why |
|---|---|---|
| Income statement | **Monthly average** of the posting month | Revenue and cost are earned through the month |
| Assets and liabilities | Closing spot at period end | Current rate method |
| Contributed capital, pre-acquisition reserves | Historical, frozen at contribution or acquisition | Isolates CTA |
| Opening retained earnings | Prior period's closing USD balance, never retranslated | Makes CTA an arithmetic residual |
| Current year result in equity | Sum of monthly translated P&L | Must equal the translated income statement |
| CTA | Computed residual | Never an input |
| Statistical accounts | Not translated | Not monetary |

### 6.2 Monthly average, not annual average

Each month's income statement is translated at that month's average rate, and year-to-date
figures are the **sum of translated months**. Applying a year-to-date average rate to a
year-to-date balance produces a different — and wrong — answer whenever activity is not
evenly spread across the year, which it never is in a business with turnaround seasonality
and project milestones.

This also makes the reconciliation clean: control `CTL-FX-03` asserts that the sum of
monthly translated P&L equals the movement in the current-year result equity account. If
the model translated year-to-date, that control could not exist.

### 6.3 Rate quotation

**Every rate in the platform is stored as USD per one unit of foreign currency.** Translation
is therefore always a multiplication. Mixed quotation conventions are a recurring source of
inverted-rate errors that are hard to spot because the resulting numbers still look like
numbers. Rates are validated on load against per-currency plausible bands (`CTL-FX-05`), and
`tests/test_anchors.py::test_fx_rates_are_quoted_as_usd_per_unit` enforces this on the
anchor set.

### 6.4 Rate sets

| Rate set | Applies to | Behaviour |
|---|---|---|
| `ACTUAL` | Actual scenario | Actual monthly average and closing rates |
| `BUDGET` | Budget scenario | Locked at budget approval. **Never restated.** |
| `FORECAST` | Forecast scenario | Actual rates for closed months, forwards for open months, frozen at version issue |

The budget is translated at budget rates and never restated because restating it destroys
accountability: a manager cannot be held to a target that moves after they agreed it. The
FX effect is instead isolated by the constant-currency view.

### 6.5 Constant currency

`fact_financials` carries **three amount columns**: `amount_local`, `amount_usd` and
`amount_usd_cc` (actual local amounts retranslated at budget rates). FX impact is then
simply `amount_usd − amount_usd_cc`.

Storing the constant-currency amount rather than computing it at query time is a deliberate
trade-off: it costs one column of storage and removes a rate join from the hot path of every
variance visual. Given that FX appears in essentially every management report this group
produces, that is the right trade.

### 6.6 CTA

CTA is the balancing figure that arises because assets and liabilities are translated at
closing rates while equity is translated at historical and derived rates. It is held as an
explicit three-account roll-forward — opening (`330100`), movement (`330200`) and recycling on
disposal (`330300`) — so that closing CTA is a derived caption rather than a moving balance,
and continuity across periods is testable (`CTL-FX-09`). It is **computed by the engine and
then independently verified**:

```
Expected CTA movement  =  opening net assets × (closing rate − prior closing rate)
                       +  current year result × (closing rate − average rate)
                       +  effect of capital movements at their transaction rates
```

`CTL-FX-04` compares the engine's CTA to this expectation. A variance above 0.5% of the
movement is a warning; above 2% is blocking. CTA entered by hand as a plug is the single
most common way a consolidation hides a translation defect, and this control exists
specifically to make that impossible.

The NCI share of the CTA movement is allocated to non-controlling interests (`340400`) rather
than group equity (`330200`), in proportion to ownership effective for the period. Allocating
100% of a partially owned subsidiary's CTA movement to group equity overstates group equity and
understates NCI by the same amount — and because both sit inside total equity, the balance sheet
still balances and nothing else catches it (`CTL-CON-11`).

### 6.7 Intercompany FX

Both sides of an intercompany balance translate at the same closing rate, so a pair
denominated in one currency eliminates exactly. Where the two entities record the balance in
**different** currencies — for example the GBP-denominated `NIG-320` receivable against the
EUR-functional `NIG-410` — a residual arises. That residual is a genuine FX gain or loss and
is posted to `740100`, not absorbed into the elimination. `CTL-IC-03` ages any unresolved
residual so that a chronic mismatch cannot hide behind a monthly rounding tolerance.

## 7. Intercompany elimination

### 7.1 Identification

Intercompany transactions are identified by **two independent mechanisms**, both required:

1. **Dedicated accounts.** `49xxxx`, `59xxxx`, `69xxxx`, `79xxxx` and the intercompany
   balance sheet accounts carry `is_intercompany = TRUE`.
2. **The partner dimension.** Every posting to an intercompany account carries an
   `ic_partner_key` naming the counterparty entity.

Accounts alone are insufficient because intercompany activity leaks into ordinary accounts.
The partner dimension alone is insufficient because it is not always populated at source.
Requiring both, and testing that they agree (`CTL-IC-04`), catches what either would miss
alone. A posting whose partner is the posting entity itself is rejected outright.

### 7.2 What is eliminated

| Flow | Eliminated against | Net effect on consolidated result |
|---|---|---|
| Management fee income / expense | Each other | Nil |
| Intercompany product and service revenue / cost of sales | Each other | Nil |
| Royalty income / expense | Each other | Nil |
| Intercompany interest income / expense | Each other | Nil |
| Intercompany receivables / payables | Each other | Nil |
| Intercompany loans receivable / payable | Each other | Nil |
| **Unrealised profit in inventory** | Inventory and cost of sales | **Not nil — reduces both** |

Elimination entries are posted to the virtual entity `ELIM-IC` and always balance
(`CTL-IC-06`). Consolidated balances on intercompany accounts are nil (`CTL-IC-07`), with
the single deliberate exception of `130500`.

### 7.3 Unrealised profit in inventory

When `NIG-200` sells to `NIG-210` at cost plus 12% and `NIG-210` still holds the goods at
period end, group profit has been recognised on a transaction that has not left the group.
That profit must be removed:

```
Dr  Cost of sales — unrealised profit adjustment
Cr  Inventory — unrealised profit in inventory (130500)

Amount = intercompany inventory held at period end × transfer margin
```

FY2025 anchor: **$0.70m**. Where the holding entity is `NIG-510` (80% owned), the
adjustment is shared between group and NCI in proportion to ownership. This is the
elimination most often missed in spreadsheet consolidations, because it requires knowing
what proportion of closing inventory was bought internally — information the GL alone does
not carry. `CTL-IC-08` enforces it.

### 7.4 Cut-off differences

If one entity records an intercompany transaction in March and the counterparty records it
in April, the elimination does not net. The design treats this as a **genuine finding**
reported by `CTL-IC-02`, not as noise to be absorbed. Absorbing timing differences into a
tolerance is how intercompany balances drift for years.

## 8. Consolidation adjustments

Posted to `ELIM-CON`. All are statutory (layer 3).

| Adjustment | Description |
|---|---|
| Investment elimination | Investment in subsidiary (`178100`) against the subsidiary's share capital and pre-acquisition reserves. Walks the **full ownership tree**, including second-tier holdings. |
| Purchase price allocation | Fair value uplifts on acquired intangibles and the associated deferred tax, plus goodwill as the residual |
| Amortisation of acquired intangibles | PPA intangibles amortised over 8–12 years, run at group level rather than pushed down |
| NCI allocation — income | 20% of `NIG-510` net income to non-controlling interests |
| NCI allocation — equity | 20% of `NIG-510` closing net assets, including the NCI share of CTA |
| Unrealised profit in inventory | Per section 7.3 |

**Ownership and consolidation method.** All twelve operating entities are fully
consolidated at **100%**, with the 20% of `NIG-510` not owned by the group presented
separately within equity and below tax in the income statement. Proportionate consolidation
is never used. Ownership percentages are effective-dated in
[`config/entities/ownership_history.csv`](../config/entities/ownership_history.csv) and
applied per period, never retrospectively (`CTL-CON-10`).

There are no equity-method investees, joint ventures or discontinued operations in scope — a
deliberate scope decision recorded in ADR-0009.

**The complete non-controlling interest treatment — consolidation mechanics, share of result,
the five-account equity roll-forward, dividends, effective dating, acquisition and disposal
changes, cash flow presentation, statutory versus management treatment and elimination
implications — is specified in [`docs/nci-policy.md`](nci-policy.md).**

**Consolidation effective dates.** Acquired entities are consolidated from their acquisition
date, not from the start of the fiscal year. `NIG-220` contributes nine months of FY2023 and
`NIG-410` six months of FY2024. `CTL-CON-02` blocks any period outside an entity's effective
window. Consolidating Halden from January 2023 rather than April would overstate FY2023
revenue by roughly $6m and quietly corrupt the organic growth bridge.

## 9. Management adjustments

Posted to `ELIM-MGT` (layer 4). **Excluded from the statutory result.**

| Type | Purpose | Example |
|---|---|---|
| `NORMALISATION` | Remove or annualise items that distort run-rate performance | Full-year effect of a mid-year acquisition for a pro-forma view |
| `RECLASS` | Present a cost where management holds accountability rather than where it was booked | Shared services cost allocated to consuming business units |
| `ONE_TIME` | Isolate an item already flagged as non-recurring for a specific analysis | Separating restructuring by programme |
| `ACQUISITION` | Purchase accounting effects presented separately for the underlying view | Amortisation of acquired intangibles shown apart from organic D&A |
| `PROVISION` | Management's view of a provision where it differs from the statutory position | |

Every adjustment carries an `adjustment_id`, type, preparer, approver, narrative, effective
period and reversal flag. Nothing is posted anonymously (`CTL-CON-07`), and adjustments
flagged as reversing are checked for their reversal in the following period
(`CTL-CON-08`).

Reclassification adjustments must net to nil within the income statement; only
normalisations change a subtotal. This is asserted rather than assumed.

## 10. Cash flow statement

The consolidated cash flow statement is **derived**, not sourced (ADR-0006). Each balance
sheet account carries a `cash_flow_category`, and the statement is built from the period
movement in each account, adjusted for non-cash movements (FX translation, acquisitions,
non-cash lease additions).

```
Net change in cash  =  Δ(liabilities) + Δ(equity) − Δ(non-cash assets)
```

Because the statement is an algebraic rearrangement of the balance sheet, it ties to the
movement in cash **by construction**. `CTL-FS-03` asserts it anyway, because the property
only holds if every balance sheet movement is categorised into exactly one cash flow line —
which is what `CTL-FS-04` enforces.

Three movements need explicit handling or the reconciliation breaks:

| Movement | Treatment |
|---|---|
| FX on foreign-currency cash | Presented as "effect of exchange rate changes on cash" |
| FX on foreign-currency working capital | A non-cash reconciling item within operating activities, **not** a working capital swing |
| Working capital acquired in a business combination | Excluded from the operating movement; the whole consideration sits in investing |

That third one is the classic error. An acquisition that brings $6.6m of working capital
with it will, if not excluded, appear as a $6.6m operating cash outflow that never happened.

## 11. Source-to-consolidated reconciliation

The headline auditability deliverable (`CTL-REC-01`). A single statement, produced every
period without being asked for:

| Step | FY2025 illustrative |
|---|---|
| Sum of source system trial balances, as extracted | Local currency by entity |
| Effect of sign and locale normalisation | Nil by design — proves nothing was lost |
| Effect of chart-of-accounts mapping | Nil in total; reclassification within the P&L |
| Effect of FX translation | Reconciles local to USD; CTA identified separately |
| Intercompany eliminations | Revenue $50.5m, balances $59.6m |
| Consolidation adjustments | Investment elimination, PPA, NCI, unrealised profit $0.70m |
| **Consolidated statutory result** | Revenue $412.1m, Adjusted EBITDA $57.8m |
| Management adjustments | Layer 4, separately identified |
| **Management view** | |

Every difference between what the ERPs say and what the board sees is named and quantified.
This is the artefact that answers "where did this number come from?" in one page rather than
one week.

## 12. Scenario handling

| Scenario | Stored? | Grain | FX rate set |
|---|---|---|---|
| Actual | Yes | Full consolidation grain | `ACTUAL` |
| Budget | Yes | Same grain, one locked version per year | `BUDGET` |
| Forecast | Yes | Same grain, multiple rolling versions | `FORECAST` |
| Prior Year | **No — derived** | Actual offset by twelve months | `ACTUAL` |

**Budget and forecast share the actual grain.** They are not held in a separate, coarser
fact table. This is what makes variance analysis a simple subtraction rather than an
allocation exercise, and it means a variance can be drilled to the same cost centre and
account as the actual (ADR-0002).

**Prior year is derived, not stored.** Storing it would duplicate every actual row and
create a restatement hazard: if a prior period is corrected, a stored prior-year copy
silently diverges. A date offset over the Actual scenario cannot diverge, and `CTL-SCN-05`
proves the two approaches agree (ADR-0004).

**Budget and forecast both open from the prior year's actual close.** They are alternative
views of the same fiscal year, so the FY2026 forecast balance sheet rolls forward from the
FY2025 actual close — never from the FY2026 budget. Rolling a forecast forward from a budget
compounds two different views of one year and is a defect that is very hard to see in
summary output. This is tested by
`tests/test_anchors.py::test_retained_earnings_rolls_forward`.

**Rolling forecast architecture.** A forecast version records how many months are actual and
how many are forecast (`FC_FY26_08` is 8+4). The actual months in a forecast version must be
byte-identical to the Actual scenario (`CTL-SCN-02`) — an 8+4 forecast whose first eight
months disagree with actuals is not a forecast. Nothing in the model is bounded to a single
fiscal year; `FC_FY27_P1` exists as a placeholder to prove it.
