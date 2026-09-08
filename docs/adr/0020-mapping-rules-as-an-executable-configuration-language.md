# ADR-0020: Mapping rules as an executable configuration language

- **Status:** Accepted
- **Date:** 2026-09-07
- **Phase:** 3
- **Related:** ADR-0007 (COA mapping as effective-dated configuration, not code),
  ADR-0019 (ingestion layers), CTL-MAP-01 to CTL-MAP-08

## Context

ADR-0007 decided in Phase 1 that chart-of-accounts mapping is configuration, not code. The
approved source charts carry that decision at account level: a `group_account`, a
`mapping_type` of `DIRECT`, `MERGE`, `SPLIT` or `DERIVED`, effective dates, and — for the
conditional accounts — a `mapping_rule` column.

That column is **prose**:

```
dept in (D100,D200,D205,D300,D305,D310) -> 515100/515200 by BU;
dept in (D105,D110,D115,D120,D210,D215) -> 520100; else 610100
```

A human can read it. A pipeline cannot execute it. So Phase 3 had a choice: implement the
conditions in Python and let the prose become documentation of what the code does, or make
the rules executable and let the prose become the *basis* they were authored from.

Fifty-three source accounts across the three systems need conditional logic, and the split
they drive is not cosmetic: Aurora books all payroll to one account whatever the labour is,
so gross margin is not derivable from the account code at all.

## Decision

**`config/mapping/mapping_rules.csv` holds one row per rule branch, and the conditions are
executable.** 127 rules, each with a rule id, the ERP and source account it applies to, a
priority, a condition, a target group account, a rule class, effective dates, an active flag,
the chart narrative it was authored from, and a note.

**The condition is a small language with an allow-list, not SQL.**

```
condition   := clause { ' AND ' clause }
clause      := 'TRUE'
             | field op literal
             | field 'IN' '(' literal { ',' literal } ')'
             | field 'NOT IN' '(' literal { ',' literal } ')'
             | field 'IS NULL' | field 'IS NOT NULL'
op          := '=' | '<>' | '<=' | '>=' | '<' | '>'
literal     := "'" text "'" | number
```

A field must be either a **context field** — a native or dimension-resolved column such as
the entity, the department code, the cost centre or the partner — or a **line attribute**
parsed out of the posting's own attribute string. Anything else is rejected when the rule set
loads, and the whole build stops. `rules.py` parses each condition into clauses and *re-emits*
the SQL rather than interpolating the text, so a literal cannot carry a predicate and a field
cannot name a subquery. `test_a_rule_cannot_smuggle_sql_through_a_literal` holds it to that.

The language is deliberately just wide enough for the rules the approved charts describe. A
wider one would be arbitrary SQL in a configuration file, which is code in the place no
control can reach.

**An ambiguity is an exception, not something priority resolves.** If a line matches more
than one non-default branch it is `AMBIGUOUS` and blocks the close. Ordering by priority and
taking the first match would make two overlapping rules look like one working rule for as
long as nobody checked.

**Every conditional account declares its default branch explicitly**, as a rule with the
condition `TRUE` and the lowest priority. `P3-MAP-06` fails the build if one is missing:
a split with no default is a silent fall-through waiting for a posting that does not match.

**Account-level mapping stays in the source charts.** The rules file carries only the
conditional refinements. Copying 300 direct mappings into a second file would create two
places to change one fact.

**The expected-mapping manifest is an oracle and is never an input.** Phase 2 recorded, per
line, the group account Phase 3 is expected to produce. `reconcile.py` reads it to grade the
engine; no transformation stage may. `test_the_manifest_is_an_oracle_and_never_an_input`
asserts the separation by inspecting the stage modules directly, because a 100% score against
a file the engine can read means nothing.

**Where the prose and the mapping contract differ, the contract wins and the difference is
recorded in the rule's own note.** Two cases arose:

| Rule | Chart narrative | Rule as authored | Why |
|---|---|---|---|
| `SAB-60700-10` | `dept in (D200,D205,D215)` | `dept_function = 'FIELD'` | the enumeration omits D210, which is also a field department: it is an incomplete statement of the same idea |
| `KES-00089000-10` | `partner_bu = 'IS' -> service` | `partner_bu IN ('FC','AM') -> product`, else service | IC-SV-03 recharges Tyneside services to an Engineered Systems partner. Expressed the other way round the rule matches the intercompany matrix |
| `AUR-5100-20` | `dept in (D115,D120)` | kept on the department **code** | D105 and D110 share the indirect-operations *function* but belong in indirect labour: here the enumeration is the precise statement, and the function would be wrong |

The last of those is the point of keeping both a code and a function available to the
language: sometimes the department is the rule and sometimes its function is, and only the
narrative says which.

**A rule field is resolved attribute-first.** Where a posting declares its own classification
the source system is stating something about that line, so the declared attribute wins and
the posted dimension is the fallback. `P3-MAP-12` reports every line where the two disagree —
5,710 of them, which is source defect P2-D-02.

## Alternatives considered

**Implement the conditions in Python.** Rejected on ADR-0007's ground. It would also have put
the material accounting judgement — where payroll sits relative to the gross margin line — in
a place a finance reviewer cannot read or change.

**Make the `mapping_rule` prose column machine-readable in place.** Rejected. It would have
meant editing the approved Phase 1 charts to suit an implementation, and the prose is doing a
second job well: it is the human statement of intent that the executable rule is authored
*from* and audited *against*.

**Resolve ambiguity by priority.** Rejected: see above.

**Derive the rules from the expected-mapping manifest.** Rejected, and it would have been
easy. It reduces the acceptance test to a tautology.

## Consequences

- 1,013,640 of 1,080,782 lines — every line the source system actually classified — map to
  the oracle's expected group account with **100.000000%** agreement.
- Adding a source account or changing a split is a configuration change with an effective
  date and a rule id, reviewable in a diff, with no code change.
- The rule set is testable on its own: parseability, field legality, one default per
  conditional account, live targets, unique ids, effective dates.
- The language will need extending when a rule needs something it cannot say — an OR across
  clauses, or a lookup against a subledger. That extension is a deliberate act with a test,
  which is the intended cost.
