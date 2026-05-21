#!/usr/bin/env python3
"""Audit creative profile routing for streamers without generating images.

The script is intentionally read-only for streamer data: it loads existing
vision cache when available, builds HostBrief + template prompt, then writes a
small review table. It never calls VLM or image generation.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from community_gift.host_brief import build_host_brief, derive_retrieval_intent
from community_gift.host_vision import (
    HostVisionBrief,
    load_vision_cache,
    load_vision_override,
    pick_vision_image,
)
from community_gift.streamers_io import read_streamers
from community_gift.template_first import build_template_first_design


TEMPERAMENT_AXES = {"rock_glam", "combat", "luxury", "predator"}
FORM_AXES = {
    "feather",
    "horn",
    "claw",
    "fang",
    "spike",
    "scale",
    "crest",
    "flame",
    "lightning",
    "predator",
}
GESTURE_HINT_AXES = {"feather", "horn", "claw", "spike", "flame", "lightning"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit current creative profile inference for streamer signals."
    )
    parser.add_argument("--start", type=int, default=0, help="Zero-based start offset.")
    parser.add_argument("--count", type=int, default=0, help="Rows to audit. 0 means all.")
    parser.add_argument("--tier", default=None, help="Optional comma-separated tier filter.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to outputs/creative_audit_<timestamp>.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tier_filter = _parse_tier_filter(args.tier)
    hosts = read_streamers(REPO / "streamers", tier_filter=tier_filter)
    if args.start:
        hosts = hosts[args.start :]
    if args.count:
        hosts = hosts[: args.count]
    if not hosts:
        raise ValueError("No streamers selected for audit.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        Path(args.output_dir).expanduser()
        if args.output_dir
        else REPO / "outputs" / f"creative_audit_{timestamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    rows = [_audit_host(host) for host in hosts]
    _write_json(output_dir / "creative_audit.json", rows)
    _write_csv(output_dir / "creative_audit.csv", rows)
    _write_markdown(output_dir / "creative_audit.md", rows)

    print(f"Audited {len(rows)} streamer(s).")
    print(f"Markdown: {output_dir / 'creative_audit.md'}")
    print(f"CSV: {output_dir / 'creative_audit.csv'}")
    print(f"JSON: {output_dir / 'creative_audit.json'}")


def _audit_host(host) -> dict[str, Any]:
    image_path, _image_source = pick_vision_image(host)
    vision, vision_source = _load_vision_for_audit(host, image_path)
    brief = build_host_brief(host, vision=vision)
    intent = derive_retrieval_intent(brief)
    design, _ = build_template_first_design(host, brief=brief, intent=intent)
    profile = brief.creative_profile
    axes = list(profile.axes)
    prompt = design.seedance_prompt
    prompt_effects = _prompt_effects(prompt)
    return {
        "row_id": host.row_id,
        "anchor_id": host.anchor_id,
        "host_name": host.host_name,
        "community_name": host.community_name,
        "text": design.text_plan.exact_text,
        "primary_symbol": brief.primary_symbol,
        "secondary_symbol": brief.secondary_symbol,
        "creative_mode": profile.mode,
        "intensity": profile.intensity,
        "axes": axes,
        "temperament_axes": _filter_axes(axes, TEMPERAMENT_AXES),
        "form_axes": _filter_axes(axes, FORM_AXES),
        "gesture_hint_axes": _filter_axes(axes, GESTURE_HINT_AXES),
        "source": profile.source,
        "notes": profile.notes,
        "vision_source": vision_source,
        "vision_symbol": _vision_symbols(vision),
        "vision_mood_tags": list(vision.mood.tags) if vision else [],
        "prompt_effects": prompt_effects,
        "prompt_chars": len(prompt),
        "manual_review_hint": _manual_review_hint(profile.mode, axes, prompt_effects, vision),
    }


def _load_vision_for_audit(host, image_path: str) -> tuple[HostVisionBrief | None, str]:
    override = load_vision_override(host)
    if override is not None:
        return override, "override"
    cached = load_vision_cache(host, image_path)
    if cached is not None:
        return cached, "cache"
    stale = _load_stale_vision_cache(host)
    if stale is not None:
        return stale, "stale_cache"
    return None, "missing"


def _load_stale_vision_cache(host) -> HostVisionBrief | None:
    """Read an existing cache even when the strict key changed.

    This is only for audit. We do not write it back and workflow generation
    still uses the strict cache key.
    """

    anchor_id = host.anchor_id or f"row{host.row_id}"
    path = REPO / "outputs" / "vision_cache" / f"{anchor_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return HostVisionBrief.model_validate(data.get("brief", {}))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _filter_axes(axes: list[str], allowed: set[str]) -> list[str]:
    return [axis for axis in axes if axis in allowed]


def _vision_symbols(vision) -> str:
    if not vision:
        return ""
    symbols = [vision.signature_symbols.primary, vision.signature_symbols.secondary]
    return " + ".join(symbol for symbol in symbols if symbol)


def _prompt_effects(prompt: str) -> list[str]:
    effects: list[str] = []
    if "整体允许更明显" in prompt or "整体在稳定应援棒结构上" in prompt:
        effects.append("gesture")
    if "这些野性或动势元素" in prompt:
        effects.append("form")
    return effects


def _manual_review_hint(mode: str, axes: list[str], prompt_effects: list[str], vision) -> str:
    if vision is None:
        return "needs vision cache"
    form_axes = _filter_axes(axes, FORM_AXES)
    temperament_axes = _filter_axes(axes, TEMPERAMENT_AXES)
    if mode == "baseline":
        if axes:
            return "baseline kept; mood-only axes"
        return "ok baseline"
    if mode == "wild" and not form_axes:
        return "review: wild without form axes"
    if mode != "baseline" and not prompt_effects:
        return "review: profile has no prompt effect"
    if mode != "baseline" and temperament_axes and not form_axes:
        return "review: temperament only"
    return "review image sample"


def _write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "row_id",
        "anchor_id",
        "host_name",
        "community_name",
        "text",
        "primary_symbol",
        "secondary_symbol",
        "creative_mode",
        "intensity",
        "axes",
        "temperament_axes",
        "form_axes",
        "gesture_hint_axes",
        "source",
        "vision_source",
        "vision_symbol",
        "vision_mood_tags",
        "prompt_effects",
        "manual_review_hint",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key, "")) for key in columns})


def _write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Creative Profile Audit",
        "",
        "This audit is read-only: it uses current signals, existing vision cache, HostBrief, and template-first prompt assembly. It does not generate images or call VLM.",
        "",
        "| # | Host | Text | Symbol | Mode | Axes | Prompt | Review |",
        "|---:|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        axes = ", ".join(row["axes"])
        prompt_effects = ", ".join(row["prompt_effects"]) or "-"
        symbol = " / ".join(v for v in [row["primary_symbol"], row["secondary_symbol"]] if v)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["row_id"]),
                    _md(row["host_name"]),
                    _md(row["text"]),
                    _md(symbol),
                    _md(f"{row['creative_mode']}:{row['intensity']}"),
                    _md(axes or "-"),
                    _md(prompt_effects),
                    _md(row["manual_review_hint"]),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("## Mode Counts")
    lines.append("")
    for mode, count in _mode_counts(rows).items():
        lines.append(f"- `{mode}`: {count}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _mode_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        mode = str(row["creative_mode"])
        counts[mode] = counts.get(mode, 0) + 1
    return dict(sorted(counts.items()))


def _csv_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _md(value: Any) -> str:
    text = _csv_value(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _parse_tier_filter(value: str | None) -> set[str] | None:
    if not value:
        return None
    tiers = {item.strip() for item in value.split(",") if item.strip()}
    return tiers or None


if __name__ == "__main__":
    main()
