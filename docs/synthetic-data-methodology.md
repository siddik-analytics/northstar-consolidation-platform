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

### 3.4 Balance sheet

Year-end balances are the anchored group captions, allocated to entities by economic driver
(receivables by revenue × entity DSO tilt, inventory only where goods are actually held,
payables by cost × DPO tilt, and so on) and converted to local at that entity's closing
rate. Interim months interpolate between year ends, modulated by the entity's own trailing
activity so working capital breathes with the business.

Retained earnings roll forward from net income. Cash is the residual.

### 3.5 Treasury pooling

Operating entities sweep surplus cash to Topco through an intercompany treasury current
account. Without it, every operating entity accumulates cash while Topco — which carries
all the external debt, paid for both acquisitions and funds the subsidiaries — runs a large
negative bank balance that no real group would tolerate. Pooling only *redistributes* cash:
the group total is untouched, and both legs are in the operating entity's currency so the
pair eliminates exactly.

### 3.6 One calibration, disclosed

Investment in subsidiaries is held at cost, and the absolute level is calibrated once so the
layer-1 group balance sheet reproduces the anchored cash position exactly. The adjustment is
**−$4.2m, −$0.9m and −$8.9m** against roughly $415m of investment — under 2.2%. Economically
it makes the difference between the parents' investment and the subsidiaries' net assets
equal the anchored purchase-price allocation, which is exactly what the Phase 4 investment
elimination will recompute as goodwill and intangibles.

It is recorded in `data/build_manifest.json` under `investment_calibration_usd_m` so nobody
has to go looking for it.

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

- **`data/raw/`** — the clean baseline. It passes all 57 source controls. It is never
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
