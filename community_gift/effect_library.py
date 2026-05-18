from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import EffectMatch, HostInput, IdealEffect


class EffectLibrary:
    """Structured ideal-effect library used for reasoning and evaluation.

    Raw winning prompts and reference images live in the library for traceability,
    but generation only receives distilled rules from each effect card.
    """

    def __init__(self, effects: list[IdealEffect], base_dir: Path) -> None:
        self.effects = effects
        self.base_dir = base_dir

    @classmethod
    def load(cls, path: Path | None) -> "EffectLibrary | None":
        if path is None or not path.exists():
            return None

        raw = json.loads(path.read_text(encoding="utf-8"))
        records = raw.get("effects", raw) if isinstance(raw, dict) else raw
        effects = [IdealEffect.model_validate(record) for record in records]
        return cls(effects=effects, base_dir=path.parent)

    def match(self, host: HostInput, limit: int = 3) -> list[EffectMatch]:
        if not self.effects:
            return []

        host_text = self._host_text(host)
        ranked: list[tuple[float, EffectMatch]] = []
        for effect in self.effects:
            positive_terms = self._terms_for(effect)
            negative_terms = [term.lower() for term in effect.not_for]
            matched_terms = [term for term in positive_terms if term and term in host_text]
            blocked_terms = [term for term in negative_terms if term and term in host_text]

            score = len(matched_terms) - (len(blocked_terms) * 2)
            if not matched_terms and effect.status == "approved" and self._wants_effect(host, effect):
                score += 0.2

            confidence = max(0.0, min(1.0, score / max(1, len(positive_terms[:8]))))
            reason = "Matched host/community terms: " + ", ".join(matched_terms)
            if not matched_terms:
                reason = "Fallback approved effect; no strong term match yet."
            if blocked_terms:
                reason += " Blocked terms present: " + ", ".join(blocked_terms)

            ranked.append(
                (
                    score,
                    EffectMatch(
                        effect_id=effect.id,
                        effect_name=effect.name,
                        confidence=confidence,
                        reason=reason,
                        matched_terms=matched_terms,
                    ),
                )
            )

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [match for score, match in ranked[:limit] if score >= 0]

    def selected_effects(self, matches: list[EffectMatch]) -> list[IdealEffect]:
        by_id = {effect.id: effect for effect in self.effects}
        return [by_id[match.effect_id] for match in matches if match.effect_id in by_id]

    def generation_context(self, matches: list[EffectMatch]) -> list[dict[str, Any]]:
        context: list[dict[str, Any]] = []
        for effect in self.selected_effects(matches):
            context.append(
                {
                    "id": effect.id,
                    "name": effect.name,
                    "best_for": effect.best_for,
                    "gift_forms": effect.gift_forms,
                    "core_effect": effect.core_effect,
                    "composition_rules": effect.composition_rules,
                    "material_rules": effect.material_rules,
                    "lighting_rules": effect.lighting_rules,
                    "prompt_principles": effect.prompt_principles,
                    "avoid": effect.avoid,
                    "evaluation_focus": effect.evaluation_focus,
                    "notes": effect.notes,
                }
            )
        return context

    def evaluation_context(self, matches: list[EffectMatch]) -> list[dict[str, Any]]:
        context: list[dict[str, Any]] = []
        for effect in self.selected_effects(matches):
            reference_images = [
                str((self.base_dir / image).resolve())
                if not image.startswith(("http://", "https://", "data:"))
                else image
                for image in effect.reference_images
            ]
            negative_reference_images = [
                str((self.base_dir / image).resolve())
                if not image.startswith(("http://", "https://", "data:"))
                else image
                for image in effect.negative_reference_images
            ]
            context.append(
                {
                    "id": effect.id,
                    "name": effect.name,
                    "source_prompt_summary": effect.source_prompt_summary,
                    "reference_images": reference_images,
                    "negative_reference_images": negative_reference_images,
                    "core_effect": effect.core_effect,
                    "composition_rules": effect.composition_rules,
                    "material_rules": effect.material_rules,
                    "lighting_rules": effect.lighting_rules,
                    "avoid": effect.avoid,
                    "evaluation_focus": effect.evaluation_focus,
                    "notes": effect.notes,
                }
            )
        return context

    def _terms_for(self, effect: IdealEffect) -> list[str]:
        terms: list[str] = []
        for values in [
            effect.best_for,
            effect.gift_forms,
            effect.core_effect,
            effect.material_rules,
            effect.lighting_rules,
        ]:
            terms.extend(term.lower() for term in values)
        return terms

    def _host_text(self, host: HostInput) -> str:
        values = [
            host.host_name,
            host.community_name,
            host.content_type,
            host.live_vibe,
            host.personality,
            host.primary_color,
            host.secondary_color,
            host.recommended_output_type,
            host.body_form,
            host.notes,
            *host.symbols,
        ]
        return " ".join(value.lower() for value in values if value)

    def _wants_effect(self, host: HostInput, effect: IdealEffect) -> bool:
        host_text = self._host_text(host)
        gift_text = " ".join(effect.gift_forms + effect.best_for).lower()
        lightstick_terms = ["light_stick", "lightstick", "应援棒", "打call", "baton"]
        return any(term in host_text for term in lightstick_terms) and any(
            term in gift_text for term in ["应援棒", "lightstick", "打call", "baton"]
        )
