# Case study — Northstar Consolidation & Board Reporting Platform

*A synthetic portfolio environment. The group, its ledgers and its financials are generated
by this repository to be realistic and internally consistent; no real organisation's data was
used. The engineering, the accounting and the controls are real.*

---

## Situation

Northstar Industrial Group is a PE-backed industrial group of ~$412M revenue, twelve legal
entities in five countries, four functional currencies and ~2,450 people, assembled through
acquisition in seven years. Finance was never rebuilt to match. Three ERP systems carry three
charts of accounts and three sign conventions. The monthly consolidation lives in a
spreadsheet: FX is translated at annual average rates with the translation adjustment plugged
to balance, intercompany is reconciled by email, the cash flow statement is rebuilt by hand
and breaks whenever the balance sheet changes, and covenant leverage — the number the lender
cares about most — cannot be traced from the board pack back to a journal.

The CFO's summary of the position: *the numbers are probably right; I cannot prove they are
right, and I cannot show the board where they came from.*

## Challenge

Build the platform that replaces the spreadsheet, and make it defensible:

* harmonise three heterogeneous ERP environments into one governed ledger without losing the
  ability to trace any group figure to its source line;
* consolidate correctly — intercompany, purchase price allocation, goodwill, non-controlling
  interests, unrealised profit in inventory, FX translation and CTA, management add-backs —
  with each step separately identifiable;
* deliver the reporting a CFO, a board and a lender actually use: an Excel management
  reporting workbook and a Power BI executive report, on the same governed numbers;
* prove all of it, continuously, with controls that would catch the mistakes consolidations
  actually make.

## Approach

Data, then accounting, then controls, then reporting — in phase gates, each with written
acceptance criteria and a review before the next began.

1. **Anchors before data.** The group's financial anchors (three statements, KPIs, business
   unit and entity figures, FX and intercompany) were defined and proven as an executable
   model before a single transaction was generated. Synthetic ERP data was then generated to
   hit those anchors and tested back against them.
2. **Harmonise without netting.** Ingestion, standardisation and chart-of-accounts mapping are
   separate, evidenced layers, so the reconciliation from what the ERPs said to what the group
   reports is a standing output.
3. **Consolidate in explicit layers.** Reported, intercompany eliminations, consolidation
   adjustments, management adjustments, translation. Statutory and management bases are
   compositions of the layers, not separate calculations.
4. **One authoritative definition per measure.** Governed reporting marts carry each measure
   once, at declared grain, on monthly, year-to-date and full-year bases, with variance and
   favourability decided upstream of any report.
5. **Control at the point of transformation, and prove the controls with faults.** Every
   layer has a control register; every control family has fixtures that reintroduce a
   specific defect and require the control named for it to fail.
6. **Validate artefacts natively.** The workbook is calculated and rendered by Excel; the
   Power BI project is deployed to the engine, opened and refreshed in Power BI Desktop, and
   its rendered pages are read back — because a model can be valid in the engine and refused
   by Desktop, and a page can be right in every number and wrong in its scope.

## Solution

An integrated platform, reproducible from a fixed seed:

| layer | what was built |
|---|---|
| Sources | three synthetic ERP environments, 507 native extracts, ~1.1M journal lines, 80 controls over the generated ledgers |
| Harmonisation | parsers for every native format, sign and period normalisation, a mapping engine with acceptance evidence, conformed dimensions |
| Consolidation | the five-layer engine, every entry a journal with a rule and its evidence; 72 controls and 23 fault fixtures |
| Marts | fifteen governed marts with declared keys and grain, 304 key-and-grain controls |
| Excel | a sixteen-sheet management reporting workbook on one style system, refreshed from the marts, calculated and rendered natively, reconciled 17 ways |
| Power BI | a governed semantic model (28 tables, 96 measures, PBIP/TMDL) and a ten-page executive report generated from declarations; 68 semantic, 43 report and 12 hierarchy-and-scope controls, validated in the engine and in Desktop |
| Lineage | canonical build ids per phase, digests per artefact, a lineage page in the report, a defect register |

## Key capabilities

* Group, business-unit and entity performance against budget, forecast and prior year, on
  month, year-to-date and full-year bases, with favourability decided by the measure.
* Cash flow derived from balance-sheet movements and checked every month; liquidity against
  the minimum-cash policy.
* Three EBITDA definitions — statutory, management-adjusted, covenant — kept apart and bridged.
* Covenant leverage against the agreement's own limit, tested only where the agreement tests
  it, *Indicative* everywhere else.
* The consolidation bridge: what each layer contributed to EBITDA and net income on the same
  basis as the headline figure it reconciles to.
* Account-level drill on a governed hierarchy; workforce and capital on corrected unique keys.
* Every count on the control pages read from a register, never typed.

## Control philosophy

A model can balance, render and still be wrong. Most of the defects in the register were found
in artefacts that balanced: an investment in the register and not in the ledger; a historical
FX rate valid for the wrong period; a reserve created to make a balance sheet close; an
intercompany control blind to the counterparties it could not see; a project key that
identified 1,846 projects with 395 values; a prior-year version that existed in no master; a
Power BI model the engine ran and Desktop refused; a business-unit dimension that filtered
nothing; a percentage that summed; a caption sorted by a key at the wrong grain.

The response each time was the same: fix at the source, add the control that would have
caught it, add the fixture that proves the control, and write down the lesson. The platform
now carries 677 automated controls, 83 fault fixtures and reconciliation across every artefact
it produces.

## Result

Management reporting a CFO can put in front of a board and a lender, with a traceable path
from every figure to the source journal that produced it — in two artefacts that agree with
each other and with the marts beneath them, rebuilt identically from source in minutes, and
proven by controls that have already caught the mistakes they were designed for.

## Demonstrated skills

FP&A and management reporting · multi-entity consolidation (IC, PPA, goodwill, NCI, unrealised
profit, FX/CTA, management adjustments) · covenant monitoring · financial systems and data
architecture · Excel automation and design · Power BI semantic modelling and report design
(PBIP, TMDL, DAX) · control design and fault-based testing · lineage and reproducibility ·
phase-gated delivery with written acceptance criteria.
