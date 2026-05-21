"""Streamers loader — reads ``streamers/<anchor_id>_<name>/signals.md`` and
produces :class:`HostInput` records.

Replaces ``csv_io.read_hosts`` when the upstream signal source is the curated
streamers folder instead of the legacy host CSV. CSV is left intact for fallback.

Mapping (signals.md → HostInput):

- header line       → ``host_name``     (display string, keeps emoji)
- ``anchor_id``     → ``anchor_id``
- ``fan_club``      → ``community_name``
- Top symbols       → ``symbols``       (comm first, host second, original order)
- Primary signals   → joined into ``notes`` as ``signals: a, b, c``
- ``tier``          → joined into ``notes`` as ``tier: <value>``
- ``avatar.jpg``    → ``host_image``    (absolute path, only if file exists)

Colors / vibe / personality are NOT in signals.md and are intentionally left
empty in v1 — see chat history. Avatar still feeds the vision brief, but it is
not sent to Seedream as an image reference by default.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from .models import HostInput


_HEADER_RE = re.compile(r"^#\s+(.+?)\s*$")
_BULLET_FIELD_RE = re.compile(r"^-\s+\*\*([^*]+)\*\*:\s*(.+?)\s*$")
_CREATIVE_FIELD_RE = re.compile(r"^-\s+(?:\*\*)?([^:*`]+?)(?:\*\*)?:\s*(.+?)\s*$")
_SYMBOL_RE = re.compile(r"^-\s+`([^`]+)`\s*(?:\(([^)]+)\))?\s*$")
_PLAIN_BULLET_RE = re.compile(r"^-\s+`([^`]+)`\s*$")


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
        "primary_signals": [],
        "missing_signals": [],
        "avatar_file": "",
        "stickers_file": "",
        "characterization": "",
        "creative_mode": "",
        "wildness_score": "",
        "wildness_axes": [],
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

        if line.startswith("## "):
            section = line[3:].strip().lower()
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

        if section in {"primary signals", "missing signals"}:
            plain = _PLAIN_BULLET_RE.match(line)
            if plain:
                key = "primary_signals" if section == "primary signals" else "missing_signals"
                record[key].append(plain.group(1).strip())
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

        if section in {"creative controls", "creative profile", "creative guidance"}:
            bullet = _CREATIVE_FIELD_RE.match(line)
            if bullet:
                key = bullet.group(1).strip().lower().replace(" ", "_").replace("-", "_")
                value = bullet.group(2).strip()
                if key in {"creative_mode", "wildness_mode"}:
                    record["creative_mode"] = value
                elif key in {"wildness_score", "wildness_intensity", "creative_intensity"}:
                    record["wildness_score"] = value
                elif key in {"wildness_axes", "creative_axes", "creative_tags"}:
                    record["wildness_axes"].extend(_split_axis_list(value))
                continue
            plain = _PLAIN_BULLET_RE.match(line)
            if plain:
                record["wildness_axes"].append(plain.group(1).strip())
            continue

    record["characterization"] = " ".join(char_lines).strip()
    return record


def _extract_backticked(text: str) -> str:
    """Pull the first `` `...` `` token out of a line. Returns '' if none."""

    match = re.search(r"`([^`]+)`", text)
    return match.group(1).strip() if match else ""


def _split_axis_list(value: str) -> list[str]:
    return [
        part.strip().strip("`")
        for part in value.replace("、", ",").replace("，", ",").replace("/", ",").split(",")
        if part.strip().strip("`")
    ]


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
    if record["primary_signals"]:
        note_parts.append("signals: " + ", ".join(record["primary_signals"]))
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
            "primary_signals": record["primary_signals"],
            "missing_signals": record["missing_signals"],
            "avatar_file": record["avatar_file"],
            "stickers_file": record["stickers_file"],
            "characterization": record["characterization"],
            "creative_mode": record["creative_mode"],
            "wildness_score": record["wildness_score"],
            "wildness_axes": record["wildness_axes"],
            "folder": str(folder),
        },
    )
