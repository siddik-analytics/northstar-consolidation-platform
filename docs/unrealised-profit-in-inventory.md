# Unrealised profit in inventory

How `src/consol/pup.py` removes the profit the group has recognised on goods it still owns.

---

## 1. Why the adjustment exists

When Meridian sells a valve to Meridian Canada at cost plus 12%, Meridian records revenue and
profit. Nothing has left the group. If Canada still holds the valve at the month end, the
group's inventory is carried at Meridian's selling price — which includes profit the group has
not earned, because no external customer has bought anything.

Group gross profit must exclude profit that has not yet been realised through a sale to a party
outside the group. The adjustment removes it from inventory and from cost of sales, and
releases it automatically when the goods are sold on.

## 2. The eligible population

`data/reference/ic_inventory_transactions.csv` — **173 intercompany goods movements** — is the
authority. Each records the seller, the buyer, the product category, the transfer price, the
seller's cost, the intercompany gross profit and the buyer's inventory account.

Four seller/buyer routes carry goods:

| Seller | Buyer | Margin |
|---|---|---|
| NIG-200 Meridian Flow Controls | NIG-210 Meridian Canada | 12% |
| NIG-200 Meridian Flow Controls | NIG-500 Aftermarket Solutions | 12% |
| NIG-200 Meridian Flow Controls | NIG-510 Northstar Parts UK | 12% |
| NIG-220 Halden Valve | NIG-200 Meridian Flow Controls | 10% |

Management fees, shared services, royalties and interest are **not** eligible. They are
services consumed in the period, not goods sitting in someone's warehouse, so there is nothing
capitalised for profit to be unrealised in.

## 3. FIFO surviving layers, each at its own margin

`ref_ic_inventory_holding` — 470 rows — records, for each month, how much of each purchase layer
the buyer still holds. Inventory turns on FIFO, so what survives at a month end is the most
recent purchases.

Each surviving layer carries **its own** margin:

```
layer margin        = intercompany gross profit ÷ transfer price
unrealised profit   = value still held × that layer's margin
```

Not a blended margin. A buyer holding two months of purchases at 12% and 10% does not hold them
at 11%, and using an average silently misstates the provision whenever the mix moves.
`P4-PUP-04` recomputes each layer and requires the product to hold to the cent.

### Worked example — NIG-200 → NIG-510, June 2025

Four purchase layers survive into 30 June 2025:

| Purchased | Months held | Transfer price | Seller cost | Margin | Still held | Unrealised |
|---|---|---|---|---|---|---|
| Mar 2025 | 3 | 470,898 | 414,391 | 12% | 52,941 | 6,353 |
| Apr 2025 | 2 | 477,839 | 420,498 | 12% | 195,094 | 23,411 |
| May 2025 | 1 | 479,683 | 422,121 | 12% | 337,765 | 40,532 |
| Jun 2025 | 0 | 517,890 | 455,743 | 12% | 517,890 | 62,147 |
| | | | | | **1,103,690** | **132,443** |

June's purchase is held in full; March's is nearly gone. The provision the group carries for
this route at 30 June 2025 is USD 132,443 — that is the profit Meridian booked on goods
Northstar Parts UK has not yet sold to anybody.

## 4. What is posted, and why the release is automatic

The engine computes the **provision required at each month end** and posts the **movement** in
it:

```
posting(t) = provision(t) − provision(t−1)
```

| | |
|---|---|
| Dr | 530100 cost of sales — unrealised profit elimination |
| Cr | 130500 inventory — unrealised profit provision |

354 legs at layer 3, posted to `ELIM-CON`.

Posting the movement rather than the balance is what makes the release happen by construction.
When last month's goods are sold to an external customer, this month's required provision is
lower, the movement is negative, and the profit is recognised — without any separate release
logic that could be forgotten, mis-dated, or applied twice. `P4-PUP-03` requires that negative
movements actually occur: a provision that only ever grows is one that is never released.

The provision is built on a **dense** spine — every route, every month, whether or not there
was a transaction — because a month with no row would break the `lag()` and the movement would
be computed against the wrong prior period.

## 5. Scale

| At | Provision |
|---|---|
| 31 December 2023 | USD 535,382 |
| 31 December 2024 | USD 618,793 |
| 31 December 2025 | USD 713,755 |

Small against USD 412m of revenue, and that is realistic: the group turns inventory roughly six
times a year, so only a few weeks of intercompany purchases survive any month end. The
adjustment matters not for its size but because it is the difference between a group gross
margin that is real and one that includes its own internal sales.

## 6. Interaction with NCI

Where the holding entity is NIG-510, 20% of the adjustment belongs to the non-controlling
interest. The provision is a layer-3 adjustment attributable to NIG-510, so it enters the NCI
attribution base described in [`nci.md`](nci.md) and the minority bears its share of the
unrealised profit on the goods it holds.

## 7. Controls and fixtures

| Control | Assertion | Authority it iterates |
|---|---|---|
| `P4-PUP-01` | the computed provision reproduces the independent expectation | the holdings' published `unrealised_profit_usd`, read here and nowhere else |
| `P4-PUP-02` | every intercompany sale reaches the calculation at its transacted value | `ref_ic_inventory_transaction`, all 173 |
| `P4-PUP-03` | prior-period profit reverses as stock is sold on | the provision movement |
| `P4-PUP-04` | each surviving layer carries its own margin | `stg_pup_layer` |

`P4-PUP-02` originally counted the holdings table against the layers built from it — a
derivation compared with itself, which passes however many rows go missing from both. Fixture
F4-12 deletes a month of holdings and the control did not notice. It now iterates the
**transactions**, which are what require the calculation to happen, and each must appear as a
layer in its own month at its own transacted value. Fixture F4-12 is now caught by it, and
F4-13 — overstating the stock still held — is caught by `P4-PUP-01`, because the independent
expectation does not move when the input does.
