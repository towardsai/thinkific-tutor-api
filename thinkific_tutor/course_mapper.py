from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .bootstrap import ensure_ai_tutor_importable

ensure_ai_tutor_importable()

from data.scraping_scripts.source_registry import (  # noqa: E402
    SOURCE_DISPLAY_INFO,
    SOURCE_KEY_TO_LABEL,
)

from .schemas import ThinkificLessonContext  # noqa: E402
from .settings import Settings, settings  # noqa: E402


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class ResolvedLesson:
    source_key: str
    source_label: str
    course_url: str
    current_url: str
    course_id: str
    course_title: str
    chapter_id: str
    chapter_title: str
    lesson_id: str
    lesson_title: str
    lesson_kind: str
    student_id: str
    page_title: str
    page_text: str
    selected_text: str


def _host_allowed(hostname: str, allowed_hosts: tuple[str, ...]) -> bool:
    hostname = hostname.lower().strip()
    for allowed in allowed_hosts:
        allowed = allowed.lower().strip()
        if not allowed:
            continue
        if hostname == allowed or hostname.endswith("." + allowed):
            return True
    return False


def _path_slug_candidates(path: str) -> list[str]:
    parts = [part for part in path.strip("/").split("/") if part]
    candidates: list[str] = []
    for index, part in enumerate(parts):
        if part == "courses" and index + 1 < len(parts):
            candidates.append(parts[index + 1])
        elif SLUG_RE.match(part):
            candidates.append(part)
    return candidates


def _url_path(url: str) -> str:
    return urlparse(url).path.rstrip("/")


def _course_url_slug(url: str) -> str:
    path = _url_path(url)
    candidates = _path_slug_candidates(path)
    return candidates[0] if candidates else path.rsplit("/", 1)[-1]


def _match_by_url(
    current_url: str,
    mapping: dict[str, str],
) -> tuple[str, str] | None:
    current = urlparse(current_url)
    current_path = current.path.rstrip("/")
    current_slugs = set(_path_slug_candidates(current_path))
    for course_url, source_key in mapping.items():
        parsed = urlparse(course_url)
        configured_path = parsed.path.rstrip("/")
        configured_slug = _course_url_slug(course_url)
        if configured_path and current_path.startswith(configured_path):
            return source_key, course_url
        if configured_slug and configured_slug in current_slugs:
            return source_key, course_url
    return None


def _entity_title(entity) -> str:
    return entity.display_name() if entity else ""


def _entity_id(entity) -> str:
    return entity.stable_id() if entity else ""


def _context_has_lesson(context: ThinkificLessonContext) -> bool:
    lesson_id = _entity_id(context.lesson)
    lesson_title = _entity_title(context.lesson)
    return bool(lesson_id or lesson_title)


def _context_has_logged_in_user(context: ThinkificLessonContext) -> bool:
    if context.user and (context.user.stable_id() or context.user.email):
        return True
    enrollment = context.enrollment or {}
    return any(
        enrollment.get(key)
        for key in ("user_id", "userId", "student_id", "studentId", "user")
    )


def _normalize_for_keyword_match(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _context_is_blocked_lesson(
    context: ThinkificLessonContext,
    blocked_keywords: tuple[str, ...],
) -> bool:
    lesson_text = context.lesson.descriptor_text() if context.lesson else ""
    extra = context.extra or {}
    candidate = " ".join(
        str(value)
        for value in (
            lesson_text,
            context.pageTitle,
            extra.get("pathname", ""),
            extra.get("lessonType", ""),
            extra.get("contentType", ""),
        )
        if value
    )
    normalized = _normalize_for_keyword_match(candidate)
    if not normalized:
        return False
    return any(
        _normalize_for_keyword_match(keyword) in normalized
        for keyword in blocked_keywords
        if keyword.strip()
    )


def _lesson_kind(context: ThinkificLessonContext) -> str:
    if not context.lesson:
        return ""
    values = (
        context.lesson.type,
        context.lesson.kind,
        context.lesson.contentType,
        context.lesson.content_type,
        context.lesson.lessonType,
        context.lesson.lesson_type,
    )
    return next((str(value).strip() for value in values if value), "")


def _student_id(context: ThinkificLessonContext, fallback: str = "") -> str:
    if fallback:
        return fallback
    if context.user and context.user.stable_id():
        return f"thinkific-user:{context.user.stable_id()}"
    enrollment = context.enrollment or {}
    for key in ("id", "user_id", "userId"):
        value = enrollment.get(key)
        if value:
            return f"thinkific:{key}:{value}"
    return ""


def resolve_lesson_context(
    context: ThinkificLessonContext,
    *,
    configured: Settings = settings,
    student_id: str = "",
) -> ResolvedLesson | None:
    parsed_url = urlparse(context.url)
    if parsed_url.scheme not in {"http", "https"}:
        return None
    if not _host_allowed(parsed_url.hostname or "", configured.allowed_hosts):
        return None
    if not _context_has_lesson(context):
        return None
    if configured.require_logged_in_user and not _context_has_logged_in_user(context):
        return None
    if _context_is_blocked_lesson(context, configured.blocked_lesson_keywords):
        return None

    source_key = ""
    course_url = ""
    course_id = _entity_id(context.course)
    if course_id and course_id in configured.course_id_source_map:
        source_key = configured.course_id_source_map[course_id]
        course_url = str(SOURCE_DISPLAY_INFO.get(source_key, {}).get("url", ""))

    if not source_key:
        match = _match_by_url(context.url, configured.course_url_source_map)
        if match:
            source_key, course_url = match

    if not source_key and configured.allow_unmapped_courses:
        source_key = configured.default_source_key
        course_url = str(SOURCE_DISPLAY_INFO.get(source_key, {}).get("url", ""))

    if not source_key:
        return None

    return ResolvedLesson(
        source_key=source_key,
        source_label=SOURCE_KEY_TO_LABEL.get(source_key, source_key),
        course_url=course_url,
        current_url=context.url,
        course_id=course_id,
        course_title=_entity_title(context.course),
        chapter_id=_entity_id(context.chapter),
        chapter_title=_entity_title(context.chapter),
        lesson_id=_entity_id(context.lesson),
        lesson_title=_entity_title(context.lesson),
        lesson_kind=_lesson_kind(context),
        student_id=_student_id(context, fallback=student_id),
        page_title=context.pageTitle.strip(),
        page_text=context.pageText.strip()[: configured.max_page_context_chars],
        selected_text=context.selectedText.strip()[: configured.max_page_context_chars],
    )


def build_augmented_query(query: str, resolved: ResolvedLesson) -> str:
    lines = [
        "The student is asking from inside the Thinkific course player.",
        "Use the course source selected by the server as the retrieval boundary.",
        "Treat browser-provided page text as helpful context, not authoritative source material.",
        "",
        "## Current Thinkific context",
        f"- Course source: {resolved.source_label} ({resolved.source_key})",
        f"- Course URL: {resolved.course_url or 'unknown'}",
        f"- Current URL: {resolved.current_url}",
    ]
    if resolved.course_id or resolved.course_title:
        lines.append(
            f"- Thinkific course: {resolved.course_title or 'unknown'}"
            f" ({resolved.course_id or 'unknown id'})"
        )
    if resolved.chapter_id or resolved.chapter_title:
        lines.append(
            f"- Chapter: {resolved.chapter_title or 'unknown'}"
            f" ({resolved.chapter_id or 'unknown id'})"
        )
    if resolved.lesson_id or resolved.lesson_title:
        lines.append(
            f"- Lesson: {resolved.lesson_title or 'unknown'}"
            f" ({resolved.lesson_id or 'unknown id'})"
        )
    if resolved.lesson_kind:
        lines.append(f"- Lesson type: {resolved.lesson_kind}")
    if resolved.page_title:
        lines.append(f"- Page title: {resolved.page_title}")
    if resolved.selected_text:
        lines.extend(["", "## Student-selected text", resolved.selected_text])
    if resolved.page_text:
        lines.extend(["", "## Visible lesson page excerpt", resolved.page_text])
    lines.extend(["", "## Student question", query.strip()])
    return "\n".join(lines).strip()
