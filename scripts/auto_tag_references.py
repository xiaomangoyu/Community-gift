"""Batch-tag reference images by four dimensions: 形 (shape) / 色 (color) / 质 (material) / 构 (composition).

Uses anthropic claude-haiku-4-5 (cheap + vision-capable). Writes
references/images/index.json with per-image tags.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 scripts/auto_tag_references.py [--dir references/images/crops/20260516-155426] [--limit N] [--concurrency 5]

Re-running is idempotent: if index.json already has an entry for an image
(matched by relative path), it is skipped unless --force is passed.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env")

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
DEFAULT_IMAGE_DIR = REPO / "references" / "images" / "crops" / "20260516-155426"
INDEX_PATH = REPO / "references" / "images" / "index.json"


SYSTEM_PROMPT = """You are tagging premium idol lightstick reference images.

Each image shows ONE collectible lightstick on a black or near-black studio background, photographed front-on.

Return a strict JSON object (no prose, no markdown) with these fields:

{
  "shape": [up to 3 tags from this enum: winged, crown, heart, brim, mascot, butterfly, flower, wave, ribbon, gem, custom],
  "color": [up to 4 tags from this enum: graphite, smoke, silver, white, pearl, gold, champagne, pink, magenta, red, coral, blue, neon_blue, purple, lavender, green, neon_green, yellow, potato_gold, brown, cream, multi],
  "material": [up to 3 tags from this enum: glossy_resin, jelly_crystal, polished_enamel, pearlescent_lacquer, metal_trim, neon_glow, milky_core, transparent_acrylic, beaded_diamond],
  "composition": [up to 3 tags from this enum: dominant_head_centered, full_body_visible, compact_bottom_cap, cutout_friendly, name_in_core, name_on_nameplate, no_text, single_product, oversized_head, has_pedestal, decoration_floating, wings_attached, crown_on_top, top_ornament],
  "quality": one of [strong, ok, weak] — strong = matches an ideal collectible lightstick; weak = poster/badge/wand/incomplete; ok = otherwise,
  "notes": one short English sentence (max 20 words) describing what is distinctive about this image
}

Only output the JSON object. Do not include any explanation. Do not wrap in code fences."""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(DEFAULT_IMAGE_DIR), help="Directory of images to tag.")
    parser.add_argument("--limit", type=int, default=None, help="Tag only the first N images.")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--force", action="store_true", help="Re-tag images already present in index.json.")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set. export it and re-run.")
    client = Anthropic(api_key=api_key)

    image_dir = Path(args.dir).expanduser()
    if not image_dir.exists():
        sys.exit(f"ERROR: {image_dir} does not exist.")

    existing: dict[str, dict] = {}
    if INDEX_PATH.exists():
        existing = {entry["path"]: entry for entry in json.loads(INDEX_PATH.read_text(encoding="utf-8"))}
        print(f"Loaded {len(existing)} existing entries from {INDEX_PATH.relative_to(REPO)}.")

    images = sorted(p for p in image_dir.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
    if args.limit:
        images = images[: args.limit]
    print(f"Found {len(images)} image(s) in {image_dir.relative_to(REPO)}.")

    todo = []
    for path in images:
        rel = str(path.relative_to(REPO))
        if rel in existing and not args.force:
            continue
        todo.append((path, rel))
    print(f"Tagging {len(todo)} image(s) with {args.model} at concurrency={args.concurrency}.")
    if not todo:
        print("Nothing to do (pass --force to re-tag).")
        return

    new_entries: dict[str, dict] = {}
    failures: list[tuple[str, str]] = []

    def worker(item):
        path, rel = item
        try:
            tags = tag_one(client, args.model, path)
            return rel, tags, None
        except Exception as exc:
            return rel, None, str(exc)

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        for future in as_completed(pool.submit(worker, item) for item in todo):
            rel, tags, error = future.result()
            if error:
                print(f"  ✗ {rel}: {error}")
                failures.append((rel, error))
                continue
            new_entries[rel] = {
                "path": rel,
                "model": args.model,
                **tags,
            }
            print(f"  ✓ {rel}: shape={tags.get('shape')} color={tags.get('color')} quality={tags.get('quality')}")

    merged = {**existing, **new_entries}
    payload = sorted(merged.values(), key=lambda entry: entry["path"])
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {len(payload)} entries to {INDEX_PATH.relative_to(REPO)}.")
    if failures:
        print(f"{len(failures)} failure(s):")
        for rel, error in failures:
            print(f"  {rel}: {error}")


def tag_one(client: Anthropic, model: str, path: Path) -> dict:
    media_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }[path.suffix.lower()]
    encoded = base64.standard_b64encode(path.read_bytes()).decode("ascii")

    response = client.messages.create(
        model=model,
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": encoded},
                    },
                    {"type": "text", "text": "Tag this lightstick reference image. Return JSON only."},
                ],
            }
        ],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(text)


if __name__ == "__main__":
    main()
