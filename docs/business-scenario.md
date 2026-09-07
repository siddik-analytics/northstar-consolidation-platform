# Business Scenario — Northstar Industrial Group

## 1. The company

**Northstar Industrial Group, Inc.** is a private-equity-backed industrial products and
services group headquartered in Columbus, Ohio. It was formed in 2019 when **Calder Ridge
Partners**, a middle-market sponsor, acquired Meridian Flow Controls as a platform and
began a buy-and-build programme across adjacent industrial niches.

| | |
|---|---|
| Reporting currency | USD |
| Fiscal year | Calendar year ending 31 December |
| FY2025 revenue | $412.1m |
| FY2025 Adjusted EBITDA | $57.8m (14.0% margin) |
| Employees | ~2,450 FTE |
| Legal entities | 12 operating, plus 3 virtual consolidation entities |
| Business units | 4 reportable, plus Corporate |
| Countries | United States, Canada, United Kingdom, Germany, Netherlands |
| Currencies | USD, CAD, GBP, EUR |
| Source ERP systems | 3 (Aurora, Sable, Kestrel) |
| Ownership | Calder Ridge Partners (majority), management co-invest, one 20% minority at NIG-510 |

Northstar sells into process industries — chemicals, refining, power generation, water
treatment, food and beverage — where equipment runs continuously and unplanned downtime is
expensive. That single fact explains the shape of the group: it sells the equipment, it
services the equipment, it engineers systems around the equipment, and it sells the spare
parts that keep the equipment running. The four business units are deliberately positioned
along that installed-base lifecycle.

## 2. Operating model

The group runs a **decentralised operating model with a light corporate centre**. Each
legal entity keeps its own P&L, its own commercial leadership and, in most cases, its own
ERP. Corporate owns treasury, tax, M&A, group reporting and the transformation agenda.

This matters for the reporting design, because it is the direct cause of the problem the
CFO has asked us to solve:

- Entities were acquired with their systems intact and never migrated. Three ERPs remain.
- Each entity's chart of accounts reflects its own history and, in the German and Dutch
  cases, a different national accounting presentation.
- Consolidation is performed monthly in a spreadsheet by two people over four working days.
- Intercompany reconciliation is done by email.
- There is no single place where the group's numbers can be traced back to their source.

A shared services centre (`NIG-110`) was established in 2019 to consolidate transactional
finance, HR administration, IT and procurement. It recovers its cost base through a
management fee of **2.5% of external revenue** charged to each operating entity. The fee
is a real intercompany flow with real balance sheet consequences, and it eliminates in
full on consolidation.

## 3. Acquisition history

| Date | Event | Consideration | Notes |
|---|---|---|---|
| Jan 2019 | Platform acquisition of Meridian Flow Controls (`NIG-200`, `NIG-210`) | — | Formation of the group. Canadian subsidiary acquired with the platform. |
| Jan 2020 | Carve-out of the aftermarket business into `NIG-500` | — | Internal reorganisation, not an acquisition. Created a distinct high-margin P&L. |
| Mar 2021 | Cascade Industrial Services (`NIG-300`, `NIG-310`) | $86m | Entry into field services. Brought the Sable ERP into the group. |
| Jun 2021 | Sponsor recapitalisation | — | $180m Term Loan B raised; dividend distributed to the sponsor. Source of the accumulated deficit on the opening balance sheet. |
| Feb 2022 | Tyneside Mechanical Services (`NIG-320`) | £18m | First European entity. Brought the Kestrel ERP into the group. |
| Sep 2022 | Vector Engineered Systems (`NIG-400`) | $44m | Entry into engineered project work. |
| Jan 2023 | Northstar Parts UK (`NIG-510`), 80% | £14m | Founding management retained 20%. The group's only non-controlling interest. |
| **Apr 2023** | **Halden Valve GmbH (`NIG-220`)** | **$52m** | German valve manufacturer. **Nine months only in FY2023.** |
| **Jul 2024** | **Vector Systems B.V. (`NIG-410`)** | **$38m** | European engineering centre. **Six months only in FY2024.** |

The two bolded acquisitions are the ones that matter to the model. Both were acquired
mid-year, so both create a partial-period consolidation problem and both make reported
growth partly inorganic. Any revenue bridge that does not separate organic from acquired
growth will mislead the board: roughly a quarter of FY2024 revenue growth came from owning
Vector Systems B.V. for six months and Halden Valve for a full year rather than nine
months.

## 4. Business units

### Flow Control & Components (`FC`) — 38% of FY2025 revenue
Design and manufacture of pumps, control valves and flow instrumentation. Order-driven,
exposed to the capital-equipment cycle, and the most inventory-intensive unit in the
group. Gross margin ~34%. This is where the FY2026 forecast shortfall originates: European
capital orders softened through the first half of FY2026.

### Industrial Services (`IS`) — 30% of FY2025 revenue
Field mechanical services, rotating equipment maintenance and planned plant turnarounds.
Labour-intensive with minimal inventory but significant unbilled revenue at period end,
because work is performed continuously and billed on a cycle. Gross margin ~22%. The most
resilient unit — maintenance is deferred, not cancelled.

### Engineered Systems (`ES`) — 18% of FY2025 revenue
Custom-engineered skid packages, automation and systems integration, delivered as
long-duration projects. Revenue is recognised over time on the cost-to-cost method, which
makes this the source of contract assets, contract liabilities and estimate-at-completion
adjustments. Gross margin ~19% and the most volatile of the four. A single large project
slipping into FY2027 is the second driver of the FY2026 forecast shortfall.

### Aftermarket & Parts (`AM`) — 14% of FY2025 revenue
Spare parts, consumables and aftermarket kits sold into the installed base. Highest gross
margin at ~43%, least cyclical, and the strategic reason the group is worth more than the
sum of its manufacturing assets. Grows with the installed base rather than with the
capital cycle.

### Corporate & Shared Services (`CORP`)
No external revenue. Group executive, treasury, tax, M&A, group finance, HR, IT and
procurement. Recovers cost through the intercompany management fee.

## 5. Legal entity structure

```
Calder Ridge Partners (sponsor, outside the reporting boundary)
└── NIG-100  Northstar Industrial Group, Inc.          US   USD  Aurora   [Topco / treasury]
    ├── NIG-110  Northstar Shared Services LLC          US   USD  Aurora   CORP
    ├── NIG-200  Meridian Flow Controls, Inc.           US   USD  Aurora   FC
    │   └── NIG-210  Meridian Flow Controls Canada ULC  CA   CAD  Aurora   FC
    ├── NIG-220  Halden Valve GmbH                      DE   EUR  Kestrel  FC    [Apr 2023]
    ├── NIG-300  Cascade Industrial Services LLC        US   USD  Sable    IS
    │   └── NIG-310  Cascade Industrial Svcs Canada Ltd CA   CAD  Sable    IS
    ├── NIG-320  Tyneside Mechanical Services Ltd.      GB   GBP  Kestrel  IS
    ├── NIG-400  Vector Engineered Systems, Inc.        US   USD  Sable    ES
    │   └── NIG-410  Vector Systems B.V.                NL   EUR  Kestrel  ES    [Jul 2024]
    └── NIG-500  Northstar Aftermarket Solutions, Inc.  US   USD  Aurora   AM
        └── NIG-510  Northstar Parts UK Ltd. (80%)      GB   GBP  Kestrel  AM    [20% NCI]
```

Three points of deliberate design:

1. **The tree is not flat.** `NIG-210`, `NIG-310`, `NIG-410` and `NIG-510` are second-tier
   holdings. An elimination engine that assumes every subsidiary is held directly by Topco
   will leave investment-in-subsidiary balances stranded.
2. **`NIG-510` is 80% owned.** One non-controlling interest is enough to exercise NCI
   allocation on the income statement, the balance sheet and the CTA — without the
   complexity of a partially-owned sub-group.
3. **ERP does not follow the legal or the BU hierarchy.** Flow Control spans Aurora and
   Kestrel; Kestrel spans three business units and three countries. Any design that assumes
   "one ERP per business unit" will not survive contact with this structure.

Full detail, including consolidation effective dates, is in
[`config/entities/entity_master.csv`](../config/entities/entity_master.csv).

## 6. Source ERP systems

| | **Aurora** | **Sable** | **Kestrel** |
|---|---|---|---|
| Archetype | Cloud mid-market ERP | Project-centric mid-market ERP | Legacy on-premise European ERP |
| Entities | NIG-100, 110, 200, 210, 500 | NIG-300, 310, 400 | NIG-220, 320, 410, 510 |
| Account format | 4-digit numeric | 5-digit numeric | 8-char zero-padded **text** |
| Amounts | One signed amount, credits negative | One **unsigned** amount, sign from account type | Separate **debit and credit columns** |
| Dimensions | Department, Class, Location | Pipe-delimited string: BU\|Dept\|Project\|Partner | Cost Centre, Profit Centre, Segment, Trading Partner |
| Periods | 1–12 | 1–12 | 1–12 **plus 13–16 adjustment periods** |
| Currency columns | Local + system-translated USD | Local only | Local + **legacy EUR group amount** |
| Locale | UTF-8, `1234.56`, `YYYY-MM-DD` | UTF-8, `1,234.56`, `MM/DD/YYYY` | **Windows-1252**, `1.234,56`, `DD.MM.YYYY` |

These are not cosmetic differences. Each one is a defect waiting to happen:

- **Sign conventions differ three ways.** Get one wrong and that entity's entire income
  statement inverts. Normalisation rules are stated explicitly per ERP in
  [`config/coa/erp_source_profile.csv`](../config/coa/erp_source_profile.csv).
- **Kestrel account codes must stay text.** `00081000` read as an integer becomes `81000`
  and matches nothing.
- **Kestrel special periods 13–16** are year-end adjustments. Treating them as missing
  months triggers false period-completeness failures; treating them as a thirteenth month
  breaks every monthly comparison. They map to December with an adjustment flag.
- **Both Aurora's USD column and Kestrel's EUR column are ignored.** Aurora translates
  using its own rate table; Kestrel's EUR column is a relic of Halden's pre-acquisition
  parent. Translating an already-translated amount produces a triangulated rate error that
  is close to impossible to find months later. Everything is translated once, from local
  currency, by the consolidation engine.
- **Kestrel entities report on the German total-cost method** (*Gesamtkostenverfahren*),
  where the movement in finished goods inventory and own work capitalised appear above the
  revenue line. The group reports on the cost-of-sales basis. Leaving these accounts in
  revenue overstates both revenue and gross margin for three of the twelve entities.

## 7. Chart-of-accounts divergence

Each ERP's chart reflects how that business was run, not how the group wants to report.
The three most consequential differences:

**Aurora books all payroll to a single account (`6100`) regardless of function.** Direct
production labour, indirect manufacturing labour and SG&A salaries all land in the same
place. Gross margin is therefore **not derivable from the Aurora account code alone** — the
department segment is mandatory. Kestrel has the same structural problem for a different
reason: the German nature-of-expense chart classifies by *what was bought* (wages, social
security) rather than *why*. Sable, being job-cost oriented, is the only one of the three
that separates direct from indirect labour at the account level.

**Sable books all professional fees to a single account (`62000`).** Audit, legal,
transformation programme and deal costs are separable only via the vendor category on the
purchase invoice. This matters more than it looks: transformation and deal costs are
Adjusted EBITDA add-backs, and ordinary consulting is not.

**Kestrel does not separate affiliate interest from third-party interest** (`00100000`).
Un-eliminated intercompany interest overstates consolidated net interest and distorts the
covenant interest-coverage ratio — a ratio the lender tests quarterly.

Every mapping, including the conditional rules that resolve these cases, is held in
[`config/coa/`](../config/coa/) and validated in CI by `tests/test_config_integrity.py`.

## 8. Revenue model

| Business unit | How revenue arises | Recognition | Working capital signature |
|---|---|---|---|
| Flow Control | Equipment and component orders, lead times of 8–20 weeks | Point in time, on shipment | High inventory, moderate receivables |
| Industrial Services | Time-and-materials, fixed-price call-offs, turnaround campaigns | Over time as services are delivered | Low inventory, high unbilled |
| Engineered Systems | Multi-month engineered projects, milestone billed | Over time, cost-to-cost | Contract assets *and* liabilities, advances received |
| Aftermarket | Transactional parts orders from the installed base | Point in time, on shipment | High inventory, fast receivables |

Approximately 46% of group revenue is recurring or semi-recurring (aftermarket parts plus
maintenance contracts plus repeat service work), which is the core of the equity story and
a metric the board tracks.

## 9. Cost structure

FY2025 group cost of sales of $292.8m and operating expenses of $68.0m break down
approximately as:

| Cost pool | Approx. share of total cost | Comment |
|---|---|---|
| Direct materials and purchased components | 34% | Concentrated in Flow Control and Aftermarket |
| Direct and field labour, including burden | 30% | Concentrated in Industrial Services and Engineered Systems |
| Subcontract | 8% | Project and turnaround overflow capacity |
| Production and delivery overhead | 10% | Facilities, indirect labour, consumables, equipment rental |
| Freight and duty | 2% | |
| SG&A personnel | 13% | Includes corporate and shared services |
| Other operating expense | 3% | Facilities, professional fees, technology, travel |

Total personnel cost across cost of sales and operating expenses is approximately $191m
against ~2,450 FTE, an average fully-loaded cost of about $78,000 — consistent with a
North America and Western Europe industrial workforce.

## 10. Workforce

| | FY2023 | FY2024 | FY2025 | FY2026B | FY2026F |
|---|---|---|---|---|---|
| Flow Control | 700 | 748 | 780 | 800 | 784 |
| Industrial Services | 930 | 1,000 | 1,050 | 1,090 | 1,074 |
| Engineered Systems | 290 | 322 | 340 | 352 | 344 |
| Aftermarket & Parts | 175 | 182 | 190 | 196 | 194 |
| Corporate & Shared Services | 85 | 88 | 90 | 92 | 90 |
| **Total FTE** | **2,180** | **2,340** | **2,450** | **2,530** | **2,486** |
| Revenue per FTE | $150k | $159k | $168k | $177k | $176k |

Rising revenue per FTE is the productivity half of the margin expansion story. Corporate
headcount grows far more slowly than the group, which is the operating leverage the sponsor
underwrote.

## 11. Capital structure

| Instrument | Terms |
|---|---|
| Term Loan B | $180.0m original (June 2021 recapitalisation), 1% p.a. amortisation, SOFR + 425bps, matures 2028 |
| Incremental Term Loan | $25.0m (Apr 2023, Halden), $30.0m (Jul 2024, Vector B.V.) |
| Interest rate swap | $100m notional, SOFR fixed at 3.00%, matures Dec 2026, **not designated for hedge accounting** |
| Revolving credit facility | $60.0m commitment, 0.50% fee on the undrawn balance |
| Finance leases | Vehicles and production equipment, ~5.4 year average term, 6.4–6.5% |
| Covenants | Max total net leverage 6.00x → 5.50x → 5.00x → 4.50x (FY2023–FY2026); min interest coverage 2.00x, tested quarterly on a trailing-twelve-month basis |

Two consequences that shape the reporting requirement:

1. **The swap matures in December 2026.** From FY2027, the group's effective interest rate
   steps up unless it is replaced. This is a board question the reporting must be able to
   answer, and it is the reason the debt schedule is modelled as an instrument-level fact
   rather than a single balance sheet line.
2. **Covenant headroom is genuinely tight in the early years** — 0.58x on leverage at
   FY2023 and 0.14x on interest coverage. Covenant compliance is therefore a first-class
   reporting output, not an appendix.

## 12. Intercompany relationships

| Flow | Direction | Basis | FY2025 |
|---|---|---|---|
| Management fee | `NIG-110` → all ten operating entities | 2.5% of external revenue | $10.30m |
| Product sales | `NIG-200` → `NIG-210`, `NIG-500`, `NIG-510`, `NIG-400`; `NIG-220` → `NIG-200` | Cost plus 10–12% | $34.50m |
| Service recharges | `NIG-310` → `NIG-300`; `NIG-300` → `NIG-400`; `NIG-320` → `NIG-410` | Cost plus 5% | $5.30m |
| Technology royalty | `NIG-200` → `NIG-220` | 1.5% of Halden external revenue | $0.44m |
| Loan interest | `NIG-100` → five borrowers | 6.0% fixed | $2.90m |
| Intercompany loans | `NIG-100` → `NIG-220`, `NIG-320`, `NIG-410`, `NIG-510`, `NIG-300` | EUR 36m, GBP 14m, USD 15m | $47.20m closing |

FY2025 intercompany revenue eliminated is **$50.5m**, meaning entity-level combined revenue
of $462.6m grosses down to $412.1m consolidated — a 12.3% gross-up. Three structural
features are deliberate:

- **`NIG-220` sells back to `NIG-200`.** A reverse-direction flow that breaks any
  assumption of a single hub-and-spoke trading pattern.
- **`NIG-320` (GBP) sells to `NIG-410` (EUR).** Neither side is in USD, so the elimination
  only nets to nil if both legs are translated at the same rate from their own local
  currency.
- **Intercompany loans are denominated in EUR and GBP.** The lender carries a genuine USD
  translation exposure on them. That exposure is a real economic result, not a consolidation
  error, and the design must not "fix" it.

Unrealised profit in closing inventory is **$0.70m** at FY2025. It is not an elimination —
it is a consolidation adjustment that genuinely reduces consolidated inventory and gross
profit, and where the holding entity is `NIG-510` it is shared with the non-controlling
interest.

Full detail: [`config/ic/intercompany_matrix.csv`](../config/ic/intercompany_matrix.csv).

## 13. The FY2026 story

The current forecast (`FC_FY26_08`, eight actual months plus four forecast) lands **$10.8m
of revenue and $4.3m of Adjusted EBITDA below budget**. The causes are specific and
traceable, which is the point — a variance with no attributable cause is not a variance,
it is noise.

### Revenue bridge, Budget to Forecast

| Driver | $m |
|---|---|
| FY2026 Budget revenue | **448.0** |
| Flow Control — European capital-equipment softness at Halden Valve | (4.7) |
| Flow Control — North American order timing, Meridian US and Canada | (3.1) |
| Engineered Systems — Vector project slipping into FY2027 | (5.1) |
| Industrial Services — reduced turnaround scope at three sites | (3.1) |
| Aftermarket & Parts — UK volume, partly offset by US outperformance | (1.0) |
| *Subtotal, constant currency* | *(16.9)* |
| FX translation versus locked budget rates | 6.1 |
| FY2026 Forecast revenue | **437.2** |

The two lines that matter are the last two. On a **constant-currency basis the business is
$16.9m behind budget**, but reported revenue is only $10.8m behind because the dollar
weakened against every currency the group earns in. The budget was locked at EUR 1.0900 and
GBP 1.2900; the forecast assumes EUR 1.1600 and GBP 1.3450. Translation alone flatters
reported revenue by $6.1m — more than half the apparent shortfall is hidden by it.

Reporting the variance without separating that effect would credit management with $6.1m of
performance that FX delivered, and next year, when the rate moves the other way, would
punish them for the same reason. This single table is the reason a constant-currency view
is a requirement of the platform rather than a refinement.

### Adjusted EBITDA bridge, Budget to Forecast

| Driver | $m |
|---|---|
| FY2026 Budget Adjusted EBITDA | **63.5** |
| Volume and mix at budget margins (constant currency) | (5.0) |
| Gross margin rate, principally Engineered Systems contract margins | (2.9) |
| FX translation on gross profit | 1.8 |
| Recurring operating expense savings from the restructuring action | 1.8 |
| FY2026 Forecast Adjusted EBITDA | **59.2** |

Gross margin rate is the residual of the bridge, which is the conventional construction:
volume is priced at budget margins and rate absorbs the remainder.

Reported EBITDA falls further, from $60.0m to $53.4m, because the restructuring taken in
response to the shortfall adds $2.3m of non-recurring cost. That is the difference between
the two EBITDA definitions doing its job — the reported number shows what the year actually
cost, and the adjusted number shows the run-rate the lender and the sponsor are underwriting.

### Consequences

Net leverage on the forecast is **3.80x against a 4.50x covenant**, versus 3.31x on budget.
Covenant headroom narrows from 1.19x to 0.70x — roughly half a turn. Interest coverage falls
from 3.62x to 3.16x against a 2.00x minimum. Neither is a breach, and the board pack should
say so plainly while making the trajectory visible.
