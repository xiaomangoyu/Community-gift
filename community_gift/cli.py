from __future__ import annotations

import argparse
import os
from pathlib import Path

from .clients.image_client import ImageGenerationClient
from .clients.openai_client import GiftOpenAIClient
from .config import load_settings
from .effect_library import EffectLibrary
from .workflow import CommunityGiftWorkflow

DEFAULT_IMAGE_SIZE = "2048x2048"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Community gift design workflow MVP.")
    parser.add_argument("--csv", required=True, help="Input CSV path.")
    parser.add_argument("--env", default=None, help="Optional .env path.")
    parser.add_argument("--output-dir", default=None, help="Override output directory.")
    parser.add_argument("--max-rows", type=int, default=None, help="Limit rows for testing.")
    parser.add_argument("--dry-run", action="store_true", help="Only build designs and prompts.")
    parser.add_argument("--mock", action="store_true", help="Run without external API calls.")
    parser.add_argument(
        "--image-provider",
        default=None,
        help="Image provider override. Main workflow only supports seedream_http aliases.",
    )
    parser.add_argument("--image-size", default=None, help="Square image size override, e.g. 2048x2048.")
    parser.add_argument(
        "--effect-library",
        default="references/effects.json",
        help="Structured ideal-effect library JSON. Use an empty path to disable.",
    )
    parser.add_argument(
        "--evaluation-threshold",
        type=float,
        default=80,
        help="Minimum VLM score for an image to pass ideal-effect evaluation.",
    )
    parser.add_argument(
        "--generation-attempts",
        type=int,
        default=1,
        help="Generate/evaluate/revise attempts per row.",
    )
    parser.add_argument(
        "--generation-concurrency",
        type=int,
        default=None,
        help="Maximum rows to generate/evaluate in parallel. Defaults to GENERATION_CONCURRENCY or 100.",
    )
    parser.add_argument(
        "--evaluate-images",
        action="store_true",
        help="Enable VLM image evaluation/retry. Default is off; pass/fail is decided manually.",
    )
    parser.add_argument(
        "--legacy-llm-design",
        action="store_true",
        help="Use the old LLM/planner design orchestration path. Default is template-first.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings(args.env)
    if args.image_size:
        _validate_square_image_size(args.image_size)
        os.environ["IMAGE_SIZE"] = args.image_size
    elif not args.dry_run:
        _validate_square_image_size(
            os.getenv("SEEDANCE_SIZE") or os.getenv("IMAGE_SIZE", DEFAULT_IMAGE_SIZE)
        )
        os.environ.setdefault("IMAGE_SIZE", DEFAULT_IMAGE_SIZE)
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else settings.output_dir
    max_rows = args.max_rows if args.max_rows is not None else settings.max_rows
    generation_concurrency = (
        args.generation_concurrency
        if args.generation_concurrency is not None
        else int(os.getenv("GENERATION_CONCURRENCY", "100") or 100)
    )
    evaluate_images = args.evaluate_images or os.getenv("ENABLE_VLM_EVALUATION", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if args.mock:
        from .clients.mock_client import MockGiftClient

        openai_client = MockGiftClient()
    else:
        if settings.openai_api_key:
            openai_client = GiftOpenAIClient(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
            )
        else:
            from .clients.modelhub_client import ModelHubGiftClient

            openai_client = ModelHubGiftClient()
    image_client = None
    if not args.dry_run and not args.mock:
        image_client = ImageGenerationClient(provider=args.image_provider)
    elif not args.dry_run and args.mock:
        print("Mock mode skips image generation. Use without --mock after env is configured.")

    effect_library_path = Path(args.effect_library).expanduser() if args.effect_library else None
    effect_library = EffectLibrary.load(effect_library_path)
    if effect_library:
        print(f"Loaded {len(effect_library.effects)} ideal effect(s) from {effect_library_path}")

    workflow = CommunityGiftWorkflow(
        openai_client=openai_client,
        image_client=image_client,
        output_dir=output_dir,
        effect_library=effect_library,
        evaluation_threshold=args.evaluation_threshold,
        generation_attempts=args.generation_attempts,
        generation_concurrency=generation_concurrency,
        evaluate_images=evaluate_images,
        use_legacy_llm_design=args.legacy_llm_design,
    )
    designs = workflow.build_designs(Path(args.csv).expanduser(), max_rows=max_rows)
    if args.dry_run:
        print(f"Built {len(designs)} design(s). Outputs saved to {output_dir}")
        return

    results = workflow.generate_images(designs)
    print(f"Generated {len(results)} image result(s). Outputs saved to {output_dir}")


def _validate_square_image_size(size: str) -> None:
    parts = size.lower().split("x")
    if len(parts) != 2:
        raise ValueError(f"IMAGE_SIZE must use WIDTHxHEIGHT format, got: {size}")
    width, height = (int(part) for part in parts)
    if width != height:
        raise ValueError(
            f"Main workflow images must be 1:1 square. Got {size}; use e.g. 2048x2048."
        )


if __name__ == "__main__":
    main()
