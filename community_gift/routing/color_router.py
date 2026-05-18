"""Color dimension router.

Reads references/color/rules.yaml + references/color_palettes.json,
returns ColorDecision(palette_id, main_color, palette[], materials[],
negative_add[], matched_rule_id, trace).

Identity anchor handling: if host input contains "黑/black", the router
still selects the graphite palette and rewrites the main color slot away
from pure black.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import (
    RouteDecision,
    RouteTraceEntry,
    first_match,
    load_rules,
)


COLOR_RULES_PATH = Path(__file__).resolve().parent.parent.parent / "references" / "color" / "rules.yaml"
COLOR_PALETTES_PATH = Path(__file__).resolve().parent.parent.parent / "references" / "color_palettes.json"


@dataclass
class ColorDecision:
    palette_id: str
    palette_name: str
    main_color: str
    palette: list[str]
    materials: list[str]
    avoid: list[str] = field(default_factory=list)
    negative_add: list[str] = field(default_factory=list)
    matched_rule_id: str = "default"
    matched_rule_reason: str = ""
    trace: list[RouteTraceEntry] = field(default_factory=list)


class ColorRouter:
    dimension = "color"

    def __init__(
        self,
        rules_path: Path = COLOR_RULES_PATH,
        palettes_path: Path = COLOR_PALETTES_PATH,
    ) -> None:
        self.rules = load_rules(rules_path)
        self.palettes = _load_palettes(palettes_path)

    def route(self, context: dict[str, Any]) -> RouteDecision:
        rules = self.rules.get("rules") or []
        defaults = self.rules.get("defaults") or {}
        matched, trace = first_match(rules, context)

        if matched:
            palette_id = matched["apply"].get("palette_id") or defaults.get("palette_id", "fallback_safe")
            negative_add = list(matched["apply"].get("negative_add") or [])
            reason = matched.get("reason", "")
            rule_id = matched["id"]
        else:
            palette_id = defaults.get("palette_id", "fallback_safe")
            negative_add = []
            reason = "no rule matched; using defaults"
            rule_id = "default"

        palette_record = self.palettes.get(palette_id) or _fallback_palette_record()

        # Honor CSV-input primary color when it's a normal color (not pure black).
        host_primary = (context.get("host", {}) or {}).get("primary_color", "") or ""
        safe_primary = _safe_main_color(host_primary, palette_record["main_color"])

        decision = ColorDecision(
            palette_id=palette_record["id"],
            palette_name=palette_record["name"],
            main_color=safe_primary,
            palette=palette_record["palette"][:5],
            materials=palette_record["materials"][:4],
            avoid=palette_record.get("avoid", []),
            negative_add=negative_add,
            matched_rule_id=rule_id,
            matched_rule_reason=reason,
            trace=trace,
        )
        return RouteDecision(
            dimension="color",
            matched_rule_id=rule_id,
            fields={
                "palette_id": decision.palette_id,
                "palette_name": decision.palette_name,
                "main_color": decision.main_color,
                "palette": decision.palette,
                "materials": decision.materials,
                "avoid": decision.avoid,
                "negative_add": decision.negative_add,
                "reason": reason,
            },
            trace=trace,
        )


def _load_palettes(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["id"]: item for item in data.get("palettes", [])}


def _fallback_palette_record() -> dict[str, Any]:
    return {
        "id": "fallback_safe",
        "name": "Fallback Safe Palette",
        "main_color": "珠光灰",
        "palette": ["珠光灰", "透明晶体", "冷白", "少量主题色高光"],
        "materials": ["圆润高光树脂", "抛光珐琅", "半透明果冻晶体", "克制金属包边"],
        "avoid": ["纯黑大面积棒身", "白色产品卡"],
    }


def _safe_main_color(host_primary: str, palette_default: str) -> str:
    clean = (host_primary or "").strip()
    if not clean:
        return palette_default
    lowered = clean.lower()
    if "黑" in clean or "black" in lowered or "pure black" in lowered:
        return "烟灰"
    # When CSV gives multi-color like "霓虹绿、深紫", take the first token.
    for sep in ("、", ",", "，", "/", ";", "；"):
        if sep in clean:
            return clean.split(sep, 1)[0].strip() or palette_default
    return clean
