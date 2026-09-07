# ADR-0018: Revolver interest priced off a daily utilisation model

- **Status:** Accepted
- **Date:** 2026-09-07
- **Phase:** 2.2
- **Supersedes:** the `RCF_AVG_DRAWN` treasury forecast set in Phase 1
- **Related:** ADR-0011 (anchor-first deterministic modelling), ADR-0015 (covenant and
  economic leverage), CA-006, CA-007, CA-033, `config/debt/treasury_policy.csv`

## Context

Phase 1 priced the revolving facility off an assumed average drawn balance of
\$15.0m / \$12.0m / \$5.0m, described in the model as *"treasury forecast, not the closing
plug"*. Phase 2.1 generated the facility as the group's actual liquidity instrument and
reported that the two did not agree, flagging it for Phase 3.

Phase 3 is ingestion and mapping. It must not redesign source economics, so the question had
to be settled before the source data was frozen.

The assumption fails on the anchor model's own numbers, before any generated data is
consulted. The facility's balance sheet roll-forward is
**\$8.0m → \$15.1m → \$23.8m → \$16.3m**. An average of \$5.0m across FY2025 would require
the group to repay \$23.8m in January, hold near nil for ten months and redraw \$16.3m in
December — while its treasury policy holds a minimum cash balance of \$15.0m and its own
generated cash position, before any drawing, is negative in most months of the year. There is
no liquidity profile that produces those endpoints and that average.

The generated ledgers confirm it independently: the group's month-end drawn balance never
falls below \$8.8m after March 2024.

A second problem sits underneath. `RCF_RATE` was an asserted blended rate of
9.25% / 9.35% / 8.35%. Backing the swap out of the approved term-loan rates gives a SOFR path
of 4.70% / 5.20% / 4.10%, which implies a revolver margin of 455bps / 415bps / 425bps — a
margin that moves every year, which no credit agreement does.

## Decision

**1. Treasury policy becomes shared configuration.** `config/debt/treasury_policy.csv` holds
the year-end minimum and target cash balances, the intra-year operating floor and headroom,
the borrowing-notice increment, the repayment block, the minimum surplus before repaying, and
the two dates that matter. Both `src/anchors/build_anchors.py` and `src/generation/series.py`
read it, so a policy cannot be changed in one layer and left in the other.

**2. Interest is built from its components.** Each charge traces to a clause:

| Component | Source | FY2023 | FY2024 | FY2025 |
|---|---|---|---|---|
| Base rate (average SOFR fixing) | economic input | 4.70% | 5.20% | 4.10% |
| Revolver margin | CA-033 | 4.25% | 4.25% | 4.25% |
| **Revolver rate** | derived | **8.95%** | **9.45%** | **8.35%** |
| Term loan margin | CA-003 | 4.25% | 4.25% | 4.25% |
| Swap: \$100m notional fixed at 3.00% | CA-008, CA-034, CA-035 | | | |
| **Term loan blended rate** | derived | **8.10%** | **8.35%** | **7.80%** |
| Commitment fee on the undrawn commitment | CA-007 | 0.50% | 0.50% | 0.50% |

The SOFR path is the one the previously approved term-loan rates always implied: the derived
blended term-loan rates reproduce 8.10% / 8.35% / 7.80% **exactly**, so no term-loan interest
moves. Only the revolver's own rate changes, and it changes because it is now a fixed margin
over a base rate instead of a number that drifted.

**3. Utilisation is resolved to a daily balance.** A month-end balance cannot price a
facility: interest accrues on the daily drawn balance and the commitment fee on the daily
undrawn commitment. The intra-month position follows the dates the agreement and the board
policy already fix:

- a **drawing** is taken on the borrowing-notice date (day 3), because it funds the supplier
  payment run and the payroll disbursement — so a month that draws is drawn for substantially
  the whole month;
- a **repayment** is made on the collections sweep date (day 25), once the month's receipts
  have cleared — so a month that repays is drawn for most of the month and repaid at the end.

The balance is a step function with one step, so the average daily balance is exact rather
than approximated, and `opening + drawings − repayments = closing` holds to the cent.
Published as `data/reference/revolver_utilisation.csv`, 44 months.

**4. `RCF_AVG_DRAWN` is derived from that model, not asserted alongside it.**
`tools/derive_anchor_inputs.py` computes it and iterates to a fixed point, because a higher
drawn balance costs interest, which reduces retained earnings, which the facility funds.

FY2026 Budget is deliberately **not** refitted. A budget is struck before the year and is not
restated by outturn; it stays at \$2.0m.

**5. The debt schedule is read from the ledger.** `data/reference/debt_schedule.csv`
previously interpolated the facility between anchored year ends, so it disagreed with the
general ledger it purported to describe. It now reads Topco's balances, and `P2-DBT-03` tests
it month by month.

## The anchor revision this forced

| Average daily drawn (\$m) | FY2023 | FY2024 | FY2025 | FY2026F |
|---|---|---|---|---|
| Phase 1 treasury forecast | 15.000 | 12.000 | 5.000 | 6.000 |
| **Phase 2.2 derived** | **17.318** | **26.347** | **22.820** | **15.403** |

Consequences on the income statement are set out in full, with the cash flow, retained
earnings and covenant effects, in `docs/phases/phase-02-2-report.md`. In summary: net interest
rises by \$0.15m / \$1.30m / \$1.40m, net income falls by \$0.18m / \$0.58m / \$1.00m, and
**no covenant is breached in any year** — FY2024 interest coverage is the tightest at 2.15x
against a 2.00x minimum. Adjusted EBITDA, and therefore every leverage covenant's numerator,
is untouched.

FY2024 net income moves from \$0.40m to \$(0.19)m. The business narrative — integration spend
against peak interest rates, a year close to break-even — is unchanged; the year now sits
just below the line rather than just above it.

## Alternatives considered

**Reshape the generated revolver so its average matches \$15.0m / \$12.0m / \$5.0m.**
Rejected. It cannot be done without either overdrawing the group's own cash below its policy
floor or abandoning the anchored year-end balances, and the arithmetic above shows FY2025 is
unreachable at any profile.

**Keep the recorded interest and infer the rate the data supports.** An average drawn balance
of \$26.3m against FY2024's recorded \$1.12m of revolver interest implies 4.3% — below the
group's hedged term-loan rate, on an unsecured-in-priority revolving facility that is not
hedged. Not credible, and it would have been an arbitrary plug in the rate rather than in a
balance.

**Split the charge into more components — utilisation fees, agency fees, ancillary
facilities — until it reconciles.** Rejected. The credit agreement contains no utilisation
fee. Inventing one to close a gap is the same defect as inventing a reserve.

**Change the year-end facility balances instead.** Rejected as a matter of direction. The
year-end balance is derived from the full balance sheet identity; the average drawn balance
was an independent assertion. When a derived figure and an asserted one disagree, the
assertion yields.

## Consequences

- The debt architecture now proves both required identities:
  `opening + draws − repayments = closing` (`P2-DBT-01`), and
  `average daily drawn × (base + margin) + commitment fee on the average daily undrawn
  = recorded charge` (`P2-DBT-02`), exact to the cent in every year.
- Interest is explainable clause by clause rather than as a blended rate.
- The facility's cost is now a function of the group's liquidity, so a change to working
  capital, capital expenditure or an acquisition date moves it. That is correct, and
  `tools/derive_anchor_inputs.py --check` runs as a test so it cannot silently go stale.
- FY2023 and FY2024 interest coverage headroom is thin (0.12x and 0.15x). That is a more
  realistic leveraged position than the previous 0.14x / 0.28x and it exercises the covenant
  reporting the platform is being built to produce. No covenant is breached.
