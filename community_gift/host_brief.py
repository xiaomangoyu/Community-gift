"""HostBrief — the canonical normalized intermediate between CSV and routers.

Pipeline position:

    CSV → HostInput (21 raw fields, lossless)
        → HostBrief  (~17 normalized fields, this module)
        → routers (color / shape / reference) read this
        → eval / repair (future)
        → GiftDesign → Seedream

Why this layer exists
---------------------
- Routers used to receive an ad-hoc ``{"host": ..., "derived": ...}`` dict
  built inside ``template_first._build_routing_context``. The dict was a
  throwaway, never persisted, so it couldn't be inspected, edited, or
  eval'd. HostBrief is the persistent, schema-checked replacement.
- Tag-inference logic (script kind, vibe tags, color tags …) used to live
  inside ``ReferenceRouter._extract_host_signals``. It's now centralized
  here so every router downstream sees the same signals.
- ``HostBrief.to_routing_context()`` keeps the old dict-shaped contract so
  existing routers don't have to change in this step.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from .host_vision import HostVisionBrief
from .models import HostInput


# ---------------------------------------------------------------------------
# RetrievalIntent — step 5 of the pipeline.
# ---------------------------------------------------------------------------


class RetrievalIntent(BaseModel):
    """What to search the reference library for, derived from a HostBrief.

    Today this is a straight mirror of brief.{shape,color,vibe,text}_tags.
    The point of having it as its own object is that eval/repair (step 3) can
    rewrite it without touching the brief — e.g. "host name is latin, so
    exclude Korean/Arabic references" sets ``avoid_text_scripts=['korean',
    'arabic']`` without changing brief.text_tags.

    Persisted next to the brief so it's inspectable.
    """

    row_id: int
    shape_anchors: list[str] = Field(default_factory=list)
    color_anchors: list[str] = Field(default_factory=list)
    material_anchors: list[str] = Field(default_factory=list)
    vibe_anchors: list[str] = Field(default_factory=list)
    text_anchors: list[str] = Field(default_factory=list)
    avoid_text_scripts: list[str] = Field(default_factory=list)  # filled by eval
    notes: str = ""


def derive_retrieval_intent(brief: "HostBrief") -> RetrievalIntent:
    """Default intent: mirror brief tags. Eval/repair may rewrite this."""

    avoid_scripts = _avoid_scripts_for(brief.script_kind)
    return RetrievalIntent(
        row_id=brief.row_id,
        shape_anchors=list(brief.shape_tags),
        color_anchors=list(brief.color_tags),
        material_anchors=list(brief.material_tags),
        vibe_anchors=list(brief.vibe_tags),
        text_anchors=list(brief.text_tags),
        avoid_text_scripts=avoid_scripts,
        notes=(
            f"avoid non-target scripts for {brief.script_kind} text"
            if avoid_scripts
            else ""
        ),
    )


# ---------------------------------------------------------------------------
# CreativeProfile — optional controlled divergence layer.
# ---------------------------------------------------------------------------


class CreativeProfile(BaseModel):
    """How far the final prompt may diverge from the stable baseline.

    The baseline prompt remains the default. ``expressive`` / ``wild`` only
    unlock stronger contour, tactile, and edge details when upstream data or
    deterministic inference says the streamer can carry that treatment.
    """

    mode: str = "baseline"  # baseline | expressive | wild
    intensity: int = 0      # 0-3, where 0 means no extra creative push
    axes: list[str] = Field(default_factory=list)
    source: str = "baseline"  # explicit | derived | baseline
    notes: str = ""


# ---------------------------------------------------------------------------
# Inference dictionaries — Chinese / mixed-text keywords → English tags.
# Centralised here (used to be inside reference_router.py).
# ---------------------------------------------------------------------------

_SHAPE_INFERENCE: dict[str, list[str]] = {
    "butterfly": ["蝴蝶", "butterfly", "나비"],
    "wing": ["翅膀", "wing", "羽翼", "feather"],
    "heart": ["爱心", "心形", "heart", "💕", "💜"],
    "star": ["星", "星形", "星星", "star"],
    "crown": ["皇冠", "王冠", "crown", "queen", "king", "rey"],
    "potato": ["土豆", "马铃薯", "potato", "spud"],
    "melon": ["蜜瓜", "哈密瓜", "melon", "🍈"],
    "baseball_cap": ["棒球帽", "baseball cap"],
    "boxing_glove": ["拳击手套", "拳套", "boxing glove"],
    "dragon": ["龙", "dragon"],
    "lightning": ["闪电", "电光", "lightning", "thunderbolt"],
    "horn": ["牛角", "兽角", "弯角", "角弧", "horn"],
    "cow_horn": ["牛角", "公牛", "bull", "cow_horn"],
    "fur": ["长毛", "毛发", "毛绒", "皮草", "鬃毛", "fur"],
    "hair": ["长发", "头发", "发束", "毛流", "hair"],
    "claw": ["爪片", "利爪", "豹爪", "claw"],
    "fang": ["獠牙", "尖牙", "牙", "fang"],
    "spike": ["尖刺", "角刺", "星刺", "尖晶", "spike", "stud"],
    "scale": ["鳞", "鳞片", "scale"],
    "crest": ["冠羽", "脊冠", "crest"],
    "hat": ["帽", "hat", "sombrero"],
    "mascot": ["土豆", "potato", "mascot", "圆润", "spud"],
    "shell": ["龟壳", "shell", "turtle"],
    "fruit_cluster": ["樱桃", "cherry", "果"],
    "bird": ["鸟", "bird", "feather", "乌鸦", "黑鸟", "crow", "raven"],
    "electric": ["闪电", "电光", "electric", "lightning", "thunderbolt"],
}

_COLOR_INFERENCE: dict[str, list[str]] = {
    "purple": ["紫", "purple", "葡萄", "薰衣草", "lavender"],
    "pink": ["粉", "pink", "rose", "magenta", "玫瑰"],
    "hot_pink": ["亮粉", "热粉", "荧光粉", "hot pink"],
    "candy_pink": ["糖果粉", "candy pink", "candy_pink"],
    "electric_pink": ["电光粉", "霓虹粉", "electric pink", "electric_pink"],
    "red": ["红", "red", "珊瑚", "coral", "cherry"],
    "blue": ["蓝", "blue", "霓虹蓝", "neon_blue"],
    "green": ["绿", "green", "mint", "pistachio", "薄荷"],
    "gold": ["金", "gold", "champagne", "香槟"],
    "white": ["白", "white", "pearl", "珠光", "cream"],
    "silver": ["银", "silver"],
    "silver_white": ["银白", "冷银", "silver white", "silver_white"],
    "pearl_white": ["珠光白", "珍珠白", "白光", "pearl white", "pearl_white"],
    "smoke_pink": ["烟粉", "smoke pink"],
    "pearl": ["珠光", "pearl"],
    "graphite": ["烟灰", "graphite", "枪灰"],
    "cherry_red": ["樱桃", "cherry"],
    "mint_green": ["薄荷", "mint"],
}

_VIBE_INFERENCE: dict[str, list[str]] = {
    "dreamy": ["梦幻", "dreamy"],
    "soft": ["温柔", "soft", "gentle"],
    "sweet": ["甜", "sweet", "甜美", "candy"],
    "playful": ["俏皮", "playful", "综艺", "game"],
    "elegant": ["优雅", "elegant", "复古"],
    "romantic": ["浪漫", "romantic", "陪伴"],
    "battle": ["竞技", "battle", "高能", "胜利", "pk"],
    "exotic": ["异域", "exotic"],
    "designer_toy": ["潮玩", "designer toy", "玩具"],
    "idol_support": ["偶像", "应援", "idol"],
    "sweet_cool": ["甜酷", "sweet cool"],
    "glamorous": ["华丽", "妖冶", "glamorous", "glam"],
    "wild": ["野性", "野感", "兽感", "wild", "feral"],
    "edgy": ["锋利", "尖锐", "叛逆", "edgy"],
    "bold": ["张扬", "大胆", "bold"],
    "luxury_collectible": ["奢闪", "轻奢", "收藏级", "luxury"],
}

_MATERIAL_INFERENCE: dict[str, list[str]] = {
    "fiber_hair": ["长毛", "毛发", "发束", "毛流", "鬃毛", "真实毛发", "fiber_hair"],
    "fur": ["长毛", "毛绒", "皮草", "fur"],
    "hair": ["头发", "长发", "hair"],
    "feather": ["羽毛", "羽片", "feather"],
    "scale_texture": ["鳞", "鳞片", "scale"],
    "leather_wrap": ["皮革", "软皮", "leather"],
    "mirror_metal": ["镜面", "银白", "冷银", "mirror"],
    "glossy_resin": ["树脂", "糖果", "果冻", "resin"],
    "translucent_jelly": ["半透明", "果冻", "jelly"],
    "pearl_coating": ["珠光", "pearl"],
}

_CREATIVE_AXIS_INFERENCE: dict[str, list[str]] = {
    "feather": ["bird", "wing", "swept_wing", "羽翼", "翅膀", "展翼", "鸟", "乌鸦", "黑鸟", "鹰", "猎鹰", "raven", "crow", "falcon", "eagle"],
    "horn": ["horn", "cow_horn", "牛角", "兽角", "弯角", "角弧", "公牛"],
    "claw": ["claw", "爪片", "利爪", "豹爪", "豹", "黑豹", "猛兽"],
    "fang": ["fang", "獠牙", "尖牙"],
    "spike": ["spike", "尖刺", "角刺", "星刺", "stud"],
    "scale": ["scale", "scale_texture", "鳞", "鳞片", "dragon", "龙"],
    "crest": ["crest", "冠羽", "脊冠"],
    "flame": ["flame", "火焰", "火苗", "火舌"],
    "predator": ["predator", "panther", "black panther", "黑豹", "猛兽", "兽感", "猎豹"],
    "lightning": ["lightning", "electric", "闪电", "电光", "thunderbolt"],
    "rock_glam": ["rock", "glam", "glamorous", "摇滚", "叛逆", "甜辣", "华丽", "edgy"],
    "combat": ["battle", "battles", "free fire", "boxing_glove", "fighter", "竞技", "拳击", "拳套", "战队", "pk"],
    "luxury": ["luxury", "luxury_collectible", "奢闪", "轻奢", "收藏级", "金箔"],
}

_AXIS_SHAPE_TAGS: dict[str, list[str]] = {
    "feather": ["wing", "bird"],
    "horn": ["horn", "cow_horn"],
    "claw": ["claw"],
    "fang": ["fang"],
    "spike": ["spike"],
    "scale": ["scale", "dragon"],
    "crest": ["crest"],
    "flame": ["flame"],
    "predator": ["claw"],
    "lightning": ["electric", "lightning"],
    "combat": ["boxing_glove"],
}

_AXIS_VIBE_TAGS: dict[str, list[str]] = {
    "predator": ["wild", "bold"],
    "rock_glam": ["edgy", "glamorous", "bold"],
    "combat": ["battle", "bold"],
    "luxury": ["luxury_collectible", "glamorous"],
}

_STRUCTURAL_CREATIVE_AXES = {
    "horn",
    "claw",
    "fang",
    "feather",
    "flame",
    "spike",
    "scale",
    "crest",
    "predator",
    "lightning",
}

_NON_MATERIAL_TAGS = {
    "bold",
    "claw",
    "cute",
    "dreamy",
    "dragon",
    "edgy",
    "electric",
    "fang",
    "glam",
    "glamorous",
    "hat",
    "horn",
    "idol_energy",
    "idol_support",
    "lightning",
    "mascot",
    "melon",
    "potato",
    "romantic",
    "scale",
    "spike",
    "star",
    "sweet",
    "sweet_cool",
    "wild",
}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class HostBrief(BaseModel):
    """Canonical normalized brief, one per host. ~17 fields.

    Sections:
      • identity   (row_id, host_name, community_name)
      • symbols    (raw list + primary/secondary extraction)
      • colors     (primary/secondary + combined)
      • vibe       (live_vibe, personality)
      • banned     (carry-over from CSV)
      • notes      (carry-over)
      • tags       (5-dim: shape/color/material/vibe/text — for routers)
      • text_meta  (script_kind / has_emoji / char_count — for eval)
    """

    # Identity
    row_id: int
    host_name: str = ""
    community_name: str = ""

    # Symbols
    symbols_raw: list[str] = Field(default_factory=list)
    primary_symbol: str = ""
    secondary_symbol: str = ""

    # Colors
    primary_color: str = ""
    secondary_color: str = ""
    all_colors: str = ""

    # Vibe / context
    content_type: str = ""
    live_vibe: str = ""
    personality: str = ""
    recommended_output_type: str = ""
    body_form: str = ""
    mapping_reason: str = ""
    banned_elements: list[str] = Field(default_factory=list)
    notes: str = ""

    # Inferred 5-dim tags
    shape_tags: list[str] = Field(default_factory=list)
    color_tags: list[str] = Field(default_factory=list)
    material_tags: list[str] = Field(default_factory=list)
    vibe_tags: list[str] = Field(default_factory=list)
    text_tags: list[str] = Field(default_factory=list)

    # Text-self-check metadata
    script_kind: str = ""        # latin / korean / arabic / chinese / mixed / empty
    has_emoji: bool = False
    char_count: int = 0

    # Vision-derived structured brief (optional — present when the workflow ran
    # ``analyze_host_visual_brief`` upstream). When non-null, template_first
    # uses these values to override router defaults so every slot is concrete.
    vision: HostVisionBrief | None = None

    # Controlled creative divergence. Baseline remains stable; expressive/wild
    # is opt-in via upstream fields or deterministic inference.
    creative_profile: CreativeProfile = Field(default_factory=CreativeProfile)

    def to_routing_context(self, intent: "RetrievalIntent | None" = None) -> dict[str, Any]:
        """Adapt to the legacy {host, derived} dict consumed by current routers.

        Reference router reads tag signals from ``intent`` (preferred) or
        falls back to the brief's raw tags.
        """

        return {
            "host": {
                "row_id": self.row_id,
                "host_name": self.host_name,
                "community_name": self.community_name,
                "primary_color": self.primary_color,
                "secondary_color": self.secondary_color,
                "symbols": list(self.symbols_raw),
                "content_type": self.content_type,
                "live_vibe": self.live_vibe,
                "personality": self.personality,
                "recommended_output_type": self.recommended_output_type,
                "body_form": self.body_form,
                "mapping_reason": self.mapping_reason,
                "banned_elements": list(self.banned_elements),
                "notes": self.notes,
            },
            "derived": {
                "primary_symbol": self.primary_symbol,
                "primary_symbol_text": self.primary_symbol,
                "secondary_symbol": self.secondary_symbol,
                "symbol_text": " ".join(self.symbols_raw),
                "all_colors": self.all_colors,
            },
            "brief": self.model_dump(),
            "intent": intent.model_dump() if intent is not None else {},
        }


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_host_brief(host: HostInput, vision: HostVisionBrief | None = None) -> HostBrief:
    """Normalize a HostInput into a HostBrief. Pure function, no IO.

    When ``vision`` is supplied, its structured signals (palette / materials /
    signature_symbols / mood) become the source of truth for the corresponding
    HostBrief fields, overriding the CSV-style heuristics. This is how we get
    every brief field populated when reading from ``streamers/<id>/signals.md``
    (which lacks color/vibe/material).
    """

    symbols_raw = _unique(host.symbols)
    primary_symbol = _first_symbol(symbols_raw[0] if symbols_raw else "") or "custom emblem"
    secondary_symbol = _first_non_duplicate(primary_symbol, symbols_raw) or "subtle glow accent"

    all_colors = " ".join(part for part in [host.primary_color, host.secondary_color] if part).strip()

    shape_tokens = _split(" ".join(symbols_raw)) + _split(host.body_form) + _split(host.content_type)
    color_tokens = _split(all_colors)
    vibe_tokens = _split(host.live_vibe) + _split(host.personality)
    material_tokens = (
        _split(" ".join(symbols_raw))
        + _split(host.material_language_hint)
        + _split(host.notes)
    )

    shape_tags = _dedupe(shape_tokens + _infer(shape_tokens, _SHAPE_INFERENCE))
    color_tags = _dedupe(color_tokens + _infer(color_tokens, _COLOR_INFERENCE))
    vibe_tags = _dedupe(vibe_tokens + _infer(vibe_tokens, _VIBE_INFERENCE))
    material_tags = _dedupe(_infer(material_tokens, _MATERIAL_INFERENCE))

    primary_color = host.primary_color
    secondary_color = host.secondary_color

    # Vision overrides — these always beat heuristic inference because vision
    # actually looked at the avatar.
    if vision is not None:
        if vision.signature_symbols.primary:
            primary_symbol = vision.signature_symbols.primary
        if vision.signature_symbols.secondary:
            secondary_symbol = vision.signature_symbols.secondary
        if vision.palette.main_color:
            primary_color = vision.palette.main_color
        if vision.palette.secondary_color:
            secondary_color = vision.palette.secondary_color
        if vision.palette.tags:
            color_tags = _dedupe(color_tags + list(vision.palette.tags))
        if vision.materials.tags:
            material_tags = _dedupe(material_tags + _material_only_tags(list(vision.materials.tags)))
        vision_material_tokens = _split(
            " ".join(
                [
                    vision.materials.main,
                    vision.materials.supporting,
                    vision.style_pitch,
                    vision.lamp_head_silhouette,
                    _theme_forms_text(vision),
                ]
            )
        )
        if vision_material_tokens:
            material_tags = _dedupe(material_tags + _infer(vision_material_tokens, _MATERIAL_INFERENCE))
        if vision.mood.tags:
            vibe_tags = _dedupe(vibe_tags + list(vision.mood.tags))
        vision_vibe_tokens = _split(
            " ".join(
                [
                    vision.mood.phrase,
                    vision.style_pitch,
                    vision.silhouette_language,
                ]
            )
        )
        if vision_vibe_tokens:
            vibe_tags = _dedupe(vibe_tags + _infer(vision_vibe_tokens, _VIBE_INFERENCE))
        if vision.signature_symbols.primary or vision.signature_symbols.secondary:
            sym_tokens = _split(
                " ".join(
                    [
                        vision.signature_symbols.primary,
                        vision.signature_symbols.secondary,
                    ]
                )
            )
            shape_tags = _dedupe(shape_tags + sym_tokens + _infer(sym_tokens, _SHAPE_INFERENCE))
        vision_shape_tokens = _split(
            " ".join(
                [
                    vision.lamp_head_silhouette,
                    vision.silhouette_language,
                    _theme_forms_text(vision),
                ]
            )
        )
        if vision_shape_tokens:
            shape_tags = _dedupe(shape_tags + _infer(vision_shape_tokens, _SHAPE_INFERENCE))
        if vision.palette.main_color or vision.palette.secondary_color:
            all_colors = " ".join(
                part
                for part in [
                    vision.palette.main_color,
                    vision.palette.secondary_color,
                    *vision.palette.accent_colors,
                ]
                if part
            ).strip()

    creative_profile = _derive_creative_profile(
        host,
        shape_tags=shape_tags,
        vibe_tags=vibe_tags,
        vision=vision,
    )
    if creative_profile.intensity > 0:
        shape_tags = _dedupe(shape_tags + _shape_tags_from_axes(creative_profile.axes))
        vibe_tags = _dedupe(vibe_tags + _vibe_tags_from_profile(creative_profile))

    script_kind, has_emoji, char_count, text_tags = _analyze_text(host.host_name)
    if vision is not None and vision.text.script:
        script_kind = vision.text.script
        if vision.text.script not in text_tags:
            text_tags = _dedupe([vision.text.script] + text_tags)

    return HostBrief(
        row_id=host.row_id,
        host_name=host.host_name,
        community_name=host.community_name,
        symbols_raw=symbols_raw,
        primary_symbol=primary_symbol,
        secondary_symbol=secondary_symbol,
        primary_color=primary_color,
        secondary_color=secondary_color,
        all_colors=all_colors,
        content_type=host.content_type,
        live_vibe=host.live_vibe,
        personality=host.personality,
        recommended_output_type=host.recommended_output_type,
        body_form=host.body_form,
        mapping_reason=host.mapping_reason,
        banned_elements=list(host.banned_elements),
        notes=host.notes,
        shape_tags=shape_tags,
        color_tags=color_tags,
        material_tags=material_tags,
        vibe_tags=vibe_tags,
        text_tags=text_tags,
        script_kind=script_kind,
        has_emoji=has_emoji,
        char_count=char_count,
        vision=vision,
        creative_profile=creative_profile,
    )


# ---------------------------------------------------------------------------
# Helpers (a few are mirrored from template_first.py — kept local so brief
# building has no upward dependency on the prompt builder).
# ---------------------------------------------------------------------------


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        clean = str(v).strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        out.append(clean)
        seen.add(key)
    return out


def _first_symbol(value: str) -> str:
    if not value:
        return ""

    return re.split(r"\s*/\s*|\s+or\s+|\s+\+\s+|[,，、;；]", value, maxsplit=1, flags=re.I)[0].strip()


def _first_non_duplicate(primary: str, values: list[str]) -> str:
    primary_key = primary.strip().lower()
    for value in values:
        candidate = _secondary_value(primary, value)
        if not candidate:
            continue
        if candidate.strip().lower() == primary_key:
            continue
        if _duplicates(primary, candidate):
            continue
        return candidate
    return ""


def _secondary_value(primary: str, value: str) -> str:
    parts = [
        part.strip()
        for part in re.split(r"\s+or\s+|\s*/\s*|\s+\+\s+|[,，、;；]", value, flags=re.I)
        if part.strip()
    ]
    for part in parts:
        if not _duplicates(primary, part):
            return part
    return ""


def _duplicates(left: str, right: str) -> bool:
    left = left.lower()
    right = right.lower()
    groups = [
        ["black bird", "bird", "黑鸟", "鸟"],
        ["potato", "土豆", "spud"],
        ["crown", "皇冠", "王冠"],
        ["hat", "sombrero", "帽"],
        ["wing", "翅膀", "翼", "butterfly", "蝴蝶"],
    ]
    return any(
        any(term in left for term in group) and any(term in right for term in group)
        for group in groups
    )


def _split(value: str) -> list[str]:
    if not value:
        return []
    parts: list[str] = []
    for token in str(value).replace("、", ",").replace("，", ",").replace("/", ",").split(","):
        token = token.strip().lower()
        if token:
            parts.append(token)
    return parts


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        key = v.lower().strip()
        if not key or key in seen:
            continue
        out.append(key)
        seen.add(key)
    return out


def _infer(tokens: list[str], table: dict[str, list[str]]) -> list[str]:
    text = " ".join(tokens).lower()
    return [tag for tag, hooks in table.items() if any(_hook_matches(text, h) for h in hooks)]


def _hook_matches(text: str, hook: str) -> bool:
    hook_text = hook.lower().strip()
    if not hook_text:
        return False
    if hook_text.isascii() and re.fullmatch(r"[a-z0-9_]+", hook_text):
        return re.search(rf"(?<![a-z0-9_]){re.escape(hook_text)}(?![a-z0-9_])", text) is not None
    return hook_text in text


def _derive_creative_profile(
    host: HostInput,
    *,
    shape_tags: list[str],
    vibe_tags: list[str],
    vision: HostVisionBrief | None,
) -> CreativeProfile:
    raw = host.raw if isinstance(host.raw, dict) else {}
    explicit_mode = _normalize_creative_mode(
        _first_raw_value(raw, "creative_mode", "creative_profile_mode", "wildness_mode")
    )
    explicit_score = _normalize_wildness_score(
        _first_raw_value(raw, "wildness_score", "wildness_intensity", "creative_intensity")
    )
    explicit_axes = _normalize_axes(
        _first_raw_value(raw, "wildness_axes", "creative_axes", "creative_tags")
    )

    source_text_parts = [
        " ".join(shape_tags),
        " ".join(vibe_tags),
        host.content_type,
        host.live_vibe,
        host.personality,
        host.notes,
        str(raw.get("characterization", "")),
        " ".join(str(v) for v in raw.get("primary_signals", []) or []),
        " ".join(str(v) for v in raw.get("host_symbols", []) or []),
        " ".join(str(v) for v in raw.get("comm_symbols", []) or []),
    ]
    if vision is not None:
        forms = vision.theme_forms
        source_text_parts.extend(
            [
                vision.style_pitch,
                vision.lamp_head_silhouette,
                vision.silhouette_language,
                " ".join(vision.mood.tags),
                forms.primary.symbol,
                " ".join(forms.primary.forms),
                forms.secondary.symbol,
                " ".join(forms.secondary.forms),
            ]
        )

    derived_axes = _infer_creative_axes(" ".join(source_text_parts))
    axes = _dedupe(explicit_axes + derived_axes)

    disabled = _is_falsey(_first_raw_value(raw, "wildness_enabled", "creative_enabled"))
    if disabled or explicit_mode == "baseline":
        return CreativeProfile(
            mode="baseline",
            intensity=0,
            axes=axes,
            source="explicit" if explicit_mode or disabled else "baseline",
            notes="wildness disabled by upstream data",
        )

    if explicit_score is not None:
        intensity = explicit_score
        source = "explicit"
    else:
        intensity = _infer_creative_intensity(axes, vibe_tags)
        source = "derived" if intensity > 0 else "baseline"

    if explicit_mode == "wild":
        intensity = max(intensity, 3)
    elif explicit_mode == "expressive":
        intensity = max(intensity, 1)

    intensity = max(0, min(3, intensity))
    if intensity <= 0:
        mode = "baseline"
        source = "baseline" if not explicit_axes else "explicit"
    elif explicit_mode in {"expressive", "wild"}:
        mode = explicit_mode
    elif intensity >= 3:
        mode = "wild"
    else:
        mode = "expressive"

    notes = (
        "explicit upstream creative controls"
        if source == "explicit"
        else "derived from temperament/form/gesture signals"
        if source == "derived"
        else "no creative divergence signal"
    )
    return CreativeProfile(mode=mode, intensity=intensity, axes=axes, source=source, notes=notes)


def _first_raw_value(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and not _is_empty_raw_value(raw[key]):
            return raw[key]
    return ""


def _normalize_creative_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "base": "baseline",
        "safe": "baseline",
        "stable": "baseline",
        "normal": "baseline",
        "exp": "expressive",
        "creative": "expressive",
        "bold": "wild",
        "feral": "wild",
    }
    text = aliases.get(text, text)
    return text if text in {"baseline", "expressive", "wild"} else ""


def _normalize_wildness_score(value: Any) -> int | None:
    if _is_empty_raw_value(value):
        return None
    if isinstance(value, str):
        label = value.strip().lower()
        label_map = {
            "none": 0,
            "off": 0,
            "low": 1,
            "medium": 2,
            "mid": 2,
            "high": 3,
            "wild": 3,
        }
        if label in label_map:
            return label_map[label]
        try:
            numeric = float(label)
        except ValueError:
            return None
    else:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
    if numeric <= 3:
        return round(numeric)
    if numeric <= 10:
        return round(numeric / 10 * 3)
    return round(min(numeric, 100) / 100 * 3)


def _normalize_axes(value: Any) -> list[str]:
    if _is_empty_raw_value(value):
        return []
    if isinstance(value, str):
        raw_values = [
            part.strip()
            for part in value.replace("、", ",").replace("，", ",").replace("/", ",").split(",")
        ]
    elif isinstance(value, (list, tuple, set)):
        raw_values = [str(part).strip() for part in value]
    else:
        raw_values = [str(value).strip()]
    aliases = {
        "wings": "feather",
        "wing": "feather",
        "swept_wing": "feather",
        "bird": "feather",
        "cow_horn": "horn",
        "panther": "predator",
        "black_panther": "predator",
        "glam": "rock_glam",
        "edgy": "rock_glam",
        "battle": "combat",
        "fighter": "combat",
    }
    out: list[str] = []
    for raw in raw_values:
        key = raw.lower().replace(" ", "_").replace("-", "_")
        key = aliases.get(key, key)
        if key in _CREATIVE_AXIS_INFERENCE:
            out.append(key)
    return _dedupe(out)


def _infer_creative_axes(text: str) -> list[str]:
    lower = text.lower()
    return [
        axis
        for axis, hooks in _CREATIVE_AXIS_INFERENCE.items()
        if any(_hook_matches(lower, hook) for hook in hooks)
    ]


def _infer_creative_intensity(axes: list[str], vibe_tags: list[str]) -> int:
    if not axes:
        return 0
    structural_hits = len([axis for axis in axes if axis in _STRUCTURAL_CREATIVE_AXES])
    expressive_vibe = bool({"wild", "edgy", "glamorous", "bold"} & set(vibe_tags))
    if structural_hits >= 2 and expressive_vibe:
        return 3
    if structural_hits >= 2:
        return 2
    if structural_hits:
        return 1
    return 0


def _is_falsey(value: Any) -> bool:
    return str(value or "").strip().lower() in {"0", "false", "no", "off", "disabled"}


def _is_empty_raw_value(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value == "")


def _shape_tags_from_axes(axes: list[str]) -> list[str]:
    return _dedupe([tag for axis in axes for tag in _AXIS_SHAPE_TAGS.get(axis, [])])


def _vibe_tags_from_profile(profile: CreativeProfile) -> list[str]:
    tags = [tag for axis in profile.axes for tag in _AXIS_VIBE_TAGS.get(axis, [])]
    if profile.intensity >= 2:
        tags.append("bold")
    if profile.mode == "wild":
        tags.append("wild")
    return _dedupe(tags)


def _material_only_tags(tags: list[str]) -> list[str]:
    return [
        str(tag).strip()
        for tag in tags
        if str(tag).strip() and str(tag).strip().lower() not in _NON_MATERIAL_TAGS
    ]


def _theme_forms_text(vision: HostVisionBrief) -> str:
    forms = vision.theme_forms
    values = [
        forms.primary.symbol,
        forms.primary.position,
        *forms.primary.forms,
        forms.secondary.symbol,
        forms.secondary.position,
        *forms.secondary.forms,
        forms.fusion_note,
    ]
    return " ".join(value for value in values if value)


def _analyze_text(host_name: str) -> tuple[str, bool, int, list[str]]:
    """Classify the host name's script and emit text_tags for the reference router."""

    if not host_name:
        return "empty", False, 0, []

    has_emoji = any(_is_emoji(c) for c in host_name)
    stripped = "".join(c for c in host_name if not _is_emoji(c) and not c.isspace())
    char_count = len(stripped)

    has_korean = any(0xAC00 <= ord(c) <= 0xD7A3 or 0x1100 <= ord(c) <= 0x11FF for c in host_name)
    has_arabic = any(0x0600 <= ord(c) <= 0x06FF or 0x0750 <= ord(c) <= 0x077F for c in host_name)
    has_chinese = any(0x4E00 <= ord(c) <= 0x9FFF for c in host_name)
    has_latin = any(c.isascii() and c.isalpha() for c in host_name)

    kinds = []
    if has_latin:
        kinds.append("latin")
    if has_korean:
        kinds.append("korean")
    if has_arabic:
        kinds.append("arabic")
    if has_chinese:
        kinds.append("chinese")

    if not kinds:
        script_kind = "empty"
    elif len(kinds) == 1:
        script_kind = kinds[0]
    else:
        script_kind = "mixed"

    text_tags: list[str] = []
    if has_latin:
        text_tags.append("latin")
    if has_korean:
        text_tags.append("korean")
    if has_arabic:
        text_tags.append("arabic")
    if has_chinese:
        text_tags.append("chinese")
    if not text_tags:
        text_tags.append("non_latin" if (has_korean or has_arabic or has_chinese) else "latin")
    text_tags.append("short" if char_count <= 12 else "long")

    return script_kind, has_emoji, char_count, _dedupe(text_tags)


def _avoid_scripts_for(script_kind: str) -> list[str]:
    """Scripts the image model should avoid for a known target text script."""

    script = (script_kind or "").lower()
    if script == "latin":
        return ["korean", "arabic", "chinese", "japanese", "cyrillic", "thai", "devanagari"]
    if script == "korean":
        return ["arabic", "chinese", "japanese", "latin", "cyrillic", "thai", "devanagari"]
    if script == "arabic":
        return ["korean", "chinese", "japanese", "latin", "cyrillic", "thai", "devanagari"]
    if script == "chinese":
        return ["korean", "arabic", "latin", "cyrillic", "thai", "devanagari"]
    return []


def _is_emoji(char: str) -> bool:
    code = ord(char)
    # Coverage: common emoji blocks + ZWJ + variation selectors.
    return (
        0x1F300 <= code <= 0x1FAFF
        or 0x2600 <= code <= 0x27BF
        or 0xFE00 <= code <= 0xFE0F
        or code == 0x200D
    )
