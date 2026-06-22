from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from thinkific_tutor.bootstrap import ensure_ai_tutor_importable

ensure_ai_tutor_importable()

from app.chat_types import ChatEvent  # noqa: E402

from thinkific_tutor import api  # noqa: E402
from thinkific_tutor.rate_limiter import FixedWindowRateLimiter, RateLimit  # noqa: E402
from thinkific_tutor.settings import settings  # noqa: E402

client = TestClient(api.app)


def lesson_context(
    course_url: str,
    *,
    course_id: str = "course-1",
    lesson_type: str = "video",
    user_id: str = "student-1",
) -> dict:
    return {
        "url": f"{course_url.rstrip('/')}/lessons/test-lesson",
        "pageTitle": "Test lesson",
        "course": {"id": course_id, "title": "Course"},
        "chapter": {"id": "chapter-1", "title": "Chapter"},
        "lesson": {"id": "lesson-1", "title": "Lesson", "type": lesson_type},
        "user": {"id": user_id, "email": f"{user_id}@example.com"} if user_id else None,
        "enrollment": {"id": "enrollment-1", "user_id": user_id} if user_id else {},
        "pageText": "This lesson explains retrieval augmented generation.",
    }


def parse_sse(text: str) -> list[dict | str]:
    events: list[dict | str] = []
    for frame in text.split("\n\n"):
        data = "\n".join(
            line.removeprefix("data:").strip()
            for line in frame.splitlines()
            if line.startswith("data:")
        )
        if not data:
            continue
        if data == "[DONE]":
            events.append(data)
            continue
        events.append(json.loads(data))
    return events


def reset_limiters() -> None:
    api.student_limiter = FixedWindowRateLimiter(
        (
            RateLimit("per_minute", 100, 60),
            RateLimit("per_day", 1000, 24 * 60 * 60),
        )
    )
    api.global_limiter = FixedWindowRateLimiter(
        (RateLimit("global_per_minute", 1000, 60),)
    )


def test_resolve_endpoint_accepts_every_configured_course_url() -> None:
    for course_url, expected_source in settings.course_url_source_map.items():
        response = client.post(
            "/api/thinkific/resolve",
            json={"context": lesson_context(course_url)},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["eligible"] is True
        assert payload["sourceKey"] == expected_source


def test_resolve_endpoint_rejects_anonymous_and_quiz_contexts() -> None:
    course_url = next(iter(settings.course_url_source_map))

    anonymous = client.post(
        "/api/thinkific/resolve",
        json={"context": lesson_context(course_url, user_id="")},
    )
    quiz = client.post(
        "/api/thinkific/resolve",
        json={"context": lesson_context(course_url, lesson_type="quiz")},
    )

    assert anonymous.status_code == 200
    assert anonymous.json() == {"eligible": False}
    assert quiz.status_code == 200
    assert quiz.json() == {"eligible": False}


def test_widget_serves_course_player_gating_script() -> None:
    response = client.get("/widget.js")

    assert response.status_code == 200
    assert "application/javascript" in response.headers["content-type"]
    assert "CoursePlayerV2" in response.text
    assert "/api/thinkific/resolve" in response.text
    assert "quiz" in response.text


def test_chat_endpoint_streams_mocked_answer_and_forces_course_source(
    monkeypatch,
) -> None:
    reset_limiters()
    captured_requests = []
    course_url, expected_source = next(iter(settings.course_url_source_map.items()))

    async def fake_stream_chat(chat_request) -> AsyncIterator[ChatEvent]:
        captured_requests.append(chat_request)
        yield ChatEvent("thread_started", {"thread_id": "thread-1"})
        yield ChatEvent("message_started", {"message_id": "message-1"})
        yield ChatEvent("text_delta", {"text": "Mock tutor answer."})
        yield ChatEvent("message_completed", {"answer": "Mock tutor answer."})

    monkeypatch.setattr(api, "stream_chat", fake_stream_chat)

    response = client.post(
        "/api/thinkific/chat",
        json={
            "query": "What is RAG?",
            "threadId": "",
            "context": lesson_context(course_url, user_id="student-chat"),
        },
    )

    assert response.status_code == 200
    events = parse_sse(response.text)
    assert any(
        event != "[DONE]" and event.get("type") == "text-delta"
        and event.get("delta") == "Mock tutor answer."
        for event in events
    )
    assert events[-1] == "[DONE]"
    assert len(captured_requests) == 1
    assert captured_requests[0].source_keys == (expected_source,)
    assert captured_requests[0].model_name == settings.model_name
    assert "## Current Thinkific context" in captured_requests[0].query


def test_chat_endpoint_rejects_unmapped_or_quiz_context(monkeypatch) -> None:
    reset_limiters()

    async def unexpected_stream_chat(_chat_request) -> AsyncIterator[ChatEvent]:
        raise AssertionError("stream_chat should not be called")
        yield  # pragma: no cover

    monkeypatch.setattr(api, "stream_chat", unexpected_stream_chat)

    unmapped = client.post(
        "/api/thinkific/chat",
        json={
            "query": "Can you help?",
            "context": lesson_context("https://academy.towardsai.net/courses/not-real"),
        },
    )
    course_url = next(iter(settings.course_url_source_map))
    quiz = client.post(
        "/api/thinkific/chat",
        json={
            "query": "What is the answer?",
            "context": lesson_context(course_url, lesson_type="quiz"),
        },
    )

    assert unmapped.status_code == 403
    assert quiz.status_code == 403


def test_chat_endpoint_applies_rate_limit(monkeypatch) -> None:
    api.student_limiter = FixedWindowRateLimiter((RateLimit("per_minute", 1, 60),))
    api.global_limiter = FixedWindowRateLimiter(
        (RateLimit("global_per_minute", 100, 60),)
    )
    course_url = next(iter(settings.course_url_source_map))

    async def fake_stream_chat(_chat_request) -> AsyncIterator[ChatEvent]:
        yield ChatEvent("thread_started", {"thread_id": "thread-1"})
        yield ChatEvent("message_started", {"message_id": "message-1"})
        yield ChatEvent("text_delta", {"text": "ok"})
        yield ChatEvent("message_completed", {"answer": "ok"})

    monkeypatch.setattr(api, "stream_chat", fake_stream_chat)
    payload = {
        "query": "What is RAG?",
        "context": lesson_context(course_url, user_id="rate-limited-student"),
    }

    first = client.post("/api/thinkific/chat", json=payload)
    second = client.post("/api/thinkific/chat", json=payload)

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0
