from __future__ import annotations

from ..models import GiftDesign, ImageEvaluation


class MockGiftClient:
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
