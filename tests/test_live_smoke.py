from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator

import pytest
import requests


LIVE_BASE_URL = os.getenv("LIVE_SPACE_BASE_URL", "").rstrip("/")
RUN_LIVE_CHAT = os.getenv("RUN_LIVE_CHAT_SMOKE", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
RUN_ALL_COURSE_CHAT = os.getenv("RUN_LIVE_ALL_COURSE_CHAT", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

COURSE_URL_TO_SOURCE = {
    "https://academy.towardsai.net/courses/beginner-to-advanced-llm-dev": "full_stack_ai_engineering",
    "https://academy.towardsai.net/courses/python-for-genai": "beginner_python_for_ai_engineering",
    "https://academy.towardsai.net/courses/ai-business-professionals": "master_ai_for_work",
    "https://academy.towardsai.net/courses/agent-engineering": "agentic_ai_engineering",
}
THINKIFIC_HEADERS = {"Origin": "https://academy.towardsai.net"}


def require_live_base_url() -> str:
    if not LIVE_BASE_URL:
        pytest.skip("LIVE_SPACE_BASE_URL is not set")
    return LIVE_BASE_URL


def max_seconds(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def timed_request(method: str, url: str, **kwargs) -> tuple[requests.Response, float]:
    start = time.perf_counter()
    response = requests.request(method, url, **kwargs)
    elapsed = time.perf_counter() - start
    return response, elapsed


def lesson_context(course_url: str, source_key: str) -> dict:
    return {
        "url": f"{course_url}/lessons/live-smoke-test",
        "pageTitle": f"Live smoke test lesson for {source_key}",
        "course": {"id": f"live-{source_key}", "title": source_key},
        "chapter": {"id": "live-chapter", "title": "Smoke tests"},
        "lesson": {"id": "live-lesson", "title": "Smoke test lesson", "type": "text"},
        "user": {
            "id": os.getenv("LIVE_SMOKE_STUDENT_ID", "github-action-smoke"),
            "email": "smoke-test@example.com",
        },
        "enrollment": {
            "id": "live-enrollment",
            "user_id": os.getenv("LIVE_SMOKE_STUDENT_ID", "github-action-smoke"),
        },
        "pageText": "This is a synthetic lesson context used by deployment smoke tests.",
    }


def iter_sse_data(response: requests.Response) -> Iterator[dict | str]:
    buffer = ""
    for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
        if not chunk:
            continue
        buffer += chunk
        while "\n\n" in buffer:
            frame, buffer = buffer.split("\n\n", 1)
            data = "\n".join(
                line.removeprefix("data:").strip()
                for line in frame.splitlines()
                if line.startswith("data:")
            )
            if not data:
                continue
            if data == "[DONE]":
                yield data
            else:
                yield json.loads(data)


@pytest.mark.live
def test_live_health_and_widget_latency() -> None:
    base_url = require_live_base_url()

    health, health_seconds = timed_request("GET", f"{base_url}/healthz", timeout=120)
    widget, widget_seconds = timed_request("GET", f"{base_url}/widget.js", timeout=120)

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert health_seconds <= max_seconds("LIVE_SMOKE_MAX_HEALTH_SECONDS", 120)
    assert widget.status_code == 200
    assert "Ask the tutor" in widget.text
    assert "Towards AI Tutor" in widget.text
    assert "renderMarkdown" in widget.text
    assert "splitTrailingUrlPunctuation" in widget.text
    assert "displayUrl(rawUrl)" in widget.text
    assert "CoursePlayerV2" in widget.text
    assert "/api/thinkific/resolve" in widget.text
    assert widget_seconds <= max_seconds("LIVE_SMOKE_MAX_WIDGET_SECONDS", 30)


@pytest.mark.live
@pytest.mark.parametrize(
    ("course_url", "expected_source"),
    COURSE_URL_TO_SOURCE.items(),
)
def test_live_resolve_accepts_all_courses(
    course_url: str,
    expected_source: str,
) -> None:
    base_url = require_live_base_url()

    response, elapsed = timed_request(
        "POST",
        f"{base_url}/api/thinkific/resolve",
        json={"context": lesson_context(course_url, expected_source)},
        headers=THINKIFIC_HEADERS,
        timeout=60,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["eligible"] is True
    assert payload["sourceKey"] == expected_source
    assert elapsed <= max_seconds("LIVE_SMOKE_MAX_RESOLVE_SECONDS", 30)


@pytest.mark.live
def test_live_resolve_rejects_sales_anonymous_and_quiz_pages() -> None:
    base_url = require_live_base_url()
    course_url, source_key = next(iter(COURSE_URL_TO_SOURCE.items()))
    valid = lesson_context(course_url, source_key)
    anonymous = {**valid, "user": None, "enrollment": {}}
    sales_page = {**valid, "url": course_url, "lesson": None}
    quiz = {**valid, "lesson": {"id": "quiz-1", "title": "Final quiz", "type": "quiz"}}

    for context in (anonymous, sales_page, quiz):
        response = requests.post(
            f"{base_url}/api/thinkific/resolve",
            json={"context": context},
            headers=THINKIFIC_HEADERS,
            timeout=60,
        )
        assert response.status_code == 200
        assert response.json() == {"eligible": False}


@pytest.mark.live
@pytest.mark.skipif(
    not RUN_LIVE_CHAT,
    reason="RUN_LIVE_CHAT_SMOKE is not enabled",
)
@pytest.mark.parametrize(
    ("course_url", "expected_source"),
    list(COURSE_URL_TO_SOURCE.items()) if RUN_ALL_COURSE_CHAT else [next(iter(COURSE_URL_TO_SOURCE.items()))],
)
def test_live_chat_streams_non_empty_answer(
    course_url: str,
    expected_source: str,
) -> None:
    base_url = require_live_base_url()
    start = time.perf_counter()
    response = requests.post(
        f"{base_url}/api/thinkific/chat",
        json={
            "query": "Answer in one short sentence: what should I focus on in this lesson?",
            "threadId": "",
            "studentId": os.getenv("LIVE_SMOKE_STUDENT_ID", "github-action-smoke"),
            "context": lesson_context(course_url, expected_source),
        },
        headers=THINKIFIC_HEADERS,
        stream=True,
        timeout=180,
    )
    assert response.status_code == 200

    text = ""
    error = ""
    for event in iter_sse_data(response):
        if event == "[DONE]":
            break
        event_type = event.get("type")
        if event_type == "text-delta":
            text += event.get("delta", "")
            if text.strip():
                break
        elif event_type == "error":
            error = event.get("errorText", "")
            break

    first_text_seconds = time.perf_counter() - start
    assert not error
    assert text.strip()
    assert first_text_seconds <= max_seconds("LIVE_SMOKE_MAX_FIRST_TEXT_SECONDS", 90)
