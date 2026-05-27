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

from typing import Any

from pydantic import BaseModel, Field

from .host_vision import HostVisionBrief
from .models import HostInput
from .style_controls import StyleControls, derive_style_controls


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
    style_controls: StyleControls = Field(default_factory=StyleControls)
    avoid_text_scripts: list[str] = Field(default_factory=list)  # filled by eval
    notes: str = ""


def derive_retrieval_intent(brief: "HostBrief") -> RetrievalIntent:
    """Default intent: mirror brief tags. Eval/repair may rewrite this."""

    avoid_scripts = _avoid_scripts_for(brief.script_kind)
    return RetrievalIntent(
        row_id=brief.row_id,
        shape_anchors=_dedupe(list(brief.shape_tags) + list(brief.style_controls.shape_boosts)),
        color_anchors=list(brief.color_tags),
        material_anchors=_dedupe(list(brief.material_tags) + list(brief.style_controls.material_boosts)),
        vibe_anchors=_dedupe(list(brief.vibe_tags) + list(brief.style_controls.vibe_boosts)),
        text_anchors=list(brief.text_tags),
        style_controls=brief.style_controls,
        avoid_text_scripts=avoid_scripts,
        notes=(
            f"avoid non-target scripts for {brief.script_kind} text"
            if avoid_scripts
            else ""
        ),
    )


# ---------------------------------------------------------------------------
# Inference dictionaries — Chinese / mixed-text keywords → English tags.
# Centralised here (used to be inside reference_router.py).
# ---------------------------------------------------------------------------

_SHAPE_INFERENCE: dict[str, list[str]] = {
    "butterfly": ["蝴蝶", "butterfly", "나비"],
    "wing": ["翅膀", "wing", "羽翼", "feather"],
    "heart": ["爱心", "heart", "💕", "💜", "心"],
    "crown": ["皇冠", "王冠", "crown", "queen", "king", "rey"],
    "hat": ["帽", "hat", "sombrero"],
    "mascot": ["土豆", "potato", "mascot", "圆润", "spud"],
    "shell": ["龟壳", "shell", "turtle"],
    "fruit_cluster": ["樱桃", "cherry", "果"],
    "bird": ["鸟", "bird", "feather", "乌鸦", "黑鸟", "crow", "raven"],
    "eagle": ["🦅", "eagle", "falcon", "hawk", "猎鹰", "鹰"],
    "panther": ["panther", "pantera", "black panther", "黑豹", "豹"],
    "electric": ["闪电", "电光", "electric", "lightning", "thunderbolt"],
}

_COLOR_INFERENCE: dict[str, list[str]] = {
    "purple": ["紫", "purple", "葡萄", "薰衣草", "lavender"],
    "pink": ["粉", "pink", "rose", "magenta", "玫瑰"],
    "red": ["红", "red", "珊瑚", "coral", "cherry"],
    "blue": ["蓝", "blue", "霓虹蓝", "neon_blue"],
    "green": ["绿", "green", "mint", "pistachio", "薄荷"],
    "gold": ["金", "gold", "champagne", "香槟"],
    "white": ["白", "white", "pearl", "珠光", "cream"],
    "silver": ["银", "silver"],
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

    # Deterministic style controls. These keep subjective range controls
    # inspectable instead of burying them in prompt prose.
    style_controls: StyleControls = Field(default_factory=StyleControls)

    # Text-self-check metadata
    script_kind: str = ""        # latin / korean / arabic / chinese / mixed / empty
    has_emoji: bool = False
    char_count: int = 0

    # Vision-derived structured brief (optional — present when the workflow ran
    # ``analyze_host_visual_brief`` upstream). When non-null, template_first
    # uses these values to override router defaults so every slot is concrete.
    vision: HostVisionBrief | None = None

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
                "style_controls": self.style_controls.model_dump(),
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

    shape_tokens = _split_many(symbols_raw) + _split(host.body_form) + _split(host.content_type)
    color_tokens = _split(all_colors)
    vibe_tokens = _split(host.live_vibe) + _split(host.personality)

    shape_tags = _dedupe(shape_tokens + _infer(shape_tokens, _SHAPE_INFERENCE))
    color_tags = _dedupe(color_tokens + _infer(color_tokens, _COLOR_INFERENCE))
    vibe_tags = _dedupe(vibe_tokens + _infer(vibe_tokens, _VIBE_INFERENCE))
    material_tags: list[str] = []

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
            material_tags = _dedupe(material_tags + list(vision.materials.tags))
        if vision.mood.tags:
            vibe_tags = _dedupe(vibe_tags + list(vision.mood.tags))
        if vision.signature_symbols.primary or vision.signature_symbols.secondary:
            sym_tokens = _split_many(
                [
                    vision.signature_symbols.primary,
                    vision.signature_symbols.secondary,
                ]
            )
            shape_tags = _dedupe(shape_tags + sym_tokens + _infer(sym_tokens, _SHAPE_INFERENCE))
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

    script_kind, has_emoji, char_count, text_tags = _analyze_text(host.host_name)
    if vision is not None and vision.text.script:
        script_kind = vision.text.script
        if vision.text.script not in text_tags:
            text_tags = _dedupe([vision.text.script] + text_tags)

    style_controls = derive_style_controls(
        host,
        primary_symbol=primary_symbol,
        secondary_symbol=secondary_symbol,
        shape_tags=shape_tags,
        vibe_tags=vibe_tags,
        material_tags=material_tags,
        color_tags=color_tags,
    )

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
        style_controls=style_controls,
        script_kind=script_kind,
        has_emoji=has_emoji,
        char_count=char_count,
        vision=vision,
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
    import re

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
    import re

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


def _split_many(values: list[str]) -> list[str]:
    parts: list[str] = []
    for value in values:
        parts.extend(_split(value))
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
    text = " ".join(tokens)
    return [tag for tag, hooks in table.items() if any(h.lower() in text for h in hooks)]


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
