"""Shape (形) dimension router.

Reads references/shape/rules.yaml, returns ShapeDecision filled with the
silhouette + theme strings consumed by community_gift/template_first.py.

Template strings may reference {primary_symbol} and {secondary_symbol};
they are formatted lazily so context-specific values are baked in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import (
    RouteDecision,
    RouteTraceEntry,
    first_match,
    load_rules,
)


SHAPE_RULES_PATH = Path(__file__).resolve().parent.parent.parent / "references" / "shape" / "rules.yaml"


SLOT_KEYS = (
    "silhouette",
    "theme_title",
    "mood",
    "symbol_translation",
    "supporting_translation",
    "text_style",
    "bottom_node",
    "silhouette_language",
)


@dataclass
class ShapeDecision:
    silhouette: str
    theme_title: str
    mood: str
    symbol_translation: str
    supporting_translation: str
    text_style: str
    bottom_node: str
    silhouette_language: str
    matched_rule_id: str = "default"
    matched_rule_reason: str = ""
    trace: list[RouteTraceEntry] = field(default_factory=list)


class ShapeRouter:
    dimension = "shape"

    def __init__(self, rules_path: Path = SHAPE_RULES_PATH) -> None:
        self.rules = load_rules(rules_path)

    def route(self, context: dict[str, Any]) -> RouteDecision:
        rules = self.rules.get("rules") or []
        defaults = self.rules.get("defaults") or {}
        matched, trace = first_match(rules, context)

        if matched:
            applied = matched["apply"]
            rule_id = matched["id"]
            reason = matched.get("reason", "")
        else:
            applied = {}
            rule_id = "default"
            reason = "no shape rule matched; using defaults"

        primary_symbol = (context.get("derived", {}) or {}).get("primary_symbol", "") or ""
        secondary_symbol = (context.get("derived", {}) or {}).get("secondary_symbol", "") or ""

        slots: dict[str, str] = {}
        for key in SLOT_KEYS:
            raw = applied.get(key) or defaults.get(key) or ""
            slots[key] = _safe_format(
                raw,
                primary_symbol=primary_symbol,
                secondary_symbol=secondary_symbol,
            )

        return RouteDecision(
            dimension="shape",
            matched_rule_id=rule_id,
            fields={**slots, "reason": reason},
            trace=trace,
        )


def _safe_format(template: str, **values: str) -> str:
    if not template:
        return ""
    try:
        return template.format(**values)
    except (KeyError, IndexError):
        return template
