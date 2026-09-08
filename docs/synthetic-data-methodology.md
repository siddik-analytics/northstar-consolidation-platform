# Synthetic Data Methodology

How Phase 2 generates 1.08 million journal lines that balance, tell a coherent business
story, reconcile to the approved anchors, and reproduce byte-for-byte from a fixed seed.

---

## 1. The problem with synthetic financial data

The usual approach is bottom-up: draw amounts from plausible distributions, assign them to
accounts, and see what emerges. The result fails in a characteristic way. Gross margin
wanders for no reason. Working capital bears no relation to revenue. The balance sheet
needs a plug. And there is no *story* — no variance has a cause, because nothing caused
anything.

That failure is fatal for this engagement, because the deliverable is management reporting
and management reporting is the business of explaining why numbers moved.

Phase 2 therefore inverts the usual order. The anchors came first, in Phase 1, as an
executable model. Phase 2's job is to produce transactions that *land on them*.

```
approved anchors  →  entity x period position  →  balanced journals  →  native extracts
   (Phase 1)              (this phase)              (this phase)         (this phase)
```

---

## 2. Four rules the generator obeys

**1. Every journal balances.** Amounts are emitted as balanced entries, never as
independent postings later reconciled. Each entry's legs are rounded and the residual
pushed onto the largest leg, so an entry balances to the cent, not approximately.

**2. Cash is never targeted.** Cash is the residual of the transactions — receipts less
payments — exactly as in a real ledger. This is what makes the trial balance close by
construction rather than by a plug, and it is why a modelling error shows up as an
implausible cash balance rather than being silently absorbed.

**3. Anchors are pushed down exactly.** Every allocation uses a largest-remainder split
(`allocate_exact`) so that a pushdown from group to entity, or from year to month, never
leaks a rounding difference. Group revenue is the anchor to the cent, not to within 0.4%.

**4. Local currency is genuine.** Entity ledgers are built in each entity's own functional
currency with real local seasonality — not USD amounts divided by a rate, which would leave
an FX wobble in a German entity's euro revenue that has no economic cause.

---

## 3. How an entity-period position is built

### 3.1 Annual pushdown to entities (USD)

| Line | Driver |
|---|---|
| Revenue | The approved entity revenue anchors directly |
| Gross profit | Business unit gross profit, split by revenue with a mean-neutral entity margin tilt |
| Operating expense | Corporate entities take a fixed share; the rest split 60% by revenue, 40% by headcount |
| Non-recurring items | Allocated to the entities that actually bore them, per the business story |
| Depreciation, capex | Revenue weighted by capital intensity |
| Interest | Term debt and facilities at Topco; finance lease interest at the lessee |
| Current tax | Positive pre-tax profit, floored so loss-making entities still pay some local tax |

Share-based compensation and its reserve are swept to the corporate entities, because they
are granted centrally — no operating entity's ERP carries either account.

### 3.2 Conversion to local currency

Each entity-year converts at a **revenue-weighted** average rate:

```
weighted_rate  = Σ (monthly seasonality share × monthly average rate)
local_annual   = usd_annual / weighted_rate
local_month    = local_annual × seasonality share
```

The consequence is worth stating: translating the resulting monthly local series back at
**monthly** average rates reproduces the USD anchor **exactly**, while the local series
itself carries no FX artefact. Monthly USD amounts still vary with the rate, which is
precisely the variation that will generate CTA and FX variance in Phase 4.

### 3.3 Seasonality

Every business unit has its own amplitude and peak month — Industrial Services peaks in
September with turnaround season, Flow Control in November, Engineered Systems in December
on project completions, Aftermarket is nearly flat. Costs are smoother than revenue.
Month-to-month noise is applied on top so the series is not drawn with a ruler.

### 3.4 Balance sheet — driver-generated months

Year-end balances are the anchored group captions, allocated to entities by economic driver
(receivables by revenue × entity DSO tilt, inventory only where goods are actually held,
payables by cost × DPO tilt, and so on) and converted to local at that entity's closing
rate.

**Interim months are generated from the economics that move each balance, not interpolated
between year ends.** Phase 2.0 interpolated, and the result was a visible straight line
month to month — the single most obvious tell that a dataset is manufactured, and the first
thing a reviewer opening a monthly balance sheet would notice. Each caption now has a driver:

| Caption | What moves it |
|---|---|
| Trade receivables | an ageing profile applied to recent billing, with the tail length set by the entity's DSO |
| Allowance for doubtful debts | assessed against the receivables ledger, so it moves with the ledger it provides for |
| Inventory | opening + purchases − cost of sales, with a seasonal build ahead of demand |
| Trade payables and goods received | an ageing profile over recent purchases and cash expenses, from the entity's DPO |
| Accrued payroll | the unpaid portion of the month's payroll on a real payday calendar |
| Accrued bonus | accretes monthly, paid out in March — a sawtooth, not a line |
| Accrued interest | accretes monthly, settled quarterly **in arrears** in the month after each interest period, so a quarter's accrual is always outstanding at the balance sheet date |
| Tax payable | accretes monthly, paid quarterly |
| Prepayments | annual contracts paid up front at staggered renewals (insurance January, software April, maintenance July, licences October) and released a twelfth a month |
| PP&E | opening + lumpy project completions − depreciation; capital spend steps, it does not ramp |
| Term loan | an instrument schedule: scheduled quarterly amortisation, drawdowns on their actual dates, voluntary prepayment at the year end |
| Revolving facility | drawn to the group's own liquidity need and repaid out of collections (§3.5) |

Each path is then scaled by a single factor per year so **December lands exactly on the
anchored year-end balance**. Drivers supply the shape; the approved anchor supplies the
level. The factor is blended from the prior year's factor across the twelve months so the
anchor is imposed without a step at the year boundary and without flattening the shape.

Two guards make this safe rather than merely convenient. A path is first *oriented* to the
sign of the caption it represents, because the drivers produce magnitudes — without that, a
credit caption such as payables receives a negative factor and, blended against the prior
year, crosses zero mid-year, producing a payables balance that starts the year as a debit.
And the build **fails** if December sits at a trough of its own driver path (below 20% of
the path's average magnitude), because scaling a trough onto the anchor would inflate the
other eleven months absurdly. That guard is not decorative: during Phase 2.1 it caught
accrued interest settling on the balance sheet date and prepayments whose every policy
expired in December, both of which are modelling errors in the driver rather than something
to scale away.

Control `P2-BR-04` measures this. `linearity` is 0.0 for a perfect straight line and rises
with genuine driver-generated movement; every working-capital and accrual caption now scores
between 0.09 and 0.86, against 0.00 for the Phase 2.0 interpolation. Accumulated
depreciation and scheduled term debt amortisation are deliberately **excluded** from the
test: a stable asset base depreciated straight-line genuinely produces a near-constant
monthly charge, and a term loan genuinely amortises on a fixed schedule, so demanding
curvature of them would be demanding noise.

Retained earnings roll forward from each entity's own locally-measured net income. Cash is
the residual of the balanced journals.

Accounts are also restricted to the entities that can actually have them. Accrued interest
is the clear case: an entity that borrows nothing accrues no interest, and giving it a
balance leaves a driver-generated path with nothing to explain it. The caption's share is
renormalised across its remaining accounts for those entities.

### 3.5 Treasury pooling and the revolving facility

Operating entities sweep surplus cash to Topco through an intercompany treasury current
account. Without it, every operating entity accumulates cash while Topco — which carries all
the external debt, paid for the acquisitions and funds the subsidiaries — runs a large
negative bank balance that no real group would tolerate. Pooling only *redistributes* cash:
the group total is untouched, and both legs are in the operating entity's currency so the
pair eliminates exactly.

The pool has exactly one counterparty on each side and always has had — the participant's
current account is with Topco and Topco's is with that participant — and since Phase 3.1
every posting to it **says so**. Topco's side of the pool divides between the participants in
proportion to what each of them holds, so the parts sum to the whole in every period.

Pooling redistributes; it does not create liquidity. A month in which working capital builds
faster than the business collects still leaves the group short, and Phase 2.0 left 76
entity-months with a negative bank balance as a result. A real group draws its revolver —
which is what the facility is for, and why the anchor model carries a drawn balance at every
year end. So the revolver is generated as the group's liquidity instrument:

- the position the balanced ledgers produce with the facility undrawn sets the need;
- the group targets a **minimum operating balance that moves with trading activity**, because
  a busier month needs more cash on hand to run;
- draws are requested in round half-millions, because that is how a borrowing notice is
  actually submitted, and repayments are made in blocks only once there is a worthwhile
  surplus — no treasurer repays half a million and redraws it a month later, so the balance
  is sticky, as a real facility is;
- **December is set to the approved year-end anchor**, so the entry and exit points of every
  year remain exactly the balances the anchor model proved;
- drawings never exceed the $60m commitment (`P2-BR-05`).

No entity now runs a materially negative bank balance in any month (`P2-BR-01`).

Treasury policy is **configuration, not a constant buried in the generator**.
`config/debt/treasury_policy.csv` holds the year-end minimum and target cash balances, the
intra-year operating floor and the headroom requested above it, the borrowing-notice
increment, the repayment block, the minimum surplus before repaying, and the two dates on
which the facility actually moves. Both the anchor model and this generator read it, so a
policy cannot be changed in one layer and left in the other.

#### The facility resolved to a daily balance

A month-end balance cannot price a facility. Interest accrues on the **daily drawn** balance
and the commitment fee on the **daily undrawn** commitment, so the intra-month position has to
exist. It follows the dates the credit agreement and the board policy already fix: a drawing
is taken on the borrowing-notice date early in the month, because it funds the supplier
payment run and the payroll disbursement; a repayment is made on the collections sweep date
late in the month, once the month's receipts have cleared. The balance is therefore a step
function with one step, which makes the average daily balance exact rather than approximated.

`data/reference/revolver_utilisation.csv` publishes all 44 months — opening drawn, drawings,
repayments, closing drawn, the day the balance moved, days in month, average daily drawn,
average daily undrawn, utilisation and the fee accrued on it. Two identities are proved
against it:

```
opening drawn + drawings - repayments             = closing drawn          (P2-DBT-01)
average daily drawn x (base rate + margin)
   + commitment fee on the average daily undrawn  = the recorded charge    (P2-DBT-02)
```

Both hold to the cent in every year. Phase 2.1 could prove neither, because it priced the
facility off an assumed average drawn balance of $15.0m, $12.0m and $5.0m that the facility's
own roll-forward ($8.0m → $15.1m → $23.8m → $16.3m) contradicted. That assumption is
superseded by the derived average daily balance — see ADR-0018 and
`docs/phases/phase-02-2-report.md`.

The debt schedule reads Topco's balances from the ledger rather than interpolating between
year ends, so `data/reference/debt_schedule.csv` and the general ledger agree in every month
(`P2-DBT-03`).

### 3.6 Investment in subsidiaries — no calibration

Phase 2.0 held investment in subsidiaries at cost and calibrated the absolute level so the
layer-1 group balance sheet reproduced the anchored cash position. That was a residual plug:
the balances could not be explained from anything, and the review was right to reject it.

Investment balances are now taken directly from `config/entities/investment_register.csv`,
which records every ownership event in the group's history — platform acquisition, formation,
carve-out, second-tier holdings acquired with their parent, and the one 80% acquisition that
creates the group's only non-controlling interest. Each row carries the event date, the
consolidation effective date, the ownership percentage acquired and cumulative, the
consideration in its transaction currency and in USD, and a note explaining the transaction.

The balance is therefore the sum of the considerations actually paid, and it **steps on
acquisition dates** rather than drifting between year ends. Interpolating it — which Phase
2.0 did — spreads a single acquisition across twelve months and makes the balance
unexplainable at every month except December. Every holding entity is USD-functional and the
register carries USD cost, so no translation is involved and the path needs no anchor
scaling at all: it is already the answer.

`data/reference/investment_rollforward.csv` presents this as a monthly roll-forward per
parent and subsidiary — opening cost, additions, disposals, closing cost, ownership and NCI
percentage, event type and first consolidated period — which is the form Phase 4's investment
elimination consumes. Control `P2-INV-01` reconciles every ledger balance in every month back
to that register.

One date deserves a note. The Northstar Parts UK acquisition (INV-009) **completed on 31
December 2022**, so the investment and the resulting non-controlling interest sit in the
group's opening balance sheet, while results consolidate from 1 January 2023. The register
carries `event_date` and `consolidation_effective_date` as separate columns for exactly this
reason; collapsing them moves the investment out of the opening balance sheet and breaks it.

### 3.7 Equity, and the translation adjustment it generates

Equity is where a synthetic group most easily stops being a ledger and starts being a
spreadsheet, so it is worth setting out exactly what each account is.

**Contributed capital is a historical-rate balance.** A subsidiary's share capital and
paid-in capital are fixed amounts *in its own currency*, struck at the rate ruling when the
capital was contributed (FX-P03). They do not move because a spot rate moved. Phase 2.1
carried them at a closing-rate USD target recomputed every year, which meant Halden Valve's
Stammkapital changed whenever EUR/USD changed — and, worse, left the entity ledgers unable to
generate any translation adjustment at all, because under the closing-rate method the CTA
*is* the difference between net assets at closing rates and capital at historical rates.

**Every other movement in equity is a dated event.** `src/generation/ledger.py::EQUITY_EVENTS`
is the register, mirroring the investment register: the \$20.0m sponsor contribution that
part-funded the Halden acquisition arrives on 1 April 2023, the day it was needed, not a
twelfth at a time; and the distributions to the non-controlling shareholder of Northstar
Parts UK leave on the dates they were declared.

**Share-based compensation is settled in equity.** The charge accretes in `315100 Share-based
compensation reserve` at the granting entity. It is non-cash, and Phase 2.1 let it leave the
group as cash because the reserve carried no balance for the credit to land in.

**Retained earnings rolls forward from the local result**, and the year-end close moves the
income statement into it — into `320200 Jahresergebnis` in the Kestrel entities, which close
the year into a dedicated account, and into `320100` elsewhere.

**There is no CTA account and no reserve in any source ledger**, because a local ledger has
neither. Both are created by the consolidation, not by the entity.

Those five statements make the layer-1 equity roll-forward close on its own arithmetic:

```
opening equity (at historical rates)
  + result for the period            (at the rates when it was earned)
  + share-based compensation
  + capital contributed              (at the rate on the contribution date)
  + equity brought in on acquisition
  - distributions                    (at the rate on the payment date)
  + the translation adjustment
  = closing equity translated at closing rates
```

`data/reference/layer1_equity_bridge.csv` publishes it year by year with an
`unexplained_usd_m` column, and control `P2-EQ-01` fails the build if that column is not nil.
It has been nil in every year since the reserve was removed.

The translation adjustment in that bridge is computed from the ledgers alone:

```
CTA movement = opening net assets    x (closing rate - prior closing rate)
             + result for the period x (closing rate - average rate)
             + equity movements      x (closing rate - transaction rate)
```

Every term is a balance in the entity's own books or a rate in the approved rate file.
`data/reference/cta_expectation.csv` carries one row per foreign entity and month — 243 rows —
and it is the **expected result** the Phase 5 translation engine will be tested against
rather than a number it will be given. `P2-FX-03` recomputes every row from the balances and
rates in it; `P2-FX-01` proves contributed capital never moved in local currency.

The consolidated CTA anchor is then derived from the layer-1 figure plus the retranslation of
the two balances that exist only on consolidation:

```
CTA(group) = CTA(layer 1)
           + FX on goodwill + FX on acquired intangibles
           - the non-controlling interest's share
           - the movement in unrealised intercompany profit
```

`tools/derive_anchor_inputs.py` regenerates it and `P2-FX-02` proves it. This superseded the
provisional Phase 1 CTA target — see ADR-0017 and `docs/phases/phase-02-2-report.md`.

#### The bridge line that made all of this possible

None of it would close without a **derived layer-1 equity target**. Phase 2's anchor bridge
derived a target for every asset, every liability and every income statement line, but not for
equity — and a balance sheet with a target for everything except equity has one free variable,
which a generator will always close with whatever is left over. Phase 2.0 left it in
investment at cost. Phase 2.1 named it `329100 Group reporting measurement reserve`, capped it
and disclosed it. Both were the same defect.

`targets.py` now derives it:

```
layer-1 equity = consolidated total equity
               + investment in subsidiaries, at cost
               - goodwill
               - acquired intangibles, net
               + deferred tax on the purchase price allocation
               + unrealised intercompany profit in inventory
```

The identity holds **exactly at the 31 December 2022 opening balance sheet**, before a single
generated period — which is how it was established as the right bridge rather than a fitted
one. With it in place, layer-1 cash lands on the approved anchor to the cent with nothing
added to any ledger. There is no measurement reserve and no equivalent account anywhere in
the source architecture, and `P2-EQ-03` fails the build if one reappears under any name.

### 3.7a Intercompany balances are built pair by pair

An intercompany balance is a balance **with somebody**, and the generator treats the pair as
the unit rather than the entity.

The approved anchor gives one group-level intercompany receivable and payable figure per
year. Allocating it to entities by each entity's share of intercompany turnover gives every
entity the right total and no pair a matching number: two sides of the same relationship land
on the same December figure by different routes and are several per cent apart in May.
Allocating the same anchor **flow by flow** gives identical entity totals — an entity's total
is the sum of its own flows either way, so no anchored balance moves — and, because a flow has
one seller and one buyer, both sides read the same USD figure. Each side then translates that
figure into its own currency at the month's closing rate, which is the rate a balance is
compared at.

The same principle covers the rest of the intercompany position:

| Balance | Counterparty, and where it comes from |
|---|---|
| Trade current account (`120500` / `210500`) | the flow: one seller, one buyer, both sides of the same amount |
| Treasury current account (`125100` / `225100`) | the pool: the participant on one side, Topco on the other |
| Loans (`175100` / `235100`) | the loan register: every loan is made by Topco, and its receivable divides between borrowers by notional |
| Investments in subsidiaries (`178100`) | the investment register, which names the subsidiary |

A pair carries no balance before **both** sides are in the group. The flow matrix is settled a
year at a time, so a company acquired in April used to carry balances with its new sister
companies from January — one side of a pair that the other side could not have.

Every posting to one of these accounts names its counterparty, including the cash settlement
that clears it, and the settlement is made counterparty by counterparty rather than as one net
figure. Anything left unattributed on such an account raises rather than posting a nameless
plug. This is what makes the position eliminable by pair, and it is the correction for defect
P2-D-03 — before it, only 37% of the position at FY2025 could be attributed to a pair at all.

### 3.8 Unrealised intercompany profit — support only

Phase 2 does **not** eliminate unrealised intercompany profit. That is a layer-3 construct
and belongs to Phase 4. What Phase 2 does is retain enough source detail for Phase 4 to
compute the elimination deterministically rather than by assumption.

Four intercompany goods flows carry stock that is still on hand at the buyer at a month end.
`data/reference/ic_inventory_transactions.csv` records each transfer — seller, buyer, transfer
price in both entities' currencies and in USD, seller cost, intercompany gross profit, margin,
product category, period, quantity and the buyer's inventory account.
`data/reference/ic_inventory_holdings.csv` then records, for each month end, **one row per
surviving FIFO purchase layer**: the transaction period it came from, how many months it has
been held, the percentage and quantity still unconsumed, and the value and unrealised profit
remaining. Goods are consumed first-in-first-out over the flow's months-on-hand, so a closing
holding is a genuine function of recent purchases rather than a percentage of the balance.

Layer-level detail matters because it lets Phase 4 eliminate at the margin actually earned on
each layer rather than at a blended assumption. Control `P2-ICP-01` proves the required fields
are present; `P2-ICP-02` proves the implied unrealised profit tracks the anchored PUP within
10%. Source inventory is carried **gross** of unrealised profit, which is why the anchor
bridge adds PUP back to the inventory target (§6).

---

## 4. From position to journals

For each entity-period the generator runs three stages.

**Stage 1 — income statement events with their natural counterparts.** Revenue becomes
invoices against receivables (or contract assets, for over-time revenue). Labour accrues to
a payroll liability. Purchases build payables. Depreciation charges accumulated
depreciation. Interest accrues to accrued interest. Every posting has an origin.

**Stage 2 — non-cash pairings.** Inventory replenishment against payables, capital additions
against payables, contract assets billed on to receivables, operating lease remeasurement
against the lease liability.

**Stage 3 — settlements.** Whatever movement each balance sheet account still needs in order
to reach its target is posted against cash. These are the receipts and payments, split into
many transactions with lognormal sizes and weekday-biased dates.

Stage 3 is what guarantees the closing balances, and because every entry is balanced the
period's lines always sum to zero. The identity is not asserted afterwards; it cannot fail.

**Volume**: 1,082,408 lines across 507 entity-periods — median 1,685 lines per
entity-period, ranging from 535 at Shared Services to 7,895 at Meridian US in a peak month.
Volume follows revenue, not a constant.

---

## 5. What "realistic" was made to mean

Specific properties, each chosen because its absence is a giveaway:

| Property | Result |
|---|---|
| Distinct amounts | 453,731 |
| Round-thousand postings | 0.01% of lines |
| Weekend postings | 1.63% (weekend entries pushed to the following Monday) |
| Transaction sizes | Lognormal, so a few large invoices and a long tail of small ones |
| Customer concentration | Top 10 customer groups = 37.3% of FY2025 revenue; top 25 = 53.6% |
| Entity margins | Differ within a business unit by a mean-neutral tilt |
| Working capital days | Differ by entity — Aftermarket collects fastest, Vector B.V. slowest |
| Payment terms | Drawn from 30/45/60/75/90 per customer, not one global term |
| Payroll cadence | Accrued monthly, paid on a separate cycle; bonus accrues through the year |
| Acquisitions | Halden brings its own opening balance sheet on 1 April 2023; Vector B.V. on 1 July 2024 |

**External business unit margins reproduce the anchors exactly**, which is the check that
matters most:

| BU | Revenue $m | Anchor | Gross margin | Anchor |
|---|---|---|---|---|
| Flow Control | 156.60 | 156.6 | 34.00% | 34.0% |
| Industrial Services | 123.60 | 123.6 | 22.00% | 22.0% |
| Engineered Systems | 74.20 | 74.2 | 19.00% | 19.0% |
| Aftermarket & Parts | 57.70 | 57.7 | 43.00% | 43.0% |
| **Group** | **412.10** | **412.1** | **28.96%** | **28.96%** |

---

## 6. Layer 1 only — and the anchor bridge

Phase 2 generates **what each entity's own ledger says**. The approved anchors are the
**consolidated** result. Comparing generated data straight to the consolidated anchor would
be wrong in two directions at once, so the bridge is derived deterministically in
`src/generation/targets.py` and written to
[`config/anchors/phase02_source_layer_targets.csv`](../config/anchors/phase02_source_layer_targets.csv).

**Intercompany gross-up** — layer 1 contains both legs of every intercompany transaction:

```
source revenue  = consolidated revenue + management fee + product + service + royalty
                = 412.10 + 50.54 = 462.64   (FY2025)
```

**Phase 4 constructs** — goodwill, acquired intangibles, the deferred tax on them, their
amortisation and unrealised intercompany profit exist only at layer 3:

```
source amortisation = nil        (all amortisation is of acquired intangibles)
source goodwill     = nil
source tax          = current tax only; deferred tax is a layer-3 item (OQ-05)
source inventory    = gross of unrealised intercompany profit
```

Every Phase 2 anchor control tests against the bridge, not against the consolidated anchor.

---

## 7. Determinism

Mandatory, and enforced.

**Seeding.** Every random draw comes from a generator derived from `MASTER_SEED = 20260907`
plus a **stable string key** — entity, period, stream. No generator is shared across
streams, and none depends on iteration order, so adding a new stream cannot shift the
numbers an existing one produces.

```python
def rng(*key_parts):
    digest = blake2b("|".join(key_parts), key=MASTER_SEED)
    return numpy.random.default_rng(int.from_bytes(digest, "big"))
```

**Proof.** Every build writes `data/build_manifest.json` with a SHA-256 for each of the 520
generated files, and `data/samples/build_digest.txt` with a single digest over all of them.
Both are committed. A rebuild that changes anything changes the digest.

```
build 1: phase2_dataset_digest=f396de9021089d375750ce993c4503187e913e4f27427993ad1e104ebba9df13
build 2: phase2_dataset_digest=f396de9021089d375750ce993c4503187e913e4f27427993ad1e104ebba9df13
```

`tests/test_phase02_generation.py::test_build_is_deterministic` re-runs the whole build and
compares.

---

## 8. Performance and formats

Full build: **~25 seconds** for 1.08m journal lines, 507 native extracts and eleven
reference datasets.

Amount splitting, seasonality and date assignment are vectorised in NumPy; the per-line
assembly is a plain Python loop building tuples, which is fast enough at this volume and far
more readable than a vectorised equivalent would be. Where a loop would have been the
bottleneck — splitting a total into 300 lognormal transactions — it is an array operation.

| Artefact | Format | Why |
|---|---|---|
| Native ERP extracts | CSV, per-ERP encoding and delimiter | Source realism *is* the deliverable |
| Journal lines, revenue detail, plan, headcount | Parquet + zstd | 1.08m rows; columnar, typed, and what Phase 3 will read |
| Masters, FX, capex, fixed assets, debt | CSV | Small, and a reviewer should be able to open them |
| Manifest and checksums | JSON | Machine-checkable reproducibility evidence |

**What is committed.** The 166 MB of raw extracts and the 10 MB journal parquet are
regenerated in 25 seconds, so they are not in git. Everything needed to *verify* a rebuild
is: the manifest with per-file checksums, the control results, extract samples from all
three systems, and the small reference masters — about 1.8 MB.

---

## 9. Clean baseline versus injected faults

Two ideas kept strictly apart:

- **`data/raw/`** — the clean baseline. It passes all 79 source controls. It is never
  corrupted.
- **`data/faults/<id>/`** — a separate copy of only the file each fault touches, with
  `expected_results.json` naming the control that must catch it.

Ten fault fixtures cover unmapped accounts, intercompany mismatch, a missing FX rate, a
duplicate journal, an invalid cost centre, a malformed German decimal, a period anomaly,
payroll misclassified across the gross margin line, an unbalanced journal, and a posting
before an entity's acquisition date. All ten are verified to fire.

The most instructive is **F08**. A production payroll line is re-tagged to an SGA
department. Every balancing control still passes — the journal balances, the trial balance
closes, the extract parses — and only gross margin moves. It is the one fault a purely
arithmetic control framework cannot see, which is why business-reasonableness controls exist.

---

## 10. Privacy

The workforce dataset carries no names. Each employee is an opaque identifier
(`E` + a hash), an entity, a cost centre, a job family, dates and a salary band. Salaries
are drawn from job-family midpoints scaled by a country pay index and a normal band, so the
distribution is realistic without any individual being derivable. Customer names are
generated from fixed word lists and are not real organisations.
