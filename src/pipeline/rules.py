"""
The mapping rule language, and its compiler.

Conditional mapping logic is configuration, not code.  `config/mapping/mapping_rules.csv`
holds one row per rule branch; this module parses each condition into a small typed tree,
validates every field it names against an allow-list, and compiles it to SQL.

The language is deliberately small.  It has to express the rules the approved source charts
actually describe -- a department set, an attribute equality, a maturity threshold -- and
nothing else.  Anything wider would be arbitrary SQL wearing a configuration file's
clothes, and would put business logic somewhere no control could reach it.

    condition   := clause { ' AND ' clause }
    clause      := 'TRUE'
                 | field op literal
                 | field 'IN' '(' literal { ',' literal } ')'
                 | field 'NOT IN' '(' literal { ',' literal } ')'
                 | field 'IS NULL' | field 'IS NOT NULL'
    op          := '=' | '<>' | '<=' | '>=' | '<' | '>'
    literal     := "'" text "'" | number

A field is resolved against the standardised line in one of two ways, and the difference
matters:

    a context field       a native or dimension-resolved column: the entity, the department
                          code, the cost centre, the partner, the account
    a line attribute      something the posting itself declares, parsed out of the source
                          system's attribute field into `attr_<name>`

`dept_function` is both: the standardised layer resolves it attribute-first and falls back
to the cost-centre dimension, and `P3-MAP-07` reports every line where the two disagree.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass

from .config import CONFIG
from .standardise import CONTEXT_FIELDS, LINE_ATTRIBUTES

RULES_FILE = CONFIG / "mapping" / "mapping_rules.csv"

OPERATORS = {"=", "<>", "<=", ">=", "<", ">"}
RULE_CLASSES = {"SPLIT_BRANCH", "SPLIT_DEFAULT", "DERIVED"}

_CLAUSE = re.compile(
    r"^\s*(?P<field>[a-z_]+)\s*"
    r"(?:(?P<op>=|<>|<=|>=|<|>)\s*(?P<value>'[^']*'|-?\d+(?:\.\d+)?)"
    r"|(?P<setop>NOT IN|IN)\s*\((?P<set>[^)]*)\)"
    r"|IS\s+(?P<null>NOT\s+NULL|NULL))\s*$",
    re.IGNORECASE)


class RuleError(ValueError):
    """A rule that cannot be trusted. Always fatal: a mapping engine must not guess."""


@dataclass(frozen=True)
class Rule:
    rule_id: str
    erp_system: str
    source_account: str
    priority: int
    condition: str
    target_group_account: str
    rule_class: str
    effective_from: str
    effective_to: str | None
    is_active: bool
    basis: str
    notes: str

    @property
    def is_default(self) -> bool:
        return self.rule_class == "SPLIT_DEFAULT"


def resolve_field(name: str) -> str:
    """The standardised column a rule field refers to."""
    if name in CONTEXT_FIELDS:
        return name
    if name in LINE_ATTRIBUTES:
        return f"attr_{name}"
    raise RuleError(
        f"unknown field '{name}'. A rule may only reference a context field "
        f"({', '.join(sorted(CONTEXT_FIELDS))}) or a line attribute "
        f"({', '.join(sorted(LINE_ATTRIBUTES))}).")


def _literal(token: str) -> str:
    token = token.strip()
    if token.startswith("'") and token.endswith("'"):
        body = token[1:-1]
        if "'" in body:
            raise RuleError(f"quote inside literal {token}")
        return f"'{body}'"
    if re.fullmatch(r"-?\d+(\.\d+)?", token):
        return token
    raise RuleError(f"literal must be quoted text or a number, got {token!r}")


def compile_clause(clause: str) -> str:
    """One clause of a condition, as SQL over the standardised line."""
    if clause.strip().upper() == "TRUE":
        return "TRUE"
    m = _CLAUSE.match(clause)
    if not m:
        raise RuleError(f"cannot parse condition clause {clause!r}")
    column = resolve_field(m.group("field").lower())
    if m.group("null"):
        return (f"{column} IS NULL" if m.group("null").upper() == "NULL"
                else f"{column} IS NOT NULL")
    if m.group("setop"):
        values = [_literal(v) for v in m.group("set").split(",") if v.strip()]
        if not values:
            raise RuleError(f"empty set in {clause!r}")
        negate = m.group("setop").upper() == "NOT IN"
        expr = f"{column} IN ({', '.join(values)})"
        return f"NOT ({expr})" if negate else expr
    op, value = m.group("op"), _literal(m.group("value"))
    if op not in OPERATORS:
        raise RuleError(f"unsupported operator {op!r}")
    if op in {"<", "<=", ">", ">="}:
        # A numeric comparison on an attribute that arrives as text. TRY_CAST keeps a
        # non-numeric value out of the comparison rather than failing the whole build --
        # the line then simply does not match, and falls to the default branch.
        return f"TRY_CAST({column} AS DOUBLE) {op} {value}"
    if op == "<>":
        return f"{column} IS DISTINCT FROM {value}"
    return f"{column} = {value}"


def compile_condition(condition: str) -> str:
    clauses = re.split(r"\s+AND\s+", condition.strip(), flags=re.IGNORECASE)
    return " AND ".join(f"({compile_clause(c)})" for c in clauses)


def load_rules() -> list[Rule]:
    """Read, validate and return the rule set. Any defect here stops the pipeline."""
    rules: list[Rule] = []
    with open(RULES_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["rule_class"] not in RULE_CLASSES:
                raise RuleError(f"{row['rule_id']}: unknown rule_class {row['rule_class']}")
            rule = Rule(
                rule_id=row["rule_id"], erp_system=row["erp_system"],
                source_account=row["source_account"], priority=int(row["priority"]),
                condition=row["condition"], target_group_account=row["target_group_account"],
                rule_class=row["rule_class"], effective_from=row["effective_from"],
                effective_to=row["effective_to"] or None,
                is_active=row["is_active"] == "TRUE",
                basis=row["basis"], notes=row["notes"])
            compile_condition(rule.condition)          # fail fast on a malformed rule
            if rule.is_default and rule.condition.strip().upper() != "TRUE":
                raise RuleError(f"{rule.rule_id}: a default branch must be unconditional")
            rules.append(rule)
    ids = [r.rule_id for r in rules]
    if len(ids) != len(set(ids)):
        raise RuleError("duplicate rule_id in the rule set")
    return rules


def defaults_by_account(rules: list[Rule]) -> dict[tuple[str, str], Rule]:
    out: dict[tuple[str, str], Rule] = {}
    for r in rules:
        if r.is_default or r.rule_class == "DERIVED":
            key = (r.erp_system, r.source_account)
            if key in out:
                raise RuleError(f"{r.source_account} has more than one default branch")
            out[key] = r
    return out


def match_case_sql(rules: list[Rule]) -> str:
    """
    One CASE expression evaluating every rule's condition against the joined line.

    The rule set joins to the line on (erp, source account) first, so each line only ever
    evaluates the handful of branches that belong to its own account. That keeps the whole
    mapping stage to a single pass over the ledger.
    """
    branches = "\n            ".join(
        f"WHEN '{r.rule_id}' THEN ({compile_condition(r.condition)})"
        for r in rules if r.is_active)
    return f"CASE r.rule_id\n            {branches}\n            ELSE FALSE\n        END"
