# Project Charter — Multi-Entity Consolidation & Board Reporting Platform

**Client:** Northstar Industrial Group, Inc. · **Sponsor:** Chief Financial Officer
**Engagement start:** September 2026 · **Current phase:** Phase 1 — Business Design & Architecture

## 1. The problem

Northstar has grown from a single platform business to a $412m, twelve-entity, five-country
group in seven years, almost entirely through acquisition. The finance function has not been
rebuilt to match.

Today:

| | |
|---|---|
| Month-end consolidation takes | **4 working days**, performed in a spreadsheet by two people |
| Source systems | **3 ERPs**, none of which will be migrated in the next 24 months |
| Charts of accounts | **3 different ones**, plus a German nature-of-expense presentation |
| Intercompany reconciliation | By **email**, with differences frequently carried forward |
| FX translation | Manual, at annual average rates, with CTA plugged to balance |
| Cash flow statement | Hand-built, breaks whenever the balance sheet changes |
| Budget vs forecast comparison | Rebuilt each cycle in a new workbook |
| Audit trail from board number to ERP | **Does not exist in reproducible form** |

The CFO's framing of the problem is precise, and worth quoting because it sets the standard
for the engagement: *"The numbers are probably right. I cannot prove they are right, and I
cannot show the board where they came from."*

That is not a reporting problem. It is a traceability problem that shows up as a reporting
problem.

## 2. What we are building

An integrated, reproducible consolidation and reporting platform:

1. **A consolidation engine** that harmonises three charts of accounts, translates four
   currencies, eliminates intercompany activity, allocates non-controlling interests, applies
   auditable adjustments and derives a cash flow statement that ties.
2. **A control framework** of 71 automated controls that makes correctness a property of the
   pipeline rather than of the person who built this month's file.
3. **An Excel management reporting and forecasting suite** for the CFO, the controller and
   FP&A.
4. **A Power BI executive reporting suite** for the CFO, the board and business unit leaders.
5. **A board reporting pack** with a structured commentary framework.
6. **Documentation** sufficient for a successor to operate and extend the platform.

## 3. Success criteria

The engagement succeeds if all of the following are true at handover:

| # | Criterion | Measure |
|---|---|---|
| 1 | The consolidation reproduces exactly | Same inputs produce byte-identical output |
| 2 | Every board figure traces to source | `CTL-REC-01` produced automatically each period |
| 3 | The statements are internally consistent | A = L + E, cash flow ties to cash, P&L ties to equity — all to $1 |
| 4 | Intercompany eliminates cleanly | Per entity pair, per account, per period — not in aggregate |
| 5 | FX is correct and explainable | CTA computed and independently verified, never plugged |
| 6 | FX is separable from performance | Constant currency available on every management measure |
| 7 | Controls actually block | No mart is published from a period with a failed blocking control |
| 8 | Close time reduces | 4 days to a target of 2 |
| 9 | Performance is acceptable | Full rebuild < 5 min; Power BI page < 3 s cold |
| 10 | It is maintainable by the client | Mappings, entities, adjustments and controls are configuration, not code |

## 4. Scope

### In scope
- 12 legal entities, 4 business units, 5 countries, 4 currencies, 3 ERPs
- FY2023–FY2025 actuals, FY2026 actuals to date, FY2026 budget, three FY2026 forecast versions
- Full consolidation including NCI, multi-tier investment elimination, purchase accounting and
  partial-period consolidation for two mid-year acquisitions
- Income statement, balance sheet, cash flow, and the full management reporting suite
- Automated control framework and reconciliation reporting
- Excel and Power BI deliverables, board pack, documentation, portfolio assets

### Out of scope
- Equity-method associates, joint ventures, disposals and discontinued operations (ADR-0009)
- Statutory local GAAP reporting; group reporting basis only
- Full tax provision by entity and deferred tax proof (modelled at effective rate)
- Defined benefit pension accounting
- Hedge accounting designation for the interest rate swap (ADR-0005)
- ERP migration or replacement
- Live connection to production systems — all data is synthetic and deterministic

### Explicitly not a goal
A large dashboard. The count of Power BI pages is deliberately constrained to twelve, each
answering a written question (`docs/reporting-design.md` §1).

## 5. Approach

**Anchor-first.** The group's financial anchors are defined and proven *before* any
transaction is generated, as an executable, self-testing model (ADR-0011). Synthetic data is
then generated to hit those anchors, and tested back against them. The alternative —
generating plausible-looking random data and reporting whatever emerges — produces a platform
with no business story, and management reporting without a story is a table of numbers.

**Configuration over code.** Entities, mappings, intercompany relationships, FX policy,
scenarios and controls are all version-controlled data files, validated in CI. A controller can
change a mapping through a pull request. Nobody needs a developer to add an account.

**Controls at the point of transformation.** Each control runs where the risk arises, not in a
batch at the end. A trial balance failure caught at ingestion costs minutes; caught after
consolidation it costs a day.

**Reproducible builds.** Clone the repository, run one command, get the same warehouse. No
manual steps, no undocumented spreadsheet in the critical path.

## 6. Phase gates

Work proceeds through formal approval gates. **No phase begins without written approval of the
preceding phase.** Each phase ends with a report in `docs/phases/`, a self-audit of its own
output, and an explicit list of decisions requiring owner input.

The full plan is in [`docs/phases/roadmap.md`](phases/roadmap.md).

## 7. Governance

| Role | Responsibility |
|---|---|
| Engagement Lead | Design integrity, phase gates, owner communication |
| Group Financial Controller (client) | Accounting policy, mapping approval, adjustment approval, control ownership |
| FP&A Lead (client) | Scenario definitions, driver assumptions, commentary standards |
| Treasury (client) | FX rates, debt and covenant data |
| Data Engineering | Ingestion, staging, data quality controls |
| Analytics Engineering | Warehouse, semantic model, reporting marts |

**Decision protocol.** Where a design decision has meaningful alternatives, it is recorded as
an ADR with the alternatives and the consequences stated. Where a decision is genuinely the
owner's to make — accounting policy, add-back definitions, scope — it is **flagged for approval
rather than assumed**. Those items are collected in
[`docs/open-questions.md`](open-questions.md).

## 8. Key risks

| Risk | Impact | Mitigation |
|---|---|---|
| Chart-of-accounts mapping is wrong in a way no balancing control catches | Gross margin materially misstated with every control passing | Conditional split rules must resolve or fail (`CTL-MAP-04`); business reasonableness controls (`CTL-BR-01`) |
| FX translation error hidden in CTA | Equity and net assets wrong, undetected indefinitely | CTA computed and independently verified (`CTL-FX-04`); never a plug |
| Intercompany differences absorbed into tolerance | Balances drift for years | Per-pair testing, not aggregate; mismatch ageing (`CTL-IC-03`) |
| Adjusted EBITDA definition drifts between artefacts | Covenant reporting inconsistent with the pack | Single account-flag definition, asserted by `CTL-FS-07` (ADR-0013) |
| Synthetic data has no coherent story | The reporting layer becomes meaningless | Anchor-first modelling with tolerance-tested reconciliation (`CTL-REC-06`) |
| Scope creep into a large dashboard | Effort spent on pages nobody opens | Every page must answer a written question |
| Model bounded to one fiscal year | Rework at the next year end | Scenario and version architecture is year-agnostic; `FC_FY27_P1` exists as proof |

## 9. Current status

**Phase 1 complete, awaiting owner review.** See
[`docs/phases/phase-01-report.md`](phases/phase-01-report.md).
