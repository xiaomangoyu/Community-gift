from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HostInput(BaseModel):
    row_id: int
    host_name: str = ""
    anchor_id: str = ""
    test_status: str = ""
    host_image: str = ""
    community_name: str = ""
    content_type: str = ""
    live_vibe: str = ""
    personality: str = ""
    primary_color: str = ""
    secondary_color: str = ""
    symbols: list[str] = Field(default_factory=list)
    banned_elements: list[str] = Field(default_factory=list)
    design_confidence: str = ""
    recommended_output_type: str = ""
    body_form: str = ""
    primary_text: str = ""
    secondary_text: str = ""
    material_language_hint: str = ""
    decoration_intensity: str = ""
    mapping_reason: str = ""
    notes: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class IdealEffect(BaseModel):
    id: str
    name: str
    status: str = "draft"
    source_prompt: str = ""
    source_prompt_summary: str = ""
    reference_images: list[str] = Field(default_factory=list)
    negative_reference_images: list[str] = Field(default_factory=list)
    best_for: list[str] = Field(default_factory=list)
    not_for: list[str] = Field(default_factory=list)
    gift_forms: list[str] = Field(default_factory=list)
    core_effect: list[str] = Field(default_factory=list)
    composition_rules: list[str] = Field(default_factory=list)
    material_rules: list[str] = Field(default_factory=list)
    lighting_rules: list[str] = Field(default_factory=list)
    prompt_principles: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    evaluation_focus: dict[str, int] = Field(default_factory=dict)
    notes: str = ""


class EffectMatch(BaseModel):
    effect_id: str
    effect_name: str
    confidence: float = 0
    reason: str = ""
    matched_terms: list[str] = Field(default_factory=list)


class ImageEvaluation(BaseModel):
    image_path: str
    total_score: float = 0
    passed: bool = False
    scores: dict[str, float] = Field(default_factory=dict)
    verdict: str = ""
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    prompt_revision_notes: list[str] = Field(default_factory=list)
    failure_types: list[str] = Field(default_factory=list)


class DesignConcept(BaseModel):
    """Small design-decision layer between raw fields and image prompting."""

    main_proposition: str = ""
    primary_symbol: str = ""
    supporting_mood: str = ""
    silhouette: str = ""
    retained_elements: list[str] = Field(default_factory=list)
    discarded_elements: list[str] = Field(default_factory=list)
    abstraction_notes: list[str] = Field(default_factory=list)
    complexity_level: str = "medium"
    effect_type: str = "lightstick"


class TextRenderPlan(BaseModel):
    mode: str = "one_shot_text"
    exact_text: str = ""
    sanitized_text: str = ""
    reason: str = ""
    max_lines: int = 1
    nameplate_instruction: str = ""


class PromptPlan(BaseModel):
    effect_id: str = ""
    camera_contract: list[str] = Field(default_factory=list)
    product_contract: list[str] = Field(default_factory=list)
    material_terms: list[str] = Field(default_factory=list)
    color_terms: list[str] = Field(default_factory=list)
    retained_elements: list[str] = Field(default_factory=list)
    banned_elements: list[str] = Field(default_factory=list)
    retry_focus: list[str] = Field(default_factory=list)


class GiftDesign(BaseModel):
    row_id: int
    host_name: str
    community_name: str
    matched_effects: list[EffectMatch] = Field(default_factory=list)
    design_concept: DesignConcept = Field(default_factory=DesignConcept)
    text_plan: TextRenderPlan = Field(default_factory=TextRenderPlan)
    prompt_plan: PromptPlan = Field(default_factory=PromptPlan)
    core_keywords: list[str]
    required_elements: list[str]
    abstract_methods: list[str]
    recommended_gift_form: str
    material_language: list[str]
    color_plan: str
    composition: str
    complexity_rules: list[str]
    negative_constraints: list[str]
    seedance_prompt: str
    seedance_negative_prompt: str
    # Per-row routing decisions (color / shape / ...), used for trace logs.
    # Not part of any stable consumer contract — workflow writes it to routing_trace.json.
    routing_trace: dict[str, Any] = Field(default_factory=dict)
    # (image_path, role_description) tuples resolved from ReferenceRouter.
    # Sent verbatim to Seedream: each role lands in pre_llm_result.input{i}
    # in the same order as the image in binary_data.
    reference_pairs: list[tuple[str, str]] = Field(default_factory=list)


class GenerationResult(BaseModel):
    row_id: int
    host_name: str
    community_name: str
    prompt: str
    negative_prompt: str
    image_paths: list[str] = Field(default_factory=list)
    evaluations: list[ImageEvaluation] = Field(default_factory=list)
    best_image_path: str | None = None
    raw_response_path: str | None = None
