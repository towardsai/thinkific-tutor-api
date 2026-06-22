from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .bootstrap import ensure_ai_tutor_importable, repo_root
from .course_mapper import ResolvedLesson, build_augmented_query, resolve_lesson_context
from .helper_router import router as helper_router
from .helper_settings import helper_settings
from .monitoring import OpikRateLimitMonitor, OpikTurnMonitor
from .rate_limiter import FixedWindowRateLimiter, RateLimit
from .schemas import ChatTurnIn, ResolveRequest, ThinkificChatRequest
from .settings import settings

ensure_ai_tutor_importable()

from app.api import UIMessageStreamEncoder, sse_frame  # noqa: E402
from app.chat_service import stream_chat, warm_up_retriever  # noqa: E402
from app.chat_types import ChatRequest, ChatTurn  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(warm_up_retriever)
    yield


app = FastAPI(
    title="Towards AI Thinkific Tutor API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted({*settings.cors_origins(), *helper_settings.cors_origins()}),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(helper_router)


@app.middleware("http")
async def reject_oversized_bodies(request: Request, call_next):
    content_length = request.headers.get("content-length")
    try:
        too_large = (
            content_length is not None and int(content_length) > settings.max_body_bytes
        )
    except ValueError:
        too_large = False
    if too_large:
        return JSONResponse({"detail": "Request body too large"}, status_code=413)
    return await call_next(request)


STATIC_DIR = repo_root() / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


student_limiter = FixedWindowRateLimiter(
    (
        RateLimit("per_minute", settings.rate_limit_per_minute, 60),
        RateLimit("per_day", settings.rate_limit_per_day, 24 * 60 * 60),
    )
)
global_limiter = FixedWindowRateLimiter(
    (RateLimit("global_per_minute", settings.rate_limit_global_per_minute, 60),)
)


class _ThreadRunSlot:
    __slots__ = ("lock", "refs")

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.refs = 0


_THREAD_RUN_SLOTS: dict[str, _ThreadRunSlot] = {}
_THREAD_RUN_SLOTS_LOCK = asyncio.Lock()
SSE_HEARTBEAT_SECONDS = 15.0


async def _claim_thread_slot(thread_id: str) -> _ThreadRunSlot | None:
    if not thread_id:
        return None
    async with _THREAD_RUN_SLOTS_LOCK:
        slot = _THREAD_RUN_SLOTS.setdefault(thread_id, _ThreadRunSlot())
        slot.refs += 1
        return slot


async def _release_thread_slot(thread_id: str, slot: _ThreadRunSlot) -> None:
    async with _THREAD_RUN_SLOTS_LOCK:
        slot.refs -= 1
        if slot.refs <= 0 and _THREAD_RUN_SLOTS.get(thread_id) is slot:
            del _THREAD_RUN_SLOTS[thread_id]


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _header_host_allowed(value: str) -> bool:
    if not value:
        return False
    hostname = (urlparse(value).hostname or "").lower()
    return any(
        hostname == allowed.lower() or hostname.endswith("." + allowed.lower())
        for allowed in settings.allowed_hosts
    )


def _require_allowed_browser_origin(request: Request) -> None:
    origin = request.headers.get("origin", "")
    referer = request.headers.get("referer", "")
    if _header_host_allowed(origin) or _header_host_allowed(referer):
        return
    raise HTTPException(
        status_code=403,
        detail="Requests must come from the configured Thinkific site.",
    )


def _history(turns: list[ChatTurnIn]) -> tuple[ChatTurn, ...]:
    return tuple(
        ChatTurn(role=turn.role, content=turn.content.strip())
        for turn in turns
        if turn.role in {"user", "assistant"} and turn.content.strip()
    )


def _rate_key(request: Request, payload: ThinkificChatRequest, student_id: str) -> str:
    student = student_id or payload.studentId.strip()
    if student:
        return student
    return f"ip:{_client_ip(request)}"


def _check_rate_limits(
    request: Request,
    payload: ThinkificChatRequest,
    resolved: ResolvedLesson,
) -> None:
    global_result = global_limiter.check("global")
    if not global_result.allowed:
        _flush_rate_limit_monitor_later(
            OpikRateLimitMonitor(
                resolved=resolved,
                user_query=payload.query,
                limit_name=global_result.limit_name,
                retry_after_seconds=global_result.retry_after_seconds,
                rate_key="global",
                client_ip=_client_ip(request),
                scope="global",
                origin=request.headers.get("origin", ""),
                referer=request.headers.get("referer", ""),
            )
        )
        raise HTTPException(
            status_code=429,
            detail=f"Global rate limit exceeded: {global_result.limit_name}",
            headers={"Retry-After": str(global_result.retry_after_seconds)},
        )
    rate_key = _rate_key(request, payload, resolved.student_id)
    student_result = student_limiter.check(rate_key)
    if not student_result.allowed:
        _flush_rate_limit_monitor_later(
            OpikRateLimitMonitor(
                resolved=resolved,
                user_query=payload.query,
                limit_name=student_result.limit_name,
                retry_after_seconds=student_result.retry_after_seconds,
                rate_key=rate_key,
                client_ip=_client_ip(request),
                scope="student",
                origin=request.headers.get("origin", ""),
                referer=request.headers.get("referer", ""),
            )
        )
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {student_result.limit_name}",
            headers={"Retry-After": str(student_result.retry_after_seconds)},
        )


def _flush_monitor_later(monitor: OpikTurnMonitor, error_message: str = "") -> None:
    if not monitor.enabled:
        return

    task = asyncio.create_task(asyncio.to_thread(monitor.flush, error_message))

    def log_failure(done: asyncio.Task) -> None:
        try:
            done.result()
        except Exception:
            logger.warning("Background Opik monitor flush failed.", exc_info=True)

    task.add_done_callback(log_failure)


def _flush_rate_limit_monitor_later(monitor: OpikRateLimitMonitor) -> None:
    if not monitor.enabled:
        return

    task = asyncio.create_task(asyncio.to_thread(monitor.flush))

    def log_failure(done: asyncio.Task) -> None:
        try:
            done.result()
        except Exception:
            logger.warning(
                "Background Opik rate-limit monitor flush failed.",
                exc_info=True,
            )

    task.add_done_callback(log_failure)


def _chat_request(
    payload: ThinkificChatRequest,
    query: str,
    source_key: str,
    student_id: str,
) -> ChatRequest:
    return ChatRequest(
        query=query,
        history=_history(payload.history),
        source_keys=(source_key,),
        model_name=settings.model_name,
        include_reasoning=False,
        thread_id=payload.threadId.strip(),
        enabled_tools=settings.enabled_tools,
        memory_preset=settings.memory_preset,
        student_id=student_id,
        disable_kb=settings.disable_kb,
        retrieval_budget=settings.retrieval_budget,
    )


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/thinkific/config")
def public_config() -> dict[str, Any]:
    opik_ready = bool(settings.opik_enabled and settings.opik_api_key)
    return {
        "allowedHosts": list(settings.allowed_hosts),
        "model": settings.model_name,
        "monitoring": {
            "opikEnabled": opik_ready,
            "opikProject": settings.opik_project_name if opik_ready else "",
        },
        "courses": settings.public_course_sources(),
    }


@app.post("/api/thinkific/resolve")
def resolve_context(payload: ResolveRequest, request: Request) -> dict[str, Any]:
    _require_allowed_browser_origin(request)
    resolved = resolve_lesson_context(payload.context)
    if not resolved:
        return {"eligible": False}
    return {
        "eligible": True,
        "sourceKey": resolved.source_key,
        "sourceLabel": resolved.source_label,
        "lessonId": resolved.lesson_id,
        "lessonTitle": resolved.lesson_title,
    }


@app.get("/widget.js")
def widget() -> FileResponse:
    path = STATIC_DIR / "thinkific-widget.js"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Widget not found")
    return FileResponse(path, media_type="application/javascript")


@app.post("/api/thinkific/chat")
async def chat(request: Request, payload: ThinkificChatRequest) -> StreamingResponse:
    _require_allowed_browser_origin(request)
    resolved = resolve_lesson_context(
        payload.context,
        student_id=payload.studentId.strip(),
    )
    if not resolved:
        raise HTTPException(
            status_code=403,
            detail="Tutor is only available from a mapped Thinkific course lesson.",
        )
    _check_rate_limits(request, payload, resolved)
    augmented_query = build_augmented_query(payload.query, resolved)
    chat_request = _chat_request(
        payload,
        augmented_query,
        resolved.source_key,
        resolved.student_id,
    )
    monitor = OpikTurnMonitor(
        resolved=resolved,
        user_query=payload.query,
        chat_request=chat_request,
        origin=request.headers.get("origin", ""),
        referer=request.headers.get("referer", ""),
    )

    async def event_stream():
        encoder = UIMessageStreamEncoder()
        slot = await _claim_thread_slot(chat_request.thread_id)
        holds_lock = False
        events = stream_chat(chat_request)
        next_event: asyncio.Task | None = None
        error_message = ""
        try:
            if slot is not None:
                acquire = asyncio.ensure_future(slot.lock.acquire())
                try:
                    while True:
                        done, _pending = await asyncio.wait(
                            {acquire}, timeout=SSE_HEARTBEAT_SECONDS
                        )
                        if done:
                            acquire.result()
                            holds_lock = True
                            break
                        yield ": ping\n\n"
                finally:
                    if not holds_lock:
                        acquire.cancel()

            next_event = asyncio.ensure_future(anext(events))
            while True:
                done, _pending = await asyncio.wait(
                    {next_event}, timeout=SSE_HEARTBEAT_SECONDS
                )
                if not done:
                    yield ": ping\n\n"
                    continue
                task, next_event = next_event, None
                try:
                    event = task.result()
                except StopAsyncIteration:
                    break
                monitor.observe_event(event)
                for part in encoder.encode(event):
                    yield sse_frame(part)
                next_event = asyncio.ensure_future(anext(events))
        except asyncio.CancelledError:
            error_message = "client disconnected before the tutor stream completed"
            raise
        except Exception:
            ref = encoder.message_id or uuid4().hex
            error_message = f"chat stream failed ref={ref}"
            logger.exception("thinkific chat stream failed ref=%s", ref)
            message = (
                "Something went wrong while answering. Please try again. "
                f"Reference: {ref}"
            )
            for part in encoder.finish_error(message):
                yield sse_frame(part)
        else:
            if not encoder.closed:
                error_message = "stream ended without completion"
                for part in encoder.finish_error("stream ended without completion"):
                    yield sse_frame(part)
        finally:
            if next_event is not None:
                next_event.cancel()
            if holds_lock:
                slot.lock.release()
            if slot is not None:
                await _release_thread_slot(chat_request.thread_id, slot)
            _flush_monitor_later(monitor, error_message)
        yield sse_frame("[DONE]")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "x-vercel-ai-ui-message-stream": "v1",
        },
    )
