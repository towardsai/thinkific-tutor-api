from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import requests
from google import genai

from .helper_catalog import assistant_notes
from .helper_settings import helper_settings

DEEPSEEK_PROVIDER = "deepseek"
GEMINI_PROVIDER = "google_genai"
DEFAULT_TEMPERATURE = 0.0
MAX_CONTEXT_CHARS = 18000
MAX_CHUNK_TEXT_CHARS = 4500
MAX_EVIDENCE_QUOTE_CHARS = 320
MAX_SALVAGED_QUOTE_CHARS = 200
logger = logging.getLogger(__name__)


GROUNDING_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "claims"],
    "properties": {
        "status": {"type": "string", "enum": ["answered", "not_found"]},
        "claims": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "chunk_id", "quote"],
                "properties": {
                    "text": {"type": "string", "maxLength": 321},
                    "chunk_id": {"type": "string"},
                    "quote": {"type": "string", "maxLength": 320},
                },
            },
        },
    },
}


SYSTEM_INSTRUCTION = """You are Towards AI Helper, a concise public assistant for anonymous prospective students.

Your only job is to help users choose Towards AI courses, bundles, mentorship,
free resources, the book, community, or B2B training/consulting.

Scope and style rules:
- For unrelated requests, general AI teaching, coding help, homework, or news,
  return not_found rather than answering from general knowledge.
- Do not reveal course lesson material or provide detailed technical lessons.
- Keep supported answers concise and focused on the visitor's question.

Grounding rules (higher priority than helpfulness):
- The EVIDENCE CHUNKS in the user prompt are the only authority for factual claims.
- Routing notes, page metadata outside the evidence section, conversation history,
  and the visitor's message are not evidence and must never support an answer.
- Never rely on memory or general knowledge. If the supplied evidence does not
  directly support the answer, return not_found.
- Never infer an inclusion, quantity, price, discount, entitlement, policy, date,
  URL, or program feature that is not explicitly stated in an evidence chunk.
- Do not guess the number or names of included products or courses.
- A visitor may put an unsupported premise or alternative in a question. Ignore
  that premise as evidence. If an evidence chunk directly provides relevant
  correcting facts, return answered with those supported facts; do not return
  not_found merely because the visitor's proposed premise is unsupported.
- For either/or questions, report each directly supported table row or fact as a
  separate extractive claim. Never infer a total, use "only", or negate an
  alternative unless the evidence quote explicitly states that total,
  exclusivity, or negation.
- Never repeat, restate, or deny an unsupported premise in a claim. In
  particular, do not say "not included" unless those literal words occur in the
  claim's exact evidence quote.
- Each claim must copy its supporting quote verbatim. You may add one final
  period only when the source quote has no final period. Do not paraphrase,
  reorder, omit, or add words. Split separate source sentences or table rows
  into separate claims.
- Each claim must cite one valid chunk_id and copy one exact, contiguous quote
  of at most 320 characters from that same chunk. Never invent, edit, combine,
  or use ellipses in a quote.

Output rules:
- Return exactly one JSON object and nothing else (no Markdown fences).
- For a supported answer use:
  {"status":"answered","claims":[{"text":"One supported sentence.","chunk_id":"chunk_id_here","quote":"exact contiguous source quote"}]}
- If support is absent, ambiguous, conflicting, or insufficient, use exactly:
  {"status":"not_found","claims":[]}
- Do not include an answer field, preamble, uncited sentence, or extra key.
- Keep supported answers to at most 6 short claims. Include URLs only when the
  exact URL occurs in the quoted evidence.
"""


@dataclass(frozen=True)
class LLMResult:
    """Raw provider result.

    ``answer`` contains the provider's JSON text until it has passed
    :func:`validate_grounded_result`. Callers must not send this field directly
    to a visitor.
    """

    answer: str
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    provider: str = ""
    model: str = ""


@dataclass(frozen=True)
class EvidenceChunk:
    chunk_id: str
    title: str
    url: str
    kind: str
    headings: tuple[str, ...]
    text: str

    @property
    def evidence_text(self) -> str:
        return "\n".join(
            [
                f"Title: {self.title}",
                f"Kind: {self.kind}",
                f"URL: {self.url}",
                f"Headings: {', '.join(self.headings)}",
                f"Text: {self.text}",
            ]
        )


@dataclass(frozen=True)
class GroundedClaim:
    text: str
    chunk_id: str
    quote: str


GroundingStatus = Literal["answered", "not_found", "validation_failure"]


@dataclass(frozen=True)
class GroundingResult:
    """Safe result returned by the deterministic grounding boundary."""

    valid: bool
    status: GroundingStatus
    answer: str = ""
    claims: tuple[GroundedClaim, ...] = ()
    cited_chunks: tuple[EvidenceChunk, ...] = ()
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    validation_error: str = ""
    provider: str = ""
    model: str = ""

    @property
    def is_answered(self) -> bool:
        return self.valid and self.status == "answered"

    @property
    def cited_chunk_ids(self) -> tuple[str, ...]:
        return tuple(chunk.chunk_id for chunk in self.cited_chunks)


_SAFE_CHUNK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*", re.IGNORECASE)
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?][\"')\]]*\s+(?=[A-Z0-9])")
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_PERCENT_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*\s*%")
_CURRENCY_RE = re.compile(
    r"(?<!\w)(?:(?:US|CA|AU)?[$€£¥]\s*\d+(?:[.,]\d+)*"
    r"|\d+(?:[.,]\d+)*\s*(?:USD|CAD|AUD|EUR|GBP|JPY))(?!\w)",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?![\w.])")
_POLARITY_RE = re.compile(
    r"\b(?:no|not|never|none|without|cannot|can't|couldn't|doesn't|don't|"
    r"isn't|aren't|won't)\b",
    re.IGNORECASE,
)
_NUMBER_WORDS = frozenset(
    [
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
        "hundred",
        "thousand",
        "million",
        "billion",
    ]
)
def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("’", "'")
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def chunk_id_for_page(page: dict[str, Any]) -> str:
    """Return a deterministic, retrieval-order-independent evidence ID."""

    explicit = str(page.get("chunk_id", "")).strip()
    if explicit and _SAFE_CHUNK_ID_RE.fullmatch(explicit):
        return explicit

    identity = json.dumps(
        {
            "url": str(page.get("url", "")),
            "title": str(page.get("title", "")),
            "kind": str(page.get("kind", "")),
            "chunk_index": page.get("chunk_index"),
            "text": _normalize_text(str(page.get("text", ""))),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"chunk_{digest}"


def _chunk_from_page(page: dict[str, Any]) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id_for_page(page),
        title=str(page.get("title", "")),
        url=str(page.get("url", "")),
        kind=str(page.get("kind", "")),
        headings=tuple(str(item) for item in page.get("headings", [])[:12]),
        text=str(page.get("text", ""))[:MAX_CHUNK_TEXT_CHARS],
    )


def _render_chunk(chunk: EvidenceChunk) -> str:
    return "\n".join(
        [
            f'<EVIDENCE_CHUNK chunk_id="{chunk.chunk_id}">',
            chunk.evidence_text,
            "</EVIDENCE_CHUNK>",
        ]
    )


def _routing_notes_section() -> str:
    notes = json.dumps(assistant_notes(), ensure_ascii=False, sort_keys=True)
    return (
        "<NON_EVIDENCE_ROUTING_NOTES>\n"
        "These notes may guide routing/style but are NOT factual evidence,\n"
        "must not be cited, and cannot support any answer claim.\n"
        f"{notes}\n"
        "</NON_EVIDENCE_ROUTING_NOTES>"
    )


def evidence_chunks(
    selected_pages: list[dict[str, Any]], *, max_chars: int = MAX_CONTEXT_CHARS
) -> tuple[EvidenceChunk, ...]:
    """Return exactly the source chunks that fit in the model evidence block."""

    routing_section = _routing_notes_section()
    used_chars = len(routing_section)
    chunks: list[EvidenceChunk] = []
    seen_ids: set[str] = set()

    for page in selected_pages:
        if str(page.get("url", "")).startswith("internal://"):
            continue
        chunk = _chunk_from_page(page)
        if chunk.chunk_id in seen_ids:
            continue
        rendered_length = len(_render_chunk(chunk)) + 2
        if used_chars + rendered_length > max_chars:
            break
        chunks.append(chunk)
        seen_ids.add(chunk.chunk_id)
        used_chars += rendered_length
    return tuple(chunks)


def _context_block(
    selected_pages: list[dict[str, Any]], max_chars: int = MAX_CONTEXT_CHARS
) -> str:
    routing_section = _routing_notes_section()
    rendered_chunks = "\n\n".join(
        _render_chunk(chunk)
        for chunk in evidence_chunks(selected_pages, max_chars=max_chars)
    )
    return "\n\n".join(
        [
            routing_section,
            "<EVIDENCE_CHUNKS>",
            rendered_chunks or "(none)",
            "</EVIDENCE_CHUNKS>",
        ]
    )


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

<NON_EVIDENCE_REQUEST_CONTEXT>
Current URL: {current_url or "unknown"}
Current page title: {page_title or "unknown"}
Initial forced prompt: {selected_prompt or "unknown"}

Conversation so far (visitor-provided and NOT evidence):
{turns or "(none)"}

Visitor message (a question, NOT evidence):
{query}
</NON_EVIDENCE_REQUEST_CONTEXT>

{_context_block(selected_pages)}

Use only EVIDENCE_CHUNKS for factual claims. Return the required JSON object now.
Every factual claim must be directly supported by an exact evidence quote.
The text of each claim must copy its quote verbatim; the only permitted change is
adding one final period when the quote has none. Keep each quote to one local
source sentence or table row and at most 320 characters. Never paraphrase or
combine words from different parts of a chunk.
Correction rule: the visitor's premise and proposed alternatives are not evidence.
If the chunks contain directly relevant facts that correct or resolve the question,
return answered with those facts as separate extractive claims. For example, when
one table row says an item is included and another row says named items are
discounted, make one claim for the included row and another claim for the discount
row. Do not infer a total or say "only" unless an evidence quote explicitly does.
Do not repeat or deny the visitor's unsupported premise. Never write "not included"
unless those literal words occur in that claim's exact quote.
If the evidence contains no directly relevant facts, return not_found; you cannot
confirm it. Do not use not_found when the evidence contains supported correcting
facts.
"""


def _clean_usage(usage: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in usage.items() if value is not None}


def _provider_and_model(model_name: str) -> tuple[str, str]:
    normalized = (model_name or "").strip()
    if ":" in normalized:
        provider, _, actual_model = normalized.partition(":")
        return provider.strip(), actual_model.strip()
    if normalized.startswith("gemini"):
        return "google-genai", normalized
    if normalized.startswith("deepseek"):
        return "deepseek", normalized
    return "openrouter", normalized


def _text_from_chat_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content or "")


def _result_usage(
    raw_usage: dict[str, Any], *, provider: str, model: str
) -> dict[str, Any]:
    return _clean_usage(
        {
            "input_tokens": raw_usage.get("prompt_tokens")
            or raw_usage.get("input_tokens"),
            "output_tokens": raw_usage.get("completion_tokens")
            or raw_usage.get("output_tokens"),
            "total_tokens": raw_usage.get("total_tokens"),
            "provider": provider,
            "model": model,
        }
    )


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
            "response_format": {"type": "json_object"},
            "temperature": DEFAULT_TEMPERATURE,
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
    answer = _text_from_chat_content(message.get("content")).strip()
    if not answer:
        raise RuntimeError("OpenRouter returned an empty answer")

    response_model = (
        payload.get("model", model_name) if isinstance(payload, dict) else model_name
    )
    actual_model = str(response_model or model_name)
    raw_usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
    usage = _result_usage(
        raw_usage if isinstance(raw_usage, dict) else {},
        provider="openrouter",
        model=actual_model,
    )
    return LLMResult(
        answer=answer,
        usage=usage,
        latency_ms=int((time.monotonic() - started) * 1000),
        provider="openrouter",
        model=actual_model,
    )


def _generate_with_deepseek(prompt: str, model_name: str) -> LLMResult:
    if not helper_settings.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    started = time.monotonic()
    response = requests.post(
        f"{helper_settings.deepseek_base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {helper_settings.deepseek_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "temperature": DEFAULT_TEMPERATURE,
            "max_tokens": helper_settings.max_output_tokens,
            "stream": False,
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
            f"DeepSeek request failed with HTTP {response.status_code}{detail}"
        )
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError("DeepSeek returned an error response")

    choices = payload.get("choices", []) if isinstance(payload, dict) else []
    first_choice = choices[0] if choices else {}
    message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
    answer = _text_from_chat_content(message.get("content")).strip()
    if not answer:
        raise RuntimeError("DeepSeek returned an empty answer")

    response_model = (
        payload.get("model", model_name) if isinstance(payload, dict) else model_name
    )
    actual_model = str(response_model or model_name)
    raw_usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
    usage = _result_usage(
        raw_usage if isinstance(raw_usage, dict) else {},
        provider=DEEPSEEK_PROVIDER,
        model=actual_model,
    )
    return LLMResult(
        answer=answer,
        usage=usage,
        latency_ms=int((time.monotonic() - started) * 1000),
        provider=DEEPSEEK_PROVIDER,
        model=actual_model,
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
            "temperature": DEFAULT_TEMPERATURE,
            "max_output_tokens": helper_settings.max_output_tokens,
            "response_mime_type": "application/json",
            "response_json_schema": GROUNDING_RESPONSE_SCHEMA,
        },
    )
    usage_metadata = getattr(response, "usage_metadata", None)
    raw_usage: dict[str, Any] = {}
    if usage_metadata is not None:
        raw_usage = {
            "input_tokens": getattr(usage_metadata, "prompt_token_count", None),
            "output_tokens": getattr(usage_metadata, "candidates_token_count", None),
            "total_tokens": getattr(usage_metadata, "total_token_count", None),
        }
    usage = _result_usage(
        raw_usage,
        provider=GEMINI_PROVIDER,
        model=model_name,
    )
    return LLMResult(
        answer=(getattr(response, "text", "") or "").strip(),
        usage=usage,
        latency_ms=int((time.monotonic() - started) * 1000),
        provider=GEMINI_PROVIDER,
        model=model_name,
    )


def _generate_for_model(prompt: str, model_name: str) -> LLMResult:
    provider, actual_model = _provider_and_model(model_name)
    if provider == "openrouter":
        return _generate_with_openrouter(prompt, actual_model)
    if provider == "deepseek":
        return _generate_with_deepseek(prompt, actual_model)
    if provider in {"google-genai", "google_genai"}:
        return _generate_with_gemini(prompt, actual_model)
    raise RuntimeError(f"Unsupported helper model provider: {provider}")


def generate_answer(prompt: str) -> LLMResult:
    """Generate raw structured JSON while retaining the configured fallback."""

    started = time.monotonic()
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
            result = _generate_for_model(prompt, fallback_model)
        except Exception as fallback_error:
            raise RuntimeError(
                "Primary and fallback helper LLM calls failed"
            ) from fallback_error

    usage = dict(result.usage)
    usage["fallback_from"] = primary[0].replace("-", "_")
    return replace(
        result,
        usage=_clean_usage(usage),
        latency_ms=int((time.monotonic() - started) * 1000),
    )


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _validation_failure(raw: LLMResult, message: str) -> GroundingResult:
    return GroundingResult(
        valid=False,
        status="validation_failure",
        usage=raw.usage,
        latency_ms=raw.latency_ms,
        validation_error=message,
        provider=raw.provider or str(raw.usage.get("provider", "")),
        model=raw.model or str(raw.usage.get("model", "")),
    )


def _trim_url(value: str) -> str:
    return value.rstrip(".,;:!?)]}").casefold()


def _critical_facts(value: str) -> dict[str, set[str]]:
    normalized = _normalize_text(value)
    word_tokens = {token.casefold() for token in _TOKEN_RE.findall(normalized)}
    return {
        "URLs": {_trim_url(item) for item in _URL_RE.findall(normalized)},
        "percentages": {
            _normalize_text(item).casefold() for item in _PERCENT_RE.findall(normalized)
        },
        "currency amounts": {
            _normalize_text(item).casefold()
            for item in _CURRENCY_RE.findall(normalized)
        },
        "numbers": {
            _normalize_text(item).casefold() for item in _NUMBER_RE.findall(normalized)
        },
        "number words": word_tokens & _NUMBER_WORDS,
    }


def _claim_is_one_sentence(text: str) -> bool:
    if not text or re.search(r"\.[\"')\]]*$", text) is None:
        return False
    return _SENTENCE_BOUNDARY_RE.search(text) is None


def _validate_claim_reference(
    claim: GroundedClaim, chunk_by_id: dict[str, EvidenceChunk]
) -> str:
    chunk = chunk_by_id.get(claim.chunk_id)
    if chunk is None:
        return f"unknown chunk_id: {claim.chunk_id}"

    normalized_quote = _normalize_text(claim.quote)
    if not normalized_quote:
        return "evidence quote must not be empty"
    if len(normalized_quote) > MAX_EVIDENCE_QUOTE_CHARS:
        return f"evidence quote exceeds {MAX_EVIDENCE_QUOTE_CHARS} characters"
    normalized_chunk = _normalize_text(chunk.evidence_text)
    if normalized_quote not in normalized_chunk:
        return "evidence quote is not an exact normalized substring of its chunk"
    return ""


def _validate_claim_text(claim: GroundedClaim) -> str:
    if not _claim_is_one_sentence(claim.text):
        return "each claim must contain exactly one complete sentence"

    normalized_claim = _normalize_text(claim.text)
    normalized_quote = _normalize_text(claim.quote)
    claim_facts = _critical_facts(claim.text)
    evidence_facts = _critical_facts(claim.quote)
    for label, facts in claim_facts.items():
        unsupported = facts - evidence_facts[label]
        if unsupported:
            values = ", ".join(sorted(unsupported))
            return f"claim contains unsupported {label}: {values}"

    claim_polarity = {
        item.casefold() for item in _POLARITY_RE.findall(_normalize_text(claim.text))
    }
    quote_polarity = {
        item.casefold() for item in _POLARITY_RE.findall(_normalize_text(claim.quote))
    }
    if claim_polarity != quote_polarity:
        return "claim changes or omits evidence negation"

    if normalized_claim.removesuffix(".") != normalized_quote.removesuffix("."):
        return "claim must copy its evidence quote verbatim"

    return ""


def _safe_quote_sentence(quote: str) -> str:
    """Return one short normalized source-only sentence, or an empty string."""

    normalized = _normalize_text(quote)
    if not normalized or len(normalized) > MAX_SALVAGED_QUOTE_CHARS:
        return ""
    if _SENTENCE_BOUNDARY_RE.search(normalized):
        return ""
    if re.search(r"[.!?][\"')\]]*$", normalized):
        return normalized
    return f"{normalized}."


def validate_grounded_result(
    raw_result: LLMResult | str,
    selected_pages: list[dict[str, Any]],
) -> GroundingResult:
    """Strictly validate provider JSON and return only evidence-backed text.

    A malformed schema, bad citation, invented quote, or unsafe quote produces
    ``validation_failure`` with an empty answer. When only the provider's claim
    wording is invalid, that wording is discarded and one short, normalized
    sentence is built solely from its already-validated exact quote. Invalid raw
    claim text is never copied into the safe result.
    """

    raw = raw_result if isinstance(raw_result, LLMResult) else LLMResult(raw_result)
    try:
        payload = json.loads(
            raw.answer,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return _validation_failure(raw, f"malformed JSON: {exc}")

    if not isinstance(payload, dict) or set(payload) != {"status", "claims"}:
        return _validation_failure(raw, "root must contain exactly status and claims")
    status = payload["status"]
    claims_payload = payload["claims"]
    if status not in {"answered", "not_found"}:
        return _validation_failure(raw, "status must be answered or not_found")
    if not isinstance(claims_payload, list):
        return _validation_failure(raw, "claims must be an array")
    if len(claims_payload) > 6:
        return _validation_failure(raw, "claims must contain at most 6 items")

    if status == "not_found":
        if claims_payload:
            return _validation_failure(raw, "not_found must contain no claims")
        return GroundingResult(
            valid=True,
            status="not_found",
            usage=raw.usage,
            latency_ms=raw.latency_ms,
            provider=raw.provider or str(raw.usage.get("provider", "")),
            model=raw.model or str(raw.usage.get("model", "")),
        )
    if not claims_payload:
        return _validation_failure(raw, "answered must contain at least one claim")

    chunks = evidence_chunks(selected_pages)
    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    claims: list[GroundedClaim] = []
    for index, item in enumerate(claims_payload):
        if not isinstance(item, dict) or set(item) != {"text", "chunk_id", "quote"}:
            return _validation_failure(
                raw,
                f"claim {index + 1} must contain exactly text, chunk_id, and quote",
            )
        if not all(isinstance(item[key], str) for key in item):
            return _validation_failure(raw, f"claim {index + 1} fields must be strings")
        claim = GroundedClaim(
            text=item["text"].strip(),
            chunk_id=item["chunk_id"].strip(),
            quote=item["quote"].strip(),
        )
        reference_error = _validate_claim_reference(claim, chunk_by_id)
        if reference_error:
            return _validation_failure(
                raw, f"claim {index + 1}: {reference_error}"
            )
        text_error = _validate_claim_text(claim)
        if text_error:
            safe_text = _safe_quote_sentence(claim.quote)
            if not safe_text:
                return _validation_failure(
                    raw,
                    f"claim {index + 1}: {text_error}; exact quote cannot be "
                    "safely salvaged",
                )
            claim = replace(claim, text=safe_text)
        claims.append(claim)

    cited_chunks: list[EvidenceChunk] = []
    cited_ids: set[str] = set()
    for claim in claims:
        if claim.chunk_id not in cited_ids:
            cited_chunks.append(chunk_by_id[claim.chunk_id])
            cited_ids.add(claim.chunk_id)

    return GroundingResult(
        valid=True,
        status="answered",
        answer=" ".join(claim.text for claim in claims),
        claims=tuple(claims),
        cited_chunks=tuple(cited_chunks),
        usage=raw.usage,
        latency_ms=raw.latency_ms,
        provider=raw.provider or str(raw.usage.get("provider", "")),
        model=raw.model or str(raw.usage.get("model", "")),
    )


def generate_grounded_answer(
    prompt: str, selected_pages: list[dict[str, Any]]
) -> GroundingResult:
    """Generate and cross the fail-closed grounding boundary in one call."""

    return validate_grounded_result(generate_answer(prompt), selected_pages)
