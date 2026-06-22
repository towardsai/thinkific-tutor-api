from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from .course_mapper import ResolvedLesson
from .settings import Settings, settings

logger = logging.getLogger(__name__)

_OPIK_CONFIGURED_FOR: tuple[str, str, str] | None = None
_OPIK_IMPORT_WARNING_EMITTED = False


def _truncate(value: str, limit: int) -> str:
    value = value.strip()
    if limit <= 0 or len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def _compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item not in (None, "", [], {}, ())
    }


def _import_opik() -> Any | None:
    global _OPIK_IMPORT_WARNING_EMITTED
    try:
        import opik  # type: ignore[import-not-found]
    except Exception:
        if not _OPIK_IMPORT_WARNING_EMITTED:
            logger.warning("Opik monitoring is enabled but the opik package is unavailable.")
            _OPIK_IMPORT_WARNING_EMITTED = True
        return None
    return opik


def _configure_opik(opik: Any, configured: Settings) -> None:
    global _OPIK_CONFIGURED_FOR
    signature = (
        configured.opik_api_key,
        configured.opik_workspace,
        configured.opik_project_name,
    )
    if _OPIK_CONFIGURED_FOR == signature:
        return

    os.environ["OPIK_API_KEY"] = configured.opik_api_key
    os.environ["OPIK_PROJECT_NAME"] = configured.opik_project_name
    if configured.opik_workspace:
        os.environ["OPIK_WORKSPACE"] = configured.opik_workspace

    configure = getattr(opik, "configure", None)
    if callable(configure):
        kwargs = {
            "api_key": configured.opik_api_key,
            "use_local": False,
            "force": True,
            "automatic_approvals": True,
        }
        if configured.opik_workspace:
            kwargs["workspace"] = configured.opik_workspace
        configure(**kwargs)

    _OPIK_CONFIGURED_FOR = signature


def _usage_from_stats(stats: dict[str, Any]) -> dict[str, Any]:
    return _compact_dict(
        {
            "prompt_tokens": stats.get("input_tokens"),
            "completion_tokens": stats.get("output_tokens"),
            "total_tokens": stats.get("total_tokens"),
            "cache_read_tokens": stats.get("cache_read_tokens"),
            "cache_creation_tokens": stats.get("cache_creation_tokens"),
        }
    )


@dataclass(slots=True)
class OpikTurnMonitor:
    resolved: ResolvedLesson
    user_query: str
    chat_request: Any
    origin: str = ""
    referer: str = ""
    configured: Settings = settings
    opik_module: Any | None = None
    started_at: float = field(default_factory=time.monotonic)
    thread_id: str = ""
    message_id: str = ""
    answer_chunks: list[str] = field(default_factory=list)
    completed_answer: str = ""
    context_stats: dict[str, Any] = field(default_factory=dict)

    @property
    def enabled(self) -> bool:
        return bool(self.configured.opik_enabled and self.configured.opik_api_key)

    def observe_event(self, event: Any) -> None:
        if not self.enabled:
            return

        event_type = str(getattr(event, "type", ""))
        data = getattr(event, "data", {}) or {}
        if event_type == "thread_started":
            self.thread_id = str(data.get("thread_id", "")).strip()
        elif event_type == "message_started":
            self.message_id = str(data.get("message_id", "")).strip()
        elif event_type == "text_delta":
            self.answer_chunks.append(str(data.get("text", "")))
        elif event_type == "context_stats":
            self.context_stats = dict(data)
        elif event_type == "message_completed":
            self.completed_answer = str(data.get("answer", "")).strip()
            self.thread_id = self.thread_id or str(data.get("thread_id", "")).strip()
            self.message_id = self.message_id or str(data.get("message_id", "")).strip()

    def flush(self, error_message: str = "") -> None:
        if not self.enabled:
            return

        opik = self.opik_module or _import_opik()
        if opik is None:
            return

        try:
            _configure_opik(opik, self.configured)
            self._write_span(opik, error_message=error_message)
        except Exception:
            logger.warning("Failed to write Opik tutor trace.", exc_info=True)

    def _write_span(self, opik: Any, *, error_message: str = "") -> None:
        duration_ms = int((time.monotonic() - self.started_at) * 1000)
        answer = self.completed_answer or "".join(self.answer_chunks).strip()
        answer = _truncate(answer, self.configured.opik_max_text_chars)
        query = _truncate(self.user_query, self.configured.opik_max_text_chars)

        metadata = _compact_dict(
            {
                "course_source_key": self.resolved.source_key,
                "course_source_label": self.resolved.source_label,
                "course_url": self.resolved.course_url,
                "current_url": self.resolved.current_url,
                "course_id": self.resolved.course_id,
                "course_title": self.resolved.course_title,
                "chapter_id": self.resolved.chapter_id,
                "chapter_title": self.resolved.chapter_title,
                "lesson_id": self.resolved.lesson_id,
                "lesson_title": self.resolved.lesson_title,
                "lesson_kind": self.resolved.lesson_kind,
                "student_id": self.resolved.student_id,
                "thread_id": self.thread_id or getattr(self.chat_request, "thread_id", ""),
                "message_id": self.message_id,
                "origin": self.origin,
                "referer": self.referer,
                "memory_preset": self.context_stats.get("memory_preset")
                or getattr(self.chat_request, "memory_preset", ""),
                "llm_calls": self.context_stats.get("llm_calls"),
                "ttft_ms": self.context_stats.get("ttft_ms"),
                "total_ms": self.context_stats.get("total_ms") or duration_ms,
                "context_messages": self.context_stats.get("context_messages"),
                "context_tokens_approx": self.context_stats.get(
                    "context_tokens_approx"
                ),
                "summary_messages": self.context_stats.get("summary_messages"),
                "cleared_tool_outputs": self.context_stats.get(
                    "cleared_tool_outputs"
                ),
                "disable_kb": getattr(self.chat_request, "disable_kb", None),
                "retrieval_budget": getattr(self.chat_request, "retrieval_budget", None),
                "status": "error" if error_message else "completed",
            }
        )
        usage = _usage_from_stats(self.context_stats)
        cost = self.context_stats.get("est_cost_usd")
        tags = [
            "thinkific",
            "course-tutor",
            self.resolved.source_key,
        ]

        span_kwargs = {
            "name": "thinkific_tutor_chat",
            "type": "llm",
            "input": {
                "query": query,
                "course": self.resolved.source_label,
                "lesson": self.resolved.lesson_title,
            },
            "output": {"answer": answer},
            "metadata": metadata,
            "tags": tags,
            "project_name": self.configured.opik_project_name,
            "model": getattr(self.chat_request, "model_name", self.configured.model_name),
            "provider": "google_genai",
            "flush": True,
        }

        with opik.start_as_current_span(**span_kwargs) as span:
            if usage:
                span.usage = usage
            if isinstance(cost, int | float):
                span.total_cost = float(cost)
            if error_message:
                span.error_info = {
                    "type": "RuntimeError",
                    "message": _truncate(error_message, 1000),
                }
