"""HostBrief eval + repair.

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
This layer catches the cheap, deterministic issues before routers run:
missing normalized tags, risky text scripts, pure-black product colour, and
sparse vision briefs. It also applies small safe repairs so downstream router
selection is less dependent on a single exact token.

Adding a rule later
-------------------
1. Write a function ``def rule_<name>(brief: HostBrief) -> list[BriefIssue]``
   that returns 0..N issues.
2. Append it to ``RULES`` at the bottom.
3. Optionally extend ``repair_brief`` with a fix for a specific issue
   ``rule_id`` — the result already carries ``applied_fixes`` for logging.

Keep rules conservative: this layer should enrich intent and debugability, not
rewrite the design concept.
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

_SYMBOL_TAG_ONTOLOGY: dict[str, dict[str, list[str]]] = {
    "bird": {
        "hooks": ["鸟", "乌鸦", "黑鸟", "crow", "raven", "bird", "feather"],
        "shape": ["bird", "wing"],
        "vibe": ["sleek", "mysterious"],
    },
    "electric": {
        "hooks": ["闪电", "电光", "electric", "lightning", "thunderbolt"],
        "shape": ["electric"],
        "color": ["neon_blue"],
        "vibe": ["battle"],
    },
    "butterfly": {
        "hooks": ["蝴蝶", "butterfly", "나비"],
        "shape": ["butterfly", "wing"],
        "vibe": ["dreamy", "soft"],
    },
    "potato": {
        "hooks": ["土豆", "potato", "spud"],
        "shape": ["mascot"],
        "color": ["gold"],
        "vibe": ["playful", "designer_toy"],
    },
    "crown": {
        "hooks": ["皇冠", "王冠", "crown", "queen", "king", "rey"],
        "shape": ["crown"],
        "color": ["gold"],
        "vibe": ["battle"],
    },
    "hat": {
        "hooks": ["帽", "hat", "sombrero", "fedora"],
        "shape": ["hat"],
        "vibe": ["elegant"],
    },
    "shell": {
        "hooks": ["贝壳", "龟壳", "shell", "turtle"],
        "shape": ["shell"],
        "color": ["mint_green", "blue"],
        "vibe": ["soft"],
    },
    "fruit": {
        "hooks": ["樱桃", "水果", "cherry", "melon", "🍈", "果"],
        "shape": ["fruit_cluster"],
        "color": ["cherry_red", "green"],
        "vibe": ["sweet", "playful"],
    },
}


def rule_missing_symbol_tags(brief: HostBrief) -> list[BriefIssue]:
    """Warn when a concrete symbol lacks the normalized tags routers expect."""

    expected = _expected_tags(brief)
    issues: list[BriefIssue] = []
    missing_shape = [tag for tag in expected["shape"] if tag not in brief.shape_tags]
    if missing_shape:
        issues.append(
            BriefIssue(
                rule_id="missing_symbol_shape_tags",
                severity="warn",
                field="shape_tags",
                detail=(
                    f"symbol '{brief.primary_symbol}' implies shape tags "
                    f"{missing_shape}, but brief lacks them"
                ),
                suggested_fix="append inferred shape tags before routing",
            )
        )
    return issues


def rule_sparse_vision_brief(brief: HostBrief) -> list[BriefIssue]:
    if brief.vision is None:
        return [
            BriefIssue(
                rule_id="missing_vision_brief",
                severity="info",
                field="vision",
                detail="no vision brief was available; routers will rely on text heuristics",
                suggested_fix="provide vision cache or vision_override.json for stronger personalization",
            )
        ]

    issues: list[BriefIssue] = []
    if not brief.vision.lamp_head_silhouette:
        issues.append(
            BriefIssue(
                rule_id="sparse_vision_silhouette",
                severity="warn",
                field="vision.lamp_head_silhouette",
                detail="vision brief did not provide a concrete lamp-head silhouette",
                suggested_fix="edit vision_override.json or rerun vision analysis",
            )
        )
    if not brief.vision.handle.main_material or not brief.vision.handle.bottom_cap:
        issues.append(
            BriefIssue(
                rule_id="sparse_vision_handle",
                severity="warn",
                field="vision.handle",
                detail="vision brief did not fully specify handle material and bottom cap",
                suggested_fix="fill handle fields so the handle does not collapse to a generic tube",
            )
        )
    return issues


def rule_text_render_risk(brief: HostBrief) -> list[BriefIssue]:
    if brief.char_count <= 20 and brief.script_kind not in {"mixed", "empty"}:
        return []
    return [
        BriefIssue(
            rule_id="text_render_risk",
            severity="warn",
            field="text_tags",
            detail=(
                f"text script={brief.script_kind!r}, char_count={brief.char_count}; "
                "one-shot text may be fragile"
            ),
            suggested_fix="prefer shorter exact_text or post-overlay in a future text pipeline",
        )
    ]


def rule_black_product_color(brief: HostBrief) -> list[BriefIssue]:
    color_text = " ".join([brief.primary_color, brief.secondary_color, brief.all_colors]).lower()
    if "黑" not in color_text and "black" not in color_text:
        return []
    return [
        BriefIssue(
            rule_id="black_product_color",
            severity="info",
            field="primary_color",
            detail="black-themed input should route to graphite/silver-safe product colours",
            suggested_fix="keep semantic black, but avoid pure black body/handle on black background",
        )
    ]


RULES: list[Rule] = [
    rule_missing_symbol_tags,
    rule_sparse_vision_brief,
    rule_text_render_risk,
    rule_black_product_color,
]


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
    """Apply deterministic, low-risk fixes for known issues."""

    expected = _expected_tags(brief)
    updates = {}

    shape_tags = _dedupe([*brief.shape_tags, *expected["shape"]])
    color_tags = _dedupe([*brief.color_tags, *expected["color"]])
    vibe_tags = _dedupe([*brief.vibe_tags, *expected["vibe"]])

    if shape_tags != brief.shape_tags:
        updates["shape_tags"] = shape_tags
        result.applied_fixes.append("append_symbol_shape_tags")
    if color_tags != brief.color_tags:
        updates["color_tags"] = color_tags
        result.applied_fixes.append("append_symbol_color_tags")
    if vibe_tags != brief.vibe_tags:
        updates["vibe_tags"] = vibe_tags
        result.applied_fixes.append("append_symbol_vibe_tags")

    if not updates:
        return brief
    return brief.model_copy(update=updates)


def _expected_tags(brief: HostBrief) -> dict[str, list[str]]:
    text = " ".join(
        [
            brief.primary_symbol,
            brief.secondary_symbol,
            " ".join(brief.symbols_raw),
            brief.notes,
        ]
    ).lower()
    out = {"shape": [], "color": [], "vibe": []}
    for entry in _SYMBOL_TAG_ONTOLOGY.values():
        hooks = [hook.lower() for hook in entry["hooks"]]
        if not any(hook and hook in text for hook in hooks):
            continue
        for dim in out:
            out[dim].extend(entry.get(dim, []))
    return {dim: _dedupe(tags) for dim, tags in out.items()}


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        key = clean.lower()
        if clean and key not in seen:
            out.append(clean)
            seen.add(key)
    return out
