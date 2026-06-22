from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import thinkific_tutor.monitoring as monitoring
from thinkific_tutor.course_mapper import ResolvedLesson
from thinkific_tutor.monitoring import OpikTurnMonitor
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
