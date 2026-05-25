from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from community_gift.streamers_io import read_streamers
from community_gift.template_first import _build_prompt, _finalize_material_terms


class MaterialStrategyTest(unittest.TestCase):
    def test_demotes_hard_vision_materials_to_soft_led_mix(self) -> None:
        slots = {
            "primary_symbol": "兔子",
            "secondary_symbol": "星星",
            "theme_title": "梦幻软萌兔耳应援风",
            "mood": "可爱、治愈、软萌",
            "silhouette_language": "圆润、包裹、柔软",
            "intent_anchor_terms": ["animal", "soft"],
            "materials": ["吹制气泡玻璃", "阳极氧化黑铝"],
            "design_directives": {"material_direction": ["plush soft silicone"]},
        }

        materials = _finalize_material_terms(slots)

        self.assertIn("短绒植绒", materials)
        self.assertIn("亲肤硅胶", materials)
        self.assertNotIn("吹制气泡玻璃", materials)
        self.assertNotIn("阳极氧化黑铝", materials)
        self.assertTrue(any("小面积" in item or "极薄" in item for item in materials))

    def test_prompt_states_soft_materials_as_dominant(self) -> None:
        slots = {
            "colors": ["薰衣草紫", "奶油白", "冰蓝"],
            "materials": ["短绒植绒", "亲肤硅胶", "小面积柔光透明树脂点缀"],
            "fusion_note": "",
            "supporting_translation": "",
            "lamp_head_silhouette": "兔耳云朵灯头",
            "primary_symbol": "兔子",
            "display_text": "Bunny",
            "theme_title": "梦幻兔耳应援风",
            "mood": "可爱、治愈、软萌",
            "color_anchor": "薰衣草紫",
            "palette_name": "柔软梦幻系",
            "symbol_translation": "将兔耳解构为灯头上缘的长耳护片和云朵鼓包",
            "silhouette_language": "圆润、包裹、柔软",
            "text_style": "文字采用圆润立体发光字",
            "handle_phrase": "握柄主体使用亲肤硅胶，表面有浅星点压纹。",
            "bottom_node": "圆润兔尾软胶尾盖",
        }

        prompt = _build_prompt(slots)

        self.assertIn("软触感材质主导", prompt)
        self.assertIn("透明、玻璃、晶体或金属元素只作为", prompt)
        self.assertNotIn("材质以吹制气泡玻璃", prompt)


class StreamersDirectionParsingTest(unittest.TestCase):
    def test_reads_direction_sections_into_raw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "123_Test"
            folder.mkdir()
            (folder / "signals.md").write_text(
                """# Test Host

- **anchor_id**: 123
- **tier**: strong
- **fan_club**: Softies

## Top symbols
- `兔子` (comm)

## Primary signals
- `recurring_mascot_or_pet`

## Material direction
- soft plush silicone
- `short velvet flock`

## Palette direction
- lavender and cream

## Mood coverage
- cute healing soft

## 形态探索
- long bunny ears

## Media
- avatar: (none)
""",
                encoding="utf-8",
            )

            host = read_streamers(Path(tmp))[0]

        self.assertEqual(host.raw["material_direction"], ["soft plush silicone", "short velvet flock"])
        self.assertEqual(host.raw["palette_direction"], ["lavender and cream"])
        self.assertEqual(host.raw["mood_coverage"], ["cute healing soft"])
        self.assertEqual(host.raw["form_exploration"], ["long bunny ears"])
        self.assertIn("material_direction", host.notes)


if __name__ == "__main__":
    unittest.main()
