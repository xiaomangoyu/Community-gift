from __future__ import annotations

import re

from .csv_io import split_list
from .models import (
    EffectMatch,
    GiftDesign,
    HostInput,
    ImageEvaluation,
    PromptPlan,
)


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


def _looks_like_text_label(value: str) -> bool:
    compact = value.replace(" ", "")
    if re.fullmatch(r"(?i)(mr|mrs|ms|miss|sir|dr)\.?\s+[a-z0-9]+", value.strip()):
        return True
    return len(compact) > 18 and bool(re.fullmatch(r"[A-Za-z0-9._'&-]+", compact))


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
