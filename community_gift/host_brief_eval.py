"""HostBrief eval + repair — placeholder container.

Pipeline position:

    HostBrief
       │
       ▼
    evaluate_brief(brief) → BriefEvalResult{issues, passed, repaired_brief}
       │
       ▼
    repair_brief(brief, result) → HostBrief'   (default: no-op pass-through)
       │
       ▼
    routers see the repaired brief

Current state
-------------
This module is intentionally an empty container. The pipeline calls
``evaluate_brief`` and ``repair_brief`` but no rules are registered yet,
so every brief passes through unchanged. The intent is to land the
infrastructure first (call sites, persistence, types) and add lint rules
incrementally without further plumbing churn.

Adding a rule later
-------------------
1. Write a function ``def rule_<name>(brief: HostBrief) -> list[BriefIssue]``
   that returns 0..N issues.
2. Append it to ``RULES`` at the bottom.
3. Optionally extend ``repair_brief`` with a fix for a specific issue
   ``rule_id`` — the result already carries ``applied_fixes`` for logging.

The container intentionally avoids any concrete rule so the surface is
stable while we iterate downstream.
"""

from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, Field

from .host_brief import HostBrief


class BriefIssue(BaseModel):
    """One finding from a single rule."""

    rule_id: str
    severity: str = "warn"           # info / warn / error
    field: str = ""                  # which brief field is at fault, "" if global
    detail: str = ""                 # human-readable explanation
    suggested_fix: str = ""          # rule's hint for how to repair (may be empty)


class BriefEvalResult(BaseModel):
    """Output of evaluate_brief().

    The repaired_brief is what downstream routers consume. When no rule
    fires (current default), ``repaired_brief == input brief`` and
    ``applied_fixes`` is empty.
    """

    row_id: int
    host_name: str
    passed: bool = True
    issues: list[BriefIssue] = Field(default_factory=list)
    applied_fixes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Rule registry (empty for now — placeholder container).
# Each rule is a pure function: HostBrief → list[BriefIssue].
# ---------------------------------------------------------------------------

Rule = Callable[[HostBrief], list[BriefIssue]]

RULES: list[Rule] = []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_brief(brief: HostBrief) -> BriefEvalResult:
    """Run all registered rules against the brief. Empty registry → pass."""

    issues: list[BriefIssue] = []
    for rule in RULES:
        issues.extend(rule(brief))

    has_error = any(issue.severity == "error" for issue in issues)
    return BriefEvalResult(
        row_id=brief.row_id,
        host_name=brief.host_name,
        passed=not has_error,
        issues=issues,
        applied_fixes=[],
    )


def repair_brief(brief: HostBrief, result: BriefEvalResult) -> HostBrief:
    """Apply automated fixes for known issues. Default: no-op.

    Future implementation:
      • Group issues by rule_id.
      • Look up a fixer function in a FIXERS dict keyed by rule_id.
      • Apply each fixer in order, append the rule_id to result.applied_fixes.
      • Return the mutated copy (use brief.model_copy(update=...)).

    Right now the registry is empty so this just returns the input.
    """

    return brief
