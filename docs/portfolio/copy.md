# Portfolio copy

Ready-to-use descriptions for the places the project will be presented. Every figure is the
current one from the committed registers; the synthetic nature of the environment is stated
in each description. Nothing here claims an outcome the work cannot support.

---

## GitHub repository description (≤ 350 characters)

Preferred:

> Multi-entity consolidation, controls and executive reporting for a synthetic $400M industrial group — three ERPs to a governed ledger, five-layer consolidation, Excel and Power BI, 677 automated controls.

Shorter alternative:

> Multi-entity consolidation, FP&A reporting, Excel and Power BI for a $400M industrial group — synthetic, deterministic, fully controlled.

## GitHub topics

`fp-and-a` · `financial-consolidation` · `financial-reporting` · `financial-modeling` ·
`power-bi` · `dax` · `pbip` · `excel` · `duckdb` · `python` · `finance-analytics` ·
`management-reporting` · `data-lineage` · `synthetic-data`

## GitHub / long description (about 200 words)

Northstar Consolidation & Board Reporting Platform is an end-to-end finance-transformation
environment for a synthetic PE-backed industrial group: twelve legal entities, four
currencies, three ERP systems, ~$400M of revenue and ~1.1M journal lines, all generated
deterministically from a fixed seed.

The platform ingests native extracts from three heterogeneous ERPs, harmonises them to a
group chart of accounts, and consolidates the group in five explicit layers — reported,
intercompany eliminations, consolidation adjustments (purchase price allocation, goodwill,
non-controlling interests, unrealised profit), management adjustments, and FX translation
with CTA. Governed reporting marts carry one authoritative definition per measure, and the
same numbers reach a sixteen-sheet Excel management reporting workbook and a ten-page Power BI
executive report built on a governed semantic model (PBIP/TMDL, 96 measures).

What sets it apart is the control architecture: 677 automated controls across eight
registers, 83 fault fixtures that each reintroduce a specific defect and require the control
named for it to fail, reconciliation across every artefact — ledger, marts, workbook, model,
rendered page — and a defect register recording what the controls found and what each finding
changed. The workbook is calculated and rendered by Excel; the Power BI project is validated
in the engine and in Power BI Desktop. A model can balance, render and still be wrong; this
platform is built to notice.

## Upwork portfolio entry

**Title.** Multi-Entity Financial Consolidation & Management Reporting Platform

**Categories.** FP&A modelling · finance transformation · consolidation and reporting ·
Power BI · Excel automation

**Description (about 700 characters).**

> Designed and built a complete consolidation and management-reporting platform for a
> twelve-entity, four-currency industrial group running three ERP systems: source
> harmonisation to a group chart of accounts, a five-layer consolidation engine (intercompany,
> PPA, NCI, unrealised profit, FX/CTA, management adjustments), governed reporting marts, a
> sixteen-sheet Excel management reporting workbook and a ten-page Power BI executive report
> on a governed semantic model. 677 automated controls, 83 fault fixtures and cross-artefact
> reconciliation give the CFO a traceable path from every board figure to the source journal.
> Built on a synthetic, deterministic dataset so every number is reproducible and shareable.

## Resume bullets

* Built an end-to-end multi-entity consolidation and management-reporting platform for a
  synthetic $400M, twelve-entity, four-currency industrial group on three ERPs: COA
  harmonisation, a five-layer consolidation engine (IC, PPA, NCI, unrealised profit, FX/CTA),
  governed reporting marts, an Excel management reporting workbook and a Power BI executive
  report on a governed semantic model.
* Designed the control architecture that proves it: 677 automated controls, 83 fault fixtures
  each caught by the control named for it, reconciliation across every artefact, deterministic
  builds with lineage, and a defect register of what the controls found.

## LinkedIn Featured (about 350 characters)

> Northstar: an end-to-end finance-transformation platform for a synthetic $400M industrial
> group — three ERPs harmonised, twelve entities consolidated in five explicit layers, Excel
> and Power BI reporting on one governed set of numbers, and 677 automated controls that
> proved a model can balance, render and still be wrong. Reproducible from a fixed seed.

## A note on claims

The environment is synthetic. The copy therefore describes what was built and what the
controls found, never a client outcome (hours saved, close shortened, errors prevented in
production). Where a figure appears, it is the current count in the committed registers.
