# The reporting control framework

36 controls over the reporting marts, and 17 reconciliations run against the calculated
workbook. Together they close the last gap in the chain: the consolidation is proved by Phases
2 to 4, and these prove that what a reader sees is what the consolidation says.

    python -m src.marts.run    # the mart controls
    python -m src.excel.qa     # the workbook checks

---

## Scenario and version integrity

The mart controls prove the reporting numbers. They do not prove that the *versions* those
numbers are filed under exist, and for four phases one of them did not: `PY_DERIVED` was the
comparator in one of the four approved comparisons and had no row in any version master
(defect P7-D-01, [ADR-0027](adr/0027-a-derived-version-is-still-a-governed-version.md)).

That family lives with the rest of the identity controls rather than here, because a version
that resolves to nothing is the same failure as a key that is not unique — see
[the key and grain framework](key-and-grain-framework.md):

    python -m src.integrity.controls

| control | asserts |
|---|---|
| `P7-VER-01` | every version code in every fact and mart resolves to the version master |
| `P7-VER-02` `P7-VER-03` | a version is compatible with its scenario, and a row with its version |
| `P7-VER-04` `P7-VER-05` | exactly one default per scenario, and no default outside the master |
| `P7-VER-06` … `P7-VER-11` | the derived-version policy: typed, locked, never source-loaded, naming its source, and equal to Actual at *t − 12* in both directions |
| `P7-VER-12` `P7-VER-13` | reserved scenarios stay unreportable and unpopulated |
| `P7-VER-14` | every reportable member is named, so no blank member is possible |

`P5-SCN-03` (each scenario has exactly one default version) remains where it is and now tests a
`ref_default_version` that is derived wholly from the governed dimension, with nothing unioned
in by hand.


## The rule, carried forward

> ### Different artefacts expressing the same financial measure must reconcile to one authoritative definition.

Phase 4C introduced it for reporting artefacts inside the consolidation. A mart is an artefact
and a workbook is an artefact, so the rule extends unchanged: **every reconciliation has one
side recomputed from `fact_financials`**, and never both sides from the same reporting
calculation. A mart agreeing with itself is not evidence, and neither is a workbook agreeing
with the mart it was built from unless the mart agrees with the ledger.

---

## Mart controls

| ID | Control | Threshold | Measured |
|---|---|---|---|
| `P5-REC-01` | The financial mart reconciles to the consolidated fact | 0.05 USD | **0.00** |
| `P5-REC-02` | Every consolidated period reaches the mart | 0 | 0 |
| `P5-REC-03` | The balance sheet mart reproduces the statement and balances | 0.01 USD | 0.00 / 0.00 |
| `P5-REC-04` | The cash flow mart reproduces the statement and still ties | 0.01 USD | 0.00 / 0.00 |
| `P5-REC-05` | Closing cash agrees between the cash flow and balance sheet marts | 0.01 USD | 0.00 |
| `P5-GRN-01` | The monthly mart holds its declared grain | 0 | 0 |
| `P5-GRN-02` | The measure mart holds its declared grain | 0 | 0 |
| `P5-GRN-03` | Every declared measure is populated | 0 | 0 |
| `P5-CAL-01` | Every stored subtotal equals its components | 0.01 USD | 0.00 |
| `P5-CAL-02` | Year to date and full year are the sums of their months | 0.01 USD | 0.00 |
| `P5-SCN-01` | No reserved scenario is exposed as a reporting option | 0 | 0 |
| `P5-SCN-02` | Every offered version carries data | 0 | 0 |
| `P5-SCN-03` | Each scenario has exactly one default version | 0 | 0 |
| `P5-SCN-04` | Every plan version covers a complete fiscal year | 0 | 0 |
| `P5-BAS-01` | No management adjustment reaches the statutory mart | 0 | 0 |
| `P5-BAS-02` | The two bases differ by layer 4 and by nothing else | explained | 0.00 |
| `P5-CMP-01` | Excluding intercompany accounts is a no-op on Actual | 1.00 USD | 0.04 |
| `P5-CMP-02` | Plan intercompany trade exists and is excluded from the measures | > 0 present | 2,976 rows |
| `P5-CMP-03` | Plan measures above EBIT are marked comparable | 0 | 0 |
| `P5-VAR-01` | Every variance is the base less the comparator | 0.01 USD | 0.00 |
| `P5-VAR-02` | Favourability is account-aware, not sign-aware | 0 | 0 |
| `P5-VAR-03` | Both favourability directions actually occur | 0 | 0 |
| `P5-VAR-04` | Every declared comparison is populated | 0 | 0 |
| `P5-AGG-01` | Business unit totals reconcile to the measure mart | 0.05 USD | 0.00 |
| `P5-AGG-02` | Entity totals reconcile to the measure mart | 0.05 USD | 0.00 |
| `P5-COV-01` | At each year end the rolling window equals the approved bridge | 0.01 USD | 0.00 |
| `P5-COV-02` | No covenant measure is null | 0 | 0 |
| `P5-COV-03` | The leverage limit steps down as the agreement requires | 0 | 0 |
| `P5-COV-04` | Headroom is the limit less the ratio | 0.0005 | 0.0000 |
| `P5-COV-05` | No leverage is reported on an incomplete window | 0 | 0 |
| `P5-OPS-01` | The headcount mart reproduces the headcount fact | 0.01 FTE | 0.00 |
| `P5-OPS-02` | Headcount is continuous and moves with net hiring | 0.0001 FTE | 0.0000 |
| `P5-OPS-03` | Every capital project row carries a project and a translated amount | 0 | 0 |
| `P5-OPS-04` | The debt roll-forward closes for every instrument and month | 0.01 USD | 0.01 |
| `P5-FX-01` | The FX mart's translation adjustment is the engine's | 0.01 USD | 0.00 |
| `P5-FX-02` | Constant currency equals reported for the presentation currency | 0 | 0 |

All **BLOCKING**. A reporting difference in a primary statement or a lender-facing measure is
not an informational warning.

### Three worth reading

**`P5-CMP-02` — a rule that excludes nothing looks exactly like a rule that works.** The
comparability rule removes intercompany accounts from both sides of every comparison. If the
plan happened to contain no intercompany rows, the rule would be untested and would look
correct forever. The control requires the plan's 2,976 intercompany rows to exist *and* to be
absent from the measures.

**`P5-VAR-03` — both answers must actually occur.** Favourability has three outcomes and a
control that only ever sees one has not exercised the rule. This requires both `FAVOURABLE` and
`UNFAVOURABLE` to appear for each direction.

**`P5-COV-01` — the window changes, the definition does not.** Covenant EBITDA is measured over
a rolling twelve months, because leverage divides a point-in-time net debt by twelve months of
earnings. The permitted add-backs and the sponsor fee cap are the approved bridge's, and the
control proves it: at each fiscal year end the rolling window *is* the fiscal year, so the two
must agree to the cent.

---

## Workbook checks

`python -m src.excel.qa` opens the workbook in Excel, forces a full calculation, and then
inspects and reconciles what comes back. openpyxl writes formulas and does not evaluate them, so
a workbook with `#REF!` in forty cells looks perfect to the library that produced it.

| Check | Applies to | Result |
|---|---|---|
| Error values — `#REF!`, `#VALUE!`, `#N/A`, `#DIV/0!`, `#NAME?`, `#NUM!`, `#SPILL!` | every report sheet | none |
| Used range within bounds | every report sheet | within 220 rows, 40 columns |
| Print area set | every report sheet | all 16 |
| Freeze panes set | every report sheet with a grid | all 14 |
| Objects on the sheet and inside the model | every chart | all 20 |
| P&L year to date, all 14 measures | against `mart_financial_ytd` | 14/14 agree |
| Balance sheet balances in the workbook | the workbook's own check row | 0.0000 |
| Closing cash | against `mart_cash_flow` | agrees |
| Net leverage at the reporting date | against `mart_covenants` | agrees |

**17 of 17 reconciliations agree. 0 blocking layout findings.** Results are written to
`data/phase05_workbook_qa.csv` and asserted by `tests/test_phase05_reporting.py`, so a
regression that quietly breaks a formula fails the suite rather than the reader.

The workbook build is also byte-reproducible — an `.xlsx` is a zip, and a zip records the
wall-clock time of each member, so two builds of identical data differed until the timestamps
and document properties were fixed.

---

## Visual review

Automated checks cannot see that a chart is unreadable, a heading is truncated or a number is
plotted as zero when it should be absent. Every sheet is therefore exported to PDF by Excel,
rendered to an image, and **looked at**.

What that found, in order, none of which any programmatic check would have caught:

| Found by looking | Why it mattered |
|---|---|
| Actual revenue plunging to zero every September | Excel plots an empty cell as zero; the actual series simply had not been posted yet |
| **A covenant breach reported at two dates the agreement never tests** | quarterly columns against a limit that steps at the fiscal year — the most expensive mistake a board pack can make |
| Net leverage 7.38x against a 4.50x limit | a fiscal-year EBITDA divided into a full net debt balance, for a year in progress |
| Every business unit at a 100% "margin" | revenue divided by revenue; the column needed to be a share of the group |
| "Not comparable" on every row | `SUMIFS` ignores booleans in a sum range |
| Revenue shown as (14.6) beside 279.0 two sheets earlier | the fact's credit-negative convention leaking into a report |
| Charts running off the right of the page | fixed chart widths on sheets narrower than the fixed width |
| A note overprinting the section band beneath it | Excel does not auto-fit a merged cell |
| A legend listing twelve months under a single line | a one-series chart does not need a legend |
| Truncated headings on six sheets | a column that carries words needs to be as wide as its own heading |
| `IT` rendered as `It` | `str.title()` does not know an acronym |

The first render attempt produced sixteen **blank white images** and reported success, because
the clipboard paste had not resolved before the export ran. A render that silently succeeds
while producing nothing is worse than no render, because the review then passes on an empty
page — so the workbook is now exported through Excel's own PDF writer, which is also the
artefact a reader would circulate.
