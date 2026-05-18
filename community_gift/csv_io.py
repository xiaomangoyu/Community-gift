from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .models import GiftDesign, HostInput


FIELD_ALIASES = {
    "主播名字": "host_name",
    "主播名": "host_name",
    "host_name": "host_name",
    "Anchor ID": "anchor_id",
    "anchor_id": "anchor_id",
    "是否进入测试": "test_status",
    "主播图片": "host_image",
    "图片": "host_image",
    "image": "host_image",
    "image_url": "host_image",
    "社群名字": "community_name",
    "社群名": "community_name",
    "community_name": "community_name",
    "内容类型": "content_type",
    "直播类型": "content_type",
    "content_type": "content_type",
    "直播氛围": "live_vibe",
    "氛围": "live_vibe",
    "live_vibe": "live_vibe",
    "主播性格": "personality",
    "性格": "personality",
    "personality": "personality",
    "主应援色": "primary_color",
    "应援色": "primary_color",
    "primary_color": "primary_color",
    "辅助色": "secondary_color",
    "secondary_color": "secondary_color",
    "主色": "primary_color",
    "代表符号": "symbols",
    "符号": "symbols",
    "symbols": "symbols",
    "Hero符号": "symbols",
    "辅助符号": "symbols",
    "禁用元素": "banned_elements",
    "不要出现": "banned_elements",
    "banned_elements": "banned_elements",
    "必须避免": "banned_elements",
    "备注": "notes",
    "notes": "notes",
    "设计置信度": "design_confidence",
    "推荐输出类型": "recommended_output_type",
    "主体形态": "body_form",
    "主文字": "primary_text",
    "副文字": "secondary_text",
    "材质语言": "material_language_hint",
    "装饰强度": "decoration_intensity",
    "映射理由": "mapping_reason",
}


DESIGN_PARAM_NOTE_FIELDS = [
    "设计置信度",
    "推荐输出类型",
    "主体形态",
    "主文字",
    "副文字",
    "材质语言",
    "装饰强度",
    "映射理由",
]


def split_list(value: str) -> list[str]:
    if not value:
        return []
    separators = ["/", "、", "，", ",", ";", "；", "|"]
    normalized = value
    for separator in separators:
        normalized = normalized.replace(separator, ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def read_hosts(csv_path: Path, max_rows: int | None = None) -> list[HostInput]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        hosts: list[HostInput] = []
        for index, row in enumerate(reader, start=1):
            if max_rows and len(hosts) >= max_rows:
                break

            normalized: dict[str, str] = {}
            for key, value in row.items():
                if key is None:
                    continue
                target = FIELD_ALIASES.get(key.strip(), key.strip())
                value = (value or "").strip()
                if not value:
                    continue
                if target in normalized and normalized[target]:
                    normalized[target] = f"{normalized[target]}；{value}"
                else:
                    normalized[target] = value

            _apply_design_param_defaults(row, normalized)

            hosts.append(
                HostInput(
                    row_id=index,
                    host_name=normalized.get("host_name", ""),
                    anchor_id=normalized.get("anchor_id", ""),
                    test_status=normalized.get("test_status", ""),
                    host_image=normalized.get("host_image", ""),
                    community_name=normalized.get("community_name", ""),
                    content_type=normalized.get("content_type", ""),
                    live_vibe=normalized.get("live_vibe", ""),
                    personality=normalized.get("personality", ""),
                    primary_color=normalized.get("primary_color", ""),
                    secondary_color=normalized.get("secondary_color", ""),
                    symbols=split_list(normalized.get("symbols", "")),
                    banned_elements=split_list(normalized.get("banned_elements", "")),
                    design_confidence=normalized.get("design_confidence", ""),
                    recommended_output_type=normalized.get("recommended_output_type", ""),
                    body_form=normalized.get("body_form", ""),
                    primary_text=normalized.get("primary_text", ""),
                    secondary_text=normalized.get("secondary_text", ""),
                    material_language_hint=normalized.get("material_language_hint", ""),
                    decoration_intensity=normalized.get("decoration_intensity", ""),
                    mapping_reason=normalized.get("mapping_reason", ""),
                    notes=normalized.get("notes", ""),
                    raw=row,
                )
            )
    return hosts


def _apply_design_param_defaults(row: dict[str, str], normalized: dict[str, str]) -> None:
    """Lift reviewed design-parameter CSVs into the standard host input shape."""

    if not normalized.get("community_name"):
        main_text = normalized.get("primary_text", "") or (row.get("主文字") or "").strip()
        if main_text:
            normalized["community_name"] = main_text

    if not normalized.get("content_type"):
        body_form = normalized.get("body_form", "") or (row.get("主体形态") or "").strip()
        if body_form:
            normalized["content_type"] = body_form

    note_parts = [normalized.get("notes", "")]
    for field in DESIGN_PARAM_NOTE_FIELDS:
        target = FIELD_ALIASES.get(field, field)
        value = normalized.get(target, "") or (row.get(field) or "").strip()
        if value:
            note_parts.append(f"{field}：{value}")
    normalized["notes"] = "；".join(part for part in note_parts if part)


def write_designs_csv(designs: Iterable[GiftDesign], output_path: Path) -> None:
    rows = [design.model_dump(exclude={"routing_trace", "reference_pairs"}) for design in designs]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "row_id",
        "host_name",
        "community_name",
        "matched_effects",
        "design_concept",
        "text_plan",
        "prompt_plan",
        "core_keywords",
        "required_elements",
        "abstract_methods",
        "recommended_gift_form",
        "material_language",
        "color_plan",
        "composition",
        "complexity_rules",
        "negative_constraints",
        "seedance_prompt",
        "seedance_negative_prompt",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (list, dict))
                    else value
                    for key, value in row.items()
                }
            )


def write_designs_json(designs: Iterable[GiftDesign], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = [design.model_dump() for design in designs]
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
