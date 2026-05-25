"""Small tag alias layer used by reference routing.

The reference router still uses deterministic exact intersections. This module
only normalizes common input variants before that scoring step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml


DEFAULT_TAG_ALIASES_PATH = (
    Path(__file__).resolve().parent.parent.parent / "references" / "imgs" / "tag_aliases.yaml"
)


@dataclass(frozen=True)
class TagAliasRules:
    aliases: dict[str, str]
    parents: dict[str, tuple[str, ...]]


def normalize_tag_map(
    tag_map: Mapping[str, list[str]] | None,
    aliases_path: Path = DEFAULT_TAG_ALIASES_PATH,
) -> dict[str, list[str]]:
    """Normalize every tag list in a dimension map.

    Example: {"shape": ["bunny"]} can become
    {"shape": ["rabbit", "animal", "soft_body"]}.
    """

    return {
        str(dim): normalize_tags(values, aliases_path=aliases_path)
        for dim, values in (tag_map or {}).items()
    }


def normalize_tags(
    values: list[str] | tuple[str, ...] | set[str] | None,
    aliases_path: Path = DEFAULT_TAG_ALIASES_PATH,
) -> list[str]:
    rules = _load_rules(str(aliases_path))
    out: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        key = _clean_tag(value)
        if not key:
            return
        canonical = rules.aliases.get(key, key)
        if canonical in seen:
            return
        seen.add(canonical)
        out.append(canonical)
        for parent in rules.parents.get(canonical, ()):
            add(parent)

    for value in values or []:
        raw = str(value)
        add(raw)
        for token in _phrase_tokens(raw):
            add(token)
    return out


def normalize_tag(value: str) -> str:
    """Public single-tag helper for small router checks."""

    return normalize_tags([value])[0] if _clean_tag(value) else ""


@lru_cache(maxsize=8)
def _load_rules(path_key: str) -> TagAliasRules:
    path = Path(path_key)
    if not path.exists():
        return TagAliasRules(aliases={}, parents={})

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_aliases = raw.get("aliases") or {}
    raw_parents = raw.get("parents") or {}

    aliases: dict[str, str] = {}
    for canonical_raw, alias_values in raw_aliases.items():
        canonical = _clean_tag(str(canonical_raw))
        if not canonical:
            continue
        aliases[canonical] = canonical
        for alias_raw in _as_list(alias_values):
            alias = _clean_tag(str(alias_raw))
            if alias:
                aliases[alias] = canonical

    parents: dict[str, tuple[str, ...]] = {}
    for child_raw, parent_values in raw_parents.items():
        child = aliases.get(_clean_tag(str(child_raw)), _clean_tag(str(child_raw)))
        if not child:
            continue
        unique: list[str] = []
        seen: set[str] = set()
        for parent_raw in _as_list(parent_values):
            parent = aliases.get(_clean_tag(str(parent_raw)), _clean_tag(str(parent_raw)))
            if not parent or parent == child or parent in seen:
                continue
            unique.append(parent)
            seen.add(parent)
        parents[child] = tuple(unique)

    return TagAliasRules(aliases=aliases, parents=parents)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _clean_tag(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", " ").split())


def _phrase_tokens(value: str) -> list[str]:
    """Split VLM-style short phrases without splitting canonical snake_case tags."""

    if "_" in value and not any(sep in value for sep in " /,;#|"):
        return []
    return [token for token in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", value) if len(token) > 1]
