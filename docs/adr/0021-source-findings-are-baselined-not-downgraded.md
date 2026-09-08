# ADR-0021: A control outcome has three states, and a source finding is baselined

- **Status:** Accepted
- **Date:** 2026-09-07
- **Phase:** 3
- **Related:** ADR-0019 (ingestion layers), CTL-DQ-09, CTL-DQ-11,
  `config/controls/source_exception_register.csv`

## Context

Phase 3 was given a frozen source layer and an explicit instruction: if ingestion reveals a
defect in Phase 2 data, stop and document it — do not silently patch the generator. It found
four, and they break seven controls.

That leaves the control framework with a problem it did not have before. A control can now
fail for two entirely different reasons:

- **the pipeline is wrong** — a mapping, a sign, a join, something this phase owns and must fix
- **the data is wrong** — and this phase is not permitted to touch it

Both were, until now, `FAIL`. Two responses are available and both are bad. Downgrade the
second kind to a warning and it stops being read: a warning that is expected every run is
indistinguishable from a warning that appeared this run. Leave it failing and the build is
red every day, which produces exactly the same blindness by a different route — the first
thing anyone does with a permanently red build is stop looking at it.

The failure mode being avoided is specific: **a known defect becoming a hiding place**. If
`P3-MAP-12` reports "postings whose declared classification contradicts their cost centre"
and the team has accepted that finding, then a *new* posting with the same shape — a genuine
mapping regression, or a fresh source defect — lands inside the accepted finding and moves
nothing. The control is still there, still reporting, and has quietly stopped working.

## Decision

**A control outcome is one of three states.**

| Status | Meaning |
|---|---|
| `PASS` | the control holds |
| `FAIL` | **the pipeline is wrong.** A blocking failure stops the build |
| `SOURCE_FINDING` | the control does not hold, and the cause is a defect in data this phase may not change. The pipeline is behaving correctly; the data is not |

A `SOURCE_FINDING` is never downgraded to a pass and never absorbed. It is reported with its
population, its amount and the defect reference it belongs to, and it is carried onto the
phase report as an open item.

**And a source finding is baselined at the population it was accepted at.** Every accepted
finding is registered in `config/controls/source_exception_register.csv` with its control id,
its defect reference, the phase that raised it, the accepted population and its unit, why it
was accepted, and the phase by which the underlying defect is expected to be corrected. The
control then compares against that baseline rather than against zero:

| Measured | Outcome |
|---|---|
| nil | `PASS` — the source was corrected |
| exactly the accepted population | `SOURCE_FINDING` — the known defect, unchanged |
| **more** | **`FAIL`** — something new is wrong |
| **fewer** | **`FAIL`** — the exception is stale and must be retired |

The third row is the one that earns the register; the fourth stops an exception outliving the
defect it excuses. An entry with no expiry is rejected by test.

## Consequences

**The population is the control.** For a defect like P2-D-02 — 5,710 postings whose declared
classification does not agree with their cost centre, affecting no reported figure — the
count is the only thing that can be asserted. Asserting it is strictly stronger than the
zero-tolerance control it replaces, which could only ever be red.

**An accepted finding cannot drift into permanence.** Each carries the phase by which it is
expected to be corrected, and the register is small enough to read in full at every phase
gate.

**It is not a tolerance and must not become one.** The register accepts a *named defect at a
measured population*, never a band, a percentage or a rounding allowance. Nothing in it
loosens a threshold: `P3-MAP-12` still fails at 5,711.

**The judgement of what may be registered stays with the owner.** Phase 3 may raise an
exception; it may not decide that a defect is acceptable. Each entry names the defect, the
amount and the downstream consequence, and P2-D-03 is recorded as a blocker for Phase 4
rather than as an accepted state of affairs.

## Alternatives rejected

**Downgrade source findings to warnings.** Loses them. A warning that fires every run is
noise within a week.

**Leave them as failures and let the build stay red.** Same outcome, worse ergonomics, and it
destroys the signal from a real pipeline regression.

**Suppress the offending rows from the control's population.** This is the one that actually
hides things: the rows disappear, the control goes green, and the next defect in those rows
is invisible. The register keeps the rows in the population and asserts their count instead.
