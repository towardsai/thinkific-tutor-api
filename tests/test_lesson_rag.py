from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

from fastapi.testclient import TestClient

from thinkific_tutor import api, lesson_rag
from thinkific_tutor.course_mapper import resolve_lesson_context
from thinkific_tutor.rate_limiter import FixedWindowRateLimiter, RateLimit
from thinkific_tutor.schemas import ThinkificLessonContext
from app.chat_types import ChatEvent


TITLE = "Lesson 0: Build a Research and Writing Agent with MCP"
client = TestClient(api.app)


def lesson_context():
    return {
        "url": "https://academy.towardsai.net/courses/agent-engineering/lessons/lesson-0",
        "course": {"title": "Agent Engineering", "slug": "agent-engineering"},
        "lesson": {"id": "lesson-0", "title": TITLE},
        "user": {"id": "rag-regression"},
    }


def current_lesson():
    context = lesson_context()
    return resolve_lesson_context(ThinkificLessonContext.model_validate(context))


def document(source="agentic_ai_engineering", title=TITLE):
    return lesson_rag.LessonDocument(
        "regression-lesson", source, title,
        "https://academy.towardsai.net/courses/agent-engineering/lessons/lesson-0",
        "Build research and writing tools exposed through an MCP server. "
        "The researcher collects notes and the writer turns those notes into an article.",
    )


def test_deictic_question_retrieves_current_lesson_content(monkeypatch):
    unrelated = replace(document(title="Memory management"), url="https://example.com/memory")
    exact = document()
    monkeypatch.setattr(lesson_rag, "course_documents", lambda source: (unrelated, exact))
    evidence = lesson_rag.retrieve_lesson_evidence("what is it about", current_lesson())
    assert evidence.current_lesson_found
    assert evidence.documents == (exact,)
    assert "researcher collects notes" in evidence.text
    assert "Memory management" not in evidence.text


def test_current_lesson_never_matches_another_course():
    assert not lesson_rag.match_current_lesson(
        document(source="full_stack_ai_engineering"), current_lesson()
    )


def test_embed_url_resolves_a_blueprint_when_titles_differ():
    blueprint = document(source="production_blueprints", title="Source page title")
    lesson = replace(
        current_lesson(), source_key="production_blueprints",
        lesson_title="Thinkific wrapper title", content_urls=(blueprint.url,),
    )
    assert lesson_rag.match_current_lesson(blueprint, lesson)


def test_prefetch_does_not_generate_a_title_based_summary(monkeypatch):
    monkeypatch.setattr(api, "student_limiter", FixedWindowRateLimiter((RateLimit("test", 100, 60),)))
    monkeypatch.setattr(api, "global_limiter", FixedWindowRateLimiter((RateLimit("test", 100, 60),)))
    monkeypatch.setattr(api, "settings", replace(api.settings, lesson_prefetch_enabled=True))
    monkeypatch.setattr(
        api, "retrieve_lesson_evidence",
        lambda *args: lesson_rag.LessonEvidence("", (), False),
    )
    context = lesson_context()
    response = client.post(
        "/api/thinkific/chat",
        json={"query": "what is it about", "context": context},
        headers={"Origin": "https://academy.towardsai.net"},
    )
    assert response.status_code == 409
    assert "indexed copy of this lesson" in response.json()["detail"]


def test_api_supplies_lesson_body_and_emits_its_source(monkeypatch):
    monkeypatch.setattr(api, "student_limiter", FixedWindowRateLimiter((RateLimit("test", 100, 60),)))
    monkeypatch.setattr(api, "global_limiter", FixedWindowRateLimiter((RateLimit("test", 100, 60),)))
    monkeypatch.setattr(api, "settings", replace(api.settings, lesson_prefetch_enabled=True))
    exact = document()
    monkeypatch.setattr(
        api, "retrieve_lesson_evidence",
        lambda *args: lesson_rag.LessonEvidence(exact.content, (exact,), True),
    )
    captured = []

    async def fake_stream(request):
        captured.append(request)
        yield ChatEvent("thread_started", {"thread_id": "grounding-test"})
        yield ChatEvent("message_started", {"message_id": "grounding-test-message"})
        yield ChatEvent("text_delta", {"text": "Build research and writing tools with MCP."})
        yield ChatEvent("message_completed", {"answer": "Build research and writing tools with MCP."})

    monkeypatch.setattr(api, "stream_chat", fake_stream)
    response = client.post(
        "/api/thinkific/chat",
        json={"query": "what is it about", "context": lesson_context()},
        headers={"Origin": "https://academy.towardsai.net"},
    )
    assert response.status_code == 200
    assert exact.content in captured[0].query
    assert captured[0].query.endswith("what is it about")
    assert captured[0].source_keys == ()
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    assert any(e.get("type") == "source-url" and e.get("url") == exact.url for e in events)
    assert any(e.get("type") == "text-delta" for e in events)


def test_unpublished_material_is_not_retrievable_even_by_exact_url(monkeypatch):
    monkeypatch.setattr(lesson_rag, "course_documents", lambda source: (replace(document(), published=False),))
    evidence = lesson_rag.retrieve_lesson_evidence("what is it about", current_lesson())
    assert not evidence.text
    assert not evidence.current_lesson_found


def test_existing_full_document_name_field_is_indexed(monkeypatch):
    from app import chat_service

    lesson_rag.course_documents.cache_clear()
    monkeypatch.setattr(lesson_rag, "private_lessons", lambda: ())
    monkeypatch.setattr(chat_service, "get_retriever", lambda: SimpleNamespace(
        _document_dict={"real-shape": {
            "name": TITLE, "source": "agentic_ai_engineering",
            "url": document().url, "content": document().content,
        }},
    ))
    try:
        records = lesson_rag.course_documents("agentic_ai_engineering")
        assert records[0].title == TITLE
        assert lesson_rag.match_current_lesson(records[0], current_lesson())
    finally:
        lesson_rag.course_documents.cache_clear()
