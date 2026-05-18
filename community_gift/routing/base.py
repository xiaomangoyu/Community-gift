"""Routing base: pluggable per-dimension routers.

A Router takes a context dict (host fields + derived values) and returns
a RouteDecision describing which rule matched and what fields to apply.

Rules are declarative YAML. Condition operators kept intentionally small;
add operators here when an actual yaml use case needs them — not before.
Future LLM-classify routers can implement the Router protocol the same way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol

import yaml


@dataclass
class RouteTraceEntry:
    rule_id: str
    matched: bool
    reason: str = ""
    skipped_because: str = ""


@dataclass
class RouteDecision:
    """Result of a single dimension router (color / shape / material / composition)."""

    dimension: str
    matched_rule_id: str            # "default" if nothing matched
    fields: dict[str, Any] = field(default_factory=dict)
    trace: list[RouteTraceEntry] = field(default_factory=list)

    def trace_dict(self) -> list[dict[str, Any]]:
        return [
            {
                "rule_id": entry.rule_id,
                "matched": entry.matched,
                "reason": entry.reason,
                "skipped_because": entry.skipped_because,
            }
            for entry in self.trace
        ]


class Router(Protocol):
    dimension: str

    def route(self, context: dict[str, Any]) -> RouteDecision: ...


# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------


def load_rules(path: Path) -> dict[str, Any]:
    """Load a routing rules.yaml. Returns {} if path missing."""

    if not path.exists():
        return {"version": 1, "defaults": {}, "rules": []}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("defaults", {})
    data.setdefault("rules", [])
    return data


# ---------------------------------------------------------------------------
# Condition matching
# ---------------------------------------------------------------------------


def evaluate_conditions(
    conditions: list[dict[str, Any]] | dict[str, Any] | None,
    context: dict[str, Any],
) -> tuple[bool, str]:
    """Evaluate a `when:` block. Returns (matched, reason).

    A `when:` block is a list of clauses ANDed together. A clause can be:
      {field: "host.primary_color", contains_any: ["黑", "black"]}
      {and: [<clause>, <clause>]}
      {or:  [<clause>, <clause>]}
      {not: <clause>}
    """

    if conditions is None:
        return True, "no conditions"
    if isinstance(conditions, dict):
        conditions = [conditions]

    reasons: list[str] = []
    for clause in conditions:
        ok, reason = _evaluate_clause(clause, context)
        if not ok:
            return False, reason
        if reason:
            reasons.append(reason)
    return True, "; ".join(reasons)


def _evaluate_clause(clause: dict[str, Any], context: dict[str, Any]) -> tuple[bool, str]:
    if "and" in clause:
        return evaluate_conditions(clause["and"], context)
    if "or" in clause:
        parts = clause["or"] or []
        for part in parts:
            ok, reason = _evaluate_clause(part, context)
            if ok:
                return True, f"or-match: {reason}"
        return False, "no or-branch matched"
    if "not" in clause:
        ok, reason = _evaluate_clause(clause["not"], context)
        return (not ok), f"not({reason})"

    field_path = clause.get("field")
    if not field_path:
        return False, "clause missing 'field'"
    value = _resolve_field(field_path, context)
    haystack = _to_text(value)

    if "contains_any" in clause:
        terms = [str(term).lower() for term in clause["contains_any"]]
        hit = next((term for term in terms if term and term in haystack), None)
        if hit:
            return True, f"{field_path} contains '{hit}'"
        return False, f"{field_path}='{_short(haystack)}' contains none of {terms}"

    if "contains_all" in clause:
        terms = [str(term).lower() for term in clause["contains_all"]]
        missing = [term for term in terms if term and term not in haystack]
        if missing:
            return False, f"{field_path} missing {missing}"
        return True, f"{field_path} contains all {terms}"

    if "equals" in clause:
        target = str(clause["equals"]).lower().strip()
        if haystack.strip() == target:
            return True, f"{field_path} == '{target}'"
        return False, f"{field_path}='{_short(haystack)}' != '{target}'"

    if "matches_regex" in clause:
        pattern = clause["matches_regex"]
        if re.search(pattern, _to_text(value, lowercase=False)):
            return True, f"{field_path} matches /{pattern}/"
        return False, f"{field_path} no match for /{pattern}/"

    if "not_empty" in clause:
        is_nonempty = bool(haystack.strip())
        target = bool(clause["not_empty"])
        if is_nonempty == target:
            return True, f"{field_path} not_empty={target}"
        return False, f"{field_path} not_empty={is_nonempty} (want {target})"

    return False, f"unknown operator in clause: {list(clause.keys())}"


def _resolve_field(path: str, context: dict[str, Any]) -> Any:
    """Resolve dotted path against context. e.g. 'host.primary_color' or 'derived.first_symbol'."""

    node: Any = context
    for part in path.split("."):
        if isinstance(node, dict):
            node = node.get(part)
        else:
            node = getattr(node, part, None)
        if node is None:
            return None
    return node


def _to_text(value: Any, lowercase: bool = True) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        text = " ".join(str(item) for item in value)
    elif isinstance(value, dict):
        text = " ".join(f"{k} {v}" for k, v in value.items())
    else:
        text = str(value)
    return text.lower() if lowercase else text


def _short(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


# ---------------------------------------------------------------------------
# Helper for routers
# ---------------------------------------------------------------------------


def first_match(
    rules: Iterable[dict[str, Any]],
    context: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[RouteTraceEntry]]:
    """Walk rules in order, return first match + trace of all attempted rules."""

    trace: list[RouteTraceEntry] = []
    matched: dict[str, Any] | None = None
    for rule in rules:
        if matched is not None:
            trace.append(
                RouteTraceEntry(
                    rule_id=rule.get("id", "<unnamed>"),
                    matched=False,
                    skipped_because="earlier rule already matched",
                )
            )
            continue
        ok, reason = evaluate_conditions(rule.get("when"), context)
        trace.append(
            RouteTraceEntry(
                rule_id=rule.get("id", "<unnamed>"),
                matched=ok,
                reason=reason if ok else "",
                skipped_because="" if ok else reason,
            )
        )
        if ok:
            matched = rule
    return matched, trace
