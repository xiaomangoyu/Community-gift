from __future__ import annotations

import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import requests

DEFAULT_IMAGE_SIZE = "2048x2048"


class ImageGenerationClient:
    """Seedream HTTP image generation client for the main workflow."""

    def __init__(self, provider: str | None = None) -> None:
        self.provider = self._normalize_provider(provider or os.getenv("IMAGE_PROVIDER") or "seedream_http")

    def generate(
        self,
        prompt: str,
        negative_prompt: str,
        output_dir: Path,
        basename: str,
        reference_images: list[Path] | None = None,
        reference_pairs: list[tuple[Path, str]] | None = None,
        payload_dump_dir: Path | None = None,
    ) -> tuple[list[Path], Path]:
        """Generate one image.

        Args:
            reference_images: simple list of paths; sent as binary_data without
                role descriptions. Uses Seedream PE.
            reference_pairs: (path, role_description) tuples. Bypasses PE and
                writes pre_llm_result with input1/input2/...=role mapping.
                Use this when the caller wants Seedream to treat each
                reference as a distinct role.
            payload_dump_dir: if set, the final conf + reference manifest is
                written to ``<dir>/<basename>.payload.json`` before the HTTP
                call. Image bytes are not duplicated — only their paths.
                Step 6 observability hook.
        """

        output_dir.mkdir(parents=True, exist_ok=True)
        max_attempts = max(1, int(os.getenv("SEEDREAM_RETRY_ATTEMPTS", "2") or 2))
        # Negative-prompt kill switch. Set SEEDREAM_NEGATIVE_PROMPT_ENABLED=0
        # to send an empty negative_prompt (useful for A/B with vs without).
        if os.getenv("SEEDREAM_NEGATIVE_PROMPT_ENABLED", "1").lower() in {"0", "false", "no", "off"}:
            negative_prompt = ""
        raw_path = output_dir / f"{basename}.{self.provider}.json"
        image_paths: list[Path] = []
        if reference_pairs:
            normalized_pairs: list[tuple[Path, str]] = [
                (Path(p), str(role or "")) for p, role in reference_pairs
            ]
        else:
            normalized_pairs = [(Path(p), "") for p in (reference_images or [])]

        if payload_dump_dir is not None:
            self._dump_payload(
                payload_dump_dir, basename, prompt, negative_prompt, normalized_pairs
            )

        for attempt in range(1, max_attempts + 1):
            started = time.monotonic()
            try:
                data = self._generate_seedream(prompt, negative_prompt, normalized_pairs)
            except RuntimeError as exc:
                data = {
                    "ok": False,
                    "error": str(exc),
                    "_community_gift_meta": {
                        "provider": self.provider,
                        "attempt": attempt,
                        "latency_ms": int((time.monotonic() - started) * 1000),
                    },
                }
                raw_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                if attempt < max_attempts and _is_retryable_seedream_error(str(exc)):
                    time.sleep(min(2.0 * attempt, 6.0))
                    continue
                raise

            data["_community_gift_meta"] = {
                "provider": self.provider,
                "attempt": attempt,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            raw_path = output_dir / f"{basename}.{self.provider}.json"
            raw_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            image_paths = self._extract_images(data, output_dir, basename)
            if image_paths:
                return image_paths, raw_path
            if attempt < max_attempts and _is_retryable_empty_response(data):
                time.sleep(min(1.5 * attempt, 4.0))
                continue
            break

        raise RuntimeError(f"{self.provider} returned no image. Raw response: {raw_path}")

    def _dump_payload(
        self,
        dump_dir: Path,
        basename: str,
        prompt: str,
        negative_prompt: str,
        reference_pairs: list[tuple[Path, str]],
    ) -> None:
        """Step 6 dump: mirror the conf the next ``_generate_seedream`` will
        build, write it to disk before the HTTP call.

        Image bytes are referenced by path only (not duplicated). This is
        intentionally tolerant of partial failure: dumping must never break
        generation, so we swallow IOError.
        """

        try:
            req_key = os.getenv("SEEDREAM_REQ_KEY", "tt_vlm_high_aes_scheduler")
            model_version = os.getenv("SEEDREAM_MODEL_VERSION", "general_v4.5")
            pre_vlm_version = os.getenv(
                "SEEDREAM_PRE_VLM_VERSION", "tt_seed_x2i_40l_pe_20b_T2_18"
            )
            cot_mode = os.getenv("SEEDREAM_COT_MODE", "enable")
            width, height = self._parse_size(os.getenv("IMAGE_SIZE", DEFAULT_IMAGE_SIZE))

            pairs = list(reference_pairs or [])[:14]
            has_references = bool(pairs)
            has_role = has_references and any(role.strip() for _, role in pairs)

            conf: dict[str, Any] = {
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
                pre_llm: dict[str, Any] = {
                    "edit": (
                        "You are given one or more reference images. Each input1..N "
                        "below describes one image (same order as attached). Some "
                        "inputs may be lightstick references (use them as design "
                        "language anchors for orientation, proportion, scale, "
                        "material handling, text-embedding). Some inputs may be "
                        "the host's avatar — treat those as colour / mood anchors "
                        "only and never render the person's face. Read each input "
                        "description carefully and obey its specified role. Do NOT "
                        "copy any one reference verbatim; fuse the signals into a "
                        "new lightstick for the host described in `output`."
                    ),
                    "output": prompt,
                    "ratio": ratio,
                }
                for index, (_, role) in enumerate(pairs, start=1):
                    pre_llm[f"input{index}"] = role.strip() or f"reference {index}"
                conf["pre_llm_result"] = json.loads(json.dumps(pre_llm, ensure_ascii=False))
                conf["use_pre_llm"] = False

            payload = {
                "algorithms": req_key,
                "conf": conf,
                "reference_files": [
                    {"name": Path(p).name, "path": str(p), "role": role}
                    for p, role in pairs
                ],
                "input_img_type": "multiple_files" if has_references else None,
            }
            dump_dir.mkdir(parents=True, exist_ok=True)
            (dump_dir / f"{basename}.payload.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _generate_seedream(
        self,
        prompt: str,
        negative_prompt: str,
        reference_pairs: list[tuple[Path, str]] | None = None,
    ) -> dict[str, Any]:
        endpoint = os.getenv("SEEDREAM_HTTP_ENDPOINT")
        req_key = os.getenv("SEEDREAM_REQ_KEY", "tt_vlm_high_aes_scheduler")
        model_version = os.getenv("SEEDREAM_MODEL_VERSION", "general_v4.5")
        pre_vlm_version = os.getenv("SEEDREAM_PRE_VLM_VERSION", "tt_seed_x2i_40l_pe_20b_T2_18")
        cot_mode = os.getenv("SEEDREAM_COT_MODE", "enable")
        ssl_verify = os.getenv("API_SSL_VERIFY", "true").lower() not in {"0", "false", "no"}
        width, height = self._parse_size(os.getenv("IMAGE_SIZE", DEFAULT_IMAGE_SIZE))
        if not endpoint:
            raise ValueError("SEEDREAM_HTTP_ENDPOINT is missing.")

        reference_pairs = list(reference_pairs or [])[:14]
        has_references = bool(reference_pairs)
        has_role_descriptions = has_references and any(role.strip() for _, role in reference_pairs)

        conf: dict[str, Any] = {
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
        if has_role_descriptions:
            # Bypass Seedream's PE so the input1/input2/... → image mapping is
            # honored verbatim. Doc: pre_llm_result format for edit / multi-edit.
            ratio = "1:1" if width == height else f"{width}:{height}"
            pre_llm_payload: dict[str, Any] = {
                "edit": (
                    "Use the following reference lightsticks (each input1..N "
                    "below describes one image in the same order they are "
                    "attached) as multi-aspect anchors for orientation, "
                    "proportion, scale, material handling, text-embedding "
                    "technique, and overall aesthetic. Do NOT copy any one "
                    "reference; fuse the shared design language into a new "
                    "lightstick for the host described in `output`."
                ),
                "output": prompt,
                "ratio": ratio,
            }
            for index, (_, role) in enumerate(reference_pairs, start=1):
                pre_llm_payload[f"input{index}"] = role.strip() or f"reference {index}"
            conf["pre_llm_result"] = json.dumps(pre_llm_payload, ensure_ascii=False)
            conf["use_pre_llm"] = False

        text_fields: dict[str, str] = {
            "algorithms": req_key,
            "conf": json.dumps(conf, ensure_ascii=False, separators=(",", ":")),
        }
        binary_fields: list[tuple[str, str, bytes]] = []
        for image_path, _ in reference_pairs:
            try:
                data_bytes = Path(image_path).read_bytes()
            except OSError as exc:
                raise RuntimeError(f"Cannot read reference image {image_path}: {exc}") from exc
            binary_fields.append(("files[]", Path(image_path).name, data_bytes))
        if has_references:
            text_fields["input_img_type"] = "multiple_files"

        body, content_type = self._encode_multipart(text_fields, binary_fields)
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )
        ssl_ctx = None
        if not ssl_verify:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        try:
            with urllib.request.urlopen(request, timeout=180, context=ssl_ctx) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"seedream_http failed: HTTP {exc.code}: {body_text[:500]}") from exc

    def _extract_images(self, data: dict[str, Any], output_dir: Path, basename: str) -> list[Path]:
        values = self._find_image_values(data)
        paths: list[Path] = []
        seen_values: set[str] = set()
        for index, value in enumerate(values, start=1):
            if value in seen_values:
                continue
            seen_values.add(value)
            path = self._save_image_value(value, output_dir, f"{basename}_{index}")
            if path:
                paths.append(path)
        return paths

    def _find_image_values(self, data: Any) -> list[str]:
        values: list[str] = []
        if isinstance(data, dict):
            afr_data = (data.get("data") or {}).get("afr_data") if isinstance(data.get("data"), dict) else None
            if isinstance(afr_data, list):
                for item in afr_data:
                    if isinstance(item, dict) and isinstance(item.get("pic"), str):
                        values.append(item["pic"])

            for key in ["b64_json", "base64", "image", "image_url", "url", "pic"]:
                value = data.get(key)
                if isinstance(value, str):
                    values.append(value)

            for value in data.values():
                values.extend(self._find_image_values(value))
        elif isinstance(data, list):
            for item in data:
                values.extend(self._find_image_values(item))
        return values

    def _save_image_value(self, value: Any, output_dir: Path, basename: str) -> Path | None:
        if not isinstance(value, str) or not value:
            return None
        if value.startswith(("http://", "https://")):
            response = requests.get(value, timeout=180)
            response.raise_for_status()
            path = output_dir / f"{basename}.png"
            path.write_bytes(response.content)
            return path

        if value.startswith("data:image"):
            value = value.split(",", 1)[-1]

        try:
            image_bytes = base64.b64decode(value)
        except Exception:
            return None

        if not image_bytes.startswith((b"\x89PNG", b"\xff\xd8", b"RIFF")):
            return None
        path = output_dir / f"{basename}.png"
        path.write_bytes(image_bytes)
        return path

    def _parse_size(self, size: str) -> tuple[int, int]:
        parts = size.lower().split("x")
        if len(parts) != 2:
            return 2048, 2048
        return int(parts[0]), int(parts[1])

    def _encode_multipart(
        self,
        text_fields: dict[str, str],
        binary_fields: list[tuple[str, str, bytes]] | None = None,
    ) -> tuple[bytes, str]:
        boundary = f"----community-gift-{uuid.uuid4().hex}"
        body = bytearray()
        for name, value in text_fields.items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            body.extend(value.encode("utf-8"))
            body.extend(b"\r\n")
        for name, filename, data in binary_fields or []:
            mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8")
            )
            body.extend(f"Content-Type: {mime}\r\n\r\n".encode("utf-8"))
            body.extend(data)
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))
        return bytes(body), f"multipart/form-data; boundary={boundary}"

    def _normalize_provider(self, provider: str) -> str:
        value = provider.strip().lower()
        if value in {"seedance", "seedance_image", "seedream", "seedream_http"}:
            return "seedream_http"
        if value in {"modelhub_grok_image", "grok", "grok_image", "grok-imagine-image"}:
            raise ValueError("Grok image generation is disabled. Main workflow only supports seedream_http.")
        raise ValueError(f"Unsupported IMAGE_PROVIDER: {provider}. Main workflow only supports seedream_http.")


def _is_retryable_empty_response(data: dict[str, Any]) -> bool:
    text = json.dumps(data, ensure_ascii=False).lower()
    retry_markers = [
        "queue is full",
        "try again later",
        "timeout",
        "temporarily",
        "rpc process error",
    ]
    return any(marker in text for marker in retry_markers)


def _is_retryable_seedream_error(message: str) -> bool:
    text = message.lower()
    retry_markers = [
        "http 500",
        "http 502",
        "http 503",
        "http 504",
        "gateway time-out",
        "timeout",
        "downstream",
        "remoteconnectionfailure",
        "pool_failure",
    ]
    return any(marker in text for marker in retry_markers)
