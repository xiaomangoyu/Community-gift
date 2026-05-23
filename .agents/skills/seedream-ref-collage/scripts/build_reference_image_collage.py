#!/usr/bin/env python3
"""Build a polished collage for references/imgs.

Default input:
  references/imgs/manifest.yaml
  references/imgs/*.{png,jpg,jpeg}

Default output:
  references/imgs/REFERENCE_COLLAGE.png
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont


REPO = Path(__file__).resolve().parents[4]
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def main() -> None:
    args = parse_args()
    refs_dir = resolve_path(args.refs_dir)
    manifest_path = resolve_path(args.manifest) if args.manifest else refs_dir / "manifest.yaml"
    output_path = resolve_path(args.output) if args.output else refs_dir / "REFERENCE_COLLAGE.png"

    entries = load_entries(refs_dir, manifest_path, output_path)
    if not entries:
        raise ValueError(f"No reference images found in {refs_dir}")

    build_collage(
        entries=entries,
        refs_dir=refs_dir,
        output_path=output_path,
        title=args.title,
        subtitle=args.subtitle,
        columns=args.columns,
    )
    print(f"Collage: {output_path}")
    print(f"Images: {len(entries)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a reference image library collage.")
    parser.add_argument("--refs-dir", default="references/imgs", help="Reference image directory.")
    parser.add_argument("--manifest", default=None, help="Manifest path. Defaults to <refs-dir>/manifest.yaml.")
    parser.add_argument("--output", default=None, help="Output image path. Defaults to <refs-dir>/REFERENCE_COLLAGE.png.")
    parser.add_argument("--columns", type=int, default=5, help="Number of collage columns.")
    parser.add_argument("--title", default="Reference Image Collection", help="Collage title.")
    parser.add_argument("--subtitle", default="images from references/imgs", help="Collage subtitle suffix.")
    return parser.parse_args()


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = REPO / path
    return path


def load_entries(refs_dir: Path, manifest_path: Path, output_path: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    manifest_images: set[str] = set()
    if manifest_path.exists():
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        for item in raw.get("references") or []:
            image_name = str(item.get("image") or "")
            ref_id = str(item.get("id") or Path(image_name).stem)
            if image_name and (refs_dir / image_name).exists() and not should_skip(image_name, output_path):
                entries.append({"id": ref_id, "image": image_name})
                manifest_images.add(image_name)

    for path in sorted(refs_dir.iterdir()):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if path.name in manifest_images or should_skip(path.name, output_path):
            continue
        entries.append({"id": path.stem, "image": path.name})
    return entries


def should_skip(name: str, output_path: Path) -> bool:
    if name == output_path.name:
        return True
    return bool(re.match(r"REFERENCE_.*COLLAGE.*\.(png|jpg|jpeg)$", name, re.IGNORECASE))


def build_collage(
    *,
    entries: list[dict[str, str]],
    refs_dir: Path,
    output_path: Path,
    title: str,
    subtitle: str,
    columns: int,
) -> None:
    columns = max(1, columns)
    rows = math.ceil(len(entries) / columns)
    tile_w, tile_h = 360, 430
    gap = 34
    margin_x = 78
    header_h = 145
    footer_h = 58
    width = margin_x * 2 + columns * tile_w + (columns - 1) * gap
    height = header_h + rows * tile_h + (rows - 1) * gap + footer_h

    canvas = Image.new("RGBA", (width, height), "#090b10ff")
    paint_background(canvas)
    draw = ImageDraw.Draw(canvas)

    fonts = {
        "title": load_font(58, bold=True),
        "sub": load_font(26),
        "label": load_font(22, bold=True),
        "small": load_font(18),
    }

    draw.rounded_rectangle((margin_x, 34, width - margin_x, 42), radius=4, fill="#27d5c8")
    draw.rounded_rectangle((margin_x + 260, 34, width - margin_x, 42), radius=4, fill="#ff5a8f")
    draw.text((margin_x, 58), title, font=fonts["title"], fill="#f6f0df")
    draw.text((margin_x, 112), f"{len(entries)} {subtitle}", font=fonts["sub"], fill="#aeb7c4")

    shadow = make_shadow((tile_w + 34, tile_h + 34))
    accents = ["#27d5c8", "#ff5a8f", "#ffd166", "#9b8cff", "#7bd88f"]

    for index, entry in enumerate(entries, 1):
        row = (index - 1) // columns
        col = (index - 1) % columns
        x = margin_x + col * (tile_w + gap)
        y = header_h + row * (tile_h + gap)

        canvas.alpha_composite(shadow, (x - 17, y - 10))
        card = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
        card_draw = ImageDraw.Draw(card)
        draw_card(
            card=card,
            draw=card_draw,
            index=index,
            ref_id=entry["id"],
            image_name=entry["image"],
            image_path=refs_dir / entry["image"],
            accent=accents[(index - 1) % len(accents)],
            fonts=fonts,
            tile_w=tile_w,
            tile_h=tile_h,
        )
        canvas.alpha_composite(card, (x, y))

    footer = f"Generated collage: {relative_display(output_path)}"
    footer_w = text_width(draw, footer, fonts["small"])
    draw.text(((width - footer_w) / 2, height - 38), footer, font=fonts["small"], fill="#6f7c8f")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, quality=95)


def draw_card(
    *,
    card: Image.Image,
    draw: ImageDraw.ImageDraw,
    index: int,
    ref_id: str,
    image_name: str,
    image_path: Path,
    accent: str,
    fonts: dict[str, ImageFont.ImageFont],
    tile_w: int,
    tile_h: int,
) -> None:
    draw.rounded_rectangle((0, 0, tile_w, tile_h), radius=24, fill="#111820", outline="#263241", width=2)
    draw.rounded_rectangle((1, 1, tile_w - 2, tile_h - 2), radius=23, outline="#38465a", width=1)
    image_area = (22, 24, tile_w - 22, 322)
    draw.rounded_rectangle(image_area, radius=18, fill="#050608", outline="#1e2835", width=1)

    thumb = fit_image(image_path, image_area[2] - image_area[0] - 18, image_area[3] - image_area[1] - 18)
    tx = image_area[0] + ((image_area[2] - image_area[0]) - thumb.width) // 2
    ty = image_area[1] + ((image_area[3] - image_area[1]) - thumb.height) // 2
    card.alpha_composite(thumb, (tx, ty))

    chip = f"{index:02d}"
    draw.rounded_rectangle((20, 340, 70, 372), radius=14, fill="#1e2937", outline="#4a5c71", width=1)
    chip_w = text_width(draw, chip, fonts["small"])
    draw.text((45 - chip_w / 2, 347), chip, font=fonts["small"], fill="#dbe7f5")

    label = ref_id.replace("_", " ")[:34]
    draw.text((82, 337), label, font=fonts["label"], fill="#f6f0df")

    file_label = image_name if len(image_name) <= 32 else image_name[:29] + "..."
    draw.text((82, 368), file_label, font=fonts["small"], fill="#94a3b8")
    draw.rounded_rectangle((20, tile_h - 20, tile_w - 20, tile_h - 14), radius=3, fill=accent)


def paint_background(canvas: Image.Image) -> None:
    width, height = canvas.size
    pix = canvas.load()
    for y in range(height):
        t = y / max(1, height - 1)
        red = int(8 + 10 * (1 - abs(t - 0.25)) + 3 * t)
        green = int(10 + 12 * (1 - abs(t - 0.30)) + 2 * t)
        blue = int(16 + 20 * (1 - abs(t - 0.20)) + 8 * t)
        for x in range(width):
            dx = abs((x / width) - 0.5) * 2
            vignette = 1 - 0.28 * (dx**1.7)
            pix[x, y] = (int(red * vignette), int(green * vignette), int(blue * vignette), 255)


def make_shadow(size: tuple[int, int]) -> Image.Image:
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    draw.rounded_rectangle((18, 18, size[0] - 18, size[1] - 18), radius=22, fill=(0, 0, 0, 180))
    return shadow.filter(ImageFilter.GaussianBlur(9))


def fit_image(path: Path, max_w: int, max_h: int) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    return image


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


def relative_display(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    main()
