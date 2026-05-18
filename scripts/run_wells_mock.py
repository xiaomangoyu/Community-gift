"""Mock 5 rows through the default pipeline and flatten artifacts into outputs/wells/.

- Does NOT modify any source code in community_gift/.
- Uses default template-first design path.
- Substitutes a fake image_client so we get .png placeholders without HTTP calls.
- After the run, copies prompts + images into a single flat folder (outputs/wells/),
  same basename for the prompt txt and the image.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path("/Users/bytedance/Documents/Community_Gifts_v02/Main")
sys.path.insert(0, str(REPO))

from community_gift.clients.image_client import ImageGenerationClient
from community_gift.csv_io import read_hosts
from community_gift.effect_library import EffectLibrary
from community_gift.template_first import build_template_first_design
from community_gift.workflow import CommunityGiftWorkflow


class FakeImageClient:
    """Stand-in for ImageGenerationClient: writes a tiny placeholder PNG.

    Reuses the real client's ``_dump_payload`` so the step-6 observability
    artifact is generated in mock runs too.
    """

    _payload_dumper = ImageGenerationClient(provider="seedream_http")

    def generate(
        self,
        prompt,
        negative_prompt,
        output_dir,
        basename,
        reference_pairs=None,
        payload_dump_dir=None,
        **_ignored,
    ):
        if payload_dump_dir is not None:
            pairs = [(Path(p), role) for p, role in (reference_pairs or [])]
            self._payload_dumper._dump_payload(
                payload_dump_dir, basename, prompt, negative_prompt, pairs
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        png_path = output_dir / f"{basename}_1.png"
        # 1x1 transparent PNG so the file is a real (tiny) PNG, not garbage bytes
        png_path.write_bytes(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
                "890000000d49444154789c63000100000005000100"
                "0d0a2db40000000049454e44ae426082"
            )
        )
        raw_path = output_dir / f"{basename}_raw.json"
        raw_path.write_text('{"mock": true}', encoding="utf-8")
        return [png_path], raw_path


# Stage the input CSV: take first 5 rows from host_design_params_simplified.csv
SRC_CSV = REPO / "examples" / "host_design_params_simplified.csv"
WELLS_DIR = REPO / "outputs" / "wells"
WELLS_DIR.mkdir(parents=True, exist_ok=True)

src_lines = SRC_CSV.read_text(encoding="utf-8").splitlines()
header = src_lines[0]
rows = [line for line in src_lines[1:] if line.strip()][:5]
wells_csv = WELLS_DIR / "input.csv"
wells_csv.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
print(f"Wrote input CSV with {len(rows)} row(s) → {wells_csv}")

# Run the workflow into a scratch dir, then flatten into outputs/wells/
SCRATCH = WELLS_DIR / "_raw"
if SCRATCH.exists():
    shutil.rmtree(SCRATCH)
SCRATCH.mkdir()

hosts = read_hosts(wells_csv)
print(f"Loaded {len(hosts)} host(s):")
for host in hosts:
    print(f"  row {host.row_id}: {host.host_name!r}  symbols={host.symbols}  primary={host.primary_color!r}")

library = EffectLibrary.load(REPO / "references" / "effects.json")
print(f"Loaded {len(library.effects)} effect card(s).")

workflow = CommunityGiftWorkflow(
    openai_client=None,
    image_client=FakeImageClient(),
    output_dir=SCRATCH,
    effect_library=library,
    evaluation_threshold=80,
    generation_attempts=1,
    generation_concurrency=1,
    evaluate_images=False,
    use_legacy_llm_design=False,
)

designs = workflow.build_designs(wells_csv)
print(f"Built {len(designs)} design(s).")

results = workflow.generate_images(designs)
print(f"Generated {len(results)} fake image result(s).")

# Flatten: move images/* and prompts/* into outputs/wells/ with matched basenames.
# Drop the trailing "_1" so the image and its prompt share the exact same basename.
img_dir = SCRATCH / "images"
prompt_dir = SCRATCH / "prompts"

flat_files = []
for png in sorted(img_dir.glob("*_1.png")):
    base = png.stem.removesuffix("_1")  # e.g. 001_Linda_Passarinheira_a01
    final_png = WELLS_DIR / f"{base}.png"
    final_prompt = WELLS_DIR / f"{base}.prompt.txt"
    final_negative = WELLS_DIR / f"{base}.negative_prompt.txt"

    shutil.copy2(png, final_png)
    shutil.copy2(prompt_dir / f"{base}.prompt.txt", final_prompt)
    shutil.copy2(prompt_dir / f"{base}.negative_prompt.txt", final_negative)
    flat_files.extend([final_png, final_prompt, final_negative])

# Keep top-level structured outputs in wells/ too
for top in ["structured_designs.csv", "structured_designs.json", "generation_results.json", "run_summary.md", "routing_trace.json"]:
    src = SCRATCH / top
    if src.exists():
        shutil.copy2(src, WELLS_DIR / top)
        flat_files.append(WELLS_DIR / top)

# Pipeline-intermediate artifacts: per-host brief / eval / intent / payload.
for subdir in ["host_briefs", "payloads", "composite_inputs"]:
    src = SCRATCH / subdir
    if src.exists():
        dst = WELLS_DIR / subdir
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

# Clean the scratch
shutil.rmtree(SCRATCH)

print(f"\nFlattened into {WELLS_DIR}:")
for path in sorted(WELLS_DIR.iterdir()):
    size = path.stat().st_size
    print(f"  {path.name}  ({size} B)")
