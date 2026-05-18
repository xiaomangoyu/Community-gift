from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    output_dir: Path
    max_rows: int | None


def load_settings(env_path: str | None = None) -> Settings:
    load_dotenv(env_path)
    max_rows_raw = os.getenv("MAX_ROWS", "").strip()
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4").strip(),
        output_dir=Path(os.getenv("OUTPUT_DIR", "outputs")).expanduser(),
        max_rows=int(max_rows_raw) if max_rows_raw else None,
    )
