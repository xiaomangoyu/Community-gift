from __future__ import annotations

import re
import unicodedata

from .csv_io import split_list
from .models import (
    DesignConcept,
    EffectMatch,
    GiftDesign,
    HostInput,
    ImageEvaluation,
    PromptPlan,
    TextRenderPlan,
)


TEXT_COMPLEXITY_LIMIT = 15

FAILURE_KEYWORDS = {
    "cropping_fail": [
        "cropped",
        "touching the frame",
        "touches the image edge",
        "裁切",
        "碰边",
        "底部",
        "bottom cap",
    ],
    "text_fail": [
        "text",
        "typography",
        "misspelled",
        "garbled",
        "blank central",
        "empty nameplate",
        "文字",
        "拼写",
        "乱码",
        "铭牌",
        "核心留空",
    ],
    "complexity_fail": [
        "too many",
        "busy",
        "clutter",
        "复杂",
        "元素过多",
        "堆",
        "compete",
    ],
    "concept_fail": [
        "theme",
        "symbol",
        "motif",
        "主题",
        "符号",
        "映射",
        "literal",
        "具象",
    ],
    "product_form_fail": [
        "not a lightstick",
        "badge",
        "poster",
        "wand",
        "flashlight",
        "tool",
        "徽章",
        "海报",
        "手电",
        "工具",
        "魔法杖",
    ],
    "material_fail": [
        "material",
        "flat",
        "metal",
        "neon",
        "材质",
        "平面",
        "过曝",
        "泛光",
    ],
}


def apply_prompt_planning(
    host: HostInput,
    design: GiftDesign,
    effect_matches: list[EffectMatch],
) -> None:
    design.design_concept = build_design_concept(host, design)
    design.text_plan = build_text_plan(host, design)
    design.prompt_plan = build_prompt_plan(host, design, effect_matches)


def build_design_concept(host: HostInput, design: GiftDesign) -> DesignConcept:
    raw_symbols = _symbol_candidates(host, design)
    primary_symbol = _choose_primary_symbol(host, raw_symbols)
    supporting_mood = _choose_supporting_mood(host, design)
    retained = _retained_elements(primary_symbol, raw_symbols)
    discarded = _discarded_elements(host, design, retained)
    silhouette = _silhouette(host, primary_symbol)
    complexity = _complexity_level(host.decoration_intensity)
    proposition = _main_proposition(host, primary_symbol, supporting_mood, silhouette)

    return DesignConcept(
        main_proposition=proposition,
        primary_symbol=primary_symbol,
        supporting_mood=supporting_mood,
        silhouette=silhouette,
        retained_elements=retained,
        discarded_elements=discarded,
        abstraction_notes=[
            f"Turn {primary_symbol} into the lamp-head silhouette, not a flat icon."
            if primary_symbol
            else "Use one clean lamp-head silhouette instead of a symbol collage.",
            "Use supporting cues only as material, rim, glow, or small molded inlay details.",
            "Do not give equal visual weight to every CSV symbol.",
        ],
        complexity_level=complexity,
        effect_type=_effect_type(host, design),
    )


def build_text_plan(host: HostInput, design: GiftDesign) -> TextRenderPlan:
    exact_text = _display_text_target(host, design)
    sanitized = _clean_exact_text(exact_text)
    if not sanitized:
        sanitized = "Creator"

    is_ascii_safe = bool(re.fullmatch(r"[A-Za-z0-9 ._'&-]+", sanitized))
    compact_length = len(sanitized.replace(" ", ""))
    complex_text = (
        compact_length > TEXT_COMPLEXITY_LIMIT
        or not is_ascii_safe
        or _has_many_punctuation(sanitized)
    )
    mode = "post_overlay_text" if complex_text else "one_shot_text"
    reason = (
        "complex text should be rendered programmatically after image generation"
        if complex_text
        else "short Latin text is acceptable for one-shot image generation"
    )
    max_lines = 2 if compact_length > 10 else 1
    instruction = (
        "Generate a blank, smooth central luminous nameplate/core reserved for later exact text overlay."
        if mode == "post_overlay_text"
        else "Render the exact text horizontally inside the central luminous core/nameplate."
    )
    return TextRenderPlan(
        mode=mode,
        exact_text=sanitized,
        sanitized_text=sanitized,
        reason=reason,
        max_lines=max_lines,
        nameplate_instruction=instruction,
    )


def build_prompt_plan(
    host: HostInput,
    design: GiftDesign,
    effect_matches: list[EffectMatch],
    retry_focus: list[str] | None = None,
) -> PromptPlan:
    effect_id = effect_matches[0].effect_id if effect_matches else ""
    concept = design.design_concept
    retained = concept.retained_elements[:3] or _symbol_candidates(host, design)[:2]
    material = _safe_material_terms(
        split_list(host.material_language_hint)[:4] or design.material_language[:4]
    )
    color_terms = _safe_color_terms([term for term in [host.primary_color, host.secondary_color] if term])
    banned = [*host.banned_elements, *design.negative_constraints, *concept.discarded_elements]
    banned.extend(
        [
            "pure black product body",
            "black handle",
            "glossy black resin as main material",
            "white product card",
            "white rounded rectangle panel",
            "split-screen product sheet",
            "detail inset panels",
            "macro close-up",
        ]
    )
    return PromptPlan(
        effect_id=effect_id,
        camera_contract=[
            "pure black background",
            "1:1 square studio product render",
            "one complete vertical lightstick fully visible",
            "front-facing to slight 3/4 view",
            "10% black margin around the full object",
            "no white card, no product sheet, no inset panels",
        ],
        product_contract=[
            "dominant sculpted lamp head",
            "solid central luminous core or inset nameplate",
            "clean unlettered handle",
            "clear connector ring",
            "compact finished bottom cap",
        ],
        material_terms=material
        or [
            "glossy resin",
            "polished enamel",
            "translucent jelly crystal",
            "restrained metallic trim",
        ],
        color_terms=color_terms,
        retained_elements=retained,
        banned_elements=_unique_nonempty(banned)[:16],
        retry_focus=retry_focus or [],
    )


def classify_evaluation_failures(evaluation: ImageEvaluation) -> list[str]:
    if evaluation.failure_types:
        return _unique_nonempty(evaluation.failure_types)
    text = " ".join(
        [
            evaluation.verdict,
            *evaluation.issues,
            *evaluation.prompt_revision_notes,
        ]
    ).lower()
    failures = [
        failure
        for failure, keywords in FAILURE_KEYWORDS.items()
        if any(keyword.lower() in text for keyword in keywords)
    ]
    if not failures and not evaluation.passed:
        failures.append("unknown_fail")
    return failures


def update_plan_for_retry(
    host: HostInput,
    design: GiftDesign,
    evaluations: list[ImageEvaluation],
) -> None:
    failures: list[str] = []
    for evaluation in evaluations:
        failures.extend(classify_evaluation_failures(evaluation))
    failures = _unique_nonempty(failures)
    if "text_fail" in failures:
        design.text_plan.mode = "post_overlay_text"
        design.text_plan.reason = "VLM detected text failure; switch to blank nameplate for later overlay."
        design.text_plan.nameplate_instruction = (
            "Generate a blank, smooth central luminous nameplate/core reserved for later exact text overlay."
        )
    if "complexity_fail" in failures:
        design.design_concept.complexity_level = "low"
        design.design_concept.retained_elements = design.design_concept.retained_elements[:2]
    design.prompt_plan = build_prompt_plan(
        host,
        design,
        design.matched_effects,
        retry_focus=failures[:4],
    )


def _symbol_candidates(host: HostInput, design: GiftDesign) -> list[str]:
    candidates = [
        *host.symbols,
        host.body_form,
        host.content_type,
        *design.required_elements,
    ]
    blocked = {
        host.host_name,
        host.community_name,
        host.primary_text,
        host.secondary_text,
        design.host_name,
        design.community_name,
    }
    return [
        item
        for item in _unique_nonempty(candidates)
        if item not in blocked and not _looks_like_text_label(item)
    ]


def _choose_primary_symbol(host: HostInput, symbols: list[str]) -> str:
    if host.body_form:
        first = re.split(r"\s*/\s*|\s+or\s+|\s+\+\s+", host.body_form, maxsplit=1, flags=re.I)[0]
        if first.strip():
            return first.strip()
    if symbols:
        first = re.split(r"\s*/\s*|\s+or\s+|\s+\+\s+", symbols[0], maxsplit=1, flags=re.I)[0]
        return first.strip()
    return "custom luminous emblem"


def _choose_supporting_mood(host: HostInput, design: GiftDesign) -> str:
    for value in [host.live_vibe, host.personality, host.material_language_hint, design.color_plan]:
        if value:
            return _safe_text_for_product_color(value)
    return "premium collectible idol support mood"


def _retained_elements(primary_symbol: str, symbols: list[str]) -> list[str]:
    retained = [primary_symbol]
    for symbol in symbols:
        secondary = _secondary_value(primary_symbol, symbol)
        if (
            secondary != primary_symbol
            and not _duplicates_primary(primary_symbol, secondary)
            and _is_strong_secondary_symbol(secondary)
        ):
            retained.append(secondary)
        if len(retained) >= 2:
            break
    return _unique_nonempty(retained)[:3]


def _discarded_elements(host: HostInput, design: GiftDesign, retained: list[str]) -> list[str]:
    retained_text = " ".join(retained).lower()
    discarded: list[str] = []
    for symbol in _symbol_candidates(host, design):
        if symbol.lower() not in retained_text:
            discarded.append(symbol)
    discarded.extend(
        [
            "extra mascot stickers",
            "detached props",
            "secondary slogans",
            "handle lettering",
        ]
    )
    return _unique_nonempty(discarded)[:8]


def _silhouette(host: HostInput, primary_symbol: str) -> str:
    source = f"{host.body_form} {primary_symbol}".lower()
    if any(word in source for word in ["wing", "羽", "butterfly", "蝴蝶"]):
        return "winged lamp-head silhouette"
    if any(word in source for word in ["crown", "皇冠"]):
        return "crown-shaped lamp-head silhouette"
    if any(word in source for word in ["potato", "土豆", "fruit", "水果"]):
        return "rounded mascot lamp-head silhouette"
    if any(word in source for word in ["wave", "海", "shell", "island"]):
        return "flowing wave lamp-head silhouette"
    if any(word in source for word in ["bird", "鸟"]):
        return "wing-crown lamp-head silhouette"
    if any(word in source for word in ["hat", "sombrero", "帽"]):
        return "brim-inspired lamp-head silhouette"
    return "bold sculpted lamp-head silhouette"


def _main_proposition(
    host: HostInput,
    primary_symbol: str,
    supporting_mood: str,
    silhouette: str,
) -> str:
    color = " and ".join(_safe_color_terms([term for term in [host.primary_color, host.secondary_color] if term]))
    pieces = [
        f"A {silhouette} built from {primary_symbol}",
        f"with {supporting_mood}" if supporting_mood else "",
        f"in {color}" if color else "",
    ]
    return ", ".join(piece for piece in pieces if piece) + "."


def _complexity_level(value: str) -> str:
    text = value.lower()
    if any(word in text for word in ["低", "low", "simple"]):
        return "low"
    if any(word in text for word in ["高", "high"]):
        return "medium"
    return "medium"


def _effect_type(host: HostInput, design: GiftDesign) -> str:
    text = " ".join(
        [
            host.recommended_output_type,
            host.body_form,
            host.content_type,
            design.recommended_gift_form,
        ]
    ).lower()
    if any(word in text for word in ["light", "stick", "baton", "应援棒"]):
        return "lightstick"
    return "collectible_gift"


def _display_text_target(host: HostInput, design: GiftDesign) -> str:
    return host.host_name or design.host_name or host.primary_text or host.community_name or design.community_name


def _clean_exact_text(value: str) -> str:
    allowed_punctuation = {" ", "-", "_", ".", "'", "&"}
    chars: list[str] = []
    for char in value:
        category = unicodedata.category(char)
        if category[0] in {"L", "N"} or char in allowed_punctuation:
            chars.append(char)
    return " ".join("".join(chars).split())


def _has_many_punctuation(value: str) -> bool:
    punctuation = [char for char in value if unicodedata.category(char).startswith("P")]
    return len(punctuation) >= 3


def _looks_like_text_label(value: str) -> bool:
    compact = value.replace(" ", "")
    if re.fullmatch(r"(?i)(mr|mrs|ms|miss|sir|dr)\.?\s+[a-z0-9]+", value.strip()):
        return True
    return len(compact) > 18 and bool(re.fullmatch(r"[A-Za-z0-9._'&-]+", compact))


def _is_strong_secondary_symbol(value: str) -> bool:
    weak_terms = [
        "mirror",
        "ghost",
        "tiny",
        "accessory",
        "details",
        "marks",
        "chant",
        "band",
        "prop",
        "slogan",
        "microphone",
    ]
    text = value.lower()
    if any(term in text for term in weak_terms):
        return False
    if len(value.strip()) <= 1 and value.strip() not in {"🐓", "⚡", "⚡️", "🥔", "🦋"}:
        return False
    return True


def _duplicates_primary(primary: str, value: str) -> bool:
    primary_text = primary.lower()
    value_text = value.lower()
    concept_groups = [
        ["黑鸟", "bird", "raven", "crow"],
        ["土豆", "potato", "spud"],
        ["蝴蝶", "butterfly", "wing", "翅膀"],
        ["皇冠", "crown"],
        ["sombrero", "hat", "帽"],
    ]
    for group in concept_groups:
        primary_hit = any(term in primary_text for term in group)
        value_hit = any(term in value_text for term in group)
        if primary_hit and value_hit:
            return True
    return False


def _secondary_value(primary: str, value: str) -> str:
    parts = [
        part.strip()
        for part in re.split(r"\s+or\s+|\s*/\s*|\s+\+\s+", value, flags=re.I)
        if part.strip()
    ]
    for part in parts:
        if not _duplicates_primary(primary, part):
            return part
    return value


def _unique_nonempty(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        output.append(clean)
        seen.add(key)
    return output


def _safe_color_terms(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        clean = value.strip()
        if not clean:
            continue
        if _contains_black(clean):
            output.append(
                "smoked graphite gray or warm gunmetal gray for the product shell, never pure black"
            )
            accents = [
                part.strip()
                for part in re.split(r"[,，、/;；]", clean)
                if part.strip() and not _contains_black(part)
            ]
            output.extend(accents)
        else:
            output.append(clean)
    if not output:
        output.append("light gray, pearlescent white, or colored resin body")
    return _unique_nonempty(output)[:4]


def _safe_material_terms(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        clean = value.strip()
        if not clean:
            continue
        lowered = clean.lower()
        if "black" in lowered or "黑" in clean:
            clean = re.sub("(?i)glossy black", "smoked graphite gray", clean)
            clean = clean.replace("黑色", "烟灰色").replace("黑", "烟灰")
            if "pure black" in lowered:
                clean = "smoked graphite gray resin"
        output.append(clean)
    output.extend(
        [
            "non-black light-separable product shell",
            "visible gray edge highlights for clean cutout",
        ]
    )
    return _unique_nonempty(output)[:5]


def _contains_black(value: str) -> bool:
    text = value.lower()
    return "black" in text or "黑" in value


def _safe_text_for_product_color(value: str) -> str:
    clean = value.strip()
    clean = re.sub("(?i)glossy black resin", "smoked graphite gray resin", clean)
    clean = re.sub("(?i)pure black", "smoked graphite gray", clean)
    clean = clean.replace("黑色", "烟灰色").replace("黑曜石", "烟晶").replace("黑", "烟灰")
    return clean
