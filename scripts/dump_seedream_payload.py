"""Dump what image_client actually sends to Seedream, without making a request.

Re-runs image_client._generate_seedream() up to the multipart encoding step,
then writes:
  /tmp/seedream_payload/<host>/conf.json         — full conf dict
  /tmp/seedream_payload/<host>/pre_llm_result.json — parsed pre_llm_result
  /tmp/seedream_payload/<host>/manifest.txt      — multipart field summary
  /tmp/seedream_payload/<host>/multipart_body.bin — raw bytes that would POST
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from community_gift.clients.image_client import ImageGenerationClient  # noqa: E402

DESIGNS = ROOT / "outputs" / "wells" / "structured_designs.json"
OUT_ROOT = Path("/tmp/seedream_payload")

os.environ.setdefault("SEEDREAM_HTTP_ENDPOINT", "https://placeholder.invalid")


def main() -> None:
    designs = json.loads(DESIGNS.read_text(encoding="utf-8"))
    client = ImageGenerationClient(provider="seedream_http")

    for design in designs:
        row_id = design["row_id"]
        host_name = design["host_name"]
        slug = f"{row_id:03d}_{_safe_slug(host_name)}"
        target = OUT_ROOT / slug
        target.mkdir(parents=True, exist_ok=True)

        prompt = design["seedance_prompt"]
        negative = design["seedance_negative_prompt"]
        pairs = [(Path(p), role) for p, role in design.get("reference_pairs", [])]

        conf, text_fields, binary_summary, body, content_type = _build_payload(
            client, prompt, negative, pairs
        )

        (target / "conf.json").write_text(
            json.dumps(conf, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        pre_llm = conf.get("pre_llm_result")
        if pre_llm:
            (target / "pre_llm_result.json").write_text(
                json.dumps(json.loads(pre_llm), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        manifest_lines = [
            f"host_name      = {host_name}",
            f"content_type   = {content_type}",
            f"use_pre_llm    = {conf.get('use_pre_llm', '(default)')}",
            f"reference imgs = {len(pairs)}",
            "",
            "[text fields]",
            *(f"  {name} ({len(value)} chars)" for name, value in text_fields.items()),
            "",
            "[binary fields]",
            *(f"  {name}  filename={fn}  bytes={size}" for name, fn, size in binary_summary),
            "",
            f"[multipart body]",
            f"  total bytes = {len(body)}",
        ]
        (target / "manifest.txt").write_text("\n".join(manifest_lines), encoding="utf-8")
        (target / "multipart_body.bin").write_bytes(body)

        print(f"[ok] {slug}  conf-keys={list(conf.keys())}  body={len(body):,}B")


def _build_payload(
    client: ImageGenerationClient,
    prompt: str,
    negative_prompt: str,
    reference_pairs: list[tuple[Path, str]],
) -> tuple[dict, dict, list, bytes, str]:
    """Mirror image_client._generate_seedream() exactly, minus the HTTP send."""

    req_key = os.getenv("SEEDREAM_REQ_KEY", "tt_vlm_high_aes_scheduler")
    model_version = os.getenv("SEEDREAM_MODEL_VERSION", "general_v4.5")
    pre_vlm_version = os.getenv("SEEDREAM_PRE_VLM_VERSION", "tt_seed_x2i_40l_pe_20b_T2_18")
    cot_mode = os.getenv("SEEDREAM_COT_MODE", "enable")
    width, height = client._parse_size(os.getenv("IMAGE_SIZE", "2048x2048"))

    reference_pairs = list(reference_pairs)[:14]
    has_references = bool(reference_pairs)
    has_role = has_references and any(role.strip() for _, role in reference_pairs)

    conf: dict = {
        "prompt": prompt,
        "model_version": model_version,
        "pre_vlm_version": pre_vlm_version,
        "width": width,
        "height": height,
        "negative_prompt": negative_prompt,
        "seed": -1,
        "force_single": True,
        "cot_mode": cot_mode,
    }
    if has_role:
        ratio = "1:1" if width == height else f"{width}:{height}"
        pre_llm = {
            "edit": (
                "Use the following reference lightsticks (each input1..N below "
                "describes one image in the same order they are attached) as "
                "multi-aspect anchors for orientation, proportion, scale, "
                "material handling, text-embedding technique, and overall "
                "aesthetic. Do NOT copy any one reference; fuse the shared "
                "design language into a new lightstick for the host described "
                "in `output`."
            ),
            "output": prompt,
            "ratio": ratio,
        }
        for index, (_, role) in enumerate(reference_pairs, start=1):
            pre_llm[f"input{index}"] = role.strip() or f"reference {index}"
        conf["pre_llm_result"] = json.dumps(pre_llm, ensure_ascii=False)
        conf["use_pre_llm"] = False

    text_fields: dict[str, str] = {
        "algorithms": req_key,
        "conf": json.dumps(conf, ensure_ascii=False, separators=(",", ":")),
    }
    binary_fields: list[tuple[str, str, bytes]] = []
    binary_summary: list[tuple[str, str, int]] = []
    for image_path, _ in reference_pairs:
        data_bytes = Path(image_path).read_bytes()
        binary_fields.append(("files[]", Path(image_path).name, data_bytes))
        binary_summary.append(("files[]", Path(image_path).name, len(data_bytes)))
    if has_references:
        text_fields["input_img_type"] = "multiple_files"

    body, content_type = client._encode_multipart(text_fields, binary_fields)
    return conf, text_fields, binary_summary, body, content_type


def _safe_slug(text: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in text)
    return safe.strip("_")[:40] or "host"


if __name__ == "__main__":
    main()
