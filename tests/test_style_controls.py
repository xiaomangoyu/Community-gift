from __future__ import annotations

import os
import unittest

from community_gift.host_brief import build_host_brief, derive_retrieval_intent
from community_gift.models import HostInput
from community_gift.template_first import _style_control_prompt_clause


class StyleControlsTest(unittest.TestCase):
    def test_eagle_battle_context_gets_wild_shape_boosts(self) -> None:
        host = HostInput(
            row_id=1,
            host_name="Zahira",
            symbols=["🦅", "Team Zahira", "🏴‍☠️", "Enigma"],
            raw={
                "evidence_signals": [
                    "recurring_mascot_or_pet",
                    "community_name_distinct_from_host",
                    "logo_style_community_stickers",
                ],
                "missing_evidence": ["no_distinct_color_system"],
                "characterization": "High-energy TikTok LIVE battles, intense focused boss persona.",
            },
        )

        brief = build_host_brief(host)
        intent = derive_retrieval_intent(brief)

        self.assertEqual(brief.style_controls.wildness_score, 3)
        self.assertGreaterEqual(brief.style_controls.effective_creativity, 2)
        self.assertIn("eagle", intent.shape_anchors)
        self.assertIn("wing", intent.shape_anchors)
        self.assertIn("protective", intent.vibe_anchors)
        self.assertTrue(any("eagle" in reason for reason in brief.style_controls.reasons))

    def test_fragrance_object_context_is_creative_not_wild(self) -> None:
        host = HostInput(
            row_id=2,
            host_name="B DUFFY404",
            symbols=["Parfum Familia", "B.DUFFY", "The Oversprayer"],
            raw={
                "evidence_signals": [
                    "community_name_distinct_from_host",
                    "recurring_object_or_prop",
                    "repeated_fan_ritual",
                ],
                "missing_evidence": [
                    "fan_club_name_textual_only_no_visuals",
                    "no_recurring_mascot_or_object",
                ],
                "characterization": "Stylish fragrance influencer reviewing perfume and cologne dupes.",
            },
        )

        brief = build_host_brief(host)

        self.assertEqual(brief.style_controls.wildness_score, 0)
        self.assertGreaterEqual(brief.style_controls.creativity_score, 1)
        self.assertIn("perfume_bottle", brief.style_controls.shape_boosts)

    def test_style_aggression_env_raises_effective_creativity_only(self) -> None:
        old = os.environ.get("STYLE_AGGRESSION")
        os.environ["STYLE_AGGRESSION"] = "1"
        try:
            host = HostInput(
                row_id=3,
                host_name="Object Host",
                symbols=["perfume bottle"],
                raw={"evidence_signals": ["recurring_object_or_prop"]},
            )
            brief = build_host_brief(host)
        finally:
            if old is None:
                os.environ.pop("STYLE_AGGRESSION", None)
            else:
                os.environ["STYLE_AGGRESSION"] = old

        self.assertEqual(brief.style_controls.aggression_delta, 1)
        self.assertGreaterEqual(
            brief.style_controls.effective_creativity,
            brief.style_controls.creativity_score,
        )

    def test_prompt_clause_keeps_wildness_soft_bounded(self) -> None:
        clause = _style_control_prompt_clause(
            {
                "wildness_score": 3,
                "effective_creativity": 3,
            }
        )

        self.assertIn("大胆异形灯头轮廓", clause)
        self.assertIn("圆钝羽翼弧片", clause)
        self.assertIn("不要做尖锐武器", clause)


if __name__ == "__main__":
    unittest.main()
