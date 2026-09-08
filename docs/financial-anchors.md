    # Financial Anchors — Northstar Industrial Group

    > **Generated file.** Produced by `src/anchors/build_anchors.py`. Do not edit by hand —
    > change the drivers in the script and re-run. Every figure below is derived from
    > drivers rather than typed in: the balance sheet closes by construction and the cash
    > flow statement ties to balance-sheet cash to the cent, enforced by assertions in the
    > script and re-tested independently in `tests/test_anchors.py`.

    ## 1. What this document is

    These are the **authoritative group financial anchors** for the engagement. They are the
    calibration target for Phase 2 synthetic transaction generation and the reconciliation
    target for Phase 9 QA. If generated data does not roll up to these numbers within
    tolerance, the data is wrong — not the anchors.

    Tolerances: revenue, EBITDA and net income ±0.5%; balance sheet captions ±1.0%; every
    balancing identity (A = L + E, cash flow to cash, eliminations to nil) must be exact
    to $1.

    | Item | Basis |
    |---|---|
    | Reporting currency | USD |
    | Fiscal year | Calendar year ending 31 December |
    | Historical actuals | FY2023, FY2024, FY2025 |
    | Current year | FY2026 — Budget (`BUD_FY26_V1`) and Forecast (`FC_FY26_08`, 8 actual + 4 forecast months) |
    | Prior year | Derived from Actual by date offset, not stored (ADR-0004) |
    | Opening balance sheet | 31 December 2022 |
    | Units | USD millions unless stated |

    ## 2. Consolidated income statement

    | USD millions | FY2023 Actual | FY2024 Actual | FY2025 Actual | FY2026 Budget | FY2026 Forecast (8+4) |
|---|---|---|---|---|---|
| **Revenue** | **328.0** | **371.4** | **412.1** | **448.0** | **437.2** |
| Cost of sales | 236.3 | 266.0 | 292.8 | 315.6 | 310.9 |
| **Gross profit** | **91.7** | **105.4** | **119.3** | **132.4** | **126.3** |
| Operating expenses | 62.5 | 66.4 | 68.0 | 72.4 | 72.9 |
| **EBITDA** | **29.2** | **39.0** | **51.3** | **60.0** | **53.4** |
| Add back: non-recurring items in opex | 9.8 | 8.2 | 6.5 | 3.5 | 5.8 |
| **Adjusted EBITDA** | **39.0** | **47.2** | **57.8** | **63.5** | **59.2** |
| Depreciation | 9.5 | 10.4 | 11.3 | 12.2 | 12.0 |
| Amortisation of acquired intangibles | 5.8 | 7.0 | 7.2 | 7.2 | 7.2 |
| Total D&A | 15.3 | 17.4 | 18.5 | 19.4 | 19.2 |
| **EBIT** | **13.9** | **21.6** | **32.8** | **40.6** | **34.2** |
| Net interest expense | 18.2 | 21.8 | 21.0 | 17.5 | 19.3 |
| **Profit before tax** | **-4.3** | **-0.2** | **11.9** | **23.1** | **14.9** |
| Income tax expense/(benefit) | 0.8 | -0.1 | 3.4 | 6.2 | 4.1 |
| **Net income** | **-5.1** | **-0.1** | **8.5** | **16.8** | **10.8** |
| Less: non-controlling interests | -0.2 | -0.2 | -0.3 | -0.2 | -0.2 |
| **Net income attributable to the group** | **-4.9** | **0.1** | **8.7** | **17.0** | **11.0** |
| Memo: interest expense - term loan | 15.4 | 18.0 | 17.8 | 16.1 | 16.8 |
| Memo: interest expense - revolving facility | 1.3 | 2.3 | 1.8 | 0.1 | 1.1 |
| Memo: interest expense - finance leases | 0.7 | 0.7 | 0.7 | 0.7 | 0.7 |
| Memo: commitment and agency fees | 0.2 | 0.2 | 0.2 | 0.3 | 0.2 |
| Memo: amortisation of deferred financing costs | 0.9 | 1.1 | 1.1 | 1.0 | 1.0 |
| Memo: interest income | -0.3 | -0.3 | -0.6 | -0.7 | -0.6 |

    **Reading the story.** Revenue grows from $328.0m to
    $412.1m, a 12.1%
    CAGR built from organic growth plus two acquisitions. Adjusted EBITDA margin expands from
    11.9% to
    14.0% as integration costs roll off and
    pricing and procurement actions land. FY2023 is a *reported* net loss — heavy one-time
    integration spend against peak interest rates — and FY2024 is close to break-even at the
    bottom line. FY2025 is the first year of meaningful net income. That is the correct shape
    for a levered buy-and-build platform, and it gives the board pack something real to
    discuss rather than a smooth upward line.

    FY2026 Forecast lands $10.8m
    (-2.4%) below Budget on revenue and
    $4.3m below on Adjusted EBITDA.
    The drivers are deliberate and traceable: European capital-equipment softness at Halden
    Valve, one large Vector Systems project slipping into FY2027, and an incremental
    restructuring charge taken in response. A favourable FX translation swing partly offsets,
    because the Budget was locked at rates weaker than those now forecast — which is exactly
    the situation that makes a constant-currency view non-optional.

    ## 3. Consolidated balance sheet

    | USD millions | FY2023 Actual | FY2024 Actual | FY2025 Actual | FY2026 Budget | FY2026 Forecast (8+4) |
|---|---|---|---|---|---|
| Cash and cash equivalents | 15.0 | 15.0 | 22.0 | 22.0 | 22.0 |
| Trade accounts receivable, net | 55.7 | 61.1 | 65.5 | 67.5 | 70.7 |
| Contract assets / unbilled | 7.5 | 8.2 | 8.9 | 9.1 | 10.1 |
| Inventory, net | 35.6 | 38.6 | 40.1 | 40.6 | 43.4 |
| Prepaid expenses and other current assets | 6.6 | 7.4 | 8.2 | 9.0 | 8.7 |
| **Total current assets** | **120.4** | **130.3** | **144.7** | **148.2** | **155.0** |
| Property, plant and equipment, net | 77.2 | 87.5 | 95.2 | 102.5 | 101.6 |
| Operating lease right-of-use assets | 22.0 | 24.0 | 24.5 | 24.0 | 25.5 |
| Goodwill | 124.4 | 140.3 | 142.2 | 142.2 | 143.2 |
| Intangible assets, net | 53.6 | 59.4 | 53.1 | 45.9 | 46.4 |
| Other non-current assets | 6.5 | 7.2 | 7.8 | 8.0 | 8.2 |
| **TOTAL ASSETS** | **404.1** | **448.7** | **467.5** | **470.8** | **479.9** |
| Trade accounts payable | 29.8 | 35.0 | 40.1 | 45.0 | 43.4 |
| Contract liabilities | 5.2 | 5.9 | 6.7 | 7.8 | 6.6 |
| Accrued liabilities | 18.0 | 20.4 | 22.7 | 24.6 | 24.0 |
| Income taxes payable | 2.0 | 2.2 | 2.5 | 2.7 | 2.6 |
| Revolving credit facility | 16.0 | 24.5 | 19.1 | 9.6 | 14.7 |
| Term loan B, net of financing costs | 196.0 | 222.5 | 221.2 | 209.9 | 219.9 |
| Finance lease liabilities | 10.3 | 10.4 | 10.9 | 10.8 | 11.3 |
| Operating lease liabilities | 22.0 | 24.0 | 24.5 | 24.0 | 25.5 |
| Deferred tax liabilities | 15.5 | 17.9 | 16.3 | 14.7 | 14.8 |
| Other long-term liabilities | 3.5 | 3.8 | 4.0 | 4.0 | 4.2 |
| **Total liabilities** | **318.3** | **366.6** | **368.0** | **353.1** | **367.3** |
| Contributed capital and APIC | 166.0 | 167.2 | 168.6 | 170.1 | 170.1 |
| Retained earnings / (accumulated deficit) | -82.0 | -81.8 | -73.1 | -56.1 | -62.1 |
| Cumulative translation adjustment | -0.9 | -5.6 | 2.2 | 2.2 | 3.2 |
| Non-controlling interests | 2.7 | 2.3 | 1.9 | 1.4 | 1.5 |
| **Total equity** | **85.8** | **82.1** | **99.6** | **117.7** | **112.6** |
| **TOTAL LIABILITIES AND EQUITY** | **404.1** | **448.7** | **467.5** | **470.8** | **479.9** |
| Memo: term loan B, gross principal | 201.2 | 228.9 | 226.6 | 214.3 | 224.3 |
| Memo: unamortised deferred financing costs | 5.2 | 6.4 | 5.3 | 4.3 | 4.3 |

    Opening (31 December 2022) retained earnings is **$-77.1m**, an
    accumulated deficit against $145m of contributed capital. The
    deficit is the normal consequence of a 2021 sponsor recapitalisation dividend charged to
    reserves plus three years of post-LBO intangible amortisation and transaction costs; it is
    not a sign of distress, and total opening equity of
    $67.2m against
    total assets is consistent with a levered platform. It is derived as the opening balancing figure and asserted to fall
    within ±$5m of the expected $-77m, so a
    careless change to an opening driver fails the build rather than silently distorting
    every subsequent year.

    ## 4. Consolidated cash flow statement

    | USD millions | FY2023 Actual | FY2024 Actual | FY2025 Actual | FY2026 Budget | FY2026 Forecast (8+4) |
|---|---|---|---|---|---|
| **Net income** | **-5.1** | **-0.1** | **8.5** | **16.8** | **10.8** |
| Depreciation and amortisation | 15.3 | 17.4 | 18.5 | 19.4 | 19.2 |
| Share-based compensation | 1.0 | 1.2 | 1.4 | 1.5 | 1.5 |
| Amortisation of deferred financing costs | 0.9 | 1.1 | 1.1 | 1.0 | 1.0 |
| Deferred income taxes | -1.4 | -1.1 | -1.6 | -1.6 | -1.5 |
| Non-cash FX translation movement on working capital | 0.7 | -1.6 | 3.5 | 0.0 | -1.6 |
| Change in working capital | 2.2 | 2.8 | 1.0 | 4.7 | -5.4 |
| Change in other assets and liabilities | -0.2 | -0.4 | -0.4 | -0.2 | -0.2 |
| **NET CASH FROM OPERATING ACTIVITIES** | **13.5** | **19.3** | **31.9** | **41.6** | **23.8** |
| Capital expenditure | -12.5 | -14.0 | -15.5 | -17.5 | -15.0 |
| Acquisitions, net of cash acquired | -50.2 | -36.9 | -0.0 | -0.0 | -0.0 |
| **NET CASH USED IN INVESTING ACTIVITIES** | **-62.7** | **-50.9** | **-15.5** | **-17.5** | **-15.0** |
| Term loan drawings | 25.0 | 30.0 | 0.0 | 0.0 | 0.0 |
| Term loan repayments | -2.0 | -2.3 | -2.3 | -12.3 | -2.3 |
| Revolving facility, net | 8.0 | 8.5 | -5.4 | -9.6 | -4.4 |
| Finance lease principal | -1.8 | -1.9 | -1.9 | -2.0 | -2.0 |
| Deferred financing costs paid | -1.6 | -2.2 | -0.0 | -0.0 | -0.0 |
| Sponsor equity contribution | 20.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Dividends to non-controlling interests | -0.0 | -0.1 | -0.2 | -0.2 | -0.2 |
| **NET CASH FROM FINANCING ACTIVITIES** | **47.6** | **31.9** | **-9.8** | **-24.1** | **-9.0** |
| Effect of exchange rate changes | 0.2 | -0.3 | 0.4 | 0.0 | 0.2 |
| **NET CHANGE IN CASH** | **-1.4** | **0.0** | **7.0** | **0.0** | **0.0** |
| Cash at beginning of period | 16.4 | 15.0 | 15.0 | 22.0 | 22.0 |
| **CASH AT END OF PERIOD** | **15.0** | **15.0** | **22.0** | **22.0** | **22.0** |
| Memo: free cash flow (OCF less capex) | 1.0 | 5.3 | 16.4 | 24.1 | 8.8 |

    The statement is prepared on the **indirect** basis and derived arithmetically from
    balance sheet movements plus net income (ADR-0006). `NET CHANGE IN CASH` therefore ties
    to the balance sheet movement in cash by construction; the script asserts this to 1e-6
    and refuses to emit output if it fails. Acquisition-related working capital acquired is
    excluded from the operating movement and shown within investing, which is the correct
    treatment and a common error in hand-built models.

    ## 5. Key performance indicators and covenant metrics

    | USD millions | FY2023 Actual | FY2024 Actual | FY2025 Actual | FY2026 Budget | FY2026 Forecast (8+4) |
|---|---|---|---|---|---|
| Gross margin % | 28.0% | 28.4% | 29.0% | 29.6% | 28.9% |
| EBITDA margin % | 8.9% | 10.5% | 12.5% | 13.4% | 12.2% |
| Adjusted EBITDA margin % | 11.9% | 12.7% | 14.0% | 14.2% | 13.5% |
| Opex % of revenue | 19.1% | 17.9% | 16.5% | 16.2% | 16.7% |
| Net margin % | -1.5% | -0.0% | 2.1% | 3.8% | 2.5% |
| Headcount (period-end FTE) | 2,180 | 2,340 | 2,450 | 2,530 | 2,486 |
| Revenue per FTE (USD) | 150,459 | 158,718 | 168,204 | 177,075 | 175,865 |
| Capex % of revenue | 3.8% | 3.8% | 3.8% | 3.9% | 3.4% |
| DSO (days) | 62 | 60 | 58 | 55 | 59 |
| DIO (days) | 55 | 53 | 50 | 47 | 51 |
| DPO (days) | 46 | 48 | 50 | 52 | 51 |
| Cash conversion cycle (days) | 71 | 65 | 58 | 50 | 59 |
| Net working capital | 52.3 | 54.0 | 53.3 | 48.8 | 58.9 |
| NWC % of revenue | 16.0% | 14.5% | 12.9% | 10.9% | 13.5% |
| Total debt | 227.5 | 263.8 | 256.6 | 234.7 | 250.4 |
| Net debt | 212.5 | 248.8 | 234.6 | 212.7 | 228.4 |
| Net leverage (x Adj. EBITDA) | 5.44x | 5.27x | 4.06x | 3.35x | 3.86x |
| Interest coverage (x) | 2.14x | 2.17x | 2.76x | 3.62x | 3.06x |
| FCF conversion % of Adj. EBITDA | 2.5% | 11.2% | 28.4% | 38.0% | 14.8% |
| Total liquidity (cash + undrawn RCF) | 59.0 | 50.5 | 62.9 | 72.4 | 67.3 |
| Covenant: maximum net leverage | 6.00x | 5.50x | 5.00x | 4.50x | 4.50x |
| Covenant headroom — leverage | 0.56x | 0.23x | 0.94x | 1.15x | 0.64x |
| Covenant headroom — interest coverage | 0.14x | 0.17x | 0.76x | 1.62x | 1.06x |
| Memo: operating lease liabilities | 22.0 | 24.0 | 24.5 | 24.0 | 25.5 |
| Economic net debt (including leases) | 234.5 | 272.8 | 259.1 | 236.7 | 253.9 |
| Economic net leverage (non-covenant) | 6.01x | 5.78x | 4.48x | 3.73x | 4.29x |

    **Deleveraging is the headline, and covenant headroom is the tension.** Net leverage falls
    from 5.44x at FY2023 (immediately post-Halden) to
    4.06x at FY2025 against a covenant maximum that steps down
    6.00x / 5.50x / 5.00x / 4.50x across FY2023–FY2026. Headroom is genuinely tight early:
    0.56x at FY2023 and
    0.23x at FY2024, widening to
    0.94x at FY2025. Interest coverage improves from
    2.14x to 2.76x against a
    2.00x minimum — only 0.14x of headroom in FY2023.

    The FY2026 Forecast at 3.86x versus a Budget of
    3.35x costs
    0.51x
    of headroom. That is a legitimate board-level talking point rather than a covenant breach:
    headroom narrows, it does not disappear. A covenant-compliance view is therefore a
    first-class reporting requirement, not a nice-to-have — see `docs/reporting-design.md`.

    ## 6. Business unit anchors

    | Business unit | Measure | FY2023 Actual | FY2024 Actual | FY2025 Actual | FY2026 Budget | FY2026 Forecast (8+4) |
    |---|---|---|---|---|---|---|
| Flow Control & Components | Revenue | 124.0 | 141.0 | 156.6 | 169.0 | 163.5 |
| Flow Control & Components | Gross margin % | 32.5% | 33.4% | 34.0% | 34.8% | 34.0% |
| Flow Control & Components | Headcount | 700 | 748 | 780 | 800 | 784 |
| Industrial Services | Revenue | 101.5 | 113.0 | 123.6 | 134.5 | 133.0 |
| Industrial Services | Gross margin % | 21.0% | 21.6% | 22.0% | 22.6% | 22.3% |
| Industrial Services | Headcount | 930 | 1,000 | 1,050 | 1,090 | 1,074 |
| Engineered Systems | Revenue | 55.0 | 65.4 | 74.2 | 82.0 | 78.2 |
| Engineered Systems | Gross margin % | 18.5% | 18.0% | 19.0% | 19.5% | 17.8% |
| Engineered Systems | Headcount | 290 | 322 | 340 | 352 | 344 |
| Aftermarket & Parts | Revenue | 47.5 | 52.0 | 57.7 | 62.5 | 62.5 |
| Aftermarket & Parts | Gross margin % | 42.0% | 42.5% | 43.0% | 43.5% | 43.4% |
| Aftermarket & Parts | Headcount | 175 | 182 | 190 | 196 | 194 |
| Corporate & Shared Services | Headcount | 85 | 88 | 90 | 92 | 90 |

Business unit gross margins are set at BU level and applied to external revenue.
Corporate and Shared Services carries no external revenue; it recovers its cost base
through an intercompany management fee (section 8) which eliminates on consolidation.

## 7. Legal entity revenue anchors (external revenue only)

| Entity | BU | FY2023 Actual | FY2024 Actual | FY2025 Actual | FY2026 Budget | FY2026 Forecast (8+4) |
|---|---|---|---|---|---|---|
| NIG-200 | FC | 72.5 | 82.0 | 92.0 | 100.0 | 98.5 |
| NIG-210 | FC | 33.0 | 33.4 | 35.6 | 37.5 | 36.5 |
| NIG-220 | FC | 18.5 | 25.6 | 29.0 | 31.5 | 28.5 |
| NIG-300 | IS | 58.5 | 65.0 | 71.0 | 77.0 | 76.5 |
| NIG-310 | IS | 22.5 | 24.5 | 26.4 | 28.5 | 28.0 |
| NIG-320 | IS | 20.5 | 23.5 | 26.2 | 29.0 | 28.5 |
| NIG-400 | ES | 55.0 | 56.9 | 55.7 | 59.0 | 57.2 |
| NIG-410 | ES | 0.0 | 8.5 | 18.5 | 23.0 | 21.0 |
| NIG-500 | AM | 30.0 | 32.5 | 35.4 | 38.0 | 38.2 |
| NIG-510 | AM | 17.5 | 19.5 | 22.3 | 24.5 | 24.3 |

`NIG-100` (Topco) and `NIG-110` (Shared Services) have no external revenue.
`NIG-220` FY2023 covers nine months only (acquired 1 April 2023) and `NIG-410` FY2024
covers six months only (acquired 1 July 2024). Phase 2 must respect these
consolidation-effective dates, and Phase 5 must present organic versus acquired growth
separately in the revenue bridge — otherwise FY2024 growth reads as organic when roughly
a quarter of it is not.

## 8. Intercompany anchors (gross, eliminated in full)

| Intercompany flow | FY2023 Actual | FY2024 Actual | FY2025 Actual | FY2026 Budget | FY2026 Forecast (8+4) |
|---|---|---|---|---|---|
| Management fee income / expense (2.5% of external revenue) | 8.20 | 9.29 | 10.30 | 11.20 | 10.93 |
| Intercompany product sales | 25.40 | 30.10 | 34.50 | 37.80 | 36.10 |
| Intercompany service sales | 3.90 | 4.60 | 5.30 | 5.90 | 5.70 |
| Intercompany technology royalty | 0.28 | 0.38 | 0.43 | 0.47 | 0.43 |
| Intercompany loan interest | 2.10 | 2.70 | 2.90 | 2.85 | 2.95 |
| Intercompany AR / AP, closing balance | 9.80 | 11.20 | 12.40 | 13.10 | 12.90 |
| Intercompany loans, closing principal | 42.00 | 48.50 | 47.20 | 44.00 | 45.80 |
| Unrealised profit in closing inventory (PUP) | 0.56 | 0.64 | 0.70 | 0.72 | 0.74 |

Total FY2025 intercompany revenue eliminated is **$50.5m**: entity-level combined
revenue of $462.6m eliminates down to consolidated revenue of
$412.1m, a 12.3% gross-up.
Intercompany interest of $2.90m eliminates against
intercompany interest expense with no effect on consolidated net interest. Unrealised
profit in inventory is a genuine consolidation adjustment: it reduces consolidated
inventory and gross profit and does **not** net to zero, which is why it is anchored
separately from the pure eliminations.

## 9. FX anchors (USD per one unit of local currency)

| Currency | FY | Rate set | Average | Closing |
|---|---|---|---|---|
| CAD | 2022 | ACTUAL | 0.7690 | 0.7383 |
| GBP | 2022 | ACTUAL | 1.2370 | 1.2083 |
| EUR | 2022 | ACTUAL | 1.0530 | 1.0666 |
| CAD | 2023 | ACTUAL | 0.7410 | 0.7561 |
| GBP | 2023 | ACTUAL | 1.2440 | 1.2745 |
| EUR | 2023 | ACTUAL | 1.0815 | 1.1050 |
| CAD | 2024 | ACTUAL | 0.7300 | 0.6959 |
| GBP | 2024 | ACTUAL | 1.2785 | 1.2520 |
| EUR | 2024 | ACTUAL | 1.0825 | 1.0355 |
| CAD | 2025 | ACTUAL | 0.7180 | 0.7250 |
| GBP | 2025 | ACTUAL | 1.2950 | 1.3400 |
| EUR | 2025 | ACTUAL | 1.1050 | 1.1650 |
| CAD | 2026 | BUDGET | 0.7200 | 0.7200 |
| GBP | 2026 | BUDGET | 1.2900 | 1.2900 |
| EUR | 2026 | BUDGET | 1.0900 | 1.0900 |
| CAD | 2026 | FORECAST | 0.7310 | 0.7350 |
| GBP | 2026 | FORECAST | 1.3450 | 1.3500 |
| EUR | 2026 | FORECAST | 1.1600 | 1.1700 |

Three rate sets exist for FY2026: `ACTUAL` (months closed to date), `BUDGET` (locked at
the October 2025 forward curve when the budget was approved) and `FORECAST` (actual to
date plus current forwards). Budget is translated at budget rates and never restated; the
constant-currency view retranslates Actual at budget rates. See ADR-0005.

The annual averages above are anchors only. Phase 2 generates a **monthly** rate series
calibrated so that the revenue-weighted monthly average reproduces the annual average
within 10 basis points, because the model translates P&L at monthly average rates rather
than applying an annual average to a year-to-date figure (ADR-0005).

## 10. Capital structure and acquisitions

| Item | Detail |
|---|---|
| Term Loan B | $180.0m original (2021 recapitalisation), 1% p.a. scheduled amortisation, SOFR + 425bps |
| Incremental term loan | $25.0m drawn April 2023 (Halden Valve); $30.0m drawn July 2024 (Vector Systems B.V.) |
| Interest rate swap | $100m notional, SOFR fixed at 3.00%, matures December 2026; not designated for hedge accounting |
| Revolving credit facility | $60.0m commitment, 0.50% commitment fee on the undrawn balance |
| Finance leases | Vehicles and production equipment, ~5.4 year average remaining term, 6.4–6.5% |
| Covenants | Maximum total net leverage 6.00x stepping down to 4.50x; minimum interest coverage 2.00x |
| Sponsor | Calder Ridge Partners — $20.0m equity contribution in 2023 to part-fund Halden |
| Treasury policy | Minimum cash $15.0m, target cash $22.0m, surplus sweeps the revolver |

| Acquisition | Date | Consideration | Goodwill | Intangibles | Funding |
|---|---|---|---|---|---|
| Halden Valve GmbH | 1 Apr 2023 | $52.0m | $24.0m | $18.0m | $25m incremental TLB + $20m sponsor equity + revolver |
| Vector Systems B.V. | 1 Jul 2024 | $38.0m | $17.5m | $13.5m | $30m incremental TLB + cash |

## 11. How to regenerate and re-validate

```bash
python src/anchors/build_anchors.py     # rebuilds config/anchors/*.csv and this document
python -m pytest tests -q               # re-validates every identity independently
```
