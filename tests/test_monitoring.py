from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import thinkific_tutor.monitoring as monitoring
import thinkific_tutor.helper_monitoring as helper_monitoring
from thinkific_tutor.course_mapper import ResolvedLesson
from thinkific_tutor.helper_monitoring import HelperRateLimitMonitor
from thinkific_tutor.helper_settings import helper_settings
from thinkific_tutor.monitoring import OpikRateLimitMonitor, OpikTurnMonitor
from thinkific_tutor.settings import settings


class FakeSpan:
    def __init__(self, kwargs: dict[str, Any]) -> None:
        self.kwargs = kwargs
        self.usage: dict[str, Any] | None = None
        self.total_cost: float | None = None
        self.error_info: dict[str, Any] | None = None


class FakeSpanContext:
    def __init__(self, span: FakeSpan) -> None:
        self.span = span

    def __enter__(self) -> FakeSpan:
        return self.span

    def __exit__(self, *_args: Any) -> None:
        return None


class FakeOpik:
    def __init__(self) -> None:
        self.configure_calls: list[dict[str, Any]] = []
        self.spans: list[FakeSpan] = []

    def configure(self, **kwargs: Any) -> None:
        self.configure_calls.append(kwargs)

    def start_as_current_span(self, **kwargs: Any) -> FakeSpanContext:
        span = FakeSpan(kwargs)
        self.spans.append(span)
        return FakeSpanContext(span)


def resolved_lesson() -> ResolvedLesson:
    return ResolvedLesson(
        source_key="agentic_ai_engineering",
        source_label="Agentic AI Engineering",
        course_url="https://academy.towardsai.net/courses/agent-engineering",
        current_url="https://academy.towardsai.net/courses/agent-engineering/lessons/intro",
        course_id="course-1",
        course_title="Agentic AI Engineering",
        chapter_id="chapter-1",
        chapter_title="Foundations",
        lesson_id="lesson-1",
        lesson_title="Intro",
        lesson_kind="video",
        student_id="thinkific-user:student-1",
        page_title="Intro",
        page_text="Do not copy this full page text into monitoring.",
        selected_text="",
    )


def event(event_type: str, data: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type=event_type, data=data)


def test_opik_monitor_writes_usage_metadata_without_page_text() -> None:
    monitoring._OPIK_CONFIGURED_FOR = None
    fake_opik = FakeOpik()
    configured = replace(
        settings,
        opik_enabled=True,
        opik_api_key="opik-test-key",
        opik_workspace="towards-ai",
        opik_project_name="towards-ai-thinkific-tutor",
    )
    chat_request = SimpleNamespace(
        model_name="google-genai:gemini-2.5-flash",
        thread_id="thread-from-request",
        memory_preset="",
        disable_kb=True,
        retrieval_budget=24000,
    )
    monitor = OpikTurnMonitor(
        resolved=resolved_lesson(),
        user_query="What should I focus on?",
        chat_request=chat_request,
        origin="https://academy.towardsai.net",
        configured=configured,
        opik_module=fake_opik,
    )

    monitor.observe_event(event("thread_started", {"thread_id": "thread-1"}))
    monitor.observe_event(event("message_started", {"message_id": "message-1"}))
    monitor.observe_event(event("text_delta", {"text": "Focus on "}))
    monitor.observe_event(event("text_delta", {"text": "tool calling."}))
    monitor.observe_event(
        event(
            "context_stats",
            {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "est_cost_usd": 0.00012,
                "ttft_ms": 300,
                "total_ms": 900,
            },
        )
    )
    monitor.observe_event(
        event("message_completed", {"answer": "Focus on tool calling."})
    )

    monitor.flush()

    assert fake_opik.configure_calls
    assert fake_opik.configure_calls[0]["api_key"] == "opik-test-key"
    assert fake_opik.configure_calls[0]["workspace"] == "towards-ai"
    span = fake_opik.spans[0]
    assert span.kwargs["project_name"] == "towards-ai-thinkific-tutor"
    assert span.kwargs["model"] == "google-genai:gemini-2.5-flash"
    assert span.kwargs["input"]["query"] == "What should I focus on?"
    assert span.kwargs["output"]["answer"] == "Focus on tool calling."
    assert span.kwargs["metadata"]["course_source_key"] == "agentic_ai_engineering"
    assert span.kwargs["metadata"]["lesson_title"] == "Intro"
    assert "page_text" not in span.kwargs["metadata"]
    assert span.usage == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }
    assert span.total_cost == 0.00012


def test_opik_monitor_is_noop_until_enabled() -> None:
    fake_opik = FakeOpik()
    configured = replace(
        settings,
        opik_enabled=False,
        opik_api_key="opik-test-key",
    )
    monitor = OpikTurnMonitor(
        resolved=resolved_lesson(),
        user_query="Hello?",
        chat_request=SimpleNamespace(model_name="google-genai:gemini-2.5-flash"),
        configured=configured,
        opik_module=fake_opik,
    )

    monitor.flush()

    assert fake_opik.configure_calls == []
    assert fake_opik.spans == []


def test_opik_rate_limit_monitor_writes_blocked_span() -> None:
    monitoring._OPIK_CONFIGURED_FOR = None
    fake_opik = FakeOpik()
    configured = replace(
        settings,
        opik_enabled=True,
        opik_api_key="opik-test-key",
        opik_workspace="towards-ai",
        opik_project_name="towards-ai-thinkific-tutor",
    )
    monitor = OpikRateLimitMonitor(
        resolved=resolved_lesson(),
        user_query="Why did this stop?",
        limit_name="per_minute",
        retry_after_seconds=42,
        rate_key="thinkific-user:student-1",
        client_ip="203.0.113.10",
        scope="student",
        origin="https://academy.towardsai.net",
        configured=configured,
        opik_module=fake_opik,
    )

    monitor.flush()

    assert fake_opik.configure_calls
    span = fake_opik.spans[0]
    assert span.kwargs["name"] == "thinkific_tutor_rate_limit"
    assert span.kwargs["type"] == "general"
    assert span.kwargs["project_name"] == "towards-ai-thinkific-tutor"
    assert span.kwargs["provider"] == "rate_limiter"
    assert span.kwargs["output"] == {"blocked": True, "reason": "rate_limited"}
    assert span.kwargs["metadata"]["status"] == "rate_limited"
    assert span.kwargs["metadata"]["bot"] == "thinkific-course-tutor"
    assert span.kwargs["metadata"]["limit_name"] == "per_minute"
    assert span.kwargs["metadata"]["retry_after_seconds"] == 42
    assert span.kwargs["metadata"]["student_id"] == "thinkific-user:student-1"
    assert span.kwargs["metadata"]["lesson_title"] == "Intro"
    assert "page_text" not in span.kwargs["metadata"]
    assert "rate-limit" in span.kwargs["tags"]
    assert span.error_info == {
        "exception_type": "RateLimitExceeded",
        "message": "per_minute exceeded",
        "traceback": "",
    }


def test_helper_rate_limit_monitor_writes_blocked_span() -> None:
    helper_monitoring._OPIK_CONFIGURED_FOR = None
    fake_opik = FakeOpik()
    configured = replace(
        helper_settings,
        opik_enabled=True,
        opik_api_key="opik-test-key",
        opik_workspace="towards-ai",
        opik_project_name="towards-ai-helper",
    )
    monitor = HelperRateLimitMonitor(
        query="I want to find mentors",
        current_url="https://academy.towardsai.net/",
        selected_prompt="I want to find mentors",
        visitor_key="visitor:test",
        client_ip="203.0.113.20",
        limit_name="helper_per_minute",
        retry_after_seconds=31,
        scope="visitor",
        configured=configured,
        opik_module=fake_opik,
    )

    monitor.flush()

    assert fake_opik.configure_calls
    span = fake_opik.spans[0]
    assert span.kwargs["name"] == "towards_ai_helper_rate_limit"
    assert span.kwargs["type"] == "general"
    assert span.kwargs["project_name"] == "towards-ai-helper"
    assert span.kwargs["provider"] == "rate_limiter"
    assert span.kwargs["output"] == {"blocked": True, "reason": "rate_limited"}
    assert span.kwargs["metadata"]["status"] == "rate_limited"
    assert span.kwargs["metadata"]["bot"] == "public-sales-helper"
    assert span.kwargs["metadata"]["limit_name"] == "helper_per_minute"
    assert span.kwargs["metadata"]["retry_after_seconds"] == 31
    assert span.kwargs["metadata"]["visitor_key"] == "visitor:test"
    assert "rate-limit" in span.kwargs["tags"]
    assert span.error_info == {
        "exception_type": "RateLimitExceeded",
        "message": "helper_per_minute exceeded",
        "traceback": "",
    }
