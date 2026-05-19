"""Mock the streamers/-driven pipeline (no CSV) and flatten artifacts.

- Reads ``streamers/<id>/signals.md`` via :func:`read_streamers`.
- Defaults to the 8 ``exceptional`` tier streamers.
- Substitutes a fake image_client so we get .png placeholders without HTTP.
- Reuses ``ImageGenerationClient._dump_payload`` for step-6 observability so
  we can inspect what would have gone to Seedream (incl. avatar reference).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path("/Users/bytedance/Documents/Community_Gifts_v02/Main")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from community_gift.clients.image_client import ImageGenerationClient
from community_gift.clients.modelhub_client import ModelHubGiftClient
from community_gift.effect_library import EffectLibrary
from community_gift.streamers_io import read_streamers
from community_gift.workflow import CommunityGiftWorkflow


TIER_FILTER = {"exceptional"}  # change here to broaden the mock run
OUTPUT_DIR = REPO / "outputs" / "wells_streamers"


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


OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCRATCH = OUTPUT_DIR / "_raw"
if SCRATCH.exists():
    shutil.rmtree(SCRATCH)
SCRATCH.mkdir()

hosts = read_streamers(REPO / "streamers", tier_filter=TIER_FILTER)
print(f"Loaded {len(hosts)} streamer(s) tier={sorted(TIER_FILTER)}:")
for host in hosts:
    avatar = Path(host.host_image).name if host.host_image else "(no avatar)"
    print(
        f"  row {host.row_id}: {host.host_name!r}  comm={host.community_name!r}  "
        f"symbols={host.symbols[:3]}…  avatar={avatar}"
    )

library = EffectLibrary.load(REPO / "references" / "effects.json")
print(f"Loaded {len(library.effects)} effect card(s).")

workflow = CommunityGiftWorkflow(
    openai_client=None,
    image_client=FakeImageClient(),
    output_dir=SCRATCH,
    effect_library=library,
    evaluation_threshold=80,
    generation_attempts=1,
    generation_concurrency=4,
    evaluate_images=False,
    vision_client=ModelHubGiftClient(),
)

designs = workflow.build_designs_from_hosts(hosts)
print(f"Built {len(designs)} design(s).")

results = workflow.generate_images(designs)
print(f"Generated {len(results)} fake image result(s).")

# Flatten: copy image + prompt + negative into the output root for at-a-glance review.
img_dir = SCRATCH / "images"
prompt_dir = SCRATCH / "prompts"
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
        flat_files.append(OUTPUT_DIR / top)

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
    size = path.stat().st_size if path.is_file() else sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    kind = "/" if path.is_dir() else ""
    print(f"  {path.name}{kind}  ({size} B)")
