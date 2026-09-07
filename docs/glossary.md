# Glossary

Terms used across the platform. Where a term has more than one defensible meaning, the
definition used here is stated along with the reason.

## Financial and consolidation

**Adjusted EBITDA** — Reported EBITDA plus costs in accounts flagged `is_ebitda_addback`. No
run-rate synergy add-backs. See ADR-0013.

**CTA (Cumulative Translation Adjustment)** — The equity reserve arising because assets and
liabilities are translated at closing rates while equity is translated at historical rates.
Computed by the engine and independently verified; never entered as a plug.

**Consolidation effective date** — The date from which an entity's results are included in the
group. For an acquisition this is the acquisition date, not the start of the fiscal year.
`NIG-220` contributes nine months of FY2023; `NIG-410` six months of FY2024.

**Constant currency** — Actual local-currency amounts translated at **budget** rates. FX impact
is reported USD less constant-currency USD.

**Contract asset** — Revenue recognised but not yet billed on an over-time contract. Called
"costs in excess of billings" in Sable and "accrued income" in Kestrel.

**Contract liability** — Amounts billed or received ahead of performance. Called "billings in
excess of costs" in Sable, "deferred revenue" in Aurora and "advance payments received" in
Kestrel.

**Current rate method** — Translation method where all assets and liabilities go at the closing
rate, income statement at average rates, and the difference to CTA. Applied to all foreign
operations here.

**EBITDA** — Revenue less cost of sales less operating expenses. **Includes** non-recurring
operating costs. Excludes D&A, interest and tax.

**Elimination entity** — A virtual entity (`ELIM-IC`, `ELIM-CON`, `ELIM-MGT`) carrying
consolidation entries. Never receives source ERP data. See ADR-0014.

**Gesamtkostenverfahren** — The German total-cost (nature-of-expense) presentation, where the
movement in finished goods inventory and own work capitalised appear above the revenue line.
Kestrel entities report on this basis; it is reclassified into cost of sales with a sign
reversal. See `CTL-MAP-08`.

**Layer** — Which class of entry a fact row belongs to: reported, intercompany elimination,
consolidation adjustment, management adjustment or CTA. Determines the reporting basis. See
ADR-0003.

**Management adjustment** — A normalisation or reclassification made for management reporting
only. Layer 4. **Excluded from the statutory result.**

**NCI (Non-controlling interest)** — The share of a subsidiary not owned by the group. Only
`NIG-510` (20%) gives rise to NCI here.

**Net debt** — Term loan gross principal + revolver + finance leases − cash. **Excludes**
operating lease liabilities, following the credit agreement. See OQ-02.

**PPA (Purchase price allocation)** — Allocation of acquisition consideration to identifiable
assets and liabilities at fair value, with goodwill as the residual.

**PUP / Unrealised profit in inventory** — Profit recognised on an intercompany sale where the
goods remain in group inventory at period end. A consolidation adjustment that genuinely
reduces inventory and gross profit — **not** an elimination that nets to nil. See `CTL-IC-08`.

**Reporting currency** — USD. The currency in which the group reports.

**Functional currency** — The currency of the primary economic environment in which an entity
operates. Each entity's local currency here.

**Rate set** — Which family of FX rates applies: `ACTUAL`, `BUDGET` (locked) or `FORECAST`.

**Statistical account** — A `9xxxxx` account holding a non-financial measure (headcount, hours,
units, bookings). Excluded from every trial balance test and never translated. See ADR-0012.

**Statutory view** — Layers 1+2+3+5. The reported consolidated result.
**Management view** — Statutory plus layer 4.

**Trading partner / Intercompany partner** — The counterparty entity on an intercompany
transaction. Mandatory on every intercompany posting (`CTL-IC-04`).

## Scenario and planning

**Scenario** — Actual, Budget, Forecast or Prior Year.

**Version** — A specific instance of a scenario, e.g. `FC_FY26_08`. Budget versions lock on
approval and are hashed so they cannot be quietly edited.

**Rolling forecast** — A forecast re-issued periodically as a new version, combining actual
months to date with forecast months to year end. `FC_FY26_08` is 8 actual + 4 forecast.

**8+4** — Shorthand for a forecast version's actual/forecast month split.

**Prior Year (PY)** — Last year's Actual, viewed as a comparative. **Derived** by a twelve-month
date offset, never stored. See ADR-0004.

**Favourable / Unfavourable (F/U)** — Variance direction accounting for the account's normal
balance. An overspend is a positive number and an unfavourable variance; the logic is defined
once in the semantic model, not per visual.

**Organic growth** — Growth excluding entities within twelve months of their acquisition date.

## Technical

**Anchor** — An authoritative target figure from the Phase 1 anchor model. Phase 2 generation
is calibrated to it and Phase 9 tests against it. See ADR-0011.

**Blocking control** — A control whose failure stops the pipeline. Nothing downstream publishes.

**Calculation group** — A Power BI construct applying a transformation (time intelligence,
scenario comparison) to any measure, avoiding hundreds of near-duplicate measures.

**Conformed dimension** — A dimension shared by several facts with identical keys and meaning,
allowing measures from different facts to be sliced consistently.

**Grain** — The precise meaning of one row in a fact table. `fact_financials` is one row per
entity × account × cost centre × partner × period × scenario × version × layer.

**Mapping type** — `DIRECT` (1:1), `MERGE` (n:1), `SPLIT` (1:n by another attribute), `DERIVED`
(needs a transformation).

**PBIP / TMDL / PBIR** — Power BI's text-based project, semantic model and report formats.
Source-controllable and diffable, unlike `.pbix`. See ADR-0010.

**Role-playing dimension** — One physical dimension used in two roles.
`dim_intercompany_partner` is a role-playing view over `dim_entity`.

**Special period** — Kestrel periods 13–16, used for year-end adjustments. Mapped to December
with an adjustment flag; not treated as extra months. See `CTL-DQ-07`.

**Suspense** — Where unmapped source accounts are held. Never defaulted into a real account;
blocks the close (`CTL-MAP-01`).

## Entities and systems

**Aurora / Sable / Kestrel** — The three source ERP systems. See
`config/coa/erp_source_profile.csv` for their conventions.

**Calder Ridge Partners** — The private equity sponsor. Outside the reporting boundary.

**Topco** — `NIG-100`, the ultimate parent. Holds all external debt, the interest rate swap and
all intercompany lending.

**Northstar Shared Services** — `NIG-110`. Recovers its cost base through a management fee of
2.5% of each operating entity's external revenue.
