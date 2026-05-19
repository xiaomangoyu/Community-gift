"""Reference (视觉锚点) dimension router.

Reads references/imgs/manifest.yaml. Scores every reference against host
signals, returns top-N (default 3). Falls back to seeded random sampling
from the quality:strong pool when nothing matches.

Why multi-image instead of 1:1?
  - References carry more than thematic content; orientation, proportion,
    scale, "悬浮在黑棚" framing, and "干净商业海报感" aesthetics are universal
    visual constants every host can benefit from.
  - 1 reference biases the output toward that reference's palette. 3 averages
    out single-reference bias while still keeping a thematic tilt.
  - Seedream binary_data caps at 14; 3 leaves plenty of headroom and is
    cheap to send.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .base import RouteDecision, RouteTraceEntry


REFERENCE_MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent.parent / "references" / "imgs" / "manifest.yaml"
)

# Scoring weights — kept literal so they're easy to tweak from yaml later.
WEIGHTS = {
    "shape": 3.0,
    "color": 2.0,
    "material": 1.0,
    "vibe": 1.0,
    "text": 1.0,
}
STRONG_QUALITY_BONUS = 0.5
WEAK_TEXT_ONLY_TAGS = {"latin", "short", "long"}
GENERIC_VIBE_TAGS = {"energetic", "powerful", "dramatic", "idol_support"}


@dataclass
class ReferencePick:
    id: str
    image_path: str
    role_description: str
    score: float
    matched_tags: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class ReferenceDecision:
    picks: list[ReferencePick]
    fallback_used: bool
    top_n: int


class ReferenceRouter:
    dimension = "reference"

    def __init__(
        self,
        manifest_path: Path = REFERENCE_MANIFEST_PATH,
        top_n: int = 3,
    ) -> None:
        self.manifest_path = manifest_path
        self.references = _load_manifest(manifest_path)
        self.top_n = max(1, top_n)

    def route(self, context: dict[str, Any]) -> RouteDecision:
        if not self.references:
            return RouteDecision(
                dimension="reference",
                matched_rule_id="empty_manifest",
                fields={"picks": [], "fallback_used": False, "top_n": self.top_n},
                trace=[],
            )

        host_signals = _extract_host_signals(context)
        scored: list[tuple[float, dict[str, list[str]], dict[str, Any]]] = []
        trace: list[RouteTraceEntry] = []
        for entry in self.references:
            score, matched = _score(entry, host_signals)
            weak_text_only = _is_weak_text_only_match(matched)
            weak_generic = _is_weak_generic_match(matched)
            trace.append(
                RouteTraceEntry(
                    rule_id=entry["id"],
                    matched=score > 0 and not weak_generic,
                    reason=_describe_match(score, matched, entry, weak_generic),
                    skipped_because=_weak_reason(matched)
                    if weak_generic
                    else "",
                )
            )
            scored.append((score, matched, entry))

        scored.sort(key=lambda item: (-item[0], item[2]["id"]))

        picks: list[ReferencePick] = []
        fallback_used = False
        positive = [item for item in scored if item[1] and not _is_weak_generic_match(item[1])]

        if positive:
            for score, matched, entry in positive[: self.top_n]:
                picks.append(_to_pick(entry, score, matched))
            if len(picks) < self.top_n:
                # Mix in strong fallbacks to reach top_n without duplicating.
                fallback_used = True
                already = {p.id for p in picks}
                filler = _strong_fallback(
                    self.references,
                    exclude=already,
                    k=self.top_n - len(picks),
                    seed=_seed_for_context(context),
                    avoid_text_scripts=_avoid_text_scripts(context),
                )
                for entry in filler:
                    picks.append(_to_pick(entry, 0.0, {}))
        else:
            fallback_used = True
            filler = _strong_fallback(
                self.references,
                exclude=set(),
                k=self.top_n,
                seed=_seed_for_context(context),
                avoid_text_scripts=_avoid_text_scripts(context),
            )
            for entry in filler:
                picks.append(_to_pick(entry, 0.0, {}))

        return RouteDecision(
            dimension="reference",
            matched_rule_id="weighted_top_n" if positive else "random_fallback",
            fields={
                "picks": [
                    {
                        "id": p.id,
                        "image_path": p.image_path,
                        "role_description": p.role_description,
                        "score": round(p.score, 2),
                        "matched_tags": p.matched_tags,
                        "matched_dimensions": sorted(p.matched_tags),
                        "weak_generic_match": _is_weak_generic_match(p.matched_tags),
                        "weak_text_only_match": _is_weak_text_only_match(p.matched_tags),
                    }
                    for p in picks
                ],
                "fallback_used": fallback_used,
                "top_n": self.top_n,
            },
            trace=trace,
        )


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("references") or []
    out: list[dict[str, Any]] = []
    for entry in entries:
        if not entry.get("id"):
            continue
        entry = dict(entry)
        if entry.get("image"):
            entry["_resolved_image_path"] = str((path.parent / entry["image"]).resolve())
        else:
            entry["_resolved_image_path"] = ""
        out.append(entry)
    return out


def _extract_host_signals(context: dict[str, Any]) -> dict[str, list[str]]:
    """Read 5-dim tag signals from a RetrievalIntent if present, else from
    the raw HostBrief tags.

    Prefer ``context['intent']`` (written by workflow after eval/repair).
    Fall back to ``context['brief']`` for callers that haven't wired the
    intent step yet.
    """

    intent = context.get("intent") or {}
    if intent:
        return {
            "shape": list(intent.get("shape_anchors") or []),
            "color": list(intent.get("color_anchors") or []),
            "material": list(intent.get("material_anchors") or []),
            "vibe": list(intent.get("vibe_anchors") or []),
            "text": list(intent.get("text_anchors") or []),
        }
    brief = context.get("brief") or {}
    return {
        "shape": list(brief.get("shape_tags") or []),
        "color": list(brief.get("color_tags") or []),
        "material": list(brief.get("material_tags") or []),
        "vibe": list(brief.get("vibe_tags") or []),
        "text": list(brief.get("text_tags") or []),
    }


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        key = v.lower().strip()
        if not key or key in seen:
            continue
        out.append(key)
        seen.add(key)
    return out


def _score(entry: dict[str, Any], host_signals: dict[str, list[str]]) -> tuple[float, dict[str, list[str]]]:
    ref_tags = entry.get("tags") or {}
    semantic_score = 0.0
    matched: dict[str, list[str]] = {}
    for dim, weight in WEIGHTS.items():
        host_terms = {t.lower() for t in host_signals.get(dim, [])}
        ref_terms = {str(t).lower() for t in ref_tags.get(dim, [])}
        hit = sorted(host_terms & ref_terms)
        if hit:
            semantic_score += weight * len(hit)
            matched[dim] = hit
    if not matched:
        return 0.0, matched
    quality_bonus = STRONG_QUALITY_BONUS if str(entry.get("quality", "")).lower() == "strong" else 0.0
    return semantic_score + quality_bonus, matched


def _is_weak_text_only_match(matched: dict[str, list[str]]) -> bool:
    """True when a reference only matched generic Latin length tags.

    Latin/short/long are useful as secondary tie-breakers, but too weak to
    select a visually strong reference by themselves. Script-specific text
    matches such as Korean or Arabic remain valid because they carry real
    typography constraints.
    """

    if sorted(matched) != ["text"]:
        return False
    return set(matched.get("text") or []).issubset(WEAK_TEXT_ONLY_TAGS)


def _is_weak_generic_match(matched: dict[str, list[str]]) -> bool:
    if _is_weak_text_only_match(matched):
        return True
    if not matched:
        return False
    dims = set(matched)
    if not dims.issubset({"text", "vibe"}):
        return False
    vibe_tags = set(matched.get("vibe") or [])
    text_tags = set(matched.get("text") or [])
    return bool(vibe_tags) and vibe_tags.issubset(GENERIC_VIBE_TAGS) and text_tags.issubset(
        WEAK_TEXT_ONLY_TAGS
    )


def _weak_reason(matched: dict[str, list[str]]) -> str:
    if _is_weak_text_only_match(matched):
        return "weak latin/length-only text match"
    return "weak generic vibe + latin/length match"


def _describe_match(
    score: float,
    matched: dict[str, list[str]],
    entry: dict[str, Any],
    weak_generic: bool = False,
) -> str:
    if not matched:
        quality = str(entry.get("quality", "")).lower()
        suffix = "; strong quality bonus held for ranking only after a real tag match" if quality == "strong" else ""
        return f"score={score:.1f} (no positive tag matches{suffix})"
    parts = [f"{dim}:{','.join(tags)}" for dim, tags in matched.items()]
    suffix = f" | ignored as {_weak_reason(matched)}" if weak_generic else ""
    return f"score={score:.1f} | " + " | ".join(parts) + suffix


def _to_pick(entry: dict[str, Any], score: float, matched: dict[str, list[str]]) -> ReferencePick:
    return ReferencePick(
        id=entry["id"],
        image_path=entry.get("_resolved_image_path", ""),
        role_description=(entry.get("role_description") or "").strip(),
        score=score,
        matched_tags=matched,
    )


def _strong_fallback(
    references: list[dict[str, Any]],
    exclude: set[str],
    k: int,
    seed: int,
    avoid_text_scripts: set[str] | None = None,
) -> list[dict[str, Any]]:
    avoid_text_scripts = avoid_text_scripts or set()
    eligible = [
        e
        for e in references
        if e["id"] not in exclude and not _has_avoided_text_script(e, avoid_text_scripts)
    ]
    safe = [
        e
        for e in eligible
        if str(e.get("fallback_safe", "")).lower() in {"1", "true", "yes", "safe"}
    ]
    pool = safe or eligible
    strong = [e for e in pool if str(e.get("quality", "")).lower() == "strong"]
    if not strong:
        strong = pool
    if not strong:
        return []
    rng = random.Random(seed)
    return rng.sample(strong, k=min(k, len(strong)))


def _avoid_text_scripts(context: dict[str, Any]) -> set[str]:
    intent = context.get("intent") or {}
    return {str(tag).lower().strip() for tag in intent.get("avoid_text_scripts") or []}


def _has_avoided_text_script(entry: dict[str, Any], avoid_text_scripts: set[str]) -> bool:
    if not avoid_text_scripts:
        return False
    text_tags = {
        str(tag).lower().strip()
        for tag in (entry.get("tags") or {}).get("text", [])
    }
    return bool(text_tags & avoid_text_scripts)


def _seed_for_context(context: dict[str, Any]) -> int:
    host = context.get("host", {}) or {}
    key = f"{host.get('row_id', 0)}|{host.get('host_name', '')}"
    return int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:8], 16)
