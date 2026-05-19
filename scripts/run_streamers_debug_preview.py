"""Run a streamer preview batch with visual routing debug sheets.

Examples:
    python3 scripts/run_streamers_debug_preview.py --start 0 --count 15
    python3 scripts/run_streamers_debug_preview.py --start 15 --count 15
    python3 scripts/run_streamers_debug_preview.py --start 0 --count 5 --dry-run

Outputs:
    outputs/preview_debug_<timestamp>/
      contact_sheet.jpg
      contact_sheet_debug.jpg
      route_summary.json
      routing_trace.json
      payloads/
      host_briefs/
      host_visions/
      debug_cards/
"""
from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

load_dotenv(REPO / ".env")

from community_gift.clients.image_client import ImageGenerationClient
from community_gift.clients.modelhub_client import ModelHubGiftClient
from community_gift.effect_library import EffectLibrary
from community_gift.models import GenerationResult
from community_gift.streamers_io import read_streamers
from community_gift.workflow import CommunityGiftWorkflow


class FakeImageClient:
    """Write tiny placeholder images while still dumping Seedream payload JSON."""

    _payload_dumper = ImageGenerationClient(provider="seedream_http")

    def generate(
        self,
        prompt: str,
        negative_prompt: str,
        output_dir: Path,
        basename: str,
        reference_pairs: list[tuple[str, str]] | None = None,
        payload_dump_dir: Path | None = None,
        **_ignored: Any,
    ) -> tuple[list[Path], Path]:
        if payload_dump_dir is not None:
            pairs = [(Path(p), role) for p, role in (reference_pairs or [])]
            self._payload_dumper._dump_payload(
                payload_dump_dir,
                basename,
                prompt,
                negative_prompt,
                pairs,
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        png_path = output_dir / f"{basename}_1.png"
        png_path.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
                "/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
            )
        )
        raw_path = output_dir / f"{basename}_raw.json"
        raw_path.write_text('{"mock": true}', encoding="utf-8")
        return [png_path], raw_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate streamer preview images plus debug contact sheets."
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Zero-based offset into sorted streamers/. Use 15 for rows 16-30.",
    )
    parser.add_argument("--count", type=int, default=15, help="Number of streamers to run.")
    parser.add_argument(
        "--tier",
        default=None,
        help="Optional comma-separated tier filter, e.g. exceptional,good.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory. Defaults to outputs/preview_debug_<timestamp>.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=6,
        help="Generation concurrency for real/mock image generation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build designs and debug JSON only; do not generate images or sheets.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use placeholder images and payload dumps instead of calling Seedream.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start < 0:
        raise ValueError("--start must be >= 0")
    if args.count <= 0:
        raise ValueError("--count must be > 0")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        Path(args.output_dir).expanduser()
        if args.output_dir
        else REPO / "outputs" / f"preview_debug_{timestamp}_s{args.start}_n{args.count}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    tier_filter = _parse_tier_filter(args.tier)
    all_hosts = read_streamers(REPO / "streamers", tier_filter=tier_filter)
    hosts = all_hosts[args.start : args.start + args.count]
    if not hosts:
        raise ValueError(
            f"No streamers selected. total={len(all_hosts)}, start={args.start}, count={args.count}"
        )

    tier_display = sorted(tier_filter) if tier_filter else "all"
    print(f"Output dir: {output_dir}")
    print(f"Loaded {len(hosts)} streamer(s), tier={tier_display}, offset={args.start}:")
    for host in hosts:
        print(f"  {host.row_id:03d} {host.host_name}")

    image_client: Any | None
    if args.dry_run:
        image_client = None
    elif args.mock:
        image_client = FakeImageClient()
    else:
        image_client = ImageGenerationClient()

    workflow = CommunityGiftWorkflow(
        openai_client=None,
        image_client=image_client,
        output_dir=output_dir,
        effect_library=EffectLibrary.load(REPO / "references" / "effects.json"),
        evaluation_threshold=80,
        generation_attempts=1,
        generation_concurrency=min(len(hosts), args.concurrency),
        evaluate_images=False,
        use_legacy_llm_design=False,
        vision_client=ModelHubGiftClient(),
    )

    designs = workflow.build_designs_from_hosts(hosts)
    print(f"Built {len(designs)} design(s).")
    route_summary = write_route_summary(output_dir)
    print(f"Wrote route summary: {output_dir / 'route_summary.json'}")

    if args.dry_run:
        print("Dry run complete. No images generated.")
        return

    t0 = time.monotonic()
    results = workflow.generate_images(designs)
    elapsed = time.monotonic() - t0
    print(f"Generated {len(results)} image result(s) in {elapsed:.1f}s")

    write_contact_sheets(output_dir, results, route_summary)
    print(f"Debug contact sheet: {output_dir / 'contact_sheet_debug.jpg'}")
    print(f"Plain contact sheet: {output_dir / 'contact_sheet.jpg'}")
    print_artifacts(output_dir)


def _parse_tier_filter(value: str | None) -> set[str] | None:
    if not value:
        return None
    tiers = {item.strip() for item in value.split(",") if item.strip()}
    return tiers or None


def write_route_summary(output_dir: Path) -> list[dict[str, Any]]:
    trace_path = output_dir / "routing_trace.json"
    if not trace_path.exists():
        return []
    rows = json.loads(trace_path.read_text(encoding="utf-8"))
    summary: list[dict[str, Any]] = []
    for row in rows:
        reference = row.get("reference", {})
        fields = reference.get("fields", {}) if isinstance(reference, dict) else {}
        picks = fields.get("picks") or []
        pick = picks[0] if picks else {}
        summary.append(
            {
                "row_id": row.get("row_id"),
                "host_name": row.get("host_name"),
                "reference_rule": reference.get("matched_rule_id"),
                "fallback_used": fields.get("fallback_used"),
                "reference_id": pick.get("id"),
                "score": pick.get("score"),
                "matched_tags": pick.get("matched_tags") or {},
                "matched_dimensions": pick.get("matched_dimensions") or [],
                "weak_generic_match": pick.get("weak_generic_match", False),
                "weak_text_only_match": pick.get("weak_text_only_match", False),
            }
        )
    (output_dir / "route_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def write_contact_sheets(
    output_dir: Path,
    results: list[GenerationResult],
    route_summary: list[dict[str, Any]],
) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        print(f"Skipping contact sheets: Pillow is not installed ({exc})")
        return

    route_by_row = {int(row["row_id"]): row for row in route_summary if row.get("row_id") is not None}
    cards = []
    for result in results:
        if not result.best_image_path:
            continue
        image_path = Path(result.best_image_path)
        if not image_path.exists():
            continue
        route = route_by_row.get(int(result.row_id), {})
        cards.append(
            {
                "row_id": result.row_id,
                "name": result.host_name or result.community_name or str(result.row_id),
                "image": image_path,
                "ref_id": route.get("reference_id") or "none",
                "score": route.get("score", ""),
                "fallback": bool(route.get("fallback_used")),
                "weak": bool(route.get("weak_generic_match") or route.get("weak_text_only_match")),
                "matched_line": _matched_line(route.get("matched_tags") or {}),
            }
        )
    if not cards:
        print("No generated images found; skipping contact sheets.")
        return

    _write_debug_sheet(output_dir / "contact_sheet_debug.jpg", cards, Image, ImageDraw, ImageFont)
    _write_plain_sheet(output_dir / "contact_sheet.jpg", cards, Image, ImageDraw, ImageFont)


def _matched_line(matched_tags: dict[str, list[str]]) -> str:
    parts: list[str] = []
    for dim in ["shape", "color", "material", "vibe", "text"]:
        vals = matched_tags.get(dim) or []
        if vals:
            parts.append(f"{dim}:{','.join(str(v) for v in vals[:3])}")
    return " | ".join(parts) if parts else "no strong tag match"


def _write_debug_sheet(path: Path, cards: list[dict[str, Any]], Image, ImageDraw, ImageFont) -> None:
    thumb = 360
    pad = 14
    label_h = 126
    cols = 5
    rows = (len(cards) + cols - 1) // cols
    sheet = Image.new(
        "RGB",
        (cols * (thumb + pad) + pad, rows * (thumb + label_h + pad) + pad),
        (246, 246, 244),
    )
    draw = ImageDraw.Draw(sheet)
    title_font = _font(ImageFont, 19)
    meta_font = _font(ImageFont, 15)
    small_font = _font(ImageFont, 13)

    for idx, card in enumerate(cards):
        col = idx % cols
        row = idx // cols
        x0 = pad + col * (thumb + pad)
        y0 = pad + row * (thumb + label_h + pad)
        image = Image.open(card["image"]).convert("RGB")
        image.thumbnail((thumb, thumb))
        bg = (255, 248, 226) if card["fallback"] else (237, 250, 244)
        draw.rounded_rectangle(
            [x0, y0, x0 + thumb, y0 + thumb + label_h],
            radius=8,
            fill=bg,
            outline=(214, 214, 210),
            width=1,
        )
        draw.rectangle([x0, y0, x0 + thumb, y0 + thumb], fill=(0, 0, 0))
        sheet.paste(image, (x0 + (thumb - image.width) // 2, y0 + (thumb - image.height) // 2))

        ly = y0 + thumb + 8
        title = f"{int(card['row_id']):03d} {card['name']}"
        title = title if len(title) <= 31 else title[:30] + "..."
        draw.text((x0 + 10, ly), title, fill=(20, 20, 20), font=title_font)
        ly += 25
        status = "fallback" if card["fallback"] else "matched"
        if card["weak"]:
            status += "/weak"
        draw.text(
            (x0 + 10, ly),
            f"ref: {card['ref_id']}  score:{card['score']}  {status}",
            fill=(45, 45, 45),
            font=meta_font,
        )
        ly += 22
        for line in _wrap_by_pixels(draw, card["matched_line"], small_font, thumb - 20)[:3]:
            draw.text((x0 + 10, ly), line, fill=(70, 70, 70), font=small_font)
            ly += 18
    sheet.save(path, quality=92)


def _write_plain_sheet(path: Path, cards: list[dict[str, Any]], Image, ImageDraw, ImageFont) -> None:
    thumb = 360
    label_h = 38
    cols = 5
    rows = (len(cards) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb, rows * (thumb + label_h)), "white")
    draw = ImageDraw.Draw(sheet)
    font = _font(ImageFont, 13)
    for idx, card in enumerate(cards):
        image = Image.open(card["image"]).convert("RGB")
        image.thumbnail((thumb, thumb))
        x = (idx % cols) * thumb + (thumb - image.width) // 2
        y = (idx // cols) * (thumb + label_h)
        sheet.paste(image, (x, y))
        label = f"{int(card['row_id']):03d} {card['name']}"[:36]
        draw.text(((idx % cols) * thumb + 8, y + thumb + 8), label, fill=(0, 0, 0), font=font)
    sheet.save(path, quality=92)


def _font(ImageFont, size: int):
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _wrap_by_pixels(draw, text: str, font, max_width: int) -> list[str]:
    if not text:
        return [""]
    parts = text.split(" ")
    lines: list[str] = []
    current = ""
    for part in parts:
        trial = part if not current else current + " " + part
        if _text_width(draw, trial, font) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        if _text_width(draw, part, font) <= max_width:
            current = part
        else:
            lines.extend(textwrap.wrap(part, width=28) or [part])
            current = ""
    if current:
        lines.append(current)
    return lines


def _text_width(draw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def print_artifacts(output_dir: Path) -> None:
    print("Artifacts:")
    for name in [
        "contact_sheet.jpg",
        "contact_sheet_debug.jpg",
        "route_summary.json",
        "routing_trace.json",
        "payloads",
        "host_briefs",
        "host_visions",
        "debug_cards",
    ]:
        path = output_dir / name
        if path.is_dir():
            count = len(list(path.iterdir()))
            size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
            print(f"  {name}/ ({count} files, {size} B)")
        elif path.exists():
            print(f"  {name} ({path.stat().st_size} B)")
        else:
            print(f"  {name}: missing")


if __name__ == "__main__":
    main()
