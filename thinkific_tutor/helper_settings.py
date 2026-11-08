from __future__ import annotations

import os
from dataclasses import dataclass, field


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


def _bool_env_chain(primary: str, fallback: str, default: bool = False) -> bool:
    if os.getenv(primary) is not None:
        return _bool_env(primary, default)
    return _bool_env(fallback, default)


@dataclass(frozen=True)
class HelperSettings:
    upstream_base_url: str = field(
        default_factory=lambda: os.getenv(
            "HELPER_UPSTREAM_BASE_URL",
            "https://towardsai-tutors-tai-helper.hf.space",
        ).strip().rstrip("/")
    )
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: _csv_env(
            "HELPER_ALLOWED_ORIGINS",
            (
                "https://towardsai.com,https://www.towardsai.com,"
                "https://academy.towardsai.net,https://towardsai.net,"
                "https://www.towardsai.net"
            ),
        )
    )
    allowed_hosts: tuple[str, ...] = field(
        default_factory=lambda: _csv_env(
            "HELPER_ALLOWED_HOSTS",
            (
                "towardsai.com,www.towardsai.com,academy.towardsai.net,"
                "towardsai.net,www.towardsai.net"
            ),
        )
    )
    site_wide_hosts: tuple[str, ...] = field(
        default_factory=lambda: _csv_env(
            "HELPER_SITE_WIDE_HOSTS",
            "towardsai.com,www.towardsai.com",
        )
    )
    model_name: str = field(
        default_factory=lambda: (
            os.getenv("HELPER_MODEL", "deepseek:deepseek-v4-flash").strip()
            or "deepseek:deepseek-v4-flash"
        )
    )
    fallback_model_name: str = field(
        default_factory=lambda: (
            os.getenv("HELPER_FALLBACK_MODEL", "gemini-2.5-flash").strip()
            or "gemini-2.5-flash"
        )
    )
    openrouter_api_key: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY", "").strip()
    )
    deepseek_api_key: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", "").strip()
    )
    deepseek_base_url: str = field(
        default_factory=lambda: (
            os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            .strip()
            .rstrip("/")
            or "https://api.deepseek.com"
        )
    )
    gemini_api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "").strip()
    )
    openrouter_site_url: str = field(
        default_factory=lambda: (
            os.getenv("OPENROUTER_SITE_URL", "https://towardsai.com").strip()
            or "https://towardsai.com"
        )
    )
    openrouter_app_name: str = field(
        default_factory=lambda: (
            os.getenv("OPENROUTER_APP_NAME", "Towards AI Helper").strip()
            or "Towards AI Helper"
        )
    )
    request_timeout_seconds: int = field(
        default_factory=lambda: _int_env("HELPER_LLM_TIMEOUT_SECONDS", 45)
    )
    max_output_tokens: int = field(
        default_factory=lambda: _int_env("HELPER_MAX_OUTPUT_TOKENS", 420)
    )
    max_query_chars: int = field(
        default_factory=lambda: _int_env("HELPER_MAX_QUERY_CHARS", 600)
    )
    max_history_turns: int = field(
        default_factory=lambda: _int_env("HELPER_MAX_HISTORY_TURNS", 8)
    )
    catalog_max_age_days: int = field(
        default_factory=lambda: _int_env("HELPER_CATALOG_MAX_AGE_DAYS", 14)
    )
    rate_limit_per_minute: int = field(
        default_factory=lambda: _int_env("HELPER_RATE_LIMIT_PER_MINUTE", 8)
    )
    rate_limit_per_day: int = field(
        default_factory=lambda: _int_env("HELPER_RATE_LIMIT_PER_DAY", 50)
    )
    ip_rate_limit_per_minute: int = field(
        default_factory=lambda: _int_env("HELPER_IP_RATE_LIMIT_PER_MINUTE", 60)
    )
    ip_rate_limit_per_day: int = field(
        default_factory=lambda: _int_env("HELPER_IP_RATE_LIMIT_PER_DAY", 300)
    )
    rate_limit_global_per_minute: int = field(
        default_factory=lambda: _int_env("HELPER_GLOBAL_RATE_LIMIT_PER_MINUTE", 120)
    )
    opik_enabled: bool = field(
        default_factory=lambda: _bool_env_chain("HELPER_OPIK_ENABLED", "OPIK_ENABLED")
    )
    opik_api_key: str = field(
        default_factory=lambda: os.getenv("OPIK_API_KEY", "").strip()
    )
    opik_workspace: str = field(
        default_factory=lambda: os.getenv("OPIK_WORKSPACE", "").strip()
    )
    opik_project_name: str = field(
        default_factory=lambda: (
            os.getenv(
                "HELPER_OPIK_PROJECT_NAME",
                "towards-ai-helper",
            ).strip()
            or "towards-ai-helper"
        )
    )
    opik_max_text_chars: int = field(
        default_factory=lambda: _int_env("HELPER_OPIK_MAX_TEXT_CHARS", 4000)
    )

    def cors_origins(self) -> list[str]:
        return list(self.allowed_origins)


helper_settings = HelperSettings()
