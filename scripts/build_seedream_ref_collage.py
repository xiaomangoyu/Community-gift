#!/usr/bin/env python3
"""Build a Seedream batch collage with reference-image usage stats.

Expected batch layout:
  <output-dir>/routing_trace.json
  <output-dir>/images/*_1.png

Outputs:
  <output-dir>/streamers32_seedream45_ref_collage.png
  <output-dir>/ref_image_usage.csv
  <output-dir>/ref_image_usage.json
  <output-dir>/ref_image_usage_summary.md
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import textwrap
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_NAME = "streamers32_seedream45_ref_collage.png"


def main() -> None:
    args = parse_args()
    output_dir = resolve_output_dir(args.output_dir)
    refs_dir = Path(args.refs_dir).expanduser()
    if not refs_dir.is_absolute():
        refs_dir = REPO / refs_dir
    manifest_path = Path(args.manifest).expanduser() if args.manifest else refs_dir / "manifest.yaml"
    if not manifest_path.is_absolute():
        manifest_path = REPO / manifest_path

    rows = load_json(output_dir / "routing_trace.json")
    ref_by_id = load_reference_manifest(manifest_path)
    images_by_row = find_generated_images(output_dir / "images")
    usage_rows = build_usage_rows(rows, ref_by_id)

    usage_csv = output_dir / args.usage_csv
    usage_json = output_dir / args.usage_json
    usage_md = output_dir / args.usage_md
    collage_path = output_dir / args.output_name
    hide_references = should_hide_references(output_dir, args.model_label, args.hide_references)

    write_usage_csv(usage_csv, usage_rows)
    usage_json.write_text(json.dumps(usage_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    write_usage_summary(usage_md, usage_rows, ref_by_id, output_dir, len(images_by_row))
    build_collage(
        collage_path=collage_path,
        rows=rows,
        usage_rows=usage_rows,
        ref_by_id=ref_by_id,
        images_by_row=images_by_row,
        refs_dir=refs_dir,
        title=args.title,
        subtitle=args.subtitle,
        columns=args.columns,
        model_label=args.model_label,
        output_dir=output_dir,
        hide_references=hide_references,
    )

    print(f"Collage: {collage_path}")
    print(f"Usage summary: {usage_md}")
    print(f"Usage CSV: {usage_csv}")
    print(f"Generated images found: {len(images_by_row)}/{len(rows)}")
    if hide_references:
        print("Reference thumbnails hidden for this collage.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a visual Seedream result board with reference usage stats."
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        help="Batch output directory. Defaults to newest outputs/* containing routing_trace.json.",
    )
    parser.add_argument("--refs-dir", default="references/imgs", help="Reference image directory.")
    parser.add_argument("--manifest", default=None, help="Reference manifest path.")
    parser.add_argument("--output-name", default=DEFAULT_OUTPUT_NAME, help="Collage image filename.")
    parser.add_argument("--usage-csv", default="ref_image_usage.csv", help="CSV usage filename.")
    parser.add_argument("--usage-json", default="ref_image_usage.json", help="JSON usage filename.")
    parser.add_argument(
        "--usage-md",
        default="ref_image_usage_summary.md",
        help="Markdown usage summary filename.",
    )
    parser.add_argument("--columns", type=int, default=4, help="Number of collage columns.")
    parser.add_argument(
        "--hide-references",
        action="store_true",
        help="Build a generated-image gallery without reference thumbnails or ref usage chips.",
    )
    parser.add_argument(
        "--title",
        default="Seedream 4.5 Streamers x Reference Map",
        help="Collage title.",
    )
    parser.add_argument(
        "--subtitle",
        default="Generated lightstick images with selected references from references/imgs",
        help="Collage subtitle.",
    )
    parser.add_argument("--model-label", default="Seedream 4.5 general_v4.5")
    return parser.parse_args()


def resolve_output_dir(value: str | None) -> Path:
    if value:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = REPO / path
    else:
        candidates = [
            p
            for p in (REPO / "outputs").iterdir()
            if p.is_dir() and (p / "routing_trace.json").exists()
        ]
        if not candidates:
            raise FileNotFoundError("No outputs/* directory with routing_trace.json found.")
        path = max(candidates, key=lambda p: p.stat().st_mtime)
    if not path.exists():
        raise FileNotFoundError(path)
    if not (path / "routing_trace.json").exists():
        raise FileNotFoundError(f"Missing routing_trace.json in {path}")
    return path


def should_hide_references(output_dir: Path, model_label: str, explicit: bool) -> bool:
    if explicit:
        return True
    label = model_label.lower().replace("_", "-")
    if "gpt-image" in label or "image2" in label:
        return True
    images_dir = output_dir / "images"
    return images_dir.exists() and any(images_dir.glob("*.gpt_image_2.json"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_reference_manifest(manifest_path: Path) -> dict[str, dict[str, str]]:
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    refs: dict[str, dict[str, str]] = {}
    for entry in raw.get("references") or []:
        ref_id = str(entry.get("id") or "")
        if not ref_id:
            continue
        refs[ref_id] = {
            "image": str(entry.get("image") or ""),
            "notes": str(entry.get("notes") or ""),
        }
    return refs


def find_generated_images(images_dir: Path) -> dict[int, Path]:
    images: dict[int, Path] = {}
    if not images_dir.exists():
        return images
    for path in sorted(images_dir.glob("*_1.png")):
        row_key = path.name.split("_", 1)[0]
        if row_key.isdigit():
            images[int(row_key)] = path
    return images


def build_usage_rows(
    rows: list[dict[str, Any]],
    ref_by_id: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    usage_rows: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: int(item.get("row_id") or 0)):
        row_id = int(row.get("row_id") or 0)
        reference = row.get("reference") or {}
        fields = reference.get("fields") or {}
        picks = fields.get("picks") or []
        if not picks:
            usage_rows.append(
                {
                    "row_id": row_id,
                    "host_name": row.get("host_name") or "",
                    "pick_rank": 1,
                    "reference_id": "none",
                    "reference_image": "",
                    "score": "",
                    "fallback_used": fields.get("fallback_used"),
                    "matched_dimensions": "",
                    "matched_tags": "",
                }
            )
            continue
        for rank, pick in enumerate(picks, 1):
            ref_id = pick.get("id") or "none"
            ref_img = ref_by_id.get(ref_id, {}).get("image") or Path(
                pick.get("image_path") or ""
            ).name
            matched_tags = pick.get("matched_tags") or {}
            usage_rows.append(
                {
                    "row_id": row_id,
                    "host_name": row.get("host_name") or "",
                    "pick_rank": rank,
                    "reference_id": ref_id,
                    "reference_image": ref_img,
                    "score": pick.get("score"),
                    "fallback_used": fields.get("fallback_used"),
                    "matched_dimensions": ",".join(
                        pick.get("matched_dimensions") or sorted(matched_tags)
                    ),
                    "matched_tags": json.dumps(
                        matched_tags, ensure_ascii=False, separators=(",", ":")
                    ),
                }
            )
    return usage_rows


def write_usage_csv(path: Path, usage_rows: list[dict[str, Any]]) -> None:
    if not usage_rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(usage_rows[0].keys()))
        writer.writeheader()
        writer.writerows(usage_rows)


def write_usage_summary(
    path: Path,
    usage_rows: list[dict[str, Any]],
    ref_by_id: dict[str, dict[str, str]],
    output_dir: Path,
    generated_count: int,
) -> None:
    top_rows = [row for row in usage_rows if int(row.get("pick_rank") or 1) == 1]
    counts = Counter(row["reference_id"] for row in top_rows)
    rows_by_ref: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in top_rows:
        rows_by_ref[row["reference_id"]].append(row)

    lines = [
        "# Seedream Ref Usage",
        "",
        f"- Output dir: `{output_dir.relative_to(REPO).as_posix()}`",
        f"- Generated images: {generated_count}/{len(top_rows)}",
        f"- Reference picks per streamer: {max((int(r.get('pick_rank') or 1) for r in usage_rows), default=1)}",
        "",
        "## Counts",
        "",
        "| Count | Ref ID | Ref Image | Rows |",
        "|---:|---|---|---|",
    ]
    for ref_id, count in counts.most_common():
        ref_img = ref_by_id.get(ref_id, {}).get("image", "")
        row_list = ", ".join(f"{int(row['row_id']):03d}" for row in rows_by_ref[ref_id])
        lines.append(f"| {count} | `{ref_id}` | `{ref_img}` | {row_list} |")

    lines.extend(
        [
            "",
            "## Per Streamer",
            "",
            "| Row | Host | Ref ID | Ref Image | Score | Matched |",
            "|---:|---|---|---|---:|---|",
        ]
    )
    for row in top_rows:
        host = str(row["host_name"]).replace("|", "/")
        matched = row["matched_dimensions"] or "fallback"
        lines.append(
            f"| {int(row['row_id']):03d} | {host} | `{row['reference_id']}` | "
            f"`{row['reference_image']}` | {row['score']} | {matched} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_collage(
    *,
    collage_path: Path,
    rows: list[dict[str, Any]],
    usage_rows: list[dict[str, Any]],
    ref_by_id: dict[str, dict[str, str]],
    images_by_row: dict[int, Path],
    refs_dir: Path,
    title: str,
    subtitle: str,
    columns: int,
    model_label: str,
    output_dir: Path,
    hide_references: bool = False,
) -> None:
    row_lookup = {int(row.get("row_id") or 0): row for row in rows}
    usage_by_row = {
        int(row["row_id"]): row
        for row in usage_rows
        if int(row.get("pick_rank") or 1) == 1
    }
    counts = Counter(row["reference_id"] for row in usage_by_row.values())

    total = len(row_lookup)
    columns = max(1, columns)
    card_w = 455
    card_h = 526 if hide_references else 604
    gap = 26
    margin_x = 54
    header_h = 210
    footer_h = 54
    rows_n = math.ceil(total / columns)
    width = margin_x * 2 + columns * card_w + (columns - 1) * gap
    height = header_h + rows_n * card_h + (rows_n - 1) * gap + footer_h

    canvas = Image.new("RGBA", (width, height), "#080b11ff")
    draw = ImageDraw.Draw(canvas)
    paint_background(canvas, draw)

    fonts = {
        "title": load_font(52, bold=True),
        "sub": load_font(24),
        "card_title": load_font(21, bold=True),
        "meta": load_font(17),
        "small": load_font(14),
        "tiny": load_font(12),
    }

    draw.rounded_rectangle((margin_x, 28, width - margin_x, 36), radius=4, fill="#26d5c8")
    draw.rounded_rectangle((margin_x + 420, 28, width - margin_x, 36), radius=4, fill="#ff5b91")
    draw.text((margin_x, 62), title, font=fonts["title"], fill="#fff6e6")
    draw.text((margin_x, 120), f"{total} {subtitle}", font=fonts["sub"], fill="#aeb8c7")

    if hide_references:
        label = "generated-only gallery"
        label_w = text_width(draw, label, fonts["small"])
        draw.rounded_rectangle(
            (margin_x, 158, margin_x + label_w + 24, 186),
            radius=14,
            fill="#162131",
            outline="#344257",
        )
        draw.text((margin_x + 12, 164), label, font=fonts["small"], fill="#dce7f7")
    else:
        chip_x = margin_x
        chip_y = 158
        for ref_id, count in counts.most_common(8):
            label = f"{count}x {ref_id}"
            label_w = text_width(draw, label, fonts["small"])
            draw.rounded_rectangle(
                (chip_x, chip_y, chip_x + label_w + 24, chip_y + 28),
                radius=14,
                fill="#162131",
                outline="#344257",
            )
            draw.text((chip_x + 12, chip_y + 6), label, font=fonts["small"], fill="#dce7f7")
            chip_x += label_w + 34
            if chip_x > width - margin_x - 220:
                break

    shadow = make_shadow((card_w + 24, card_h + 24))
    accents = ["#26d5c8", "#ff5b91", "#ffd166", "#a78bfa", "#7bd88f"]

    for index, row_id in enumerate(sorted(row_lookup), 1):
        row = row_lookup[row_id]
        usage = usage_by_row.get(row_id, {})
        ref_id = usage.get("reference_id") or "none"
        ref_img_name = usage.get("reference_image") or ref_by_id.get(ref_id, {}).get("image") or ""
        image_path = images_by_row.get(row_id)

        grid_index = index - 1
        row_i = grid_index // columns
        col_i = grid_index % columns
        x = margin_x + col_i * (card_w + gap)
        y = header_h + row_i * (card_h + gap)

        canvas.alpha_composite(shadow, (x - 12, y - 8))
        card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        card_draw = ImageDraw.Draw(card)
        draw_card(
            card=card,
            draw=card_draw,
            row_id=row_id,
            host_name=str(row.get("host_name") or ""),
            image_path=image_path,
            ref_id=str(ref_id),
            ref_img_name=str(ref_img_name),
            ref_path=refs_dir / str(ref_img_name) if ref_img_name else None,
            score=usage.get("score", ""),
            fallback=bool(usage.get("fallback_used")),
            matched=str(usage.get("matched_dimensions") or "fallback/random"),
            fonts=fonts,
            accent=accents[grid_index % len(accents)],
            card_w=card_w,
            card_h=card_h,
            hide_references=hide_references,
        )
        canvas.alpha_composite(card, (x, y))

    footer = (
        f"Images: {len(images_by_row)}/{total} | Model: {model_label} | "
        f"Output: {output_dir.relative_to(REPO).as_posix()}"
    )
    footer_w = text_width(draw, footer, fonts["small"])
    draw.text(((width - footer_w) / 2, height - 34), footer, font=fonts["small"], fill="#748197")
    canvas.convert("RGB").save(collage_path, quality=95)


def draw_card(
    *,
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    row_id: int,
    host_name: str,
    image_path: Path | None,
    ref_id: str,
    ref_img_name: str,
    ref_path: Path | None,
    score: Any,
    fallback: bool,
    matched: str,
    fonts: dict[str, ImageFont.ImageFont],
    accent: str,
    card_w: int,
    card_h: int,
    hide_references: bool = False,
) -> None:
    draw.rounded_rectangle((0, 0, card_w, card_h), radius=22, fill="#101823", outline="#2d3b4e", width=2)
    image_bottom = 430 if hide_references else 395
    image_fit_h = image_bottom - 30
    draw.rounded_rectangle((18, 18, card_w - 18, image_bottom), radius=16, fill="#030405", outline="#1f2a38", width=1)
    if image_path and image_path.exists():
        image = fit_image(image_path, card_w - 48, image_fit_h)
        card.alpha_composite(image, (24 + (card_w - 48 - image.width) // 2, 24 + (image_fit_h - image.height) // 2))
    else:
        draw.text((36, image_bottom // 2), "missing image", font=fonts["meta"], fill="#ff9c9c")

    meta_top = image_bottom + 19
    draw.rounded_rectangle((18, meta_top, 68, meta_top + 30), radius=15, fill="#1d2938", outline="#46576d")
    number = f"{row_id:02d}"
    draw.text((43 - text_width(draw, number, fonts["small"]) / 2, meta_top + 7), number, font=fonts["small"], fill="#deebfb")

    title_lines = wrap_pixels(draw, host_name, fonts["card_title"], card_w - 102, 2)
    title_y = meta_top - 4
    for line in title_lines:
        draw.text((82, title_y), line, font=fonts["card_title"], fill="#fff4df")
        title_y += 25

    if hide_references:
        draw.rounded_rectangle((18, card_h - 18, card_w - 18, card_h - 12), radius=3, fill=accent)
        return

    ref_box = (18, 468, 108, 558)
    draw.rounded_rectangle(ref_box, radius=14, fill="#050608", outline="#263243")
    if ref_path and ref_path.exists():
        ref_image = fit_image(ref_path, 82, 82)
        card.alpha_composite(ref_image, (ref_box[0] + (90 - ref_image.width) // 2, ref_box[1] + (90 - ref_image.height) // 2))

    meta_x = 124
    draw.text((meta_x, 469), f"ref: {ref_id}", font=fonts["meta"], fill="#dce7f7")
    draw.text((meta_x, 493), f"image: {ref_img_name}", font=fonts["small"], fill="#92a1b5")
    status = "fallback" if fallback else "matched"
    draw.text((meta_x, 515), f"score: {score}  {status}", font=fonts["small"], fill="#92a1b5")
    match_line = wrap_pixels(draw, f"match: {matched}", fonts["tiny"], card_w - meta_x - 20, 1)[0]
    draw.text((meta_x, 537), match_line, font=fonts["tiny"], fill="#76869b")
    draw.rounded_rectangle((18, card_h - 18, card_w - 18, card_h - 12), radius=3, fill=accent)


def paint_background(canvas: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    width, height = canvas.size
    for y in range(height):
        t = y / max(height - 1, 1)
        red = int(7 + 9 * (1 - t) + 5 * t)
        green = int(10 + 12 * (1 - abs(t - 0.22)))
        blue = int(17 + 22 * (1 - abs(t - 0.18)) + 7 * t)
        draw.line((0, y, width, y), fill=(red, green, blue, 255))


def fit_image(path: Path, max_w: int, max_h: int) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    return image


def make_shadow(size: tuple[int, int]) -> Image.Image:
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    draw.rounded_rectangle((12, 12, size[0] - 12, size[1] - 12), radius=22, fill=(0, 0, 0, 150))
    return shadow.filter(ImageFilter.GaussianBlur(10))


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates.extend(
            [
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            ]
        )
    candidates.extend(
        [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
    )
    for candidate in candidates:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def wrap_pixels(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    if not text:
        return [""]
    parts = text.split(" ")
    lines: list[str] = []
    current = ""
    for part in parts:
        trial = part if not current else current + " " + part
        if text_width(draw, trial, font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            if text_width(draw, part, font) <= max_width:
                current = part
            else:
                chunks = textwrap.wrap(part, width=18) or [part]
                lines.extend(chunks[:-1])
                current = chunks[-1]
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines[:max_lines]


if __name__ == "__main__":
    main()
