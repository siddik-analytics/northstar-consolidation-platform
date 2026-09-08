# ADR-0023: Intercompany balances are built pair by pair, and every posting names its counterparty

- **Status:** Accepted
- **Date:** 2026-09-07
- **Phase:** 3.1
- **Related:** ADR-0007 (mapping as configuration), ADR-0011 (anchor-first deterministic
  modelling), ADR-0014 (eliminations posted to virtual entities), CTL-IC-01, CTL-IC-02,
  CTL-IC-04, defect P2-D-03

## Context

Phase 3 found that intercompany postings did not consistently carry the counterparty. The
invoice leg of every flow did; the cash settlement that cleared it did not, nor did the group
treasury current account, the intercompany loans, or the investment in each subsidiary. At 31
December 2025 the intercompany receivable and payable position was USD (24.284)m in total, of
which **only 37% could be attributed to an entity pair**.

That is not a data-quality nicety. Phase 4 eliminates intercompany balances **by pair** — A's
receivable from B against B's payable to A — and a balance that names nobody cannot be matched
to anything. The intercompany *result* elimination would have worked, because the invoice legs
carried partners. The intercompany *balance sheet* elimination would have had 63% of the
position with nothing to eliminate it against.

Phase 2's own `P2-IC-01` did not catch it because the control filtered to lines that **already
had** a partner. A control measured over the subset that satisfies it cannot fail.

Correcting the attribution then exposed two things that the missing counterparty had been
hiding, because a balance nobody could attribute to a pair could not be compared with its
mirror:

- **The pairs did not net.** The anchored group intercompany balance was allocated to entities
  by each entity's share of intercompany turnover. Every entity got the right total and no
  pair got a matching number: in May 2025 one entity's receivable from another and that
  other's payable to it were 10% apart.
- **A pair carried a balance before both sides were in the group.** The flow matrix is settled
  a year at a time, so a company acquired in April carried balances with its new sister
  companies from January — one side of a pair that the other side could not have.

## Decision

**An intercompany balance is a balance with somebody, and the pair is the unit it is built
from.**

**1. Every posting to an intercompany account names its counterparty.** `IC_BALANCE_ACCOUNTS`
enumerates the seven accounts whose balance is by definition owed to or by another group
entity: the trade current account, the treasury current account, the loans, and investments in
subsidiaries. Each is settled **counterparty by counterparty** in its own stage of the journal
generator, and the per-counterparty residuals sum to the account residual, so cash is
unaffected. Anything left unattributed on such an account **raises** rather than posting a
nameless plug.

The one exception is the year-end close, which sweeps the whole income statement into retained
earnings in a single entry: its lines are a position, not a transaction with any one
counterparty. That exclusion is named in the control rather than assumed.

**2. The anchor is allocated flow by flow, not entity by entity.** An entity's total is the
sum of its own flows either way, so **no entity balance and no anchored figure moves**. But a
flow has one seller and one buyer, so both sides of a pair read the same USD figure. Each side
translates that figure into its own currency at the month's closing rate, which is the rate a
balance is compared at.

**3. The pair, not the entity, is what runs between year ends.** A pair's balance runs from
what it owed at the last year end to what the anchor says it will owe at this one. Summing a
pair path over an entity's pairs reproduces exactly the entity total the anchor allocation
gives.

**4. A pair has no balance before both sides are in the group.**

**5. Where a register already knows the counterparty, the register is the source.** Loans and
investments are decomposed month by month from the loan register and the investment register
rather than from a fixed annual fraction, because whether a counterparty is in the group at
all changes during the year and a fraction cannot express that.

**6. The controls follow what is actually being tested.** A **balance** matches its mirror at
the **closing** rate, and it is the cumulative balance that must match, not the month's
movement (`P2-IC-01`, CTL-IC-01). A **flow** matches at the **average** rate of the month it
was recorded in (`P2-IC-03`, CTL-IC-02). Every intercompany posting names a counterparty that
is not itself, measured over the **whole** population (`P2-IC-02`, CTL-IC-04).

**7. Investments in subsidiaries are intercompany but not reciprocal.** A holding eliminates
against the subsidiary's **equity**, not against a mirror balance in the subsidiary's books, so
it is excluded from the pair test and reconciled to the investment register by `P2-INV-01`.

## Consequences

**Phase 4's intercompany balance sheet elimination is unblocked.** 100% of the position is
attributable to an entity pair; every pair nets to under USD 1.00 at closing rates in every
period and every flow to under USD 1.00 at average rates. Fault fixture F02 — a one-sided
intercompany difference — now has a threshold four orders of magnitude below it to fail
against, where before it would have been lost inside 63% unattributable position.

**No anchored economics moved.** The intercompany receivable/payable and loan anchors are
identical; so are revenue, gross profit, EBITDA, cash, the term loan and every working-capital
caption. What did move is the intra-year cash position — cash is the residual of the balanced
entity journals, so changing when an intercompany balance sits changes when the group is
short — and therefore the revolver drawn against it. Average daily drawn falls, revolver
interest falls, the commitment fee on the larger undrawn balance rises, and FY2025 net income
rises 0.48%. That chain is set out in the Phase 3.1 report and evidenced in
`data/phase03_1_source_diff.json`.

**The generator can now fail.** Refusing to post an unattributed residual on an intercompany
account means a defect in the decomposition stops the build instead of producing a plausible
dataset. That is the intended trade.

**Later phases inherit the requirement.** An elimination, an NCI allocation or a management
adjustment that touches an intercompany account must carry the counterparty through, and
`P3-DIM-08` is written against the conformed fact so it will catch a regression there.

## Alternatives rejected

**Attribute the balances in Phase 4 instead.** This is the option the Phase 3 report explicitly
warned against and the brief explicitly forbids: deferring a known source defect into the
consolidation engine. The engine would have to invent an attribution the source did not
record, and every elimination would then rest on that invention.

**Allocate the settlement across partners in proportion to the period's invoices.** Gives every
line a partner and still does not make the pairs net, because the two entities' totals are set
independently. It would have produced attributable balances that eliminate to a residual — the
worst outcome, because it looks correct.

**Let the pairs differ and treat the residual as a genuine reconciling item.** Real groups do
have intercompany differences, and Phase 4 will need to handle them. But a synthetic clean
baseline that cannot net is untestable: there would be no state in which `CTL-IC-01` is
expected to pass, so the control could never distinguish a real break from the noise floor.
The differences belong in the fault fixtures, where they are deliberate and measured.
