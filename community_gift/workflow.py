from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
from pathlib import Path

from .clients.openai_client import GiftOpenAIClient
from .clients.image_client import ImageGenerationClient
from .csv_io import read_hosts, split_list, write_designs_csv, write_designs_json
from .effect_library import EffectLibrary
from .host_brief import HostBrief, RetrievalIntent, build_host_brief, derive_retrieval_intent
from .host_brief_eval import BriefEvalResult, evaluate_brief, repair_brief
from .host_vision import (
    HostVisionBrief,
    load_vision_cache,
    load_vision_override,
    pick_vision_image,
    save_vision_cache,
)
from .models import GenerationResult, GiftDesign, ImageEvaluation
from .prompt_planner import (
    apply_prompt_planning,
    classify_evaluation_failures,
    update_plan_for_retry,
)
from .seedance_prompt import build_reference_negative_prompt, build_reference_seedance_prompt
from .template_first import build_template_first_design


def slugify(value: str) -> str:
    value = value.strip() or "unknown"
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^\w\-\u4e00-\u9fff]+", "", value)
    return value[:80] or "unknown"


class CommunityGiftWorkflow:
    def __init__(
        self,
        openai_client: GiftOpenAIClient,
        image_client: ImageGenerationClient | None,
        output_dir: Path,
        effect_library: EffectLibrary | None = None,
        evaluation_threshold: float = 80,
        generation_attempts: int = 1,
        generation_concurrency: int = 100,
        evaluate_images: bool = False,
        use_legacy_llm_design: bool = False,
        vision_client=None,
    ) -> None:
        self.openai_client = openai_client
        self.image_client = image_client
        self.output_dir = output_dir
        self.effect_library = effect_library
        self.evaluation_threshold = evaluation_threshold
        self.generation_attempts = max(1, generation_attempts)
        self.generation_concurrency = max(1, generation_concurrency)
        self.evaluate_images = evaluate_images
        self.use_legacy_llm_design = use_legacy_llm_design
        # Vision client: must expose ``analyze_host_visual_brief(host) -> HostVisionBrief``.
        # When None, build_host_brief falls back to heuristic-only mode.
        self.vision_client = vision_client

    def build_designs(self, csv_path: Path, max_rows: int | None = None) -> list[GiftDesign]:
        """Read a CSV and build designs. Thin wrapper around :meth:`build_designs_from_hosts`.

        Kept for backward compatibility with scripts that still feed a CSV.
        New entry points (e.g. ``streamers_io.read_streamers``) should call
        :meth:`build_designs_from_hosts` directly.
        """

        hosts = read_hosts(csv_path, max_rows=max_rows)
        csv_dir = csv_path.parent
        for host in hosts:
            if host.host_image and not host.host_image.startswith(("http://", "https://", "data:")):
                image_path = Path(host.host_image).expanduser()
                if not image_path.is_absolute():
                    host.host_image = str((csv_dir / image_path).resolve())
        return self.build_designs_from_hosts(hosts)

    def build_designs_from_hosts(self, hosts: list) -> list[GiftDesign]:
        designs: list[GiftDesign] = []
        briefs: list[HostBrief] = []
        eval_results: list[BriefEvalResult] = []
        intents: list[RetrievalIntent] = []
        vision_briefs: dict[int, HostVisionBrief] = self._analyze_visions(hosts)
        for host in hosts:
            print(f"[{host.row_id}] analyzing: {host.host_name or host.community_name}")
            effect_matches = self.effect_library.match(host) if self.effect_library else []
            if effect_matches:
                matched_names = ", ".join(match.effect_name for match in effect_matches)
                print(f"[{host.row_id}] matched ideal effects: {matched_names}")
            if self.use_legacy_llm_design:
                visual = self.openai_client.analyze_image(host)
                effect_context = (
                    self.effect_library.generation_context(effect_matches)
                    if self.effect_library
                    else []
                )
                design = self.openai_client.create_design(host, visual, effect_context=effect_context)
                design.matched_effects = effect_matches
                _apply_reviewed_design_hints(host, design)
                apply_prompt_planning(host, design, effect_matches)
                if _should_use_reference_lightstick(effect_matches):
                    form_hint = host.body_form or host.content_type or design.recommended_gift_form
                    design.recommended_gift_form = (
                        f"premium full-body personalized lightstick based on {form_hint}"
                        if form_hint
                        else "premium full-body personalized lightstick"
                    )
                    design.seedance_prompt = build_reference_seedance_prompt(design, host)
                    design.seedance_negative_prompt = build_reference_negative_prompt(design)
            else:
                # Step 2: normalize HostInput → HostBrief, with vision overrides.
                vision = vision_briefs.get(host.row_id)
                raw_brief = build_host_brief(host, vision=vision)
                # Step 3: eval (no-op container today) + repair (pass-through)
                eval_result = evaluate_brief(raw_brief)
                repaired_brief = repair_brief(raw_brief, eval_result)
                eval_results.append(eval_result)
                # Step 5: derive retrieval intent for reference search.
                # Default mirrors brief tags; eval/repair will mutate this later.
                intent = derive_retrieval_intent(repaired_brief)
                intents.append(intent)
                # Step 4: feed repaired brief + intent into routers + composite
                design, brief = build_template_first_design(
                    host, effect_matches, brief=repaired_brief, intent=intent
                )
                briefs.append(brief)
            designs.append(design)

        write_designs_csv(designs, self.output_dir / "structured_designs.csv")
        write_designs_json(designs, self.output_dir / "structured_designs.json")
        _write_routing_trace(self.output_dir / "routing_trace.json", designs)
        _write_host_briefs(
            self.output_dir / "host_briefs", briefs, eval_results, intents
        )
        _write_composite_inputs(
            self.output_dir / "composite_inputs", designs, briefs, intents
        )
        _write_vision_briefs(self.output_dir / "host_visions", vision_briefs)
        return designs

    def _analyze_visions(self, hosts: list) -> dict[int, HostVisionBrief]:
        """Build vision briefs, in order of priority:

            1. ``streamers/<id>/vision_override.json``  (designer-edited)
            2. ``outputs/vision_cache/<anchor_id>.json`` (per-input hash)
            3. live ``analyze_host_visual_brief()`` call (then cached)

        Failures are swallowed and logged — heuristic build_host_brief still
        produces a brief, just with empty router-default slots.
        """

        results: dict[int, HostVisionBrief] = {}
        to_analyze: list = []

        for host in hosts:
            override = load_vision_override(host)
            if override is not None:
                results[host.row_id] = override
                print(f"[{host.row_id}] vision: using vision_override.json")
                continue
            image_path, _ = pick_vision_image(host)
            cached = load_vision_cache(host, image_path)
            if cached is not None:
                results[host.row_id] = cached
                print(f"[{host.row_id}] vision: cache hit")
                continue
            to_analyze.append((host, image_path))

        if to_analyze and self.vision_client is None:
            print(
                f"vision_client not configured; {len(to_analyze)} host(s) "
                "will fall back to heuristic build_host_brief."
            )
            return results
        if not to_analyze:
            return results

        workers = min(self.generation_concurrency, max(1, len(to_analyze)))
        print(f"Analyzing {len(to_analyze)} host(s) with vision client (workers={workers}).")

        def _run(host, image_path):
            # One-shot retry — gateway hiccups (HTTP 403/5005 transient) are
            # the dominant failure mode and recover instantly.
            import time as _t
            last_exc: Exception | None = None
            for attempt in range(2):
                try:
                    brief = self.vision_client.analyze_host_visual_brief(host)
                    save_vision_cache(host, image_path, brief)
                    return brief
                except Exception as exc:
                    last_exc = exc
                    if attempt == 0:
                        _t.sleep(2.0)
                        continue
            raise last_exc  # noqa: F821

        if workers <= 1 or len(to_analyze) <= 1:
            for host, image_path in to_analyze:
                try:
                    results[host.row_id] = _run(host, image_path)
                except Exception as exc:
                    print(f"[{host.row_id}] vision analysis failed: {exc}")
            return results
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_run, host, image_path): host
                for host, image_path in to_analyze
            }
            for future in as_completed(futures):
                host = futures[future]
                try:
                    results[host.row_id] = future.result()
                except Exception as exc:
                    print(f"[{host.row_id}] vision analysis failed: {exc}")
        return results

    def generate_images(self, designs: list[GiftDesign]) -> list[GenerationResult]:
        if not self.image_client:
            raise ValueError("Image client is not configured.")

        print(
            f"Generating {len(designs)} row(s) with concurrency "
            f"{min(self.generation_concurrency, len(designs))}."
        )
        if self.generation_concurrency <= 1 or len(designs) <= 1:
            results = [self._generate_one_design(design) for design in designs]
        else:
            results = []
            with ThreadPoolExecutor(
                max_workers=min(self.generation_concurrency, len(designs))
            ) as executor:
                futures = {
                    executor.submit(self._generate_one_design, design): design
                    for design in designs
                }
                for future in as_completed(futures):
                    design = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        print(f"[{design.row_id}] generation failed: {exc}")
                        results.append(_failed_generation_result(design, exc))
            results.sort(key=lambda result: result.row_id)

        results_path = self.output_dir / "generation_results.json"
        results_path.write_text(
            json.dumps([result.model_dump() for result in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _write_run_summary(self.output_dir, results)
        return results

    def _generate_one_design(self, design: GiftDesign) -> GenerationResult:
        image_dir = self.output_dir / "images"
        basename = f"{design.row_id:03d}_{slugify(design.host_name or design.community_name)}"
        effect_context = (
            self.effect_library.evaluation_context(design.matched_effects)
            if self.evaluate_images and self.effect_library
            else []
        )
        prompt = design.seedance_prompt
        all_image_paths = []
        all_evaluations = []
        raw_path = None
        best_image_path = None
        best_score = -1.0

        for attempt in range(1, self.generation_attempts + 1):
            attempt_basename = f"{basename}_a{attempt:02d}"
            print(f"[{design.row_id}] generating image: {attempt_basename}")
            _write_attempt_prompt_log(
                self.output_dir,
                attempt_basename,
                prompt,
                design.seedance_negative_prompt,
            )
            reference_pairs = [
                (Path(path), role)
                for path, role in design.reference_pairs
                if path
            ]
            image_paths, raw_path = self.image_client.generate(
                prompt=prompt,
                negative_prompt=design.seedance_negative_prompt,
                output_dir=image_dir,
                basename=attempt_basename,
                reference_pairs=reference_pairs,
                payload_dump_dir=self.output_dir / "payloads",
            )
            all_image_paths.extend(str(path) for path in image_paths)
            if not best_image_path and image_paths:
                best_image_path = str(image_paths[0])

            attempt_evaluations = []
            if self.evaluate_images and effect_context:
                for image_path in image_paths:
                    print(f"[{design.row_id}] evaluating image: {image_path.name}")
                    try:
                        evaluation = self.openai_client.evaluate_candidate_image(
                            image_path=str(image_path),
                            design=design,
                            effect_context=effect_context,
                        )
                    except Exception as exc:
                        evaluation = ImageEvaluation(
                            image_path=str(image_path),
                            total_score=0,
                            passed=False,
                            verdict="evaluation_failed",
                            issues=[f"VLM evaluation failed: {exc}"],
                            prompt_revision_notes=[],
                        )
                        print(f"[{design.row_id}] evaluation failed: {exc}")
                    evaluation.passed = evaluation.total_score >= self.evaluation_threshold
                    evaluation.failure_types = classify_evaluation_failures(evaluation)
                    attempt_evaluations.append(evaluation)
                    all_evaluations.append(evaluation)
                    if evaluation.total_score > best_score:
                        best_score = evaluation.total_score
                        best_image_path = evaluation.image_path
                if any(evaluation.passed for evaluation in attempt_evaluations):
                    break
                update_plan_for_retry(_host_from_design(design), design, attempt_evaluations)
                if _should_use_reference_lightstick(design.matched_effects):
                    design.seedance_prompt = build_reference_seedance_prompt(design)
                    design.seedance_negative_prompt = build_reference_negative_prompt(design)
                    prompt = design.seedance_prompt
                else:
                    prompt = _revise_prompt(prompt, attempt_evaluations, self.evaluation_threshold)
            else:
                continue

        if not best_image_path and all_image_paths:
            best_image_path = all_image_paths[0]
        return GenerationResult(
            row_id=design.row_id,
            host_name=design.host_name,
            community_name=design.community_name,
            prompt=prompt,
            negative_prompt=design.seedance_negative_prompt,
            image_paths=all_image_paths,
            evaluations=all_evaluations,
            best_image_path=best_image_path,
            raw_response_path=str(raw_path) if raw_path else None,
        )


def _write_routing_trace(output_path: Path, designs: list[GiftDesign]) -> None:
    """Per-row trace of which rule matched in every routing dimension."""

    payload = []
    for design in designs:
        trace = design.routing_trace or {}
        payload.append(
            {
                "row_id": design.row_id,
                "host_name": design.host_name,
                **trace,
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_composite_inputs(
    output_dir: Path,
    designs: list[GiftDesign],
    briefs: list[HostBrief],
    intents: list[RetrievalIntent],
) -> None:
    """One JSON per host: everything that fed the final prompt composition.

    Schema:
      {row_id, host_name, brief, intent, routing_trace,
       final: {seedance_prompt, seedance_negative_prompt, reference_pairs}}

    This is the "what went into composite" view. Pairs with payloads/<id>.payload.json
    (the "what came out, sent to Seedream") for full step-6 observability.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    brief_by_row = {b.row_id: b for b in briefs}
    intent_by_row = {i.row_id: i for i in intents}
    for design in designs:
        brief = brief_by_row.get(design.row_id)
        intent = intent_by_row.get(design.row_id)
        slug = slugify(design.host_name) or f"row{design.row_id}"
        payload = {
            "row_id": design.row_id,
            "host_name": design.host_name,
            "brief": brief.model_dump() if brief else None,
            "intent": intent.model_dump() if intent else None,
            "routing_trace": design.routing_trace,
            "final": {
                "seedance_prompt": design.seedance_prompt,
                "seedance_negative_prompt": design.seedance_negative_prompt,
                "reference_pairs": design.reference_pairs,
            },
        }
        (output_dir / f"{design.row_id:03d}__{slug}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _write_vision_briefs(output_dir: Path, vision_briefs: dict) -> None:
    """One JSON per host: the raw vision LLM output. Inspectable + editable."""

    if not vision_briefs:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    for row_id, brief in vision_briefs.items():
        slug = slugify(brief.host_name) or f"row{row_id}"
        (output_dir / f"{row_id:03d}__{slug}.json").write_text(
            json.dumps(brief.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _write_host_briefs(
    output_dir: Path,
    briefs: list[HostBrief],
    eval_results: list[BriefEvalResult] | None = None,
    intents: list[RetrievalIntent] | None = None,
) -> None:
    """Per host: brief.json + eval.json + intent.json.

    All three are hand-editable artifacts for designers to debug a single
    host's path through the pipeline.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    eval_by_row = {r.row_id: r for r in (eval_results or [])}
    intent_by_row = {i.row_id: i for i in (intents or [])}
    for brief in briefs:
        slug = slugify(brief.host_name) or f"row{brief.row_id}"
        base = f"{brief.row_id:03d}__{slug}"
        (output_dir / f"{base}.json").write_text(
            json.dumps(brief.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result = eval_by_row.get(brief.row_id)
        if result is not None:
            (output_dir / f"{base}.eval.json").write_text(
                json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        intent = intent_by_row.get(brief.row_id)
        if intent is not None:
            (output_dir / f"{base}.intent.json").write_text(
                json.dumps(intent.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )


def _failed_generation_result(design: GiftDesign, exc: Exception) -> GenerationResult:
    return GenerationResult(
        row_id=design.row_id,
        host_name=design.host_name,
        community_name=design.community_name,
        prompt=design.seedance_prompt,
        negative_prompt=design.seedance_negative_prompt,
        image_paths=[],
        evaluations=[
            ImageEvaluation(
                image_path="",
                total_score=0,
                passed=False,
                verdict="generation_failed",
                issues=[str(exc)],
                failure_types=["generation_fail"],
            )
        ],
        best_image_path=None,
        raw_response_path=None,
    )


def _should_use_reference_lightstick(effect_matches) -> bool:
    return any(
        match.effect_id == "strong_heart_lightstick_product_series"
        for match in effect_matches
    )


def _apply_reviewed_design_hints(host, design: GiftDesign) -> None:
    if host.material_language_hint:
        hints = split_list(host.material_language_hint)
        design.material_language = _prepend_unique(hints, design.material_language)
    if host.decoration_intensity:
        design.complexity_rules = _prepend_unique(
            [f"reviewed decoration intensity: {host.decoration_intensity}"],
            design.complexity_rules,
        )


def _prepend_unique(prefix: list[str], values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in [*prefix, *values]:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        output.append(item)
        seen.add(key)
    return output


def _revise_prompt(prompt: str, evaluations, threshold: float) -> str:
    if not evaluations:
        return prompt
    best = max(evaluations, key=lambda item: item.total_score)
    notes = best.prompt_revision_notes or best.issues
    if not notes:
        return prompt
    revision = " ".join(notes[:6])
    return (
        prompt
        + f"\n\nRevision for next attempt because VLM score {best.total_score:.1f} is below {threshold:.1f}: "
        + revision
        + " Highest priority: pure black background, full-body product visibility, no cropping, compact bottom cap fully visible with black margin below."
    )


def _host_from_design(design: GiftDesign):
    """Small compatibility shim for retry planning when the original HostInput is out of scope."""

    from .models import HostInput

    return HostInput(
        row_id=design.row_id,
        host_name=design.host_name,
        community_name=design.community_name,
        symbols=design.prompt_plan.retained_elements,
        banned_elements=design.prompt_plan.banned_elements,
        primary_color=", ".join(design.prompt_plan.color_terms),
        material_language_hint=", ".join(design.prompt_plan.material_terms),
        body_form=design.design_concept.silhouette,
        recommended_output_type=design.design_concept.effect_type,
    )


def _write_attempt_prompt_log(
    output_dir: Path,
    attempt_basename: str,
    prompt: str,
    negative_prompt: str,
) -> None:
    prompt_dir = output_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / f"{attempt_basename}.prompt.txt").write_text(prompt, encoding="utf-8")
    (prompt_dir / f"{attempt_basename}.negative_prompt.txt").write_text(
        negative_prompt,
        encoding="utf-8",
    )


def _write_run_summary(output_dir: Path, results: list[GenerationResult]) -> None:
    lines = [
        "# Run Summary",
        "",
        "| Row | Host | Best image | Best score | Passed | Failure types |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for result in results:
        best_eval = None
        if result.evaluations:
            best_eval = max(result.evaluations, key=lambda item: item.total_score)
        score = f"{best_eval.total_score:.1f}" if best_eval else ""
        passed = str(best_eval.passed) if best_eval else ""
        failures = ", ".join(best_eval.failure_types) if best_eval else ""
        lines.append(
            "| {row} | {host} | {image} | {score} | {passed} | {failures} |".format(
                row=result.row_id,
                host=(result.host_name or result.community_name).replace("|", "\\|"),
                image=result.best_image_path or "",
                score=score,
                passed=passed,
                failures=failures,
            )
        )

    lines.extend(["", "## Attempt Details", ""])
    for result in results:
        lines.append(f"### {result.row_id}. {result.host_name or result.community_name}")
        if not result.evaluations:
            lines.append("")
            lines.append("No VLM evaluation was recorded.")
            lines.append("")
            continue
        for evaluation in result.evaluations:
            lines.append("")
            lines.append(
                f"- `{Path(evaluation.image_path).name}`: score {evaluation.total_score:.1f}, "
                f"passed={evaluation.passed}, failures={', '.join(evaluation.failure_types) or 'none'}"
            )
            if evaluation.verdict:
                lines.append(f"  Verdict: {evaluation.verdict}")
            if evaluation.issues:
                issue_text = "; ".join(evaluation.issues[:4])
                lines.append(f"  Issues: {issue_text}")
            if evaluation.prompt_revision_notes:
                note_text = "; ".join(evaluation.prompt_revision_notes[:4])
                lines.append(f"  Next: {note_text}")
        lines.append("")

    (output_dir / "run_summary.md").write_text("\n".join(lines), encoding="utf-8")
