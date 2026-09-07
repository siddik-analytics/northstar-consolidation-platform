# Power BI Deliverables

Built in Phase 7. Specified in `docs/reporting-design.md` §4.

A single `.pbip` project in **PBIP / TMDL / PBIR** format, so the semantic model and the
report are text and can be reviewed in a pull request (ADR-0010). A published `.pbix` is a
build artefact, not a source file, and is git-ignored.

- Star schema, import mode, incremental refresh partitioned on `period_key`
- Explicit measures only; implicit measures disabled
- Two calculation groups: `Time Intelligence` and `Scenario Comparison`
- Account-aware favourable/unfavourable variance logic, defined once
- Twelve report pages, two drill-through pages, one information page
- Row-level security by entity

Targets: page render under 3 seconds cold, under 1 second warm.
