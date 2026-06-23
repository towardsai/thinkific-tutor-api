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


def test_resolves_llm_primer_from_course_player_url() -> None:
    # Real Thinkific Course Player URLs use the /courses/take/<slug>/lessons/...
    # form, so resolution relies on slug matching against the ai-tutor-app
    # `llm-primer` course URL rather than a path prefix.
    context = ThinkificLessonContext(
        url="https://academy.towardsai.net/courses/take/llm-primer/lessons/65266782-foundational-knowledge-and-using-llms",
        course=ThinkificEntity(
            id="999", title="10-Hour Video-based Crash Course on LLM Fundamentals"
        ),
        lesson=ThinkificEntity(
            id="65266782", title="Foundational Knowledge and Using LLMs", type="video"
        ),
        user=logged_in_user(),
    )

    resolved = resolve_lesson_context(context)

    assert resolved is not None
    assert resolved.source_key == "llm_primer"
    assert (
        resolved.source_label == "10-Hour Video-based Crash Course on LLM Fundamentals"
    )


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
