from __future__ import annotations

from typing import Any

from thinkific_tutor import helper_llm as llm
from thinkific_tutor.helper_settings import HelperSettings


class FakeDeepSeekResponse:
    def __init__(self, status_code: int, payload: dict[str, Any], text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeUsageMetadata:
    prompt_token_count = 5
    candidates_token_count = 7
    total_token_count = 12


class FakeGeminiResponse:
    text = "Gemini fallback answer"
    usage_metadata = FakeUsageMetadata()


class FakeGeminiModels:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs) -> FakeGeminiResponse:
        self.calls.append(kwargs)
        return FakeGeminiResponse()


class FakeGeminiClient:
    models = FakeGeminiModels()

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key


def test_prompt_requires_direct_support_for_exact_offer_claims() -> None:
    prompt = llm.build_prompt(
        query="How many courses are included in mentorship?",
        selected_prompt="I want to find mentors",
        current_url="https://towardsai.com/academy/mentorship/",
        page_title="Towards AI Mentorship",
        history=[],
        selected_pages=[
            {
                "title": "Towards AI Mentorship",
                "kind": "mentorship",
                "url": "https://towardsai.com/academy/mentorship/",
                "headings": ["The curriculum comes with the team"],
                "text": (
                    "Towards AI Mentorship includes one course: the 10-Hour LLM "
                    "Fundamentals video course from day one."
                ),
            }
        ],
    )

    instruction = llm.SYSTEM_INSTRUCTION.lower()
    assert "only authority for factual claims" in instruction
    assert "number or names of included products or courses" in instruction
    assert "do not guess" in instruction
    assert "every factual claim must be directly supported" in prompt.lower()
    assert "cannot confirm it" in prompt.lower()
    assert "includes one course" in prompt


def test_prompt_corrects_unsupported_alternatives_with_supported_table_facts() -> None:
    prompt = llm.build_prompt(
        query=(
            "Does the mentorship include two courses of our choice, or only the "
            "LLM Fundamentals course?"
        ),
        selected_prompt="I want to find mentors",
        current_url="https://towardsai.com/academy/mentorship/",
        page_title="Towards AI Mentorship",
        history=[],
        selected_pages=[
            {
                "chunk_id": "mentorship-curriculum-table",
                "title": "Towards AI Mentorship",
                "kind": "mentorship",
                "url": "https://towardsai.com/academy/mentorship/",
                "headings": ["The curriculum comes with the team"],
                "text": (
                    "10-Hour LLM Fundamentals video course $199 Included from "
                    "day one Full Stack AI Engineering · Agent Engineering · "
                    "Master AI for Work $349–499 each 25% off, always"
                ),
            }
        ],
    )

    instruction = llm.SYSTEM_INSTRUCTION.lower()
    assert "unsupported premise or alternative" in instruction
    assert "do not return" in instruction
    assert "merely because the visitor's proposed premise is unsupported" in instruction
    assert 'never infer a total, use "only"' in instruction
    prompt_lower = prompt.lower()
    assert "correction rule" in prompt_lower
    assert (
        "return answered with those facts as separate extractive claims" in prompt_lower
    )
    assert "one table row says an item is included" in prompt_lower
    assert 'do not infer a total or say "only"' in prompt_lower
    assert "do not repeat or deny the visitor's unsupported premise" in prompt_lower
    assert 'never write "not included"' in prompt_lower
    assert 'unless those literal words occur in that claim\'s exact quote' in prompt_lower


def test_generate_answer_uses_deepseek_primary(monkeypatch) -> None:
    request_calls = []
    monkeypatch.setattr(
        llm,
        "helper_settings",
        HelperSettings(
            deepseek_api_key="deepseek-key",
            gemini_api_key="gemini-key",
            model_name="deepseek:deepseek-v4-flash",
            fallback_model_name="gemini-2.5-flash",
        ),
    )

    def fake_post(*args, **kwargs):
        request_calls.append({"args": args, **kwargs})
        return FakeDeepSeekResponse(
            200,
            {
                "choices": [{"message": {"content": "DeepSeek answer"}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 8,
                    "total_tokens": 18,
                },
            },
        )

    monkeypatch.setattr(llm.requests, "post", fake_post)

    result = llm.generate_answer("Visitor prompt")

    assert result.answer == "DeepSeek answer"
    assert result.usage["provider"] == "deepseek"
    assert result.usage["model"] == "deepseek-v4-flash"
    assert result.provider == "deepseek"
    assert result.model == "deepseek-v4-flash"
    assert result.usage["total_tokens"] == 18
    assert request_calls[0]["args"] == ("https://api.deepseek.com/chat/completions",)
    assert request_calls[0]["headers"] == {
        "Authorization": "Bearer deepseek-key",
        "Content-Type": "application/json",
    }
    assert request_calls[0]["json"]["model"] == "deepseek-v4-flash"
    assert request_calls[0]["json"]["thinking"] == {"type": "disabled"}
    assert request_calls[0]["json"]["messages"][0]["role"] == "system"
    assert request_calls[0]["json"]["messages"][1] == {
        "role": "user",
        "content": "Visitor prompt",
    }


def test_generate_answer_falls_back_to_gemini_when_deepseek_fails(
    monkeypatch,
) -> None:
    FakeGeminiClient.models = FakeGeminiModels()
    monkeypatch.setattr(
        llm,
        "helper_settings",
        HelperSettings(
            deepseek_api_key="deepseek-key",
            gemini_api_key="gemini-key",
            model_name="deepseek:deepseek-v4-flash",
            fallback_model_name="gemini-2.5-flash",
        ),
    )
    monkeypatch.setattr(
        llm.requests,
        "post",
        lambda *_args, **_kwargs: FakeDeepSeekResponse(
            503, {}, "temporarily unavailable"
        ),
    )
    monkeypatch.setattr(llm.genai, "Client", FakeGeminiClient)

    result = llm.generate_answer("Visitor prompt")

    assert result.answer == "Gemini fallback answer"
    assert result.usage["provider"] == "google_genai"
    assert result.usage["model"] == "gemini-2.5-flash"
    assert result.usage["fallback_from"] == "deepseek"
    assert result.provider == "google_genai"
    assert result.model == "gemini-2.5-flash"
    assert FakeGeminiClient.models.calls[0]["model"] == "gemini-2.5-flash"


def test_generate_answer_preserves_openrouter_compatibility(monkeypatch) -> None:
    request_calls = []
    monkeypatch.setattr(
        llm,
        "helper_settings",
        HelperSettings(
            openrouter_api_key="openrouter-key",
            model_name="openrouter:deepseek/deepseek-chat",
            fallback_model_name="",
            openrouter_site_url="https://towardsai.com",
            openrouter_app_name="Towards AI Helper",
        ),
    )

    def fake_post(*args, **kwargs):
        request_calls.append({"args": args, **kwargs})
        return FakeDeepSeekResponse(
            200,
            {
                "model": "deepseek/deepseek-chat",
                "choices": [
                    {
                        "message": {
                            "content": '{"status":"not_found","claims":[]}'
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 9,
                    "completion_tokens": 4,
                    "total_tokens": 13,
                },
            },
        )

    monkeypatch.setattr(llm.requests, "post", fake_post)

    result = llm.generate_answer("Visitor prompt")

    assert result.provider == "openrouter"
    assert result.model == "deepseek/deepseek-chat"
    assert result.usage["provider"] == "openrouter"
    assert request_calls[0]["args"] == (
        "https://openrouter.ai/api/v1/chat/completions",
    )
    assert request_calls[0]["headers"]["HTTP-Referer"] == "https://towardsai.com"
    assert request_calls[0]["json"]["response_format"] == {"type": "json_object"}
    assert request_calls[0]["json"]["temperature"] == 0.0
