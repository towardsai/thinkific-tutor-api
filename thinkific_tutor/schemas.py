from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator


MAX_QUERY_CHARS = 8000
MAX_TURN_CHARS = 16000
MAX_HISTORY_TURNS = 24
MAX_CONTEXT_JSON_CHARS = 128000


class ChatTurnIn(BaseModel):
    role: str = Field(max_length=32)
    content: str = Field(max_length=MAX_TURN_CHARS)


class ThinkificEntity(BaseModel):
    id: str | int | None = None
    title: str | None = Field(default=None, max_length=500)
    name: str | None = Field(default=None, max_length=500)
    slug: str | None = Field(default=None, max_length=500)
    type: str | None = Field(default=None, max_length=160)
    kind: str | None = Field(default=None, max_length=160)
    contentType: str | None = Field(default=None, max_length=160)
    content_type: str | None = Field(default=None, max_length=160)
    lessonType: str | None = Field(default=None, max_length=160)
    lesson_type: str | None = Field(default=None, max_length=160)

    def stable_id(self) -> str:
        return "" if self.id is None else str(self.id).strip()

    def display_name(self) -> str:
        return (self.title or self.name or self.slug or "").strip()

    def descriptor_text(self) -> str:
        values = (
            self.type,
            self.kind,
            self.contentType,
            self.content_type,
            self.lessonType,
            self.lesson_type,
            self.title,
            self.name,
            self.slug,
        )
        return " ".join(str(value).strip() for value in values if value)


class ThinkificUser(BaseModel):
    id: str | int | None = None
    email: str | None = Field(default=None, max_length=320)
    firstName: str | None = Field(default=None, max_length=160)
    lastName: str | None = Field(default=None, max_length=160)

    def stable_id(self) -> str:
        return "" if self.id is None else str(self.id).strip()


class ThinkificLessonContext(BaseModel):
    url: str = Field(default="", max_length=2048)
    origin: str = Field(default="", max_length=512)
    referrer: str = Field(default="", max_length=2048)
    pageTitle: str = Field(default="", max_length=500)
    course: ThinkificEntity | None = None
    chapter: ThinkificEntity | None = None
    lesson: ThinkificEntity | None = None
    enrollment: dict[str, Any] | None = None
    user: ThinkificUser | None = None
    selectedText: str = Field(default="", max_length=4000)
    pageText: str = Field(default="", max_length=24000)
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("extra")
    @classmethod
    def _cap_extra_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, ensure_ascii=False)) > MAX_CONTEXT_JSON_CHARS:
            raise ValueError("extra context is too large")
        return value


class ThinkificChatRequest(BaseModel):
    query: str = Field(max_length=MAX_QUERY_CHARS)
    history: list[ChatTurnIn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)
    threadId: str = Field(default="", max_length=128)
    studentId: str = Field(default="", max_length=128)
    context: ThinkificLessonContext


class ResolveRequest(BaseModel):
    context: ThinkificLessonContext
