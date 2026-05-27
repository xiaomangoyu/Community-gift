"""HostVisionBrief — structured visual analysis of a streamer.

Sits between :class:`HostInput` (from streamers/<id>/signals.md) and
:class:`HostBrief` (used by routers). Produced by a vision LLM call with the
streamer's avatar (or sticker, or text-only) as input.

Why structured (and not free prose):
- Every field is eval-able (e.g. assert palette.tags has >= 2 entries).
- Designers can edit a single form word without rewriting prose.
- template_first joins the structured pieces into a Chinese prompt sentence
  with a deterministic format, so output stays consistent across hosts.

Schema mirrors the dimensions found in ``references/imgs/*.txt`` (Cherry /
Purple_heart / Cream_heart / Butterfly).
"""

from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError


# Reasonable cap for text rendered inside a lightstick lamp head.
# Beyond ~20 chars typography starts to crowd the central core.
DEFAULT_TEXT_MAX_LEN = 20


# ---------------------------------------------------------------------------
# Nested models
# ---------------------------------------------------------------------------


class TextBlock(BaseModel):
    """The exact text rendered into the lamp-head core.

    Eval-critical: the workflow will compare ``exact_text`` against the
    rendered image's typography. ``source`` records which signal supplied it
    (fan_club / host_name / "") so we can debug picker decisions.

    TODO(text-source): pick_exact_text currently chooses between fan_club and
    host_name. Future sources may include: repeated catchphrase, hand-edited
    YAML override, signature emoji-stripped tag.
    """

    exact_text: str = ""
    source: str = ""  # fan_club | host_name | ""
    script: str = ""  # latin | korean | arabic | chinese | mixed | empty
    style_hint: str = ""  # e.g. "甜感立体描边发光体"


class PaletteBlock(BaseModel):
    family: str = ""  # 商业化风格家族, e.g. 甜冷糖果系 / 暖色系 / 烟灰冷调
    main_color: str = ""
    secondary_color: str = ""
    accent_colors: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)  # English tags for routers


class MaterialsBlock(BaseModel):
    main: str = ""
    supporting: str = ""
    tags: list[str] = Field(default_factory=list)


class SignatureSymbols(BaseModel):
    primary: str = ""
    secondary: str = ""
    source: str = ""  # avatar | sticker | text_only


class SymbolForms(BaseModel):
    """How a single symbol breaks down into lamp-head form elements."""

    symbol: str = ""
    position: str = ""  # 灯头顶部两侧 / 灯头下半部 / 灯头中心 / 边缘 ...
    forms: list[str] = Field(default_factory=list)


class ThemeForms(BaseModel):
    primary: SymbolForms = Field(default_factory=SymbolForms)
    secondary: SymbolForms = Field(default_factory=SymbolForms)
    fusion_note: str = ""  # optional short structural note; final prompt ignores prose-heavy notes


class MoodBlock(BaseModel):
    phrase: str = ""  # comma-separated Chinese words: 甜美、治愈、俏皮 ...
    tags: list[str] = Field(default_factory=list)


class HandleBlock(BaseModel):
    """Per-host handle treatment.

    The default template used "统一简洁手柄造型，细长顺直完整握柄" — too
    generic, Seedream averaged everyone to a plain white tube. Forcing the
    vision call to fill these fields produces handle continuity with the
    lamp-head theme (e.g. potato handle with golden ridges, falcon handle
    with feathered grip wrap).
    """

    main_material: str = ""        # 珠光奶白树脂 / 烟熏哑光金属 / 透明果冻 ...
    surface_treatment: str = ""    # 螺旋羽纹 / 横向凹槽 / 镜面抛光 ...
    connector_detail: str = ""     # 双层金环 + 微型徽章 / 透明晶体连接 / 雕花护片 ...
    bottom_cap: str = ""           # 圆顶按钮 / 主题底座节点 + 微型护翼 ...
    decoration_continuation: str = ""  # how the lamp-head theme bleeds onto the handle


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


class HostVisionBrief(BaseModel):
    """The full visual brief produced by ``analyze_host_visual_brief``."""

    row_id: int
    host_name: str = ""
    text: TextBlock = Field(default_factory=TextBlock)
    style_pitch: str = ""  # short style label, not a final-prompt sentence
    palette: PaletteBlock = Field(default_factory=PaletteBlock)
    materials: MaterialsBlock = Field(default_factory=MaterialsBlock)
    signature_symbols: SignatureSymbols = Field(default_factory=SignatureSymbols)
    theme_forms: ThemeForms = Field(default_factory=ThemeForms)
    # Concrete lamp-head silhouette — REQUIRED to break Seedream's circular bias.
    # Examples: "盾形上扬展翼" / "椭圆果实双叶护片" / "六角晶体冠" / "拱顶马铃薯块状"
    # Must NOT be just rhythm words like 圆润/上扬 — those go into silhouette_language.
    lamp_head_silhouette: str = ""
    silhouette_language: str = ""  # 鼓起、圆润、包裹、对称 ... (rhythm/feel words)
    lighting: str = ""  # 清晰主光、晶体折射、软硬对比 ...
    mood: MoodBlock = Field(default_factory=MoodBlock)
    handle: HandleBlock = Field(default_factory=HandleBlock)
    # Operational metadata — useful for debugging which source the LLM saw.
    image_source: str = ""  # avatar | sticker | text_only
    image_path: str = ""


# ---------------------------------------------------------------------------
# Text picker — fan_club vs host_name, catchy-first
# ---------------------------------------------------------------------------


def pick_exact_text(
    fan_club: str,
    host_name: str,
    max_len: int = DEFAULT_TEXT_MAX_LEN,
) -> tuple[str, str]:
    """Choose the catchiest text for the lamp head.

    Priority order:
      1. Both candidates cleaned (emoji/whitespace/hashtag stripped).
      2. Drop any candidate that exceeds ``max_len`` after cleaning.
      3. Among survivors, prefer the lower (length + special-char-penalty).
      4. On tie, prefer fan_club (community identity > personal handle for a
         community gift).
      5. If none survive, return ("", "").

    Returns: (text, source) where source ∈ {"fan_club","host_name",""}.

    TODO(text-source): future hook — accept a third candidate
    ``catchphrase``, plus an explicit override slot per streamer.
    """

    candidates: list[tuple[str, str]] = []  # (cleaned, source)
    for raw, source in [(fan_club, "fan_club"), (host_name, "host_name")]:
        cleaned = _clean_for_typography(raw)
        if cleaned and len(cleaned) <= max_len:
            candidates.append((cleaned, source))

    if not candidates:
        return "", ""

    def score(item: tuple[str, str]) -> float:
        text, source = item
        penalty = sum(1 for c in text if c in "!?#@&*+_=/\\|<>")
        # Bias toward fan_club: community identity is the gift's main subject.
        # Only let host_name win when it's *meaningfully* shorter (≥3 chars).
        bias = -3 if source == "fan_club" else 0
        return len(text) + penalty * 2 + bias

    candidates.sort(key=score)
    return candidates[0]


_TYPOGRAPHY_KEEP = {" ", "-", "_", ".", "'", "&", "!"}


def _clean_for_typography(value: str) -> str:
    """Strip emoji, ZWJ, variation selectors, leading/trailing hashtags."""

    if not value:
        return ""
    value = value.strip()
    if value.startswith("#"):
        value = value.lstrip("#")
    chars: list[str] = []
    for char in value:
        if _is_emoji(char):
            continue
        category = unicodedata.category(char)
        if category[0] in {"L", "N"} or char in _TYPOGRAPHY_KEEP:
            chars.append(char)
    cleaned = "".join(chars).strip()
    # Collapse internal whitespace.
    return " ".join(cleaned.split())


def _is_emoji(char: str) -> bool:
    code = ord(char)
    return (
        0x1F300 <= code <= 0x1FAFF
        or 0x2600 <= code <= 0x27BF
        or 0xFE00 <= code <= 0xFE0F
        or code == 0x200D
        or 0x10000 <= code <= 0x1FFFF and unicodedata.category(char).startswith("S")
    )


# ---------------------------------------------------------------------------
# Image source picker — avatar > sticker > text_only
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Cache + designer override
# ---------------------------------------------------------------------------

# Bump when schema or prompt policy changes such that old briefs would carry
# stale routing assumptions.
VISION_SCHEMA_VERSION = 11

# Default cache directory — outside source data, can be wiped without risk.
_DEFAULT_CACHE_DIR = Path("outputs/vision_cache")


def load_vision_override(host) -> "HostVisionBrief | None":
    """Designer-edited override under ``streamers/<id>/vision_override.json``.

    When present, wins unconditionally — no LLM call, no cache lookup. Schema
    is the same as a cached :class:`HostVisionBrief`. Missing fields default
    to empty (Pydantic), so a partial override file is allowed.
    """

    raw = getattr(host, "raw", None) or {}
    folder = raw.get("folder")
    if not folder:
        return None
    path = Path(folder) / "vision_override.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["row_id"] = host.row_id
        data.setdefault("host_name", host.host_name)
        return HostVisionBrief.model_validate(data)
    except (ValidationError, json.JSONDecodeError, OSError) as exc:
        print(f"[{host.row_id}] vision_override.json invalid ({exc}); ignoring.")
        return None


def _cache_key(host, image_path: str) -> str:
    """SHA-1 over (anchor_id, schema version, image bytes, signals.md text).

    Re-runs the LLM whenever the inputs change. anchor_id-keyed so caches are
    portable across runs / output dirs.
    """

    raw = getattr(host, "raw", None) or {}
    anchor_id = host.anchor_id or str(host.row_id)
    folder = raw.get("folder", "")
    parts: list[bytes] = [
        anchor_id.encode("utf-8"),
        f"v{VISION_SCHEMA_VERSION}".encode("utf-8"),
    ]
    if image_path and Path(image_path).exists():
        parts.append(b"img:" + hashlib.sha1(Path(image_path).read_bytes()).digest())
    if folder:
        signals = Path(folder) / "signals.md"
        if signals.exists():
            parts.append(b"sig:" + hashlib.sha1(signals.read_bytes()).digest())
    return hashlib.sha1(b"|".join(parts)).hexdigest()[:16]


def _cache_path(host, cache_dir: Path | None = None) -> Path:
    base = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
    anchor_id = host.anchor_id or f"row{host.row_id}"
    return base / f"{anchor_id}.json"


def load_vision_cache(
    host,
    image_path: str,
    *,
    cache_dir: Path | None = None,
) -> "HostVisionBrief | None":
    """Reuse a previously-saved vision brief when inputs haven't changed."""

    if os.getenv("VISION_NO_CACHE", "").lower() in {"1", "true", "yes"}:
        return None
    path = _cache_path(host, cache_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("_cache_key") != _cache_key(host, image_path):
        return None
    try:
        return HostVisionBrief.model_validate(data.get("brief", {}))
    except ValidationError:
        return None


def save_vision_cache(
    host,
    image_path: str,
    brief: "HostVisionBrief",
    *,
    cache_dir: Path | None = None,
) -> None:
    """Persist a brief to disk so the next run skips the LLM call."""

    path = _cache_path(host, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_cache_key": _cache_key(host, image_path),
        "_schema_version": VISION_SCHEMA_VERSION,
        "brief": brief.model_dump(),
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def pick_vision_image(host) -> tuple[str, str]:
    """Return (image_path, source) for the vision call.

    source ∈ {"avatar","sticker","text_only"}. ``text_only`` returns empty
    path — caller must run the LLM without an image attachment.
    """

    avatar = (host.host_image or "").strip()
    if avatar and Path(avatar).exists():
        return avatar, "avatar"

    sticker = ""
    raw = host.raw if isinstance(getattr(host, "raw", None), dict) else {}
    sticker_file = raw.get("stickers_file") if raw else ""
    folder = raw.get("folder") if raw else ""
    if sticker_file and folder:
        candidate = Path(folder) / sticker_file
        if candidate.exists():
            sticker = str(candidate.resolve())
    if sticker:
        return sticker, "sticker"

    return "", "text_only"
