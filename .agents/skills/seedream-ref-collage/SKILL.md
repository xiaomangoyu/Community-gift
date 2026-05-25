---
name: seedream-ref-collage
description: Create polished visual collage boards and reference-image usage statistics for Community Gifts Seedream streamer batches and references/imgs libraries. Use when the user asks to combine generated streamer/lightstick images, show which references were used, make a gallery/contact sheet, summarize ref image hits, make a reference image collection/demo board, or reuse the Seedream 4.5 batch display style.
---

# Seedream Ref Collage

## Quick Start

Use the bundled reference-library script when the user asks for a combined board of `references/imgs`:

```bash
python3 .agents/skills/seedream-ref-collage/scripts/build_reference_image_collage.py
```

It writes:

```text
references/imgs/REFERENCE_COLLAGE.png
```

Use the project script whenever a Seedream batch output directory contains:

```text
<output-dir>/routing_trace.json
<output-dir>/images/*_1.png
```

For `gpt-image-2` / `gpt_image_2` batches, do not show reference thumbnails in
the final board unless the run explicitly used the image edit endpoint with
uploaded reference images. Use `--hide-references` (or set
`--model-label gpt-image-2`, which is auto-detected) so the board is a
generated-image gallery rather than a reference map.

Run on a specific batch:

```bash
python3 scripts/build_seedream_ref_collage.py outputs/seedream45_streamers32_20260522
```

Run on the newest `outputs/*` directory that has `routing_trace.json`:

```bash
python3 scripts/build_seedream_ref_collage.py
```

The script writes:

```text
<output-dir>/streamers32_seedream45_ref_collage.png
<output-dir>/ref_image_usage_summary.md
<output-dir>/ref_image_usage.csv
<output-dir>/ref_image_usage.json
```

## Reference Library Board

For a different references folder or output name:

```bash
python3 .agents/skills/seedream-ref-collage/scripts/build_reference_image_collage.py \
  --refs-dir references/imgs \
  --output references/imgs/REFERENCE_COLLAGE.png \
  --columns 5
```

The script reads `manifest.yaml` when present, keeps manifest order, appends image files not listed in the manifest, and skips existing `REFERENCE_*COLLAGE*` outputs so old boards do not get tiled into new boards.

## Full Batch Workflow

If the user asks to generate a fresh 32-streamer Seedream 4.5 batch and then make the board:

```bash
SEEDREAM_MODEL_VERSION=general_v4.5 \
IMAGE_PROVIDER=seedream_http \
IMAGE_SIZE=2048x2048 \
REFERENCE_TOP_N=1 \
python3 scripts/run_streamers_debug_preview.py \
  --start 0 \
  --count 32 \
  --concurrency 6 \
  --output-dir outputs/<batch_name>

python3 scripts/build_seedream_ref_collage.py outputs/<batch_name>
```

Use lower concurrency, usually `--concurrency 1`, to retry a single failed row if Seedream returns a transient queue/limit error:

```bash
SEEDREAM_MODEL_VERSION=general_v4.5 \
IMAGE_PROVIDER=seedream_http \
IMAGE_SIZE=2048x2048 \
REFERENCE_TOP_N=1 \
python3 scripts/run_streamers_debug_preview.py \
  --start <zero_based_offset> \
  --count 1 \
  --concurrency 1 \
  --output-dir outputs/<batch_name>_retry<row>
```

After a successful retry, copy the retry image and raw response into the main batch `images/` directory, then rerun `scripts/build_seedream_ref_collage.py` on the main batch.

## Style Controls

Use these optional flags for variants:

```bash
python3 scripts/build_seedream_ref_collage.py outputs/<batch_name> \
  --columns 4 \
  --title "Seedream 4.5 Streamers x Reference Map" \
  --subtitle "generated images with selected references" \
  --output-name streamers32_seedream45_ref_collage.png
```

For image2 generated-only galleries:

```bash
python3 scripts/build_seedream_ref_collage.py outputs/<batch_name> \
  --columns 4 \
  --title "GPT Image 2 Streamers" \
  --subtitle "generated lightstick images" \
  --model-label gpt-image-2 \
  --hide-references \
  --output-name image2_gallery.png
```

Keep the default Seedream style for this project unless the user requests a different format: dark dashboard background, 4 columns, large generated image, row chip, host name, selected ref thumbnail, ref id, source image name, score, and matched dimensions. For image2 generated-only runs, hide the reference area and use the same card style as a plain gallery.

## Validation

Before final response:

1. Confirm `images/*_1.png` count matches the intended row count.
2. Open the collage image with `view_image` and check that cards are not cropped or overlapping.
3. Read the top of `ref_image_usage_summary.md` and report the highest-count refs.
4. Mention any missing rows or Seedream failures clearly.
