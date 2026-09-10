# Phase 6A.3 — report-discovered semantic integrity correction

**Status:** sealed, awaiting owner review before Phase 6B resumes
**Baseline:** `331814d` (Phase 6B stop, three defects registered); Excel frozen at `bde5ead1fbd6f945`
**Docs:** [semantic model](../powerbi-semantic-model.md) · [measures](../powerbi-measures.md) ·
[controls](../powerbi-controls.md) · [defect register](../defect-register.md) ·
[lessons §16](../architecture-lessons.md)

---

## 1. What this phase is

The first report built on the sealed model put a business unit on an axis, a percentage in a
matrix and a negative number on a card, and each was wrong in a way no control had asked
about. Phase 6B stopped; this phase corrects the model narrowly, adds the controls that were
missing, and reseals. The report at `331814d` is preserved and regenerated against the
corrected model with no design change; the three defects correct its behaviour on their own.

## 2. The corrections

| defect | correction | proof |
|---|---|---|
| **P6B-D-05** Business Unit filtered nothing | one active, single-direction relationship `Entity[bu_code] (*) → Business Unit[bu_code] (1)`, so the filter flows Business Unit → Entity → fact. The five direct fact→unit paths stay inactive | units sum to the Group for Revenue, Gross Profit, Statutory and Adjusted EBITDA, EBIT, Net Income, Closing FTE and CapEx; unit revenue matches `mart_financial_ytd` by `bu_code` to the cent (§4) |
| **P6B-D-04** `[Variance %]` summed stored percentages | `DIVIDE ( [Variance], ABS ( [Variance Comparator] ) )` at every grain — one architecture, no stored-percentage branch. It is the mart's own convention: `var / |comparator|` on all 17,462 rows with a non-zero comparator | 60 grain × comparison × basis combinations agree with SQL over `mart_variance` to 1.1e-16; the leaf value equals the stored one (−0.037956) |
| **P6B-D-03** Excel-style format strings | `M_USD = '#,0,,.0;(#,0,,.0);"–"'` and `M_USD2` likewise, chosen by rendering (§5). The report's interim projection overrides are removed; display units are held at None | the engine renders 5.6, (5.6), –, 279.0, (0.9); pages render `279.0`, `(5.6)`, axes `40.0`/`–`, ratios `5.00x` |

Nothing else in the model changed: consolidation, FX, CTA, NCI, PPA, PUP, Covenant EBITDA,
the Actual cutoff, the scenario and version architecture and the Capital Project key are as
sealed.

**Excel.** The approved design and every financial value are untouched. Under the same
exception the owner accepted at Phase 6A.2, the workbook's control-status tables (Cover and
sheet 13) now read the Phase 6A register's 68 controls rather than 53 — `tools/workbook_diff.py`
frozen (`bde5ead1fbd6f945`) → rebuilt (`bf847b4327526a39`): **4 numeric cells, all that
count; 0 text; 0 financial**; 17/17 reconciliations, 0 layout findings. One checkout of
`e186cf8` reverts it if the owner prefers the stale count.

## 3. Six narrow reporting measures (owner-approved scope)

| measure | what it is | what it is not |
|---|---|---|
| `Account Amount` | the monthly mart at account grain, on the statement measures' reporting basis, period basis and Actual cutoff; reconciles to the Revenue line within a dollar of monthly cent rounding (`P6-XAR-20`) | not a new financial definition — month, year-to-date and full-year are sums of the mart's rows |
| `Layer EBITDA`, `Layer Net Income`, `Layer Entries` | the consolidation bridge by layer and fiscal year, as `mart_consolidation_bridge` holds it: Reported, IC eliminations, consolidation adjustments, management adjustments, translation | presentation of the approved layers, not a policy |
| `Revenue Share of Group` | revenue in context ÷ Group revenue in the same period, scenario and basis (removes only Business Unit and Entity) | |
| `Revenue Share of Unit` | revenue in context ÷ the unit's revenue (removes only Entity) | a separate measure, so a denominator never changes meaning invisibly |

**Deferred, on record** (`P6-COV-02`): DSO, DIO, DPO, cash conversion cycle, revolver drawn
and available, principal by instrument — each needs a metric-policy decision nobody has made.

## 4. Business Unit filtering, by measure (Aug 2026, YTD, Actual, statutory)

| measure | Group | sum of units | units |
|---|---|---|---|
| Revenue | 278,980,889.78 | 278,980,889.78 | FC 103.6m · IS 84.1m · ES 50.5m · AM 40.8m · CORP 0 |
| Gross Profit | 75,980,813.59 | 75,980,813.59 | five distinct |
| Statutory EBITDA | 28,100,907.83 | 28,100,907.83 | five distinct |
| Management Adjusted EBITDA | 31,911,102.90 | 31,911,102.90 | five distinct |
| EBIT | 15,473,409.60 | 15,473,409.60 | five distinct |
| Net Income | (939,022.82) | (939,022.82) | five distinct |
| Closing FTE | 2,477.4 | 2,477.4 | five distinct |
| Actual CapEx (August) | 1,895,221.42 | 1,895,221.42 | five distinct |

The Group figures are recomputed from the engine, not typed; the unit revenues equal the
mart's by `bu_code`.

## 5. The format test

Rendered in the engine with `FORMAT()`, then on cards and axes in Desktop:

| value | Excel form `#,0.0,,` | chosen `#,0,,.0` |
|---|---|---|
| 5,553,457.50 | `5,553,457.5` | `5.6` |
| −5,553,457.50 | `(5,553,457.5)` | `(5.6)` |
| 0 | `–` | `–` |
| 278,980,889.78 | `278,980,889.8` | `279.0` |
| −939,022.82 | `(939,022.8)` | `(0.9)` |

The Excel form scales nothing in Power BI (and, on a visual, leaves a stray comma). One
nuance is recorded rather than hidden: the engine picks the zero section on the *rounded*
value, so 49,999 prints `–` where the workbook prints `0.0`.

**Display-units rule.** A measure that scales in its own format is shown with display units
*None*; a K/M/B unit on top of it would scale twice. `P6-FMT-06` reads every generated visual
for a scaled measure under a display unit other than None, and `P6-FMT-05` for any
projection-level format on a money measure. Both are clean.

## 6. Controls and fixtures

| | before | after |
|---|---|---|
| controls | 53 in 5 families | **68 in 9 families**, 68/68 pass, 0 not executed |
| fixtures | 12 | **16**, 16/16 detected by their intended control |

`P6-PATH-01…04` active-path integrity · `P6-PCT-01…02` aggregate-percentage integrity ·
`P6-FMT-01…06` format integrity · `P6-COV-01…02` reporting-concept coverage ·
`P6-XAR-20` account-grain reconciliation. Fixtures `F6A3-01…04` put each defect back and
add an unmapped concept.

## 7. Digests

| digest | 6A.2 | 6A.3 | why |
|---|---|---|---|
| `definition_digest` | `c7f74db69a967dd9` | `af1c6264f61aeb66` | one relationship added, one measure's DAX corrected, one format constant changed, six measures added — every one an approved definition change |
| `project_digest` | `9db029ca825664ae` | `28178e288544b27f` | the above, and the report regenerated |
| `build_id` | `92d8040957b6a34f` | `cfefefbaa93f16a1` | `config.py`, `measures.py`, `model.py` are declared inputs |

## 8. Native validation

Desktop 2.157.1354.0 opened the regenerated project through its own Open dialog, refreshed
every partition, and the report's pages rendered with zero visual errors; the unit page now
reads 103.6 / 84.1 / 50.5 / 40.8 for revenue by unit and 21.8 / 4.6 / 2.5 / 13.4 / (10.4) for
adjusted EBITDA — the workbook's Business Units sheet — and the Executive Overview's
variance column reads (2.0%) for revenue and (9.4%) for EBITDA. Renders:
`docs/assets/phase-06a-3/`.

Phase 6B has not resumed.
