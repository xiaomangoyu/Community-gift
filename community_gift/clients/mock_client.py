from __future__ import annotations

from ..models import EffectMatch, GiftDesign, HostInput, ImageEvaluation, VisualAnalysis


class MockGiftClient:
    def analyze_image(self, host: HostInput) -> VisualAnalysis:
        cues = []
        if host.host_image:
            cues.append("参考图存在，真实模式会提炼帽子、服装色、配饰等非人脸线索")
        return VisualAnalysis(
            usable_non_face_cues=cues,
            image_style_notes=["mock mode: no real VLM call"],
            avoid_copying=["no human face", "no portrait", "no realistic identity"],
        )

    def create_design(
        self,
        host: HostInput,
        visual: VisualAnalysis,
        effect_context: list[dict] | None = None,
    ) -> GiftDesign:
        symbols = host.symbols[:3] or visual.usable_non_face_cues[:3] or ["community emblem"]
        community = host.primary_text or host.community_name or "Community"
        host_name = host.host_name or "Host"
        primary = host.primary_color or "signature accent color"
        secondary = host.secondary_color or "deep premium base color"
        keywords = [
            item
            for item in [
                host.body_form or host.content_type,
                host.live_vibe,
                host.personality,
                host.decoration_intensity,
                "simple",
                "premium physical gift",
            ]
            if item
        ]

        form = _choose_form(host)
        material = _material_language(host)
        secondary_text = f"secondary text '{host.secondary_text}', " if host.secondary_text else ""
        prompt = (
            f"Premium physical TikTok live community gift asset, {form}, "
            f"center text '{community}', small signature '{host_name}', "
            f"{secondary_text}"
            f"simple abstract symbols: {', '.join(symbols)}, "
            f"color palette: {primary} with {secondary}, "
            "luxury collectible object, clean centered composition, "
            f"materials: {', '.join(material)}, restrained glow, studio product render, "
            "small-size readable, no human face, no portrait, no poster, no busy background"
        )
        if effect_context:
            effect_names = ", ".join(effect["name"] for effect in effect_context)
            core_effects = ", ".join(
                item
                for effect in effect_context
                for item in effect.get("core_effect", [])[:3]
            )
            prompt += f", guided by distilled ideal effect rules: {effect_names}, {core_effects}"
        negative = (
            "human face, portrait, realistic person, poster, esports poster, clutter, "
            "too many icons, excessive glow, slogan overload, low quality, blurry text"
        )

        return GiftDesign(
            row_id=host.row_id,
            host_name=host_name,
            community_name=community,
            matched_effects=[
                EffectMatch(
                    effect_id=effect["id"],
                    effect_name=effect["name"],
                    confidence=0.5,
                    reason="mock mode carried matched ideal-effect rules into design metadata",
                )
                for effect in (effect_context or [])
            ],
            core_keywords=keywords,
            required_elements=[
                item
                for item in [community, host_name, *symbols]
                if item
            ],
            abstract_methods=[
                f"Turn {symbol} into a small embossed or acrylic emblem"
                for symbol in symbols
            ],
            recommended_gift_form=form,
            material_language=material,
            color_plan=f"{primary} as the luminous accent, {secondary} as the premium base.",
            composition="Centered product object with one dominant community name and 2-3 small abstract emblems.",
            complexity_rules=[
                "simple composition",
                "2-4 core elements only",
                "no human face",
                "readable at live-room gift size",
            ],
            negative_constraints=host.banned_elements
            + ["human face", "portrait", "poster layout", "overly complex decoration"],
            seedance_prompt=prompt,
            seedance_negative_prompt=negative,
        )

    def evaluate_candidate_image(
        self,
        image_path: str,
        design: GiftDesign,
        effect_context: list[dict],
    ) -> ImageEvaluation:
        return ImageEvaluation(
            image_path=image_path,
            total_score=75,
            passed=True,
            scores={
                "ideal_similarity": 75,
                "physical_gift_feel": 80,
                "small_size_readability": 70,
            },
            verdict="mock evaluation: candidate would be compared against ideal references in real mode",
            strengths=["physical gift framing", "simple central subject"],
            issues=[],
            prompt_revision_notes=[],
        )


def _choose_form(host: HostInput) -> str:
    if host.body_form:
        return f"premium lightstick based on {host.body_form}"
    if host.recommended_output_type:
        return f"premium {host.recommended_output_type} collectible"
    text = " ".join(
        [
            host.content_type,
            host.live_vibe,
            host.personality,
            host.notes,
        ]
    ).lower()
    if any(word in text for word in ["battle", "胜利", "高能", "pk", "冲榜"]):
        return "luxury support baton with a glowing emblem"
    if any(word in text for word in ["唱歌", "music", "音乐", "dance", "舞蹈"]):
        return "premium music wand collectible"
    if any(word in text for word in ["温柔", "陪伴", "治愈", "甜"]):
        return "glowing acrylic charm display"
    return "premium collectible light emblem"


def _material_language(host: HostInput) -> list[str]:
    if host.material_language_hint:
        return _split_list(host.material_language_hint)
    return [
        "brushed metal frame",
        "glowing acrylic core",
        "glass light tube",
        "subtle enamel details",
    ]


def _split_list(value: str) -> list[str]:
    separators = ["/", "、", "，", ",", ";", "；", "|"]
    normalized = value
    for separator in separators:
        normalized = normalized.replace(separator, ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]
