"""Run the default pipeline against Seedream for real, with parallel generation.

- Loads .env from the repo root for SEEDREAM_HTTP_ENDPOINT etc.
- Uses real ImageGenerationClient (HTTP).
- Concurrency = 5 (= number of rows).
- Flattens artifacts into outputs/wells/ with same basename for prompt + image.
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
from community_gift.csv_io import read_hosts
from community_gift.effect_library import EffectLibrary
from community_gift.workflow import CommunityGiftWorkflow


SRC_CSV = REPO / "examples" / "host_design_params_simplified.csv"
WELLS_DIR = REPO / "outputs" / "wells"
WELLS_DIR.mkdir(parents=True, exist_ok=True)

src_lines = SRC_CSV.read_text(encoding="utf-8").splitlines()
header = src_lines[0]
rows = [line for line in src_lines[1:] if line.strip()][:5]
wells_csv = WELLS_DIR / "input.csv"
wells_csv.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
print(f"Wrote input CSV with {len(rows)} row(s) → {wells_csv}")

SCRATCH = WELLS_DIR / "_raw"
if SCRATCH.exists():
    shutil.rmtree(SCRATCH)
SCRATCH.mkdir()

hosts = read_hosts(wells_csv)
print(f"Loaded {len(hosts)} host(s).")

library = EffectLibrary.load(REPO / "references" / "effects.json")

workflow = CommunityGiftWorkflow(
    openai_client=None,
    image_client=ImageGenerationClient(),
    output_dir=SCRATCH,
    effect_library=library,
    evaluation_threshold=80,
    generation_attempts=1,
    generation_concurrency=5,
    evaluate_images=False,
)

designs = workflow.build_designs(wells_csv)
print(f"Built {len(designs)} design(s).")

t0 = time.monotonic()
results = workflow.generate_images(designs)
elapsed = time.monotonic() - t0
print(f"Generated {len(results)} image result(s) in {elapsed:.1f}s wall time.")

# Flatten outputs/wells/_raw/{images,prompts}/* into outputs/wells/
img_dir = SCRATCH / "images"
prompt_dir = SCRATCH / "prompts"

# Clear old per-row artifacts in wells/ before copying fresh ones
for old in WELLS_DIR.glob("*_a*.png"):
    old.unlink()
for old in WELLS_DIR.glob("*_a*.prompt.txt"):
    old.unlink()
for old in WELLS_DIR.glob("*_a*.negative_prompt.txt"):
    old.unlink()

flat_files = []
for png in sorted(img_dir.glob("*_1.png")):
    base = png.stem.removesuffix("_1")
    final_png = WELLS_DIR / f"{base}.png"
    final_prompt = WELLS_DIR / f"{base}.prompt.txt"
    final_negative = WELLS_DIR / f"{base}.negative_prompt.txt"
    shutil.copy2(png, final_png)
    shutil.copy2(prompt_dir / f"{base}.prompt.txt", final_prompt)
    shutil.copy2(prompt_dir / f"{base}.negative_prompt.txt", final_negative)
    flat_files.extend([final_png, final_prompt, final_negative])

for top in ["structured_designs.csv", "structured_designs.json", "generation_results.json", "run_summary.md", "routing_trace.json"]:
    src = SCRATCH / top
    if src.exists():
        shutil.copy2(src, WELLS_DIR / top)

shutil.rmtree(SCRATCH)

print(f"\nFlattened into {WELLS_DIR}:")
for path in sorted(WELLS_DIR.iterdir()):
    size = path.stat().st_size
    print(f"  {path.name}  ({size} B)")

# Quick result summary
print("\nResult summary:")
for result in results:
    name = result.host_name or result.community_name
    img = Path(result.best_image_path).name if result.best_image_path else "<no image>"
    status = "ok" if result.best_image_path and not result.evaluations else (
        "failed" if result.evaluations and result.evaluations[0].verdict == "generation_failed" else "ok"
    )
    print(f"  row {result.row_id} {name!r}: {status}  → {img}")
