# Investment elimination, purchase price allocation and goodwill

How `src/consol/investments.py` removes each parent's investment against the subsidiary's
equity, recognises the fair value of what was acquired, and derives goodwill as the residual it
is.

---

## 1. The investment register is the authority

`config/entities/investment_register.csv` — eleven relationships — is the authoritative record
of what the group bought, from whom, when, and for how much. Everything downstream is derived
from it: the acquisition schedules, the ownership register, the elimination entries, the PPA
tranches and three of the controls.

Two dates, and the distinction matters:

| Field | Meaning |
|---|---|
| `event_date` | when the transaction happened |
| `consolidation_effective_date` | from when the group consolidates the subsidiary |

They are usually the same and are not required to be. The **consolidation effective date**
governs: it decides the first period in which the subsidiary's results enter the group, the
rate at which its opening balance sheet is translated (FX-P16), and the month in which the
investment is eliminated.

Seven relationships predate the reporting window and are consolidated from the window opening
(202301). Two are acquisitions inside the window:

| | Halden Valve (NIG-220) | Vector Systems (NIG-410) |
|---|---|---|
| Acquired by | NIG-100 Topco | NIG-400 Vector Engineered Systems |
| Effective | 1 April 2023 | 1 July 2024 |
| Consideration | USD 52.0m | USD 38.0m |
| Funded by | cash and revolver | USD 30m incremental term loan and cash |

## 2. Second-tier holdings

Four subsidiaries are held by an operating company, not by Topco: NIG-210, NIG-310, NIG-410 and
NIG-510. The elimination is performed **relationship by relationship**, against the equity of
the specific subsidiary and the investment of the specific parent that holds it.

Eliminating at aggregate group level cannot express a second-tier holding at all: the group's
total investment balance nets against the group's total subsidiary equity and produces a number
that balances while describing nothing. `P4-INV-02` reconciles each of the eleven relationships
on its own.

## 3. What the elimination posts

For each relationship, in the month the register gives it:

| Leg | Account | Sign | Meaning |
|---|---|---|---|
| 1 | 310200 contributed capital | Dr | eliminate the acquired equity |
| 3 | 160100 goodwill | Dr | the residual of the bridge |
| 11–12 | 165100 / 165200 intangibles | Dr | acquired customer relationships and technology at fair value |
| 30 | 240100 deferred tax liability | Cr | deferred tax on the fair value uplift |
| 40 | 178100 investment in subsidiary | Cr | eliminate the parent's investment at cost |

67 legs across 11 relationships. Every posting carries `rule_id = <acquisition_id>`, so
`P4-PPA-04` can require that no goodwill exists that cannot be traced to an acquisition — a
goodwill balance nobody can explain is a goodwill balance nobody can impair.

`P4-INV-03` requires the elimination in the month the **register** gives, exactly. Eliminating
early removes equity that was still outside the group; eliminating late leaves an investment in
a subsidiary the group already owns; eliminating not at all leaves both. Every one of those
still balances.

## 4. The goodwill bridge

```
goodwill = consideration + NCI at acquisition − fair value of identifiable net assets

where  fair value of identifiable net assets
     = book net assets + intangibles recognised + PP&E uplift − deferred tax on the uplift
```

Computed for every acquisition, never plugged. `P4-PPA-01` recomputes the identity and requires
it to hold to the cent for all eleven.

| Acq | Subsidiary | Consideration | NCI | Book net assets | Intangibles | Deferred tax | FV net assets | **Goodwill** |
|---|---|---|---|---|---|---|---|---|
| ACQ-001 | Meridian Flow Controls | 118.0 | — | 68.5 | 16.0 | (4.5) | 80.0 | **38.0** |
| ACQ-002 | Meridian Canada | 22.0 | — | 12.8 | 3.0 | (0.8) | 15.0 | **7.0** |
| ACQ-003 | Shared Services | 2.0 | — | 2.0 | — | — | 2.0 | **—** |
| ACQ-004 | Aftermarket Solutions | 34.0 | — | 34.0 | — | — | 34.0 | **—** |
| ACQ-005 | Cascade Industrial | 86.0 | — | 51.1 | 11.0 | (3.1) | 59.0 | **27.0** |
| ACQ-006 | Cascade Canada | 16.0 | — | 9.6 | 2.0 | (0.6) | 11.0 | **5.0** |
| ACQ-007 | Tyneside Mechanical | 22.3 | — | 13.1 | 3.0 | (0.8) | 15.3 | **7.0** |
| ACQ-008 | Vector Engineered | 44.0 | — | 33.1 | 4.0 | (1.1) | 36.0 | **8.0** |
| ACQ-009 | Northstar Parts UK | 16.9 | 2.8 | 14.3 | 2.0 | (0.6) | 15.7 | **4.0** |
| ACQ-010 | Halden Valve | 52.0 | — | 11.8 | 18.0 | (5.4) | 24.4 | **27.6** |
| ACQ-011 | Vector Systems | 38.0 | — | 10.9 | 13.5 | (3.497) | 20.904 | **17.097** |
| | | | | | | | | **140.697** |

USD m. Goodwill agrees with the consolidated balance sheet at every period end.

### Worked example — ACQ-011, Vector Systems B.V., 1 July 2024

```
Consideration                                          38.000
NCI at acquisition (100% acquired)                          —
                                                       ------
                                                       38.000
Less fair value of identifiable net assets
    Book net assets acquired                  10.900
    Customer relationships at fair value       9.000
    Technology and patents at fair value       4.500
    Deferred tax at 25.9% on the uplift       (3.497)
                                              ------
                                                     (20.904)
                                                       ------
Goodwill                                               17.097
```

Posted 1 July 2024 as: Dr contributed capital 10.900, Dr goodwill 17.097, Dr customer
relationships 9.000, Dr technology 4.500, Cr deferred tax 3.497, Cr investment 38.000.
Six legs, summing to nil, each naming `ACQ-011`.

`P4-PPA-03` recomputes the deferred tax from the schedule's own rate; `P4-PPA-02` reports any
negative goodwill, which would be a bargain purchase and a disclosure rather than a silent
balance. There are none.

## 5. Acquired intangibles and amortisation

18 tranches across the eleven acquisitions, in `config/consolidation/ppa_intangible.csv`. Each
carries its class, its gross fair value, its useful life and the period amortisation begins.

The pre-window block is split into a short-lived and a long-lived tranche (2.00 and 10.53
years) so that the group's amortisation profile is not a single straight line — real
allocations are not. The two in-window acquisitions carry customer relationships at 10 years
and technology at 8.

| | Gross | Life | Amortisation from |
|---|---|---|---|
| PPA-011-C customer relationships | 9.000 | 10.0 y | 202407 |
| PPA-011-T technology and patents | 4.500 | 8.0 y | 202407 |

Amortisation is a layer-3 charge to `720100` against accumulated amortisation `166100`, 1,314
legs. Net book value of acquired intangibles at 31 December 2025: **USD 52.476m**.

Four controls guard the schedule:

| Control | Assertion |
|---|---|
| `P4-INT-01` | every tranche in the register has a schedule |
| `P4-INT-02` | amortisation never begins before the **register's** effective month |
| `P4-INT-03` | nothing amortises past its cost |
| `P4-INT-04` | gross − accumulated = net book value, every period |

`P4-INT-02` is measured against the investment register rather than against the PPA schedule
the charge was computed from. A schedule that says amortisation starts in January is perfectly
self-consistent with a charge that starts in January; only the register knows when the group
actually bought the business. Starting at the beginning of the acquisition year rather than the
acquisition month overstates the charge by the months before completion — small, plausible, and
entirely wrong. Fixture F4-10 injects exactly that.

## 6. The investment roll-forward

`data/reference/investment_rollforward.csv` — 463 relationship-periods — records what each
parent held in each subsidiary in each month. It is produced at source generation and is **not
read by the consolidation engine**; it exists so that the source layer can be checked against
the register independently.

## 7. P3-D-06, and the control-design lesson

**The defect.** NIG-500's USD 16.9m investment in NIG-510 was in the investment register, and
in the roll-forward, and in no ledger. The consolidation engine found it: the investment
elimination had a register relationship with nothing to eliminate against.

**Why it survived so long.** The source control that should have caught it, `P2-INV-01`,
iterated the **investments the ledgers contained** and checked each against the register. Every
investment that existed was correct — so the control passed, perfectly, while an entire
relationship was missing. A control built that way can only ever find a wrong row. It is
structurally incapable of finding a missing one, and a missing row is the more dangerous defect
because nothing about the accounts looks unusual: the trial balance still closed, because the
retained-earnings plug absorbed the difference.

**The permanent fix.** `P2-INV-01` was rebuilt to iterate the **register** — all 463
relationship-periods — and to classify each as present, missing, wrong amount, wrong
relationship, duplicated or early. A relationship the ledgers do not contain now fails, because
the register is what requires the balance to exist.

**And the second-order fix**, because this was the *second* time the same shape of defect cost
a phase — `P2-IC-01` had it too, walking the intercompany lines that already carried a
counterparty. The rule was written down and applied to every Phase 4 control:

> **Controls iterate from the authority that requires the data, not from the data being
> tested.**

For investments the authority is `ref_investment_register`. `P4-INV-01` walks it and requires
an acquisition schedule for every relationship; fixture F4-08 removes one schedule and is
caught by it. A control walking the schedules could never have seen it.
