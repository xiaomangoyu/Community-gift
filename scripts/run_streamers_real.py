"""Run the streamers/-driven pipeline against Seedream for real.

- Loads .env from the repo root for SEEDREAM_HTTP_ENDPOINT etc.
- Reads ``streamers/<id>/signals.md`` via :func:`read_streamers`.
- Defaults to the 8 ``exceptional`` tier streamers.
- Concurrency = min(rows, 4) — be polite to Seedream.
- Flattens artifacts into outputs/wells_streamers/.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from community_gift.clients.image_client import ImageGenerationClient
from community_gift.clients.modelhub_client import ModelHubGiftClient
from community_gift.effect_library import EffectLibrary
from community_gift.streamers_io import read_streamers
from community_gift.workflow import CommunityGiftWorkflow


TIER_FILTER: set[str] | None = None  # None = all 4 tiers (32 streamers)
OUTPUT_DIR = REPO / "outputs" / "wells_streamers"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCRATCH = OUTPUT_DIR / "_raw"
if SCRATCH.exists():
    shutil.rmtree(SCRATCH)
SCRATCH.mkdir()

hosts = read_streamers(REPO / "streamers", tier_filter=TIER_FILTER)
tier_display = sorted(TIER_FILTER) if TIER_FILTER else "all"
print(f"Loaded {len(hosts)} streamer(s) tier={tier_display}.")
for host in hosts:
    print(f"  row {host.row_id}: {host.host_name!r}")

library = EffectLibrary.load(REPO / "references" / "effects.json")

workflow = CommunityGiftWorkflow(
    openai_client=None,
    image_client=ImageGenerationClient(),
    output_dir=SCRATCH,
    effect_library=library,
    evaluation_threshold=80,
    generation_attempts=1,
    generation_concurrency=min(len(hosts), 6),
    evaluate_images=False,
    vision_client=ModelHubGiftClient(),
)

designs = workflow.build_designs_from_hosts(hosts)
print(f"Built {len(designs)} design(s).")

t0 = time.monotonic()
results = workflow.generate_images(designs)
elapsed = time.monotonic() - t0
print(f"Generated {len(results)} image result(s) in {elapsed:.1f}s wall time.")

img_dir = SCRATCH / "images"
prompt_dir = SCRATCH / "prompts"

for old in OUTPUT_DIR.glob("*_a*.png"):
    old.unlink()
for old in OUTPUT_DIR.glob("*_a*.prompt.txt"):
    old.unlink()
for old in OUTPUT_DIR.glob("*_a*.negative_prompt.txt"):
    old.unlink()

flat_files = []
for png in sorted(img_dir.glob("*_1.png")):
    base = png.stem.removesuffix("_1")
    final_png = OUTPUT_DIR / f"{base}.png"
    final_prompt = OUTPUT_DIR / f"{base}.prompt.txt"
    final_negative = OUTPUT_DIR / f"{base}.negative_prompt.txt"
    shutil.copy2(png, final_png)
    shutil.copy2(prompt_dir / f"{base}.prompt.txt", final_prompt)
    shutil.copy2(prompt_dir / f"{base}.negative_prompt.txt", final_negative)
    flat_files.extend([final_png, final_prompt, final_negative])

for top in [
    "structured_designs.csv",
    "structured_designs.json",
    "generation_results.json",
    "run_summary.md",
    "routing_trace.json",
]:
    src = SCRATCH / top
    if src.exists():
        shutil.copy2(src, OUTPUT_DIR / top)

for subdir in ["host_briefs", "payloads", "composite_inputs", "host_visions"]:
    src = SCRATCH / subdir
    if src.exists():
        dst = OUTPUT_DIR / subdir
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

shutil.rmtree(SCRATCH)

print(f"\nFlattened into {OUTPUT_DIR}:")
for path in sorted(OUTPUT_DIR.iterdir()):
    if path.is_file():
        print(f"  {path.name}  ({path.stat().st_size} B)")
    else:
        total = sum(p.stat().st_size for p in path.rglob('*') if p.is_file())
        print(f"  {path.name}/  ({total} B, {len(list(path.iterdir()))} files)")

print("\nResult summary:")
for result in results:
    name = result.host_name or result.community_name
    img = Path(result.best_image_path).name if result.best_image_path else "<no image>"
    print(f"  row {result.row_id} {name!r}: → {img}")
