"""Template-first design path.

Builds a stable Seedream prompt from a fixed skeleton plus a few host slots.
Per-dimension decisions (color / shape) are delegated to routers in
community_gift/routing/. The skeleton itself stays in this file as a single
f-string so it is easy to diff visually.
"""

from __future__ import annotations

import os
import re
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
            _style_control_summary(slots.get("style_controls") or {}),
        ],
        complexity_level=_style_complexity_level(slots.get("style_controls") or {}),
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
            _style_control_summary(slots.get("style_controls") or {}),
        ],
        negative_constraints=slots["banned"],
        seedance_prompt=prompt,
        seedance_negative_prompt=negative_prompt,
        reference_pairs=_assemble_reference_pairs(host, reference_decision, slots),
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
            "style_controls": slots.get("style_controls") or {},
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


def _assemble_reference_pairs(
    host: HostInput,
    reference_decision,
    slots: dict | None = None,
) -> list[tuple[str, str]]:
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
            role = pick.get("role_description", "")
            if slots and slots.get("avoid_mirror_finish") and _is_hard_reflective_reference_role(role):
                continue
            pairs.append((image_path, _soften_reference_role(role)))
    return pairs


def _is_hard_reflective_reference_role(role: str) -> bool:
    text = str(role or "").lower()
    return any(
        token in text
        for token in (
            "glossy",
            "crystal",
            "chrome",
            "metal",
            "mirror",
            "glass",
            "polished",
            "strong glow",
        )
    )


def _soften_reference_role(role: str) -> str:
    text = str(role or "").strip()
    if not text:
        return ""
    softened = text
    replacements = {
        "glossy": "satin",
        "polished": "smooth satin",
        "crystal": "soft luminous",
        "chrome": "low-reflection trim",
        "metal": "low-reflection trim",
        "mirror": "matte",
        "strong purple glow": "controlled purple glow",
        "strong glow": "controlled glow",
    }
    for src, dst in replacements.items():
        softened = re.sub(src, dst, softened, flags=re.IGNORECASE)
    if softened != text:
        return (
            softened
            + " Use this reference only for full-product orientation, proportion, and readable central text placement; "
            "adapt the generated product with soft-touch matte/satin surfaces, broad gentle highlights, "
            "and low-reflection material handling."
        )
    return softened


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
    raw = host.raw if isinstance(host.raw, dict) else {}

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
    style_controls = (
        intent.style_controls.model_dump()
        if getattr(intent, "style_controls", None) is not None
        else brief.style_controls.model_dump()
    )

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
        "style_controls": style_controls,
        "design_directives": {
            "palette_direction": list(raw.get("palette_direction") or []),
            "material_direction": list(raw.get("material_direction") or []),
            "mood_coverage": list(raw.get("mood_coverage") or []),
            "form_exploration": list(raw.get("form_exploration") or []),
            "evidence_signals": list(raw.get("evidence_signals") or raw.get("primary_signals") or []),
            "primary_signals": list(raw.get("evidence_signals") or raw.get("primary_signals") or []),
            "characterization": raw.get("characterization", ""),
        },
        "banned": banned,
        "discarded": _discarded(brief.symbols_raw, [primary_symbol, secondary_symbol]),
    }
    if brief.vision is not None:
        _apply_vision_overrides(slots, brief.vision)
    _soften_reflective_slots(slots)
    slots["materials"] = _finalize_material_terms(slots)
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
        slots["text_style"] = _sanitize_text_style(vision.text.style_hint)

    if vision.style_pitch:
        slots["theme_title"] = _compact_style_pitch(
            vision.style_pitch,
            display_text=slots.get("display_text", ""),
        )
    if vision.mood.phrase:
        slots["mood"] = _sanitize_text_label_language(vision.mood.phrase)
    if vision.silhouette_language:
        slots["silhouette_language"] = vision.silhouette_language
    if vision.lighting:
        slots["lighting"] = vision.lighting
    # Do not pass raw VLM fusion_note into the final prompt. It tends to be
    # prose-heavy and repeats the Chinese theme word near text/core language.

    primary_prose = _format_symbol_forms(vision.theme_forms.primary)
    if primary_prose:
        primary_symbol = str(vision.theme_forms.primary.symbol or "").strip()
        if primary_symbol:
            primary_prose = primary_prose.replace(f"将{primary_symbol}解构为", "主体符号解构为")
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
    # theme references use the visual concept
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
        connector = str(handle.connector_detail).strip()
        if connector.startswith("连接处"):
            parts.append(connector)
        else:
            parts.append(f"连接处搭配{connector}")
    if handle.bottom_cap:
        parts.append(f"底盖设计为{handle.bottom_cap}")
    if handle.decoration_continuation:
        parts.append(f"主题延续上，{handle.decoration_continuation}")
    if len(parts) < 2:
        return ""
    return _sanitize_text_label_language("。".join(parts) + "。")


def _format_symbol_forms(forms) -> str:
    """Join a SymbolForms object into one Chinese phrase. Empty if too sparse."""

    if not forms or not forms.symbol or not forms.forms:
        return ""
    position = forms.position or "灯头主体"
    return f"将{forms.symbol}解构为{position}的{'、'.join(forms.forms)}"


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
    materials = "、".join(slots["materials"])
    lighting_phrase = "柔和棚拍主光、克制边缘描光、低反射材质对比、中央文字小范围内发光"
    reflective_clause = (
        "深色冷调主题也使用雾灰软胶厚框、柔雾珐琅名牌、烟灰软胶和宽柔高光，整体保持吸光、低亮、低反射。"
        if slots.get("avoid_mirror_finish")
        else ""
    )
    fusion_note = slots.get("fusion_note") or ""
    fusion_clause = f"{fusion_note}。" if fusion_note else ""
    secondary_clause = (
        f"；{slots['supporting_translation']}"
        if slots.get("supporting_translation")
        else ""
    )
    lamp_head_silhouette = (
        slots.get("lamp_head_silhouette")
        or f"以{slots['primary_symbol']}为核心的一体化立体灯头"
    )
    handle_phrase = slots.get("handle_phrase") or (
        "握柄主体延续主题材质，与灯头形成同语义的视觉一体化。"
    )
    handle_phrase = _sanitize_text_label_language(_soften_handle_phrase(handle_phrase))
    bottom_node = _sanitize_text_label_language(_soften_handle_phrase(slots["bottom_node"]))
    bottom_sentence = (
        f"{bottom_node}，与手柄整体协调。"
        if bottom_node.startswith(("底部", "底盖", "尾端", "底端"))
        else f"底部装饰为{bottom_node}，与手柄整体协调。"
    )
    script_guidance = _text_script_guidance(slots["display_text"])
    style_control_clause = _style_control_prompt_clause(slots.get("style_controls") or {})

    prompt = f"""黑色背景，1:1 正方形画面，固定 45 度朝右产品视角，完整展示整支打call棒，从灯头、连接处、握柄到底部节点全部清晰可见，主体居中，高精度3D收藏级应援棒。灯头是视觉重心，握柄短而完整，整体是一体连续的圆润产品造型。顶部为{lamp_head_silhouette}，中央为完整饱满的实体核心，中间嵌入发光文字「{slots['display_text']}」。

整体风格围绕{slots['primary_symbol']}主题延展，设定为{slots['theme_title']}，整体气质偏{slots['mood']}。
{style_control_clause}

整体配色采用{colors}（主色锚点为{slots['color_anchor']}，来自{slots['palette_name']}）。背景保持纯黑棚拍质感；如果主题需要深色，用烟灰、枪灰、珠光灰或深色透明树脂表达，让产品边缘和材质层次仍然清楚。

材质组合采用{materials}。大面积灯头外壳和握柄必须由软触感材质主导，强调可触摸的柔软表面、圆钝厚度、低反射质感和干净的收藏玩具完成度。硬质反光元素只作为文字核心、小徽章、极薄连接边或少量发光节点出现，不主导灯头和握柄外壳；皮革、织物或护具感元素转译为连续哑光包覆、浅压纹和干净表面。{reflective_clause}打光以{lighting_phrase}为主，重点表现真实厚度、柔和圆角、受控高光和表面触感。

主题为{slots['primary_symbol']}的解构设计：{slots['symbol_translation']}{secondary_clause}。{fusion_clause}所有外扩装饰、包边、护片或框架都与灯头主体一体成型，中央核心保持完整饱满，不做空心镂空，也不做贴纸式平面图案。

让整体灯头像一个被主题轮廓包裹塑造的收藏级应援圣物，既有偶像应援感，也有独特的个人辨识度。整体轮廓语言强调{slots['silhouette_language']}，从正面和侧面都能读出清楚的立体结构。

文字「{slots['display_text']}」自然嵌入灯头中央实体核心。{slots['text_style']}。{script_guidance}画面中只出现这一处主文字，文字与核心结构融合，不做外接文字牌。

手柄设计：{handle_phrase}手柄保持短而饱满的握把比例，与灯头自然连接，不做细长法杖感。{bottom_sentence}

整体气质：{slots['mood']}，带有偶像周边收藏感。

整体强调：收藏级实体产品渲染、强3D体积感、真实材质厚度、克制明暗层次、文字与中央核心局部发光、整支棒体不做全局霓虹泛光、干净棚拍产品感。整支打call棒完整入画，灯头、连接件、完整手柄和底部节点都清晰可见，产品像悬浮在纯黑摄影棚中。"""
    return _polish_prompt_text(_reserve_quotes_for_display_text(prompt, slots["display_text"]))


def _style_control_prompt_clause(style_controls: dict) -> str:
    """Translate numeric style controls into bounded visual direction."""

    if not style_controls:
        return ""
    wildness = _safe_int(style_controls.get("wildness_score"), 0)
    creativity = _safe_int(
        style_controls.get("effective_creativity", style_controls.get("creativity_score")),
        0,
    )
    parts: list[str] = []
    if creativity >= 3:
        parts.append(
            "创意强度为高：允许大胆异形灯头轮廓、更明确的主题包裹结构和不对称护片，但所有结构必须圆钝、一体成型、软材质主导。"
        )
    elif creativity >= 2:
        parts.append(
            "创意强度为中高：允许明显的非圆主题轮廓、包裹式护片、浅浮雕和主题压纹，仍保持完整可握的商品比例。"
        )
    elif creativity >= 1:
        parts.append(
            "创意强度为轻度：在默认圆润轮廓上加入少量主题外形差异和浮雕细节，不改变打call棒的清晰产品结构。"
        )

    if wildness >= 2:
        parts.append(
            "野性/守护信号转译为圆钝羽翼弧片、徽章护盾、爪痕浅压纹或上扬软胶护片；不要做尖锐武器、硬甲、真实动物头或机甲碎片。"
        )
    elif wildness == 1:
        parts.append(
            "轻微野性信号只作为边缘弧片、徽章轮廓或浅压纹出现，避免过度攻击性。"
        )
    return "\n".join(parts)


def _style_complexity_level(style_controls: dict) -> str:
    creativity = _safe_int(
        style_controls.get("effective_creativity", style_controls.get("creativity_score")),
        0,
    )
    if creativity >= 3:
        return "high"
    if creativity >= 2:
        return "medium"
    return "low"


def _style_control_summary(style_controls: dict) -> str:
    if not style_controls:
        return "style controls: wildness=0, creativity=0"
    wildness = _safe_int(style_controls.get("wildness_score"), 0)
    creativity = _safe_int(
        style_controls.get("effective_creativity", style_controls.get("creativity_score")),
        0,
    )
    return f"style controls: wildness={wildness}, creativity={creativity}"


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
        "mirror surface",
        "black mirror finish",
        "piano black gloss",
        "glossy black shell",
        "reflective black body",
        "hard specular streaks",
        "strong white reflection stripes",
        "chrome rim glow",
        "camera lens",
        "glossy lens",
        "lens reflection",
        "metal bezel",
        "silver metal ring",
        "mechanical ring",
        "tech gadget",
        "cheap glossy plastic",
        "heavy chrome metal",
        "large metal body",
        "large glass body",
        "hard crystal shell",
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
        "连接处搭配连接处": "连接处",
        "底部装饰为底部": "底部",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.strip()


def _compact_style_pitch(text: str, display_text: str = "") -> str:
    """Turn VLM prose into a short theme label before it reaches the prompt."""

    value = str(text or "").strip()
    if not value:
        return ""
    if display_text:
        value = value.replace(f"“{display_text}”", "").replace(f"「{display_text}」", "")
        value = value.replace(display_text, "")
    value = re.sub(r"围绕[，。]*延展为", "", value)
    value = re.sub(r"围绕.*?延展为", "", value)
    value = re.sub(r"整体围绕.*?延展为", "", value)
    value = value.split("，", 1)[0].split("。", 1)[0].strip(" ：:，。")
    value = _sanitize_text_label_language(value)
    if len(value) > 36:
        value = value[:36].rstrip("、× /")
    return value or "个性化收藏级应援风"


def _sanitize_text_style(text: str) -> str:
    value = str(text or "").strip()
    value = _sanitize_text_label_language(value)
    return value


def _sanitize_text_label_language(text: str) -> str:
    replacements = {
        "招牌感": "舞台灯光感",
        "招牌": "灯光",
        "标题牌": "立体字标",
        "标题": "字标",
        "灯牌感": "灯光感",
        "灯牌": "灯光",
        "铭牌": "内嵌字标",
        "牌匾": "立体字标",
        "标识": "字标",
        "logo": "字标",
        "wordmark": "字标",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def _reserve_quotes_for_display_text(text: str, display_text: str) -> str:
    """Keep quotes only around the exact render text, not Chinese theme labels."""

    display_text = (display_text or "").strip()
    placeholders: dict[str, str] = {}
    if display_text:
        for idx, wrapped in enumerate(
            [
                f"「{display_text}」",
                f"“{display_text}”",
                f'"{display_text}"',
                f"'{display_text}'",
            ]
        ):
            token = f"__DISPLAY_TEXT_QUOTE_{idx}__"
            if wrapped in text:
                placeholders[token] = wrapped
                text = text.replace(wrapped, token)

    text = re.sub(r"「([^」]*[\u4e00-\u9fff][^」]*)」", r"\1", text)
    text = re.sub(r"“([^”]*[\u4e00-\u9fff][^”]*)”", r"\1", text)
    text = re.sub(r'"([^"\n]*[\u4e00-\u9fff][^"\n]*)"', r"\1", text)
    text = re.sub(r"'([^'\n]*[\u4e00-\u9fff][^'\n]*)'", r"\1", text)

    for token, wrapped in placeholders.items():
        text = text.replace(token, wrapped)
    return text


_HARD_MATERIAL_TRIGGERS = (
    "玻璃",
    "水晶",
    "晶体",
    "金属",
    "铝",
    "铬",
    "黄铜",
    "钛",
    "钢",
    "镜面",
    "阳极氧化",
    "硬漆",
    "硬树脂",
)
_HARD_ACCENT_QUALIFIERS = (
    "小面积",
    "少量",
    "局部",
    "极薄",
    "微型",
    "小型",
    "点缀",
    "饰边",
    "包边",
    "核心",
    "连接点",
)
_SOFT_MATERIAL_CUES = (
    "软",
    "硅胶",
    "搪胶",
    "植绒",
    "毛绒",
    "短绒",
    "丝绒",
    "绒感",
    "布",
    "织",
    "泡棉",
    "棉",
    "毛毡",
    "橡胶",
    "珐琅",
    "果冻",
    "陶",
    "木",
    "哑光",
    "柔雾",
)
_REFLECTIVE_GLOSS_TRIGGERS = (
    "镜面",
    "镜像",
    "镜框",
    "镜芯",
    "镜子",
    "曜石黑",
    "墨黑",
    "冷黑",
    "亮黑",
    "漆黑",
    "mirror",
    "chrome",
    "glossy black",
    "black_silver",
    "mirror_noir",
)
_REFLECTIVE_SLOT_KEYS = (
    "primary_symbol",
    "secondary_symbol",
    "theme_title",
    "mood",
    "symbol_translation",
    "supporting_translation",
    "text_style",
    "bottom_node",
    "silhouette_language",
    "fusion_note",
    "lamp_head_silhouette",
    "handle_phrase",
    "element_anchor",
    "palette_name",
)
_REFLECTIVE_TEXT_REPLACEMENTS = {
    "黑银镜像": "烟灰雾灰",
    "黑银冷调": "烟灰雾灰冷调",
    "黑白冷调": "烟灰冷调",
    "黑银": "烟灰雾灰",
    "内凹镜面": "柔雾珐琅内芯",
    "内凹镜芯": "柔雾珐琅内芯",
    "真实镜面": "柔雾珐琅内芯",
    "镜面反射": "柔雾低亮层次",
    "镜面": "柔雾珐琅内芯",
    "镜像": "雾银",
    "镜心": "柔雾中心",
    "镜芯": "柔雾内芯",
    "竖椭镜框": "竖椭雾灰软胶厚框",
    "椭圆镜框": "椭圆雾灰软胶厚框",
    "镜框": "雾灰软胶厚框",
    "镜子相关": "椭圆软胶徽章相关",
    "镜子": "椭圆雾灰软徽章",
    "晶体镶嵌": "软发光嵌件",
    "一圈极薄银白饰边": "一圈冷灰软胶薄边",
    "极薄银白饰边": "冷灰软胶薄边",
    "银白饰边": "冷灰软胶薄边",
    "雾银": "雾灰",
    "银白": "冷白灰",
    "银灰": "冷灰",
    "断口圆环": "断口软胶弧片",
    "薄圈护沿": "浅浮雕弧片",
    "断环": "断口软胶弧片",
    "圆环": "软胶弧片",
    "饰边": "软胶薄边",
    "切面": "圆角",
    "曜石黑": "烟灰黑",
    "墨黑": "烟灰黑",
    "冷黑": "冷灰",
    "亮黑": "炭灰",
    "漆黑": "石墨灰",
    "纯黑": "烟灰",
    "mirror noir": "soft matte noir",
    "mirror": "matte oval badge",
    "chrome": "low-reflection trim",
    "glossy black": "matte graphite",
    "glossy": "soft satin",
}


def _soften_reflective_slots(slots: dict) -> None:
    """Turn mirror/noir cues into matte badge language before prompt assembly."""

    if not _has_reflective_gloss_context(slots):
        slots["avoid_mirror_finish"] = False
        return

    slots["avoid_mirror_finish"] = True
    for key in _REFLECTIVE_SLOT_KEYS:
        value = slots.get(key)
        if isinstance(value, str):
            slots[key] = _soften_reflective_text(value)
    slots["colors"] = _unique(
        [_soften_reflective_text(str(color)) for color in slots.get("colors") or []]
    )
    if slots.get("color_anchor"):
        slots["color_anchor"] = _soften_reflective_text(str(slots["color_anchor"]))
    if not slots.get("colors"):
        slots["colors"] = ["烟灰黑", "雾银灰", "冷白", "石墨灰"]
    if slots["colors"] and any(token in slots["colors"][0] for token in ("黑", "black")):
        slots["colors"][0] = _soften_reflective_text(slots["colors"][0])


def _has_reflective_gloss_context(slots: dict) -> bool:
    parts: list[str] = []
    for key in _REFLECTIVE_SLOT_KEYS:
        value = slots.get(key)
        if isinstance(value, str):
            parts.append(value)
    parts.extend(str(color) for color in slots.get("colors") or [])
    parts.append(str(slots.get("color_anchor") or ""))
    context = " ".join(parts).lower()
    return any(trigger in context for trigger in _REFLECTIVE_GLOSS_TRIGGERS)


def _soften_reflective_text(value: str) -> str:
    text = str(value or "")
    for src, dst in sorted(_REFLECTIVE_TEXT_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        text = text.replace(src, dst)
    return _cleanup_material_text(text)


def _finalize_material_terms(slots: dict) -> list[str]:
    """Make the final prompt material mix soft-led and visually varied.

    Vision can legitimately notice glass/metal/crystal, but those words become
    too dominant when they enter the final prompt as the main material. This
    final deterministic pass keeps hard materials only as small accents.
    """

    preferred = _preferred_soft_materials(_material_context_text(slots))
    source = _soften_material_terms(list(slots.get("materials") or []))
    out: list[str] = []

    for material in source:
        text = _demote_hard_material(material)
        if text:
            out.append(text)

    body_terms = [material for material in out if _is_body_soft_material(material)]
    accent_terms = [material for material in out if not _is_body_soft_material(material)]
    for material in preferred:
        if len(body_terms) >= 2:
            break
        body_terms.append(material)
    out = body_terms + accent_terms

    # Keep the material line focused: two soft/tactile leads plus at most two
    # accents read better than a long ingredient list.
    return _unique(out)[:4]


def _material_context_text(slots: dict) -> str:
    directives = slots.get("design_directives") or {}
    parts: list[str] = [
        slots.get("primary_symbol", ""),
        slots.get("secondary_symbol", ""),
        slots.get("theme_title", ""),
        slots.get("mood", ""),
        slots.get("silhouette_language", ""),
        " ".join(slots.get("intent_anchor_terms") or []),
    ]
    for key in (
        "material_direction",
        "mood_coverage",
        "form_exploration",
        "evidence_signals",
        "primary_signals",
    ):
        parts.extend(str(item) for item in directives.get(key) or [])
    parts.append(str(directives.get("characterization") or ""))
    return " ".join(part for part in parts if part).lower()


def _preferred_soft_materials(context: str) -> list[str]:
    pairs = [
        (
            (
                "毛绒",
                "plush",
                "pet",
                "cat",
                "rabbit",
                "bunny",
                "elephant",
                "alpaca",
                "penguin",
                "duck",
                "bird",
                "eagle",
                "frog",
                "animal",
                "宠物",
                "动物",
                "兔",
                "猫",
                "大象",
                "羊驼",
                "企鹅",
                "小鸭",
                "鸟",
                "鹰",
                "青蛙",
            ),
            ["短绒植绒", "亲肤硅胶"],
        ),
        (
            (
                "food",
                "fruit",
                "dessert",
                "potato",
                "melon",
                "lychee",
                "churro",
                "gummy",
                "candy",
                "甜",
                "水果",
                "食物",
                "糖",
                "软糖",
                "土豆",
                "蜜瓜",
                "荔枝",
                "吉拿",
                "甜点",
            ),
            ["雾面软搪胶", "柔软果冻树脂"],
        ),
        (
            ("sport", "basketball", "tennis", "bowling", "ball", "运动", "球"),
            ["哑光软胶", "短绒植绒"],
        ),
        (
            ("ghost", "sticker", "cloud", "soft", "healing", "cute", "治愈", "软萌", "贴纸", "幽灵", "云"),
            ["丝绒触感涂层", "亲肤硅胶"],
        ),
        (
            ("hat", "cap", "fabric", "textile", "帽", "布", "织物"),
            ["短绒布艺包覆", "柔雾珐琅"],
        ),
        (
            ("crown", "badge", "perfume", "globe", "police", "皇冠", "徽章", "香水"),
            ["珠光软搪胶", "柔雾珐琅"],
        ),
        (
            ("dark", "gothic", "black", "night", "夜", "黑", "暗"),
            ["哑光软搪胶", "丝绒触感涂层"],
        ),
    ]
    for triggers, materials in pairs:
        if any(trigger in context for trigger in triggers):
            return materials
    return ["哑光软搪胶", "柔雾珐琅"]


def _demote_hard_material(material: str) -> str:
    text = str(material or "").strip()
    if not text:
        return ""
    if not _is_dominant_hard_material(text):
        return text
    if any(token in text for token in ("黄铜", "金", "古铜")):
        return "极薄哑光古金饰边"
    if any(token in text for token in ("银", "铝", "铬", "钛", "钢", "金属", "阳极氧化")):
        return "极薄低反射银灰饰边"
    if any(token in text for token in ("玻璃", "水晶", "晶体")):
        return "小面积柔光透明树脂点缀"
    return "小面积低反射硬质点缀"


def _is_dominant_hard_material(material: str) -> bool:
    text = str(material or "")
    if not any(trigger in text for trigger in _HARD_MATERIAL_TRIGGERS):
        return False
    return not any(qualifier in text for qualifier in _HARD_ACCENT_QUALIFIERS)


def _has_soft_material_cue(material: str) -> bool:
    return any(cue in str(material or "") for cue in _SOFT_MATERIAL_CUES)


def _is_body_soft_material(material: str) -> bool:
    text = str(material or "")
    return _has_soft_material_cue(text) and not any(
        qualifier in text for qualifier in _HARD_ACCENT_QUALIFIERS
    )


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
        "吹制气泡玻璃": "小面积柔光透明树脂点缀",
        "磨砂玻璃": "小面积柔雾透明树脂点缀",
        "切面水晶": "小面积柔光透明树脂点缀",
        "透明水晶": "小面积柔光透明树脂点缀",
        "发光晶体核心": "小范围软发光核心",
        "冷白晶体核心": "小范围冷白软发光核心",
        "冷白晶体内芯": "小范围冷白软发光核心",
        "半透明晶体内芯": "小范围半透明软发光核心",
        "半透明果冻晶体内芯": "半透明柔雾果冻内芯",
        "半透明果冻晶体": "半透明柔雾果冻树脂",
        "透明晶体": "小面积柔光透明树脂点缀",
        "镜面铬金属": "极薄低反射深灰饰边",
        "拉丝铝金属": "极薄低反射银灰饰边",
        "阳极氧化黑铝": "低反射深灰软质饰边",
        "阳极氧化枪灰": "低反射枪灰软质饰边",
        "镜面银色细包边": "极薄低反射银灰饰边",
        "银灰金属护边": "低反射银灰软质护边",
        "金属皇冠细包边": "极薄低反射金色软质包边",
        "金属包边": "极薄低反射饰边",
        "拉丝古金属": "哑光古金薄饰边",
        "做旧黄铜": "哑光古铜薄饰边",
        "香槟金属包边": "极薄香槟色柔雾饰边",
        "香槟金细包边": "极薄香槟色柔雾饰边",
        "细腻缝纫皮革": "哑光软皮包覆",
        "雾面缝纫皮革": "雾面软皮包覆",
        "缝纫皮革": "哑光软皮包覆",
        "黑色丝绒包覆件": "黑色丝绒触感包覆",
    }
    softened: list[str] = []
    for material in materials:
        text = str(material).strip()
        if not text:
            continue
        for src, dst in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
            text = text.replace(src, dst)
        softened.append(_cleanup_material_text(text))
    return _unique(softened)


def _soften_handle_phrase(text: str) -> str:
    """Tone down stitch/metal/strap language from vision-derived handle copy."""

    replacements = {
        "吹制气泡玻璃": "柔光透明软树脂",
        "磨砂玻璃": "柔雾透明软树脂",
        "玻璃窗": "透明软树脂小窗",
        "玻璃腰身": "透明软树脂腰身",
        "透明晶体": "透明软树脂",
        "冷白晶体": "冷白软发光",
        "阳极氧化黑铝": "低反射深灰软胶",
        "阳极氧化枪灰": "低反射枪灰软胶",
        "镜面铬金属": "极薄低反射深灰饰边",
        "镜面金属饰边": "低反射薄饰边",
        "金属尾盖": "低反射圆润尾盖",
        "金属边": "低反射薄边",
        "金属曲面": "低反射哑光曲面",
        "黄铜装饰边": "哑光古金薄饰边",
        "黄铜包芯握柄": "哑光软胶包覆握柄",
        "缝纫皮革": "哑光软皮",
        "缝线皮革": "哑光软皮",
        "细缝线": "细浅压纹",
        "缝线": "浅压纹",
        "车缝": "浅压纹",
        "金属折片纹带": "浅浮雕折片纹带",
        "金属护片": "低反射小护片",
        "银色护片": "低反射银灰小护片",
        "粗金属": "粗硬",
        "绑带": "柔和包覆带",
        "护具": "圆润护片",
    }
    for src, dst in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        text = text.replace(src, dst)
    return _cleanup_material_text(text)


def _cleanup_material_text(text: str) -> str:
    """Collapse duplicated descriptors created by overlapping replacements."""

    cleaned = str(text or "")
    for token in ("哑光", "低反射", "柔雾", "极薄"):
        cleaned = cleaned.replace(token + token, token)
    return cleaned


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
