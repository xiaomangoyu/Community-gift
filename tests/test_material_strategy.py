from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from community_gift.streamers_io import read_streamers
from community_gift.template_first import (
    _build_negative_prompt,
    _build_prompt,
    _finalize_material_terms,
    _is_hard_reflective_reference_role,
    _soften_material_terms,
    _soften_reference_role,
    _soften_reflective_slots,
)


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
        self.assertIn("硬质反光元素只作为", prompt)
        self.assertNotIn("材质以吹制气泡玻璃", prompt)

    def test_hard_paint_never_becomes_primary_soft_body(self) -> None:
        slots = {
            "primary_symbol": "黑豹",
            "secondary_symbol": "礼服",
            "theme_title": "暖金豹影礼装风",
            "mood": "锋利、华贵、夜感",
            "silhouette_language": "包裹、圆润、上扬",
            "intent_anchor_terms": [],
            "materials": ["镜面铬金属", "哑光软皮包覆"],
            "design_directives": {},
        }

        materials = _finalize_material_terms(slots)

        self.assertNotIn("低反射深灰硬漆", materials)
        self.assertNotIn("硬漆", materials[0])
        self.assertTrue(materials[0] in {"珠光软搪胶", "哑光软搪胶"} or "软" in materials[0])
        self.assertTrue(any("极薄" in item or "小面积" in item for item in materials[1:]))

    def test_soften_material_terms_is_idempotent_for_leather(self) -> None:
        once = _soften_material_terms(["细腻缝纫皮革", "雾面缝纫皮革"])
        twice = _soften_material_terms(once)

        self.assertEqual(once, twice)
        self.assertFalse(any("哑光哑光" in item for item in twice))

    def test_reflective_black_mirror_language_is_softened(self) -> None:
        slots = {
            "primary_symbol": "镜子",
            "secondary_symbol": "领带",
            "theme_title": "黑银镜像冷峻风",
            "mood": "冷峻、克制",
            "symbol_translation": "主体符号解构为椭圆镜框、内凹镜面、厚边包框",
            "supporting_translation": "将领带作为小型晶体镶嵌",
            "text_style": "窄体无衬线大写字形，冷白微光描边",
            "bottom_node": "加入与镜子相关的压纹",
            "silhouette_language": "对称、包裹",
            "fusion_note": "",
            "lamp_head_silhouette": "椭圆镜框领带包心灯头",
            "handle_phrase": "握柄主体使用亲肤硅胶。",
            "element_anchor": "镜子",
            "palette_name": "黑银冷调系",
            "colors": ["曜石黑", "墨黑", "雾银灰", "冷白", "石墨灰"],
            "color_anchor": "墨黑",
            "display_text": "VERONICA SANCHEZ",
            "materials": ["亲肤硅胶", "柔雾珐琅"],
            "palette_id": "black_safe",
            "intent_avoid_text_scripts": [],
            "banned": ["pure black product body"],
        }

        _soften_reflective_slots(slots)

        joined = " ".join(
            [
                slots["primary_symbol"],
                slots["theme_title"],
                slots["symbol_translation"],
                slots["lamp_head_silhouette"],
                " ".join(slots["colors"]),
            ]
        )
        self.assertTrue(slots["avoid_mirror_finish"])
        self.assertNotIn("镜面", joined)
        self.assertNotIn("镜像", joined)
        self.assertNotIn("镜芯", joined)
        self.assertNotIn("曜石黑", joined)
        self.assertNotIn("墨黑", joined)
        self.assertIn("椭圆雾灰软徽章", joined)

        negative = _build_negative_prompt(slots)
        self.assertIn("black mirror finish", negative)
        self.assertIn("strong white reflection stripes", negative)
        self.assertIn("camera lens", negative)
        self.assertIn("silver metal ring", negative)

    def test_reference_role_softens_hard_finish_words(self) -> None:
        role = (
            "A glossy black core with crystal contrast, chrome rim, "
            "mirror finish, and strong purple glow."
        )

        softened = _soften_reference_role(role)

        for term in ("glossy", "crystal", "chrome", "mirror", "strong purple glow"):
            self.assertNotIn(term, softened.lower())
        self.assertIn("soft-touch", softened)
        self.assertIn("low-reflection", softened)
        self.assertTrue(_is_hard_reflective_reference_role(role))


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
        self.assertEqual(host.raw["evidence_signals"], ["recurring_mascot_or_pet"])
        self.assertEqual(host.raw["primary_signals"], ["recurring_mascot_or_pet"])
        self.assertEqual(host.raw["palette_direction"], ["lavender and cream"])
        self.assertEqual(host.raw["mood_coverage"], ["cute healing soft"])
        self.assertEqual(host.raw["form_exploration"], ["long bunny ears"])
        self.assertIn("material_direction", host.notes)

    def test_reads_direction_section_heading_variants(self) -> None:
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

## Evidence signals
- `recurring_object_or_prop`

## Missing evidence
- `no_distinct_color_system`

### Material Directions:
- plush fabric

## Palette-Direction:
- lavender cream

## Mood Coverages:
- cute healing

## Shape Explorations:
- rounded ears
""",
                encoding="utf-8",
            )

            host = read_streamers(Path(tmp))[0]

        self.assertEqual(host.raw["material_direction"], ["plush fabric"])
        self.assertEqual(host.raw["evidence_signals"], ["recurring_object_or_prop"])
        self.assertEqual(host.raw["missing_evidence"], ["no_distinct_color_system"])
        self.assertEqual(host.raw["palette_direction"], ["lavender cream"])
        self.assertEqual(host.raw["mood_coverage"], ["cute healing"])
        self.assertEqual(host.raw["form_exploration"], ["rounded ears"])


if __name__ == "__main__":
    unittest.main()
