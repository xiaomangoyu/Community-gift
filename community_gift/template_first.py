"""Template-first design path.

Builds a stable Seedream prompt from a fixed skeleton plus a few host slots.
Per-dimension decisions (color / shape) are delegated to routers in
community_gift/routing/. The skeleton itself stays in this file as a single
f-string so it is easy to diff visually.
"""

from __future__ import annotations

import os
import unicodedata

from .host_brief import HostBrief, RetrievalIntent, build_host_brief, derive_retrieval_intent
from .host_vision import HostVisionBrief
from .models import (
    DesignConcept,
    EffectMatch,
    GiftDesign,
    HostInput,
    PromptPlan,
    TextRenderPlan,
)
from .routing.color_router import ColorRouter
from .routing.reference_router import ReferenceRouter
from .routing.shape_router import ShapeRouter


_color_router: ColorRouter | None = None
_shape_router: ShapeRouter | None = None
_reference_router: ReferenceRouter | None = None


def _routers() -> tuple[ColorRouter, ShapeRouter, ReferenceRouter]:
    global _color_router, _shape_router, _reference_router
    if _color_router is None:
        _color_router = ColorRouter()
    if _shape_router is None:
        _shape_router = ShapeRouter()
    if _reference_router is None:
        # Default 1: avatar + 1 lightstick reference. The vision brief now
        # supplies palette/materials/shape/handle in detail, so multiple
        # references mostly add cross-host visual averaging. Override via env.
        top_n = max(1, int(os.getenv("REFERENCE_TOP_N", "1") or 1))
        _reference_router = ReferenceRouter(top_n=top_n)
    return _color_router, _shape_router, _reference_router


def build_template_first_design(
    host: HostInput,
    effect_matches: list[EffectMatch] | None = None,
    brief: HostBrief | None = None,
    intent: RetrievalIntent | None = None,
) -> tuple[GiftDesign, HostBrief]:
    """Build a stable prompt from a fixed template and a few host slots.

    Returns (design, brief). Workflow persists the brief separately so the
    pre-router intermediate is inspectable and editable.

    Both ``brief`` and ``intent`` are normally supplied by workflow (which
    runs eval + repair upstream). Defaults are fresh defaults so this
    function is also usable in isolation (scripts, tests).
    """

    if brief is None:
        brief = build_host_brief(host)
    if intent is None:
        intent = derive_retrieval_intent(brief)
    slots, color_decision, shape_decision, reference_decision = _extract_slots(host, brief, intent)

    text_plan = TextRenderPlan(
        mode="one_shot_text",
        exact_text=slots["display_text"],
        sanitized_text=slots["display_text"],
        reason=slots.get("text_policy_reason")
        or "template-first mode renders the selected exact text inside the lamp-head shape",
        max_lines=2 if len(slots["display_text"].replace(" ", "")) > 10 else 1,
        nameplate_instruction="exact selected text inside the central lamp-head nameplate",
    )
    concept = DesignConcept(
        main_proposition=(
            f"{slots['theme_title']}：以{slots['primary_symbol']}作为唯一主视觉，"
            f"{slots['secondary_symbol']}只作为边缘辅助细节。"
        ),
        primary_symbol=slots["primary_symbol"],
        supporting_mood=slots["mood"],
        silhouette=slots["silhouette"],
        retained_elements=[slots["primary_symbol"], slots["secondary_symbol"]],
        discarded_elements=slots["discarded"],
        abstraction_notes=[
            "Host data is a delta, not the prompt skeleton.",
            "Only the primary symbol may shape the lamp-head silhouette.",
            "Supporting data may become small rim detail, material cue, or color accent.",
        ],
        complexity_level="low",
        effect_type="lightstick",
    )
    prompt_plan = PromptPlan(
        effect_id=(effect_matches or [EffectMatch(effect_id="", effect_name="")])[0].effect_id,
        camera_contract=[
            "pure black background",
            "single full-body lightstick",
            "front to very slight 3/4 studio product view",
            "complete handle and compact bottom cap",
        ],
        product_contract=[
            "dominant lamp head",
            "streamer nameplate inside the lamp-head shape",
            "central luminous core",
            "connector ring",
            "unlettered handle",
            "compact bottom cap",
        ],
        material_terms=slots["materials"],
        color_terms=slots["colors"],
        retained_elements=[slots["primary_symbol"], slots["secondary_symbol"]],
        banned_elements=slots["banned"],
        retry_focus=[],
    )
    prompt = _build_prompt(slots)
    negative_prompt = _build_negative_prompt(slots)
    design = GiftDesign(
        row_id=host.row_id,
        host_name=host.host_name or "Host",
        community_name=host.primary_text or host.community_name or "Community",
        matched_effects=effect_matches or [],
        design_concept=concept,
        text_plan=text_plan,
        prompt_plan=prompt_plan,
        core_keywords=[
            "template-first",
            "premium full-body lightstick",
            slots["primary_symbol"],
            slots["secondary_symbol"],
        ],
        required_elements=[
            "single full-body lightstick",
            "pure black background",
            "exact streamer name inside the lamp-head shape",
            slots["primary_symbol"],
            slots["color_anchor"],
        ],
        abstract_methods=[
            f"Turn {slots['primary_symbol']} into one bold lamp-head silhouette or perimeter mass.",
            f"Use {slots['secondary_symbol']} only as a small molded inlay, rim accent, or glow detail.",
        ],
        recommended_gift_form="premium full-body personalized lightstick",
        material_language=slots["materials"],
        color_plan=", ".join(slots["colors"]),
        composition=(
            "Single centered full-body product render on pure black, with complete handle and bottom cap."
        ),
        complexity_rules=[
            "template-first mode",
            "one primary symbol only",
            "one supporting motif only",
            "one streamer element must appear on the lightstick body",
            "one streamer color group must appear on the lightstick body",
            "ignore extra host details after these anchors are satisfied",
        ],
        negative_constraints=slots["banned"],
        seedance_prompt=prompt,
        seedance_negative_prompt=negative_prompt,
        reference_pairs=_assemble_reference_pairs(host, reference_decision),
        routing_trace={
            "color": {
                "matched_rule_id": color_decision.matched_rule_id,
                "fields": color_decision.fields,
                "trace": color_decision.trace_dict(),
            },
            "shape": {
                "matched_rule_id": shape_decision.matched_rule_id,
                "fields": shape_decision.fields,
                "trace": shape_decision.trace_dict(),
            },
            "reference": {
                "matched_rule_id": reference_decision.matched_rule_id,
                "fields": reference_decision.fields,
                "trace": reference_decision.trace_dict(),
            },
        },
    )
    return design, brief


_HOST_AVATAR_ROLE = (
    "host avatar (NOT a lightstick reference) — extract dominant colors, "
    "lighting mood, vibe, and any signature visual element (mascot, prop, "
    "fashion item, hair colour). Do NOT copy the person's face or render "
    "any human figure. Use as colour/mood anchor only. Ignore the avatar "
    "background, white canvas, circular avatar crop, border, edge colour, "
    "profile-frame layout, and any UI-like framing; never use them as "
    "composition or background references."
)


def _include_host_avatar_reference() -> bool:
    return os.getenv("INCLUDE_HOST_AVATAR_REFERENCE", "false").lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _assemble_reference_pairs(host: HostInput, reference_decision) -> list[tuple[str, str]]:
    """Avatar first (when present), then lightstick references from the router."""

    pairs: list[tuple[str, str]] = []
    avatar = (host.host_image or "").strip()
    if _include_host_avatar_reference() and avatar and not avatar.startswith(("http://", "https://", "data:")):
        from pathlib import Path as _Path

        if _Path(avatar).exists():
            pairs.append((avatar, _HOST_AVATAR_ROLE))

    for pick in reference_decision.fields.get("picks", []) or []:
        image_path = pick.get("image_path")
        if image_path:
            pairs.append((image_path, pick.get("role_description", "")))
    return pairs


def _extract_slots(host: HostInput, brief: HostBrief, intent: RetrievalIntent):
    primary_symbol = brief.primary_symbol
    secondary_symbol = brief.secondary_symbol

    context = brief.to_routing_context(intent)
    color_router, shape_router, reference_router = _routers()
    color_decision = color_router.route(context)
    shape_decision = shape_router.route(context)
    reference_decision = reference_router.route(context)

    color_fields = color_decision.fields
    shape_fields = shape_decision.fields
    reference_fields = reference_decision.fields

    banned = _unique(list(color_fields.get("negative_add", [])))
    display_text, text_policy_reason = _select_display_text(host, brief)

    intent_anchor_terms = _unique(
        list(intent.shape_anchors)
        + list(intent.vibe_anchors)
        + list(intent.material_anchors)
    )
    # Filter out raw multi-token Chinese fragments that came straight from
    # CSV columns — they're noisy in a prompt anchor line. Keep only
    # short single-word tags (the inferred English ones from manifests).
    intent_anchor_terms = [t for t in intent_anchor_terms if len(t) <= 20 and " " not in t]

    slots = {
        "display_text": display_text,
        "text_policy_reason": text_policy_reason,
        "primary_symbol": primary_symbol,
        "secondary_symbol": secondary_symbol,
        "silhouette": shape_fields["silhouette"],
        "colors": list(color_fields["palette"]),
        "materials": list(color_fields["materials"]),
        "theme_title": shape_fields["theme_title"],
        "mood": shape_fields["mood"],
        "symbol_translation": shape_fields["symbol_translation"],
        "supporting_translation": shape_fields["supporting_translation"],
        "text_style": shape_fields["text_style"],
        "bottom_node": shape_fields["bottom_node"],
        "silhouette_language": shape_fields["silhouette_language"],
        "lighting": "",
        "fusion_note": "",
        "lamp_head_silhouette": "",
        "handle_phrase": "",
        "element_anchor": primary_symbol,
        "color_anchor": color_fields["main_color"],
        "palette_id": color_fields["palette_id"],
        "palette_name": color_fields["palette_name"],
        "intent_anchor_terms": intent_anchor_terms,
        "intent_avoid_text_scripts": list(intent.avoid_text_scripts),
        "banned": banned,
        "discarded": _discarded(brief.symbols_raw, [primary_symbol, secondary_symbol]),
    }
    if brief.vision is not None:
        _apply_vision_overrides(slots, brief.vision)
    _enforce_display_text_policy(slots, host, brief)
    return slots, color_decision, shape_decision, reference_decision


def _apply_vision_overrides(slots: dict, vision: HostVisionBrief) -> None:
    """Override router-default slots with vision-derived values where present.

    Router output is the fallback; vision wins because it actually looked at
    the avatar. We only replace a slot when vision has a non-empty value, so a
    partially-failed vision call still degrades gracefully.
    """

    # Display text — eval-critical, ensures rendered glyphs == decided text.
    if vision.text.exact_text:
        slots["display_text"] = vision.text.exact_text
    if vision.text.style_hint:
        slots["text_style"] = vision.text.style_hint

    if vision.style_pitch:
        slots["theme_title"] = vision.style_pitch
    if vision.mood.phrase:
        slots["mood"] = vision.mood.phrase
    if vision.silhouette_language:
        slots["silhouette_language"] = vision.silhouette_language
    if vision.lighting:
        slots["lighting"] = vision.lighting
    if vision.theme_forms.fusion_note:
        slots["fusion_note"] = vision.theme_forms.fusion_note

    primary_prose = _format_symbol_forms(vision.theme_forms.primary)
    if primary_prose:
        slots["symbol_translation"] = primary_prose
    secondary_prose = _format_symbol_forms(vision.theme_forms.secondary)
    if secondary_prose:
        slots["supporting_translation"] = secondary_prose

    # Palette — main, secondary, accents in declared order.
    palette_terms = [
        t
        for t in [
            vision.palette.main_color,
            vision.palette.secondary_color,
            *vision.palette.accent_colors,
        ]
        if t
    ]
    if palette_terms:
        slots["colors"] = palette_terms
    if vision.palette.main_color:
        slots["color_anchor"] = vision.palette.main_color
    if vision.palette.family:
        slots["palette_name"] = vision.palette.family

    material_terms = [t for t in [vision.materials.main, vision.materials.supporting] if t]
    if material_terms:
        slots["materials"] = material_terms

    # Override primary/secondary symbol display text too, so the prompt's
    # backticked references ("主题为「X」的解构设计") use the visual concept
    # instead of the streamer's plain name.
    if vision.signature_symbols.primary:
        slots["primary_symbol"] = vision.signature_symbols.primary
        slots["element_anchor"] = vision.signature_symbols.primary
    if vision.signature_symbols.secondary:
        slots["secondary_symbol"] = vision.signature_symbols.secondary

    if vision.lamp_head_silhouette:
        slots["lamp_head_silhouette"] = vision.lamp_head_silhouette

    handle_phrase = _format_handle(vision.handle)
    if handle_phrase:
        slots["handle_phrase"] = handle_phrase


def _format_handle(handle) -> str:
    """Join a HandleBlock into one Chinese sentence. Empty if too sparse."""

    if not handle:
        return ""
    parts: list[str] = []
    if handle.main_material:
        parts.append(f"握柄主体使用{handle.main_material}")
    if handle.surface_treatment:
        parts.append(f"表面处理为{handle.surface_treatment}")
    if handle.connector_detail:
        parts.append(f"连接处搭配{handle.connector_detail}")
    if handle.bottom_cap:
        parts.append(f"底盖设计为{handle.bottom_cap}")
    if handle.decoration_continuation:
        parts.append(f"主题延续上，{handle.decoration_continuation}")
    if len(parts) < 2:
        return ""
    return "。".join(parts) + "。"


def _format_symbol_forms(forms) -> str:
    """Join a SymbolForms object into one Chinese phrase. Empty if too sparse."""

    if not forms or not forms.symbol or not forms.forms:
        return ""
    position = forms.position or "灯头主体"
    return f"将「{forms.symbol}」解构为{position}的{'、'.join(forms.forms)}"


def _select_display_text(host: HostInput, brief: HostBrief) -> tuple[str, str]:
    """Pick the exact text rendered in the lamp head.

    Long streamer names should first try a community-owned text target. If no
    community text exists, keep the streamer name rather than generating a
    blank plate; current previews still need a readable first-shot label.
    """

    host_text = _clean_optional_text(host.host_name or brief.host_name or "")
    community_text = _clean_optional_text(host.primary_text or host.community_name or brief.community_name or "")
    limit = _text_switch_limit()

    if host_text and _compact_text_len(host_text) > limit and community_text:
        return (
            community_text,
            f"host name exceeds {limit} compact characters; using community text",
        )
    if host_text:
        return host_text, "using streamer name as exact one-shot text"
    if community_text:
        return community_text, "streamer name unavailable; using community text"
    return "Creator", "no usable text source; using Creator fallback"


def _enforce_display_text_policy(slots: dict, host: HostInput, brief: HostBrief) -> None:
    """Re-apply text policy after vision overrides.

    Cached vision briefs may carry an older exact_text choice. The final rule
    remains: if the host name is over the compact length limit and community
    text exists, use community text; otherwise render whichever usable text we
    have rather than switching to a blank post-overlay core.
    """

    selected, reason = _select_display_text(host, brief)
    host_text = _clean_optional_text(host.host_name or brief.host_name or "")
    community_text = _clean_optional_text(host.primary_text or host.community_name or brief.community_name or "")
    limit = _text_switch_limit()

    if host_text and _compact_text_len(host_text) > limit and community_text:
        slots["display_text"] = selected
        slots["text_policy_reason"] = reason
        return

    current = _clean_optional_text(slots.get("display_text", ""))
    if current:
        slots["display_text"] = current
        slots.setdefault("text_policy_reason", "using vision-selected exact one-shot text")
        return
    slots["display_text"] = selected
    slots["text_policy_reason"] = reason


def _text_switch_limit() -> int:
    raw = os.getenv("TEXT_COMMUNITY_FALLBACK_LIMIT", "15")
    try:
        return max(1, int(raw))
    except ValueError:
        return 15


def _compact_text_len(text: str) -> int:
    return len(str(text or "").replace(" ", ""))


def _clean_optional_text(value: str) -> str:
    cleaned = _clean_text(value or "")
    return "" if cleaned == "Creator" and not str(value or "").strip() else cleaned


def _build_prompt(slots: dict) -> str:
    """Reference-style final prompt.

    Keep the same section order as the strongest hand-written references,
    but avoid over-constraining language. Repeated "hard constraint" phrasing
    tends to make the render stiff, so safety rules now live mostly in the
    negative prompt.
    """

    colors = "、".join(slots["colors"])
    materials = "、".join(_soften_material_terms(slots["materials"]))
    lighting_phrase = "柔和棚拍主光、克制边缘描光、低反射材质对比、中央文字小范围内发光"
    fusion_note = slots.get("fusion_note") or ""
    fusion_clause = f"{fusion_note}。" if fusion_note else ""
    secondary_clause = (
        f"；{slots['supporting_translation']}"
        if slots.get("supporting_translation")
        else ""
    )
    lamp_head_silhouette = (
        slots.get("lamp_head_silhouette")
        or f"以「{slots['primary_symbol']}」为核心的一体化立体灯头"
    )
    handle_phrase = slots.get("handle_phrase") or (
        "握柄主体延续主题材质，与灯头形成同语义的视觉一体化。"
    )
    handle_phrase = _soften_handle_phrase(handle_phrase)
    bottom_node = _soften_handle_phrase(slots["bottom_node"])
    script_guidance = _text_script_guidance(slots["display_text"])

    prompt = f"""黑色背景，1:1 正方形画面，固定 45 度朝右产品视角，完整展示整支打call棒，从灯头、连接处、握柄到底部节点全部清晰可见，主体居中，高精度3D收藏级应援棒。灯头是视觉重心，握柄短而完整，整体是一体连续的圆润产品造型。顶部为{lamp_head_silhouette}，中央为完整饱满的实体核心，中间嵌入发光文字「{slots['display_text']}」。

整体风格围绕「{slots['primary_symbol']}」延展，设定为{slots['theme_title']}，整体气质偏{slots['mood']}。

整体配色采用{colors}（主色锚点「{slots['color_anchor']}」，来自{slots['palette_name']}）。背景保持纯黑棚拍质感；如果主题需要深色，用烟灰、枪灰、珠光灰或深色透明树脂表达，让产品边缘和材质层次仍然清楚。

材质以{materials}为主，整体强调圆润实体厚度、材质对比、精致倒角、收藏级产品质感。亮面硬质饰件只作为薄边、微小徽章或少量连接点出现；皮革、织物或护具感元素转译为连续哑光包覆、浅压纹和干净表面。打光以{lighting_phrase}为主，重点表现真实厚度、清晰倒角、柔和受控高光。

主题为「{slots['primary_symbol']}」的解构设计：{slots['symbol_translation']}{secondary_clause}。{fusion_clause}所有外扩装饰、包边、护片或框架都与灯头主体一体成型，中央核心保持完整饱满，不做空心镂空，也不做贴纸式平面图案。

让整体灯头像一个被「{slots['primary_symbol']}」包裹塑造的收藏级应援圣物，既有偶像应援感，也有独特的个人辨识度。整体轮廓语言强调{slots['silhouette_language']}，从正面和侧面都能读出清楚的立体结构。

文字「{slots['display_text']}」自然嵌入灯头中央实体核心。{slots['text_style']}。{script_guidance}画面中只出现这一处主文字，文字与核心结构融合，不做外接文字牌。

手柄设计：{handle_phrase}手柄保持短而饱满的握把比例，与灯头自然连接，不做细长法杖感。底部装饰为{bottom_node}，与手柄整体协调。

整体气质：{slots['mood']}，带有偶像周边收藏感。

整体强调：收藏级实体产品渲染、强3D体积感、真实材质厚度、克制明暗层次、文字与中央核心局部发光、整支棒体不做全局霓虹泛光、干净棚拍产品感。整支打call棒完整入画，灯头、连接件、完整手柄和底部节点都清晰可见，产品像悬浮在纯黑摄影棚中。"""
    return _polish_prompt_text(prompt)


def _build_negative_prompt(slots: dict) -> str:
    """Compact negatives focused on the recurring failure modes."""
    base = [
        # 人像/真人
        "person",
        "human face",
        # 白底/灰底/卡片背景
        "white background",
        "gray background",
        "product card",
        # 裁切/只拍灯头/缺手柄
        "close-up",
        "cropped handle",
        "cropped lamp head",
        "missing handle",
        "missing bottom cap",
        # 长杆/法杖/武器/手电筒
        "weapon",
        "staff",
        "wand",
        "scepter",
        "long thin shaft",
        "flashlight",
        # 多余文字/错字/外部文字牌
        "fake letters",
        "misspelled name",
        "wrong name",
        "extra text",
        "external nameplate",
        # 过曝/强反光/廉价塑料/大面积金属
        "overexposed",
        "excessive bloom",
        "mirror-like reflections",
        "cheap glossy plastic",
        "heavy chrome metal",
    ]
    avoid_scripts = set(slots.get("intent_avoid_text_scripts") or [])
    if not avoid_scripts:
        avoid_scripts = _infer_avoid_scripts_from_text(slots.get("display_text", ""))
    script_negatives = _negatives_from_avoid_scripts(avoid_scripts)
    return ", ".join(_unique(base + slots["banned"] + script_negatives))


_SCRIPT_NEGATIVE_TERMS: dict[str, list[str]] = {
    "latin": ["Latin text"],
    "korean": ["Korean text"],
    "arabic": ["Arabic text"],
    "chinese": ["Chinese text"],
    "japanese": ["Japanese text"],
    "cyrillic": ["Cyrillic text"],
    "thai": ["Thai script"],
    "devanagari": ["Hindi text"],
}


def _infer_avoid_scripts_from_text(text: str) -> set[str]:
    """Fallback script guard for mixed/non-Latin names."""

    all_scripts = set(_SCRIPT_NEGATIVE_TERMS)
    allowed = _detect_text_scripts(text)
    return all_scripts - allowed if allowed else set()


def _detect_text_scripts(text: str) -> set[str]:
    scripts: set[str] = set()
    for char in text or "":
        code = ord(char)
        if "A" <= char <= "Z" or "a" <= char <= "z":
            scripts.add("latin")
        elif 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF:
            scripts.add("korean")
        elif 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
            scripts.add("arabic")
        elif 0x3040 <= code <= 0x30FF:
            scripts.add("japanese")
        elif 0x4E00 <= code <= 0x9FFF:
            scripts.update({"chinese", "japanese"})
        elif 0x0400 <= code <= 0x04FF:
            scripts.add("cyrillic")
        elif 0x0E00 <= code <= 0x0E7F:
            scripts.add("thai")
        elif 0x0900 <= code <= 0x097F:
            scripts.add("devanagari")
    return scripts


def _text_script_guidance(text: str) -> str:
    scripts = _detect_text_scripts(text)
    if "japanese" in scripts and "latin" not in scripts:
        return "文字必须保持日文假名/日文字符结构，不要转写成英文字母或其他文字。"
    if "korean" in scripts and "latin" not in scripts:
        return "文字必须保持韩文字形结构，不要转写成英文字母或其他文字。"
    if "arabic" in scripts and "latin" not in scripts:
        return "文字必须保持阿拉伯字形结构和书写方向，不要转写成英文字母或其他文字。"
    if "thai" in scripts and "latin" not in scripts:
        return "文字必须保持泰文字形结构，不要转写成英文字母或其他文字。"
    if "chinese" in scripts and "latin" not in scripts:
        return "文字必须保持中文汉字结构，不要转写成英文字母或其他文字。"
    return ""


def _negatives_from_avoid_scripts(scripts: list[str]) -> list[str]:
    out: list[str] = []
    for script in scripts:
        terms = _SCRIPT_NEGATIVE_TERMS.get(str(script).lower())
        if terms:
            out.extend(terms)
    return out


def _format_anchor_line(terms: list[str]) -> str:
    """Append-on-same-paragraph anchor line. Empty string if no terms."""

    if not terms:
        return ""
    return f" 设计语言锚点参考:{', '.join(terms)}（用于内部一致性约束,不作为字面文字呈现）。"


def _polish_prompt_text(text: str) -> str:
    """Clean punctuation introduced by slot-level generated prose."""

    replacements = {
        "。，": "，",
        "。。": "。",
        "；。": "。",
        "，。": "。",
        "主题延续上,": "主题延续上，",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.strip()


def _soften_anchor_terms(terms: list[str]) -> list[str]:
    """Remove anchor hints that tend to overproduce armor/stitch/chrome detail."""

    blocked = {
        "stitched_leather",
        "mirror_chrome",
        "metal_family",
        "metallic_trim",
        "glossy_metal",
        "leather_wrap",
    }
    replacements = {
        "hard_soft_contrast": "soft_matte_contrast",
        "gloss_vs_matte": "soft_matte_contrast",
    }
    softened: list[str] = []
    for term in terms:
        key = str(term).strip()
        if not key or key in blocked:
            continue
        softened.append(replacements.get(key, key))
    return _unique(softened)


def _soften_material_terms(materials: list[str]) -> list[str]:
    """Keep material intent, but reduce AI-ish chrome/stitch/armor triggers."""

    replacements = {
        "镜面铬金属": "低反射深灰硬漆",
        "拉丝铝金属": "低反射阳极氧化漆面",
        "拉丝古金属": "哑光古金薄饰边",
        "做旧黄铜": "哑光古铜薄饰边",
        "缝纫皮革": "哑光软皮包覆",
        "细腻缝纫皮革": "哑光软皮包覆",
        "雾面缝纫皮革": "雾面软皮包覆",
        "黑色丝绒包覆件": "黑色丝绒触感包覆",
    }
    softened: list[str] = []
    for material in materials:
        text = str(material).strip()
        if not text:
            continue
        for src, dst in replacements.items():
            text = text.replace(src, dst)
        softened.append(text)
    return _unique(softened)


def _soften_handle_phrase(text: str) -> str:
    """Tone down stitch/metal/strap language from vision-derived handle copy."""

    replacements = {
        "缝纫皮革": "哑光软皮",
        "缝线皮革": "哑光软皮",
        "细缝线": "细浅压纹",
        "缝线": "浅压纹",
        "车缝": "浅压纹",
        "镜面金属饰边": "低反射薄饰边",
        "金属折片纹带": "浅浮雕折片纹带",
        "金属护片": "低反射小护片",
        "银色护片": "低反射银灰小护片",
        "粗金属": "粗硬",
        "绑带": "柔和包覆带",
        "护具": "圆润护片",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


# ---------------------------------------------------------------------------
# Remaining helpers (symbol extraction moved to host_brief.py).
# ---------------------------------------------------------------------------


def _discarded(values: list[str], retained: list[str]) -> list[str]:
    retained_text = " ".join(retained).lower()
    return [
        value
        for value in values
        if value
        and value.lower() not in retained_text
        and not any(item.lower() in value.lower() for item in retained)
    ][:8]


def _clean_text(value: str) -> str:
    allowed_punctuation = {" ", "-", "_", ".", "'", "&"}
    chars = []
    for char in value:
        category = unicodedata.category(char)
        if category[0] in {"L", "N"} or char in allowed_punctuation:
            chars.append(char)
    return " ".join("".join(chars).split()) or "Creator"


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen = set()
    for value in values:
        clean = str(value).strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        output.append(clean)
        seen.add(key)
    return output
