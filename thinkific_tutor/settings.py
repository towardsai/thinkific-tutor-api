from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from .bootstrap import ensure_ai_tutor_importable

ensure_ai_tutor_importable()

from data.scraping_scripts.source_registry import (  # noqa: E402
    COURSE_SOURCE_KEYS,
    SOURCE_DISPLAY_INFO,
    SOURCE_KEY_TO_LABEL,
)


def _csv_env(name: str, default: str = "") -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _json_map_env(name: str) -> dict[str, str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return {
        str(key).strip(): str(val).strip()
        for key, val in value.items()
        if str(key).strip() and str(val).strip()
    }


def default_course_url_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for source_key in COURSE_SOURCE_KEYS:
        display = SOURCE_DISPLAY_INFO.get(source_key, {})
        url = str(display.get("url", "")).strip()
        if url:
            mapping[url] = source_key
    return mapping


def _validate_source_map(mapping: dict[str, str], name: str) -> dict[str, str]:
    allowed = set(COURSE_SOURCE_KEYS)
    invalid = sorted({source for source in mapping.values() if source not in allowed})
    if invalid:
        raise ValueError(
            f"{name} contains non-course source keys: {', '.join(invalid)}"
        )
    return mapping


@dataclass(frozen=True)
class Settings:
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: _csv_env(
            "THINKIFIC_ALLOWED_ORIGINS", "https://academy.towardsai.net"
        )
    )
    allowed_hosts: tuple[str, ...] = field(
        default_factory=lambda: _csv_env(
            "THINKIFIC_ALLOWED_HOSTS", "academy.towardsai.net"
        )
    )
    model_name: str = field(
        default_factory=lambda: os.getenv(
            "THINKIFIC_TUTOR_MODEL", "google-genai:gemini-2.5-flash"
        ).strip()
        or "google-genai:gemini-2.5-flash"
    )
    enabled_tools: tuple[str, ...] = field(
        default_factory=lambda: _csv_env("THINKIFIC_ENABLED_TOOLS", "")
    )
    disable_kb: bool = field(
        default_factory=lambda: _bool_env("THINKIFIC_DISABLE_KB", True)
    )
    memory_preset: str = field(
        default_factory=lambda: os.getenv("THINKIFIC_MEMORY_PRESET", "").strip()
    )
    retrieval_budget: int = field(
        default_factory=lambda: _int_env("THINKIFIC_RETRIEVAL_BUDGET", 24000)
    )
    max_body_bytes: int = field(
        default_factory=lambda: _int_env("THINKIFIC_MAX_BODY_BYTES", 512 * 1024)
    )
    max_page_context_chars: int = field(
        default_factory=lambda: _int_env("THINKIFIC_MAX_PAGE_CONTEXT_CHARS", 6000)
    )
    rate_limit_per_minute: int = field(
        default_factory=lambda: _int_env("THINKIFIC_RATE_LIMIT_PER_MINUTE", 6)
    )
    rate_limit_per_day: int = field(
        default_factory=lambda: _int_env("THINKIFIC_RATE_LIMIT_PER_DAY", 120)
    )
    rate_limit_global_per_minute: int = field(
        default_factory=lambda: _int_env("THINKIFIC_GLOBAL_RATE_LIMIT_PER_MINUTE", 120)
    )
    opik_enabled: bool = field(
        default_factory=lambda: _bool_env("OPIK_ENABLED", False)
    )
    opik_api_key: str = field(
        default_factory=lambda: os.getenv("OPIK_API_KEY", "").strip()
    )
    opik_workspace: str = field(
        default_factory=lambda: os.getenv("OPIK_WORKSPACE", "").strip()
    )
    opik_project_name: str = field(
        default_factory=lambda: os.getenv(
            "OPIK_PROJECT_NAME",
            "towards-ai-thinkific-tutor",
        ).strip()
        or "towards-ai-thinkific-tutor"
    )
    opik_max_text_chars: int = field(
        default_factory=lambda: _int_env("OPIK_MAX_TEXT_CHARS", 8000)
    )
    require_logged_in_user: bool = field(
        default_factory=lambda: _bool_env("THINKIFIC_REQUIRE_LOGGED_IN_USER", True)
    )
    blocked_lesson_keywords: tuple[str, ...] = field(
        default_factory=lambda: _csv_env(
            "THINKIFIC_BLOCKED_LESSON_KEYWORDS",
            "quiz,quizz,exam,assessment",
        )
    )
    allow_unmapped_courses: bool = field(
        default_factory=lambda: _bool_env("THINKIFIC_ALLOW_UNMAPPED_COURSES", False)
    )
    default_source_key: str = field(
        default_factory=lambda: os.getenv("THINKIFIC_DEFAULT_SOURCE_KEY", "").strip()
    )
    course_url_source_map: dict[str, str] = field(
        default_factory=lambda: _validate_source_map(
            {**default_course_url_map(), **_json_map_env("THINKIFIC_COURSE_URL_SOURCE_MAP")},
            "THINKIFIC_COURSE_URL_SOURCE_MAP",
        )
    )
    course_id_source_map: dict[str, str] = field(
        default_factory=lambda: _validate_source_map(
            _json_map_env("THINKIFIC_COURSE_ID_SOURCE_MAP"),
            "THINKIFIC_COURSE_ID_SOURCE_MAP",
        )
    )

    def cors_origins(self) -> list[str]:
        return list(self.allowed_origins) or ["https://academy.towardsai.net"]

    def public_course_sources(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for source_key in sorted(COURSE_SOURCE_KEYS):
            display = SOURCE_DISPLAY_INFO.get(source_key, {})
            result.append(
                {
                    "sourceKey": source_key,
                    "label": SOURCE_KEY_TO_LABEL.get(source_key, source_key),
                    "url": display.get("url", ""),
                }
            )
        return result


settings = Settings()
