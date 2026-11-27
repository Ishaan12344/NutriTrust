"""Central, environment-backed settings for the NutriTrust backend.

The project intentionally uses a small standard-library settings object instead
of adding another dependency.  It is immutable after startup and does not
contain or log secret values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"))


@dataclass(frozen=True)
class Settings:
    max_image_size_bytes: int
    sarvam_api_key: str | None
    sarvam_timeout_seconds: int
    sarvam_download_timeout_seconds: int
    open_food_facts_timeout_seconds: float
    mongodb_uri: str
    mongodb_db_name: str
    summary_enabled: bool
    summary_model_path: str
    summary_max_new_tokens: int
    summary_timeout_seconds: float


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    """Return validated settings once per process."""
    key = os.getenv("SARVAM_API_KEY", "").strip() or None
    return Settings(
        max_image_size_bytes=_positive_int("NUTRITRUST_MAX_IMAGE_SIZE_BYTES", 10 * 1024 * 1024),
        sarvam_api_key=key,
        sarvam_timeout_seconds=_positive_int("NUTRITRUST_SARVAM_TIMEOUT_SECONDS", 180),
        sarvam_download_timeout_seconds=_positive_int("NUTRITRUST_SARVAM_DOWNLOAD_TIMEOUT_SECONDS", 60),
        open_food_facts_timeout_seconds=_positive_float("NUTRITRUST_OFF_TIMEOUT_SECONDS", 10.0),
        mongodb_uri=os.getenv("MONGODB_URI", "mongodb://localhost:27017").strip(),
        mongodb_db_name=os.getenv("MONGODB_DB_NAME", "nutritrust").strip(),
        summary_enabled=_bool("NUTRITRUST_SUMMARY_ENABLED", True),
        summary_model_path=os.getenv(
            "NUTRITRUST_SUMMARY_MODEL_PATH",
            str(Path(__file__).resolve().parent / "models" / "Qwen2.5-1.5B-Instruct"),
        ).strip(),
        summary_max_new_tokens=_positive_int("NUTRITRUST_SUMMARY_MAX_NEW_TOKENS", 320),
        summary_timeout_seconds=_positive_float("NUTRITRUST_SUMMARY_TIMEOUT_SECONDS", 120.0),
    )
