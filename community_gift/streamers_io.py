"""Streamers loader — reads ``streamers/<anchor_id>_<name>/signals.md`` and
produces :class:`HostInput` records.

Replaces ``csv_io.read_hosts`` when the upstream signal source is the curated
streamers folder instead of the legacy host CSV. CSV is left intact for fallback.

Mapping (signals.md → HostInput):

- header line       → ``host_name``     (display string, keeps emoji)
- ``anchor_id``     → ``anchor_id``
- ``fan_club``      → ``community_name``
- Top symbols       → ``symbols``       (comm first, host second, original order)
- Evidence signals  → joined into ``notes`` as ``signals: a, b, c``
- ``tier``          → joined into ``notes`` as ``tier: <value>``
- ``avatar.jpg``    → ``host_image``    (absolute path, only if file exists)

Direction fields such as palette / material / mood / form exploration are kept
in ``HostInput.raw`` so downstream deterministic prompt code can use them
without relying on free-form notes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from .models import HostInput


_HEADER_RE = re.compile(r"^#\s+(.+?)\s*$")
_BULLET_FIELD_RE = re.compile(r"^-\s+\*\*([^*]+)\*\*:\s*(.+?)\s*$")
_SYMBOL_RE = re.compile(r"^-\s+`([^`]+)`\s*(?:\(([^)]+)\))?\s*$")
_PLAIN_BULLET_RE = re.compile(r"^-\s+`([^`]+)`\s*$")
_SECTION_HEADING_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$")

_DIRECTION_SECTIONS = {
    "palette direction": "palette_direction",
    "material direction": "material_direction",
    "mood coverage": "mood_coverage",
    "form exploration": "form_exploration",
    "shape exploration": "form_exploration",
    "配色方向": "palette_direction",
    "材质方向": "material_direction",
    "情绪覆盖": "mood_coverage",
    "形态探索": "form_exploration",
}
_SECTION_ALIASES = {
    "top symbol": "top symbols",
    "top symbols": "top symbols",
    "primary signal": "evidence signals",
    "primary signals": "evidence signals",
    "evidence signal": "evidence signals",
    "evidence signals": "evidence signals",
    "signal evidence": "evidence signals",
    "missing signal": "missing evidence",
    "missing signals": "missing evidence",
    "missing evidence": "missing evidence",
    "missing evidences": "missing evidence",
    "characterization": "characterization",
    "media": "media",
    "palette directions": "palette direction",
    "material directions": "material direction",
    "mood coverages": "mood coverage",
    "form explorations": "form exploration",
    "shape explorations": "shape exploration",
}


def read_streamers(
    streamers_root: Path,
    *,
    tier_filter: Iterable[str] | None = None,
    anchor_ids: Iterable[str] | None = None,
    max_rows: int | None = None,
) -> list[HostInput]:
    """Walk ``streamers_root`` and return one :class:`HostInput` per folder.

    Args:
        streamers_root: directory containing ``<anchor_id>_<name>/`` subfolders.
        tier_filter: if set, keep only streamers whose tier is in this set
            (e.g. ``{"exceptional"}``).
        anchor_ids: if set, keep only streamers with one of these anchor_ids.
        max_rows: hard cap, applied after filtering.

    Order:
        Stable — sorted by (tier_rank, anchor_id) where exceptional < strong <
        medium < weak. This gives a deterministic ``row_id`` assignment.
    """

    tier_set = {t.lower() for t in tier_filter} if tier_filter else None
    anchor_set = {str(a) for a in anchor_ids} if anchor_ids else None

    parsed: list[dict] = []
    for folder in sorted(streamers_root.iterdir()):
        if not folder.is_dir():
            continue
        signals_path = folder / "signals.md"
        if not signals_path.exists():
            continue
        record = _parse_signals_md(signals_path)
        record["_folder"] = folder
        parsed.append(record)

    tier_rank = {"exceptional": 0, "strong": 1, "medium": 2, "weak": 3}
    parsed.sort(key=lambda r: (tier_rank.get(r.get("tier", "").lower(), 99), r.get("anchor_id", "")))

    hosts: list[HostInput] = []
    for record in parsed:
        if tier_set is not None and record.get("tier", "").lower() not in tier_set:
            continue
        if anchor_set is not None and record.get("anchor_id", "") not in anchor_set:
            continue

        host = _to_host_input(record, row_id=len(hosts) + 1)
        hosts.append(host)
        if max_rows and len(hosts) >= max_rows:
            break
    return hosts


def _parse_signals_md(path: Path) -> dict:
    """Section-aware parser. Returns a dict — keeps parsing dumb on purpose."""

    record: dict = {
        "host_name": "",
        "anchor_id": "",
        "tier": "",
        "fan_club": "",
        "host_symbols": [],
        "comm_symbols": [],
        "evidence_signals": [],
        "missing_evidence": [],
        # Backward-compatible aliases. Downstream code should prefer
        # evidence_signals / missing_evidence.
        "primary_signals": [],
        "missing_signals": [],
        "palette_direction": [],
        "material_direction": [],
        "mood_coverage": [],
        "form_exploration": [],
        "avatar_file": "",
        "stickers_file": "",
        "characterization": "",
    }
    char_lines: list[str] = []
    section = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()

        if not record["host_name"]:
            header = _HEADER_RE.match(line)
            if header and not line.startswith("##"):
                record["host_name"] = header.group(1).strip()
                continue

        section_heading = _SECTION_HEADING_RE.match(line)
        if section_heading:
            section = _normalize_section_name(section_heading.group(1))
            continue

        bullet_field = _BULLET_FIELD_RE.match(line)
        if bullet_field and section == "":
            key = bullet_field.group(1).strip().lower().replace(" ", "_")
            value = bullet_field.group(2).strip()
            if key in {"anchor_id", "tier", "fan_club"}:
                if value.strip().lower() in {"(none)", "none", "-", "n/a"}:
                    value = ""
                record[key] = value
            continue

        if section == "top symbols":
            sym = _SYMBOL_RE.match(line)
            if sym:
                symbol = sym.group(1).strip()
                tag = (sym.group(2) or "").strip().lower()
                if tag == "comm":
                    record["comm_symbols"].append(symbol)
                else:
                    record["host_symbols"].append(symbol)
            continue

        if section in {"evidence signals", "missing evidence"}:
            value = _bullet_text(line)
            if value:
                if section == "evidence signals":
                    record["evidence_signals"].append(value)
                    record["primary_signals"].append(value)
                else:
                    record["missing_evidence"].append(value)
                    record["missing_signals"].append(value)
            continue

        if section in _DIRECTION_SECTIONS:
            value = _bullet_text(line)
            if value:
                record[_DIRECTION_SECTIONS[section]].append(value)
            continue

        if section == "characterization":
            if line.strip():
                char_lines.append(line.strip())
            continue

        if section == "media":
            # ``- avatar: `avatar.jpg` (token `xxx`)``
            stripped = line.lstrip("- ").strip()
            if stripped.startswith("avatar:"):
                fname = _extract_backticked(stripped)
                if fname:
                    record["avatar_file"] = fname
            elif stripped.startswith("stickers:"):
                fname = _extract_backticked(stripped)
                if fname:
                    record["stickers_file"] = fname
            continue

    record["characterization"] = " ".join(char_lines).strip()
    return record


def _extract_backticked(text: str) -> str:
    """Pull the first `` `...` `` token out of a line. Returns '' if none."""

    match = re.search(r"`([^`]+)`", text)
    return match.group(1).strip() if match else ""


def _normalize_section_name(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[：:]+$", "", text)
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return _SECTION_ALIASES.get(text, text)


def _bullet_text(line: str) -> str:
    """Return a bullet value, accepting both backticked tags and plain bullets."""

    plain = _PLAIN_BULLET_RE.match(line)
    if plain:
        return plain.group(1).strip()
    stripped = line.strip()
    if not stripped.startswith("-"):
        return ""
    value = stripped.lstrip("-").strip()
    return value.strip("` ")


def _to_host_input(record: dict, row_id: int) -> HostInput:
    folder: Path = record["_folder"]

    # Symbols: comm first (community-owned, more on-brand for a community gift),
    # then host symbols. Preserve original order within each group.
    symbols = list(record["comm_symbols"]) + list(record["host_symbols"])

    avatar_path = ""
    if record["avatar_file"]:
        candidate = folder / record["avatar_file"]
        if candidate.exists():
            avatar_path = str(candidate.resolve())

    note_parts = []
    if record["tier"]:
        note_parts.append(f"tier: {record['tier']}")
    if record["fan_club"]:
        note_parts.append(f"fan_club: {record['fan_club']}")
    evidence_signals = record.get("evidence_signals") or record.get("primary_signals") or []
    missing_evidence = record.get("missing_evidence") or record.get("missing_signals") or []
    if evidence_signals:
        note_parts.append("signals: " + ", ".join(evidence_signals))
    if record["material_direction"]:
        note_parts.append("material_direction: " + ", ".join(record["material_direction"]))
    if record["palette_direction"]:
        note_parts.append("palette_direction: " + ", ".join(record["palette_direction"]))
    if record["stickers_file"]:
        note_parts.append(f"stickers_file: {record['stickers_file']}")

    return HostInput(
        row_id=row_id,
        host_name=record["host_name"],
        anchor_id=record["anchor_id"],
        community_name=record["fan_club"],
        host_image=avatar_path,
        symbols=symbols,
        notes="; ".join(note_parts),
        raw={
            "tier": record["tier"],
            "fan_club": record["fan_club"],
            "host_symbols": record["host_symbols"],
            "comm_symbols": record["comm_symbols"],
            "evidence_signals": evidence_signals,
            "missing_evidence": missing_evidence,
            "primary_signals": evidence_signals,
            "missing_signals": missing_evidence,
            "palette_direction": record["palette_direction"],
            "material_direction": record["material_direction"],
            "mood_coverage": record["mood_coverage"],
            "form_exploration": record["form_exploration"],
            "avatar_file": record["avatar_file"],
            "stickers_file": record["stickers_file"],
            "characterization": record["characterization"],
            "folder": str(folder),
        },
    )
