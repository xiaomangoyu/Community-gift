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
    slots, color_decision, shape_decision, reference_decision = _extract_slots(brief, intent)

    text_plan = TextRenderPlan(
        mode="one_shot_text",
        exact_text=slots["display_text"],
        sanitized_text=slots["display_text"],
        reason="template-first mode requires the streamer name inside the lamp-head shape",
        max_lines=2 if len(slots["display_text"].replace(" ", "")) > 10 else 1,
        nameplate_instruction="exact streamer name inside the central lamp-head nameplate",
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
    "any human figure. Use as colour/mood anchor only."
)


def _include_host_avatar_reference() -> bool:
    return os.getenv("INCLUDE_HOST_AVATAR_REFERENCE", "true").lower() not in {
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


def _extract_slots(brief: HostBrief, intent: RetrievalIntent):
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

    banned = _unique(
        [
            "human face",
            "portrait",
            "white product card",
            "split-screen layout",
            "detail inset panels",
            "macro close-up",
            "pure black product body",
            "black handle",
            "flat sticker",
            "poster",
            "badge-only composition",
            "extra slogans or unrelated text",
            *color_fields.get("negative_add", []),
        ]
    )
    display_text = _clean_text(brief.host_name or "Creator")

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
        parts.append(f"主题延续上,{handle.decoration_continuation}")
    if len(parts) < 2:
        return ""
    return "。".join(parts) + "。"


def _format_symbol_forms(forms) -> str:
    """Join a SymbolForms object into one Chinese phrase. Empty if too sparse."""

    if not forms or not forms.symbol or not forms.forms:
        return ""
    position = forms.position or "灯头主体"
    return f"将「{forms.symbol}」解构为{position}的{'、'.join(forms.forms)}"


def _build_prompt(slots: dict) -> str:
    """Reference-driven skeleton.

    The 10-section structure mirrors the validated reference prompts in
    references/imgs/*.txt (45° hero shot, solid one-piece heart, embedded
    glowing text, "clean commercial poster-grade render"). Routing fills
    slots; manifest fragments fill the rest.
    """

    colors = "、".join(slots["colors"])
    materials = "、".join(slots["materials"])
    anchor_line = _format_anchor_line(slots.get("intent_anchor_terms") or [])
    lighting_phrase = (
        slots.get("lighting") or "清晰主光、边缘轮廓光、晶体折射、软硬高光对比、局部内发光"
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
        or f"以「{slots['primary_symbol']}」为核心的一体化立体灯头"
    )
    handle_phrase = slots.get("handle_phrase") or (
        f"握柄主体延续主题材质,与灯头形成同语义的视觉一体化,避免出现纯白通用塑料管造型。"
    )

    return f"""**构图与朝向(硬约束)**：纯黑棚拍背景，1:1 正方形画面。整支应援棒呈固定 45° 倾斜，**灯头在画面右上方、握柄从右上向左下延伸**(整支产品沿画面对角线方向)，灯头中心位于画面右上 40% 区域，底盖位于画面左下 35% 区域。**整支应援棒高度占画面 70-80%，顶端与底端各保留约 10% 黑色边距，左右各保留约 12-15% 黑色边距**。灯头、连接件、完整握柄、底部节点都必须完整可见，不允许任何部分触碰或超出画面边缘。

**比例硬约束**：灯头是绝对视觉重心，灯头高度占整支应援棒高度的 **55-65%**；握柄(含连接件 + 底盖)占 **35-45%**，握柄长度始终短于灯头高度，**绝对不允许握柄长于灯头**。握柄整体是短粗的偶像周边握把(可一手握持)，不是长细的法杖/魔杖/剑柄/旗杆。整体读感为"圆润饱满的收藏级周边",**不是武器、不是兵器、不是细长冲击感的造型**。

**一体成型 / 流线型硬约束**：整支应援棒是**一体连续的流线型有机造型**，灯头→连接处→握柄→底盖之间由**柔和的曲面收束**自然过渡，**禁止分段拼装感**。**严禁**:战术电筒筒身、橡胶按钮、缠绕凹槽、螺纹滚花、可见接缝、粗壮金属箍环、机械拼接件、工业组件感。允许的过渡是细腻的一圈装饰边或柔和的颈部收束(像吹制玻璃的腰身)，而不是切割明显的金属环。优先**圆润/有机/吹塑/连续曲面**的几何语言，而不是棱角分明的多边形拼接。**灯头轮廓为{lamp_head_silhouette}**，整体为完整饱满的实体结构，无外框、无镂空、无中空轮廓，中央嵌入发光文字「{slots['display_text']}」。

整体风格围绕「{slots['primary_symbol']}」延展，设定为{slots['theme_title']}，整体气质偏{slots['mood']}。{anchor_line}

整体配色采用 {colors}（主色锚点「{slots['color_anchor']}」，来自 {slots['palette_name']}）。背景为纯黑棚拍质感，产品本体、手柄、外壳和大面积装饰不能是纯黑；如主题需要黑色，只用烟灰、枪灰、银灰、珠光灰或深色透明树脂表达，保留清楚的灰色、银色或彩色边缘高光，方便从黑底抠图。

灯头材质以 {materials} 为主，整体强调圆润、清透、精致、收藏级3D产品质感。打光强调{lighting_phrase}，重点表现真实材质厚度、清晰倒角与软硬高光对比。

主题解构：{slots['symbol_translation']}{secondary_clause}。{fusion_clause}灯头本体为完整封闭的一体化实体，不使用外框骨架，不使用心形外框结构，不使用中空轮廓，不出现悬空骨架感。

让整个灯头像一个被「{slots['primary_symbol']}」包裹塑造的收藏级实体圣物，既有偶像应援感，也有独特的个人辨识度。整体轮廓语言强调{slots['silhouette_language']}，而不是平面logo、贴纸、徽章、展示牌、魔法杖或手电筒。

文字「{slots['display_text']}」自然嵌入灯头中央实体核心。{slots['text_style']}。只允许出现这一个主文字，不要出现伪字母、错字、额外口号、副标题、手柄文字、外接文字牌、顶部文字牌或悬浮标题。

手柄设计：{handle_phrase}手柄保持**短粗握把比例(高度约为灯头高度的 60-75%，宽度饱满)**，不能是通用细长白色塑料管造型，也不能是细长法杖造型。底部装饰为{slots['bottom_node']}，与手柄整体协调。

整体气质：{slots['mood']}，带有偶像周边收藏感。

整体强调：收藏级产品渲染、强3D体积感、丰富明暗层次、文字与中央核心局部发光、整支棒体不做全局霓虹泛光、干净商业海报感。整支打call棒必须完整入画，灯头、连接件、完整手柄和底部节点都要可见，产品像悬浮在纯黑摄影棚中，不接触任何地面或台面。"""


def _build_negative_prompt(slots: dict) -> str:
    """Reference-aligned negatives.

    Key shift from the previous skeleton:
      - We no longer list `poster` (the new template requests
        '干净商业海报感' meaning poster-grade render quality). Instead we
        ban specific bad layouts: `marketing poster layout`,
        `multi-product collage`.
      - We no longer ban `empty center` / `hollow center` — the new
        template explicitly asks for a solid one-piece heart core.
    """

    base = [
        "human face",
        "portrait",
        "person",
        "white background",
        "gray background",
        "white floor",
        "white tabletop",
        "white product card",
        "white rounded rectangle panel",
        "white card behind product",
        "rounded black panel on white background",
        "rectangular background panel",
        "display board",
        "presentation board",
        "split-screen layout",
        "multi-product collage",
        "detail inset panels",
        "product catalog page",
        "infographic",
        "instruction diagram",
        "callout labels",
        "annotation arrows",
        "leader lines",
        "dimension lines",
        "Chinese explanatory text",
        "side notes",
        "captions",
        "marketing poster layout",
        "billboard advertisement",
        "flat sticker",
        "badge only",
        "logo only",
        "heart-shaped outer frame",
        "open heart frame",
        "hollow heart outline",
        "outer skeleton frame",
        "wireframe heart",
        "close-up",
        "macro shot",
        "zoomed-in head",
        "head-only close-up",
        # Framing / cropping negatives — strengthened to catch 08/02-style cuts.
        "extreme diagonal crop",
        "cropped handle",
        "cropped lamp head",
        "cropped bottom cap",
        "missing handle",
        "missing bottom cap",
        "subject touches frame edge",
        "subject extends past frame",
        "tight crop with no margin",
        "off-center composition",
        # Orientation negatives — lock 45 degree right-up.
        "wrong orientation",
        "front-facing product",
        "head-on view",
        "horizontal product layout",
        "lamp head pointing left",
        "lamp head pointing down",
        "handle on the right side",
        "vertical product layout",
        "pure black product body",
        "black handle",
        "fake letters",
        "misspelled streamer name",
        "wrong name",
        "extra unrelated text",
        "handle text",
        "text above the lamp head",
        "external nameplate",
        "top nameplate",
        "floating text banner",
        "extra slogans",
        "detached props",
        "too many symbols",
        "weapon-like",
        "sword-like silhouette",
        "staff-like silhouette",
        "wand proportions",
        "scepter proportions",
        "flagpole proportions",
        "long thin shaft",
        "handle longer than lamp head",
        "handle taller than lamp head",
        "elongated shaft handle",
        "spear proportions",
        "aggressive weapon shape",
        "pointed weapon tip",
        # Anti-segmented / anti-tool look — push toward one-piece streamlined.
        "tactical flashlight body",
        "police flashlight",
        "industrial torch",
        "knurled grip",
        "ribbed cylindrical handle",
        "rubber grip ring",
        "tactical grip texture",
        "screw thread",
        "twist-cap",
        "visible mechanical seam",
        "thick metal collar ring",
        "metal sleeve joint",
        "segmented cylindrical body",
        "discrete cylinder sections",
        "assembled tool look",
        "button on handle",
        "switch button on body",
        "machined component",
        "industrial component assembly",
        "sharp polygonal facets",
        "angular faceted body",
    ]
    avoid_scripts = slots.get("intent_avoid_text_scripts") or []
    script_negatives = _negatives_from_avoid_scripts(avoid_scripts)
    return ", ".join(_unique(base + slots["banned"] + script_negatives))


_SCRIPT_NEGATIVE_TERMS: dict[str, list[str]] = {
    "korean": ["Korean glyphs", "Hangul characters", "Korean text"],
    "arabic": ["Arabic glyphs", "Arabic script", "right-to-left text"],
    "chinese": ["Chinese characters", "CJK glyphs", "kanji"],
    "japanese": ["Japanese glyphs", "kana", "katakana"],
    "cyrillic": ["Cyrillic characters", "Russian text"],
    "thai": ["Thai script"],
    "devanagari": ["Devanagari script", "Hindi text"],
}


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
