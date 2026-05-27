"""Deterministic style controls for prompt/retrieval aggressiveness.

This layer deliberately does not call an LLM. It translates already-extracted
signals into two inspectable knobs:

- wildness_score: whether the streamer evidence supports wilder, guardian,
  animal/emblem, battle-oriented form language.
- creativity_score / effective_creativity: how far the product silhouette may
  depart from the default rounded lightstick body.

Set STYLE_AGGRESSION=-1/0/1/2 to globally make a batch safer or bolder.
"""

from __future__ import annotations

import os
import re
from typing import Any

from pydantic import BaseModel, Field


class StyleControls(BaseModel):
    """Small, persisted style-control result used by routers and prompts."""

    wildness_score: int = Field(default=0, ge=0, le=3)
    creativity_score: int = Field(default=0, ge=0, le=3)
    aggression_delta: int = 0
    effective_creativity: int = Field(default=0, ge=0, le=3)
    confidence: str = "low"
    shape_boosts: list[str] = Field(default_factory=list)
    vibe_boosts: list[str] = Field(default_factory=list)
    material_boosts: list[str] = Field(default_factory=list)
    prompt_cues: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def derive_style_controls(
    host: Any,
    *,
    primary_symbol: str = "",
    secondary_symbol: str = "",
    shape_tags: list[str] | None = None,
    vibe_tags: list[str] | None = None,
    material_tags: list[str] | None = None,
    color_tags: list[str] | None = None,
) -> StyleControls:
    """Derive no-LLM style controls from host fields, tags, and raw evidence."""

    raw = getattr(host, "raw", {}) if host is not None else {}
    raw = raw if isinstance(raw, dict) else {}

    evidence = _as_list(raw.get("evidence_signals") or raw.get("primary_signals"))
    missing = _as_list(raw.get("missing_evidence") or raw.get("missing_signals"))
    context_parts = [
        getattr(host, "host_name", ""),
        getattr(host, "community_name", ""),
        getattr(host, "content_type", ""),
        getattr(host, "live_vibe", ""),
        getattr(host, "personality", ""),
        getattr(host, "body_form", ""),
        getattr(host, "mapping_reason", ""),
        getattr(host, "notes", ""),
        primary_symbol,
        secondary_symbol,
        " ".join(getattr(host, "symbols", []) or []),
        " ".join(_as_list(raw.get("host_symbols"))),
        " ".join(_as_list(raw.get("comm_symbols"))),
        " ".join(evidence),
        " ".join(_as_list(raw.get("palette_direction"))),
        " ".join(_as_list(raw.get("material_direction"))),
        " ".join(_as_list(raw.get("mood_coverage"))),
        " ".join(_as_list(raw.get("form_exploration"))),
        str(raw.get("characterization") or ""),
        " ".join(shape_tags or []),
        " ".join(vibe_tags or []),
        " ".join(material_tags or []),
        " ".join(color_tags or []),
    ]
    context = " ".join(str(part) for part in context_parts if part).lower()

    wild_points = 0
    creative_points = 0
    evidence_hits = 0
    shape_boosts: list[str] = []
    vibe_boosts: list[str] = []
    material_boosts: list[str] = []
    prompt_cues: list[str] = []
    reasons: list[str] = []

    for rule in _WILD_RULES:
        if _contains_any(context, rule["terms"]):
            points = int(rule["points"])
            wild_points += points
            creative_points += int(rule.get("creative", 0))
            evidence_hits += 1
            shape_boosts.extend(rule.get("shape", []))
            vibe_boosts.extend(rule.get("vibe", []))
            prompt_cues.extend(rule.get("cues", []))
            reasons.append(f"wild +{points}: {rule['label']}")

    for rule in _CREATIVE_RULES:
        if _contains_any(context, rule["terms"]):
            points = int(rule["points"])
            creative_points += points
            evidence_hits += 1
            shape_boosts.extend(rule.get("shape", []))
            vibe_boosts.extend(rule.get("vibe", []))
            material_boosts.extend(rule.get("material", []))
            prompt_cues.extend(rule.get("cues", []))
            reasons.append(f"creative +{points}: {rule['label']}")

    for signal in evidence:
        lowered = str(signal).lower()
        if lowered in _EVIDENCE_CREATIVE_SIGNALS:
            creative_points += 1
            evidence_hits += 1
            reasons.append(f"creative +1: signal={lowered}")

    soft_hits = [term for term in _SOFT_SAFETY_TERMS if term in context]
    if soft_hits and wild_points:
        wild_points -= 1
        reasons.append("wild -1: soft/cute context present")

    conservative_hits = [term for term in missing if str(term).lower() in _CONSERVATIVE_MISSING_SIGNALS]
    if conservative_hits:
        creative_points -= min(2, len(conservative_hits))
        reasons.append(
            "creative -%d: missing evidence=%s"
            % (min(2, len(conservative_hits)), ",".join(str(v) for v in conservative_hits))
        )

    wildness_score = _clamp(wild_points, 0, 3)
    creativity_score = _clamp(creative_points, 0, 3)
    aggression_delta = _env_int("STYLE_AGGRESSION", 0)
    effective_creativity = _clamp(creativity_score + aggression_delta, 0, 3)

    if wildness_score >= 2:
        shape_boosts.extend(["non_round", "soft_body"])
        vibe_boosts.extend(["protective", "bold"])
        prompt_cues.append("wild_guardian")
    if effective_creativity >= 2:
        shape_boosts.append("non_round")
        vibe_boosts.append("bold")
        prompt_cues.append("bolder_silhouette")
    if effective_creativity <= 1:
        prompt_cues.append("controlled_variation")

    confidence = "high" if evidence_hits >= 3 else "medium" if evidence_hits >= 1 else "low"
    return StyleControls(
        wildness_score=wildness_score,
        creativity_score=creativity_score,
        aggression_delta=aggression_delta,
        effective_creativity=effective_creativity,
        confidence=confidence,
        shape_boosts=_dedupe(shape_boosts),
        vibe_boosts=_dedupe(vibe_boosts),
        material_boosts=_dedupe(material_boosts),
        prompt_cues=_dedupe(prompt_cues),
        reasons=reasons or ["no strong style-control evidence"],
    )


_WILD_RULES: list[dict[str, Any]] = [
    {
        "label": "eagle/falcon emblem",
        "terms": ["🦅", "eagle", "falcon", "hawk", "猎鹰", "鹰"],
        "points": 3,
        "creative": 1,
        "shape": ["eagle", "bird", "wing", "animal"],
        "vibe": ["protective", "battle", "bold"],
        "cues": ["raised_wings", "feather_relief"],
    },
    {
        "label": "raven/crow emblem",
        "terms": ["raven", "crow", "乌鸦", "黑鸟"],
        "points": 2,
        "creative": 1,
        "shape": ["bird", "wing", "animal"],
        "vibe": ["mysterious", "protective", "dramatic"],
        "cues": ["layered_feathers"],
    },
    {
        "label": "wild feline",
        "terms": ["panther", "black panther", "pantera", "leopard", "jaguar", "黑豹", "豹"],
        "points": 2,
        "creative": 1,
        "shape": ["panther", "animal", "non_round"],
        "vibe": ["protective", "powerful", "bold"],
        "cues": ["rounded_claw_relief"],
    },
    {
        "label": "dragon/snake fantasy creature",
        "terms": ["dragon", "drake", "snake", "serpent", "龙", "蛇"],
        "points": 2,
        "creative": 1,
        "shape": ["dragon", "animal", "non_round"],
        "vibe": ["fantasy", "powerful", "battle"],
        "cues": ["scale_relief"],
    },
    {
        "label": "battle/protective energy",
        "terms": ["battle", "pk", "competitive", "competition", "boss", "protective", "guardian", "fierce", "intense", "高能", "竞技", "守护"],
        "points": 1,
        "creative": 1,
        "shape": ["non_round"],
        "vibe": ["battle", "protective", "energetic"],
        "cues": ["shielding_arc"],
    },
    {
        "label": "pirate/enigma edge",
        "terms": ["🏴‍☠️", "pirate", "enigma", "skull", "mystery"],
        "points": 1,
        "creative": 1,
        "shape": ["flag", "non_round"],
        "vibe": ["mysterious", "dramatic", "bold"],
        "cues": ["crest_badge"],
    },
]

_CREATIVE_RULES: list[dict[str, Any]] = [
    {
        "label": "recurring object/prop",
        "terms": ["recurring_object_or_prop", "prop", "object", "perfume", "parfum", "fragrance", "香水"],
        "points": 2,
        "shape": ["perfume_bottle", "object_body"],
        "vibe": ["elegant", "designer_toy"],
        "material": ["silicone", "matte_enamel"],
        "cues": ["object_body"],
    },
    {
        "label": "logo/sticker visual system",
        "terms": ["logo_style_community_stickers", "sticker", "logo", "emblem", "badge", "crest"],
        "points": 1,
        "shape": ["badge"],
        "vibe": ["idol_support", "bold"],
        "cues": ["emblem_badge"],
    },
    {
        "label": "distinct form exploration",
        "terms": ["form_exploration", "shape exploration", "形态探索", "silhouette", "wing", "crest", "hat", "crown", "chain", "cap", "帽", "皇冠", "金链"],
        "points": 1,
        "shape": ["non_round"],
        "vibe": ["designer_toy"],
        "cues": ["theme_silhouette"],
    },
]

_EVIDENCE_CREATIVE_SIGNALS = {
    "recurring_mascot_or_pet",
    "recurring_object_or_prop",
    "logo_style_community_stickers",
}

_CONSERVATIVE_MISSING_SIGNALS = {
    "no_recurring_mascot_or_object",
    "fan_club_name_textual_only_no_visuals",
    "no_distinct_color_system",
    "no_branded_environment",
}

_SOFT_SAFETY_TERMS = {
    "cute",
    "kawaii",
    "soft",
    "gentle",
    "healing",
    "cozy",
    "rabbit",
    "bunny",
    "panda",
    "elephant",
    "penguin",
    "frog",
    "可爱",
    "软萌",
    "治愈",
    "温柔",
}


def _contains_any(context: str, terms: list[str]) -> bool:
    for term in terms:
        clean = str(term).lower().strip()
        if not clean:
            continue
        if re.fullmatch(r"[a-z0-9_ ]+", clean):
            pattern = r"(?<![a-z0-9_])" + re.escape(clean) + r"(?![a-z0-9_])"
            if re.search(pattern, context):
                return True
        elif clean in context:
            return True
    return False


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, set):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        out.append(clean)
        seen.add(key)
    return out


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except ValueError:
        return default
