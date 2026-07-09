from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests
from google import genai

from .helper_catalog import assistant_notes
from .helper_settings import helper_settings

logger = logging.getLogger(__name__)


SYSTEM_INSTRUCTION = """You are Towards AI Helper, a concise public assistant for anonymous prospective students.

Your only job is to help users choose Towards AI courses, bundles, mentorship,
free resources, the book, community, or B2B training/consulting.

Rules:
- Stay on this scope. If asked general AI, coding, homework, news, or unrelated questions, briefly say you can only help with choosing Towards AI learning/training options.
- Do not teach course lesson content, reveal course material, or provide detailed technical lessons. Give high-level fit guidance and link to relevant public pages.
- Keep answers short: usually 2-5 sentences plus links when useful.
- When recommending a specific course, bundle, mentorship, B2B page, free
  resource, book, or YouTube channel, include the destination inline as a
  Markdown link on the relevant phrase.
- Do not add a generic sources, references, or citations section.
- For course-choice prompts, ask one practical follow-up if you need background, coding level, goals, or company context.
- For B2B/company training/consulting, ask for use case, team background, timeline, and suggest emailing louis@towardsai.net.
- For mentors, recommend the mentorship program and ask what kind of guidance they need.
- For eager learners wanting the best value, recommend the Get it all bundle.
- For coupon code requests, do not provide a code.
"""


@dataclass(frozen=True)
class LLMResult:
    answer: str
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    provider: str = ""
    model: str = ""


def _context_block(selected_pages: list[dict[str, Any]], max_chars: int = 12000) -> str:
    chunks = []
    notes = assistant_notes()
    chunks.append("ROUTING NOTES:\n" + str(notes))
    for index, page in enumerate(selected_pages, start=1):
        if str(page.get("url", "")).startswith("internal://"):
            continue
        text = str(page.get("text", ""))
        chunks.append(
            "\n".join(
                [
                    f"SOURCE {index}",
                    f"Title: {page.get('title', '')}",
                    f"Kind: {page.get('kind', '')}",
                    f"URL: {page.get('url', '')}",
                    f"Headings: {', '.join(str(h) for h in page.get('headings', [])[:12])}",
                    f"Text: {text[:2600]}",
                ]
            )
        )
    block = "\n\n".join(chunks)
    return block[:max_chars]


def build_prompt(
    *,
    query: str,
    selected_prompt: str,
    current_url: str,
    page_title: str,
    history: list[tuple[str, str]],
    selected_pages: list[dict[str, Any]],
) -> str:
    turns = "\n".join(
        f"{role}: {content[:800]}" for role, content in history[-8:] if content.strip()
    )
    return f"""The visitor is on a public Towards AI page.

Current URL: {current_url or "unknown"}
Current page title: {page_title or "unknown"}
Initial forced prompt: {selected_prompt or "unknown"}

Conversation so far:
{turns or "(none)"}

Visitor message:
{query}

Use only these public sales/resource sources and the routing notes:
{_context_block(selected_pages)}

Answer now. Include inline Markdown links only for the specific course/page/resource you recommend. Do not add a separate sources or citations list. Do not mention internal routing notes.
"""


def _provider_and_model(model_name: str) -> tuple[str, str]:
    normalized = (model_name or "").strip()
    if ":" in normalized:
        provider, _, actual_model = normalized.partition(":")
        return provider.strip(), actual_model.strip()
    if normalized.startswith("gemini"):
        return "google-genai", normalized
    return "openrouter", normalized


def _clean_usage(usage: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in usage.items() if value is not None}


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts).strip()
    return ""


def _generate_with_openrouter(prompt: str, model_name: str) -> LLMResult:
    if not helper_settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    started = time.monotonic()
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {helper_settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": helper_settings.openrouter_site_url,
            "X-Title": helper_settings.openrouter_app_name,
        },
        json={
            "model": model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": helper_settings.max_output_tokens,
        },
        timeout=helper_settings.request_timeout_seconds,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code >= 400:
        message = ""
        if isinstance(payload, dict):
            error = payload.get("error") or {}
            if isinstance(error, dict):
                message = str(error.get("message") or "").strip()
        detail = f": {message}" if message else ""
        raise RuntimeError(
            f"OpenRouter request failed with HTTP {response.status_code}{detail}"
        )

    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError("OpenRouter returned an error response")

    choices = payload.get("choices", []) if isinstance(payload, dict) else []
    first_choice = choices[0] if choices else {}
    message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
    answer = _message_text(message.get("content"))
    if not answer:
        raise RuntimeError("OpenRouter returned an empty answer")

    usage_metadata = payload.get("usage", {}) if isinstance(payload, dict) else {}
    usage = {}
    if isinstance(usage_metadata, dict):
        usage = {
            "input_tokens": usage_metadata.get("prompt_tokens"),
            "output_tokens": usage_metadata.get("completion_tokens"),
            "total_tokens": usage_metadata.get("total_tokens"),
        }
    response_model = (
        payload.get("model", model_name) if isinstance(payload, dict) else model_name
    )
    return LLMResult(
        answer=answer,
        usage=_clean_usage(usage),
        latency_ms=int((time.monotonic() - started) * 1000),
        provider="openrouter",
        model=str(response_model or model_name),
    )


def _generate_with_gemini(prompt: str, model_name: str) -> LLMResult:
    if not helper_settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    started = time.monotonic()
    client = genai.Client(api_key=helper_settings.gemini_api_key)
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={
            "system_instruction": SYSTEM_INSTRUCTION,
            "thinking_config": {"thinking_budget": 0},
            "temperature": 0.2,
            "max_output_tokens": helper_settings.max_output_tokens,
        },
    )
    usage_metadata = getattr(response, "usage_metadata", None)
    usage = {}
    if usage_metadata is not None:
        usage = {
            "input_tokens": getattr(usage_metadata, "prompt_token_count", None),
            "output_tokens": getattr(usage_metadata, "candidates_token_count", None),
            "total_tokens": getattr(usage_metadata, "total_token_count", None),
        }
    return LLMResult(
        answer=(getattr(response, "text", "") or "").strip(),
        usage=_clean_usage(usage),
        latency_ms=int((time.monotonic() - started) * 1000),
        provider="google_genai",
        model=model_name,
    )


def _generate_for_model(prompt: str, model_name: str) -> LLMResult:
    provider, actual_model = _provider_and_model(model_name)
    if provider == "openrouter":
        return _generate_with_openrouter(prompt, actual_model)
    if provider == "google-genai":
        return _generate_with_gemini(prompt, actual_model)
    raise RuntimeError(f"Unsupported helper model provider: {provider}")


def generate_answer(prompt: str) -> LLMResult:
    try:
        return _generate_for_model(prompt, helper_settings.model_name)
    except Exception:
        fallback_model = helper_settings.fallback_model_name
        primary = _provider_and_model(helper_settings.model_name)
        fallback = _provider_and_model(fallback_model)
        if not fallback_model or fallback == primary:
            raise
        logger.warning(
            "Primary helper LLM failed; falling back to Gemini.",
            exc_info=True,
        )
        try:
            return _generate_for_model(prompt, fallback_model)
        except Exception as fallback_error:
            raise RuntimeError(
                "Primary and fallback helper LLM calls failed"
            ) from fallback_error
