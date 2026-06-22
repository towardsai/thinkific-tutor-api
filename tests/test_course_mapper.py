from __future__ import annotations

from thinkific_tutor.course_mapper import build_augmented_query, resolve_lesson_context
from thinkific_tutor.schemas import (
    ThinkificEntity,
    ThinkificLessonContext,
    ThinkificUser,
)


def logged_in_user() -> ThinkificUser:
    return ThinkificUser(id="student-1", email="student@example.com")


def test_resolves_course_from_academy_url() -> None:
    context = ThinkificLessonContext(
        url="https://academy.towardsai.net/courses/beginner-to-advanced-llm-dev/lessons/intro",
        course=ThinkificEntity(id="123", title="Full Stack AI Engineering"),
        lesson=ThinkificEntity(id="456", title="Welcome"),
        user=logged_in_user(),
    )

    resolved = resolve_lesson_context(context)

    assert resolved is not None
    assert resolved.source_key == "full_stack_ai_engineering"
    assert resolved.lesson_id == "456"


def test_rejects_domain_without_lesson() -> None:
    context = ThinkificLessonContext(
        url="https://academy.towardsai.net/",
        course=ThinkificEntity(id="123", title="Full Stack AI Engineering"),
        user=logged_in_user(),
    )

    assert resolve_lesson_context(context) is None


def test_rejects_anonymous_lesson_context() -> None:
    context = ThinkificLessonContext(
        url="https://academy.towardsai.net/courses/beginner-to-advanced-llm-dev/lessons/intro",
        course=ThinkificEntity(id="123", title="Full Stack AI Engineering"),
        lesson=ThinkificEntity(id="456", title="Welcome"),
    )

    assert resolve_lesson_context(context) is None


def test_rejects_quiz_lesson_context() -> None:
    context = ThinkificLessonContext(
        url="https://academy.towardsai.net/courses/beginner-to-advanced-llm-dev/quizzes/final",
        course=ThinkificEntity(id="123", title="Full Stack AI Engineering"),
        lesson=ThinkificEntity(id="456", title="Final quiz", type="quiz"),
        user=logged_in_user(),
    )

    assert resolve_lesson_context(context) is None


def test_augmented_query_includes_lesson_context() -> None:
    context = ThinkificLessonContext(
        url="https://academy.towardsai.net/courses/agent-engineering/lessons/tools",
        course=ThinkificEntity(id="1", title="Agentic AI Engineering"),
        chapter=ThinkificEntity(id="2", title="Tool use"),
        lesson=ThinkificEntity(id="3", title="Calling tools", type="video"),
        user=logged_in_user(),
        pageText="Visible lesson content",
    )
    resolved = resolve_lesson_context(context)

    assert resolved is not None
    prompt = build_augmented_query("How does tool calling work?", resolved)

    assert "Agentic AI Engineering" in prompt
    assert "Calling tools" in prompt
    assert "How does tool calling work?" in prompt
