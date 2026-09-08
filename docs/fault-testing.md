# Fault testing

A control that has never failed has never been tested. Both the pipeline and the consolidation
engine are run against deliberately broken inputs, and each fixture names the control family
that is supposed to find it.

    python -m src.pipeline.faults      # Phase 3, 10 fixtures
    python -m src.consol.faults        # Phase 4, 19 fixtures

Results are committed at `data/phase03_fault_results.csv` and `data/phase04_fault_results.csv`.

---

## Detection is not the same as something failing

The distinction the harness enforces, and the reason it exists:

| Verdict | Meaning |
|---|---|
| `DETECTED` | caught by a control in the family that **owns** the risk |
| `ACCIDENTAL_DETECTION` | caught only by an unrelated control — recorded as a **control-design defect**, not a success |
| `NOT_DETECTED` | no control fired |
| `SUPPRESSED` | the fixture proves a gate holds: nothing was posted and nothing moved |
| `SEPARATION_PROVEN` | the fixture proves two bases stay apart, showing its working |
| `NOT_APPLICABLE_DEFERRED` | no artefact at this phase contains what the fault would be measured against; the owning control is named and the fixture deferred |

A fault found by a control that does not own it is a control-design defect wearing the costume
of a success. If the intercompany fixture is caught only because the balance sheet stopped
balancing, then the intercompany reconciliation is still untested and the next intercompany
defect — one that happens to balance — will pass.

Two further rules the Phase 4 harness follows:

* **The fault is injected into an input the engine consumes** — the ownership register, the
  investment register, the acquisition schedules, the chart of accounts, the intercompany
  holdings, the historical rates — and never into the engine's own output. Corrupting an answer
  and watching a control notice proves nothing about whether the engine would ever produce that
  answer.
* **Every fixture runs a full consolidation.** No fixture is checked against a fragment.

Each fixture runs inside a transaction that is rolled back. The first version of the harness
reused one database copy without one, and the input tables Phase 4 only *reads* kept their
damage: from the fifth fixture on, every run failed on the previous fixture's fault and the
results looked like a control suite in a very good mood.

---

## Phase 4 — 19 of 19 handled as intended, 0 accidental detections

| Fixture | Injected defect | Intended family | Result | Detected by |
|---|---|---|---|---|
| F4-01 | a second ownership row effective at the same time | `P4-OWN` | DETECTED | `P4-OWN-03` |
| F4-02 | NIG-200's parent set to its own subsidiary | `P4-OWN` | DETECTED | `P4-OWN-02` |
| F4-03 | NIG-510 reparented to Topco, register unchanged | `P4-OWN` | DETECTED | `P4-OWN-05` |
| F4-04 | NCI % set to 0.10 against a group % of 0.80 | `P4-OWN` | DETECTED | `P4-OWN-04` |
| F4-05 | share capital given `fx_method = CLOSE` | `P4-FX` | DETECTED | `P4-FX-04` |
| F4-06 | NIG-410's opening translation base deleted | `P4-FX` | DETECTED | `P4-FX-02` |
| F4-07 | NIG-410's opening rate moved 5% | `P4-FX` | DETECTED | `P4-FX-04` |
| **F02** | **USD 45,000 removed from one side of an IC pair** | **`P4-IC`** | **DETECTED** | **`P4-IC-01`** |
| F4-08 | ACQ-011's acquisition schedule removed | `P4-INV` | DETECTED | `P4-INV-01` |
| F4-09 | ACQ-011 eliminated in 202401 instead of 202407 | `P4-INV` | DETECTED | `P4-INV-02`, `P4-INV-03` |
| F4-10 | amortisation started in January of the acquisition year | `P4-INT` | DETECTED | `P4-INT-02` |
| F4-11 | opening accumulated amortisation above cost | `P4-INT` | DETECTED | `P4-INT-03` |
| F4-12 | a month of intercompany holdings deleted | `P4-PUP` | DETECTED | `P4-PUP-02` |
| F4-13 | stock still held overstated by 20% | `P4-PUP` | DETECTED | `P4-PUP-01` |
| F4-14 | an APPROVED adjustment with no approver or rationale | `P4-MGT` | DETECTED | `P4-MGT-02` |
| F4-15 | a balance sheet account's cash flow category blanked | `P4-CF` | DETECTED | `P4-CF-03` |
| F4-16 | an account given a second balance sheet caption | `P4-BS` | DETECTED | `P4-BS-02` |
| F4-MGT-LEAK | an APPROVED layer-4 adjustment of USD 2.5m a month | separation | SEPARATION_PROVEN | 96 legs, 8 measures moved, statutory unmoved |
| F4-17 | the same adjustment marked DRAFT | suppression | SUPPRESSED | 0 legs, 0 measures moved |

### Fixtures that prove a negative must show their working

"Nothing broke" is also what an edit that never reached the engine looks like. So the two
non-detection fixtures read the engine's output back:

* `F4-MGT-LEAK` is only `SEPARATION_PROVEN` if layer 4 actually received legs **and** measures
  actually moved on the management basis **and** `P4-LAY-03` and `P4-BAS-01` still pass. It
  posts 96 legs and moves EBITDA and EBIT in all four years, while the statutory basis does not
  move at all.
* `F4-17` is only `SUPPRESSED` if the adjustment reached no layer and moved no measure.

### The four controls the fixtures exposed

Four Phase 4 controls were caught by their own fixtures — they did not fire, because they had
been written to walk the data rather than the authority. All four were rewritten in Phase 4A:
`P4-PUP-02`, `P4-INV-03`, `P4-INT-02` and `P4-OWN-06`. See
[`consolidation-controls.md`](consolidation-controls.md).

That is the return on fault testing. Four controls that would have passed forever, found by
nineteen deliberately broken builds.

---

## Phase 3 — 10 of 10 handled as intended

| Fixture | Defect | Owning family | Result |
|---|---|---|---|
| F01 | account absent from the ERP chart | `P3-MAP` | DETECTED |
| **F02** | **one-sided intercompany difference** | **deferred** | **`NOT_APPLICABLE_DEFERRED`** |
| F03 | missing FX rate | `P3-DIM` | DETECTED |
| F04 | duplicated journal | `P3-ING` | DETECTED |
| F05 | cost centre absent from the master | `P3-DIM` | DETECTED |
| F06 | amount that does not parse under the declared locale | `P3-ING` | DETECTED |
| F07 | posting date outside its own accounting period | `P3-ING` | DETECTED |
| F08 | payroll moved across the gross margin line | `P3-REC` | DETECTED |
| F09 | unbalanced journal | `P3-TB` | DETECTED |
| F10 | posting before the consolidation effective date | `P3-CMP` | DETECTED |

### F02, and why a deferral is a legitimate result

F02 removes USD 45,000 from one side of an intercompany pair. In Phase 3 the file parses, the
journal balances, the account maps, the dimension resolves and both trial balances close —
because a one-sided intercompany difference is a **valid posting at the entity that made it**.
There is no Phase 3 artefact in which the two sides of the pair meet.

Every Phase 3 control was therefore correct to pass, and claiming detection would have meant a
control firing for a reason it does not own. Phase 3 recorded the fixture as
`NOT_APPLICABLE_DEFERRED`, wrote down why, and named the Phase 4 control that would own it.

Phase 4 closed the deferral on those terms: the fixture runs through the **entire pipeline**
and then the elimination engine, and `P4-IC-01` — the pair reconciliation — catches it.
Detection by any other control would not have closed it.
