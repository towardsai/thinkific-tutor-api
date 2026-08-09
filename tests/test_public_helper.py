from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from thinkific_tutor import api, helper_llm, helper_router
from thinkific_tutor.helper_catalog import (
    allowed_paths_by_host,
    coupon_followup,
    coupon_intent,
    forced_prompts,
    in_scope,
    page_is_allowed,
    retrieve,
    sources_from_pages,
)
from thinkific_tutor.helper_llm import EvidenceChunk, GroundingResult, LLMResult
from thinkific_tutor.rate_limiter import FixedWindowRateLimiter, RateLimit

client = TestClient(api.app)
HEADERS = {"Origin": "https://towardsai.com"}
PUBLIC_URL = "https://towardsai.com/academy/agent-engineering/"
FIRST_PROMPT = "I want help deciding which course to take."


def reset_helper_limiters() -> None:
    helper_router.helper_visitor_limiter = FixedWindowRateLimiter(
        (
            RateLimit("helper_per_minute", 100, 60),
            RateLimit("helper_per_day", 1000, 24 * 60 * 60),
        )
    )
    helper_router.helper_ip_limiter = FixedWindowRateLimiter(
        (
            RateLimit("helper_ip_per_minute", 100, 60),
            RateLimit("helper_ip_per_day", 1000, 24 * 60 * 60),
        )
    )
    helper_router.helper_global_limiter = FixedWindowRateLimiter(
        (RateLimit("helper_global_per_minute", 1000, 60),)
    )


def helper_payload(
    query: str = FIRST_PROMPT,
    *,
    url: str = PUBLIC_URL,
    signed_in: bool = False,
) -> dict:
    return {
        "query": query,
        "selectedPrompt": query if query == FIRST_PROMPT else FIRST_PROMPT,
        "visitorId": "test-visitor",
        "threadId": "",
        "history": [],
        "context": {
            "url": url,
            "pageTitle": "Agent course",
            "signedIn": signed_in,
        },
    }


def test_helper_catalog_routes_public_pages_and_queries() -> None:
    assert forced_prompts()[0] == FIRST_PROMPT
    assert page_is_allowed(PUBLIC_URL)
    assert page_is_allowed("https://towardsai.net/b2b")
    assert page_is_allowed("https://www.towardsai.net/b2b")
    assert page_is_allowed("https://towardsai.com/academy/full-stack-ai-engineering/")
    assert page_is_allowed("https://www.towardsai.com/a-future-public-page/")
    assert not page_is_allowed(
        "https://academy.towardsai.net/courses/take/agent-engineering/lessons/x"
    )
    assert not page_is_allowed("https://towardsai.com/wp-admin/edit.php")
    assert not page_is_allowed("https://towardsai.com/academy/?preview=true")
    assert "/b2b" in allowed_paths_by_host()["www.towardsai.net"]
    assert "/academy/agent-engineering" in allowed_paths_by_host()[
        "www.towardsai.com"
    ]

    mentorship = sources_from_pages(retrieve("I want to find mentors"))
    b2b = sources_from_pages(retrieve("I want training inside my company"))
    bundle = sources_from_pages(retrieve("What is the best value bundle?"))

    assert any(
        "towardsai.com/academy/mentorship" in source["url"] for source in mentorship
    )
    assert any(source["url"].startswith("https://towardsai.com/") for source in b2b)
    assert any(
        source["url"] == "https://towardsai.com/academy/bundles/get-it-all/"
        for source in bundle
    )
    assert in_scope("Which course is best for learning agents?")
    assert not in_scope("Who won the world cup?")
    assert coupon_intent("Do you have a coupon code?")
    assert coupon_followup("Please I really need a discount code", ["coupon?"])


@pytest.mark.parametrize(
    ("query", "expected_url_fragment"),
    [
        (
            "What is included in the Full Stack AI Engineering course?",
            "full-stack-ai-engineering",
        ),
        ("I want help to integrate AI into my company", "towardsai.com/"),
        ("I want a training inside my company", "towardsai.com/"),
        (
            "Where is the Agent Engineering free preview?",
            "agent-engineering-free-preview",
        ),
        ("I want to find mentors", "academy/mentorship"),
        ("Where are the Building LLMs book companion resources?", "academy/book"),
        ("I am a beginner with no coding experience", "python-for-ai-engineering"),
        ("I am a business professional and manager", "ai-for-work"),
    ],
)
def test_helper_catalog_routes_common_public_intents(
    query: str,
    expected_url_fragment: str,
) -> None:
    sources = sources_from_pages(
        retrieve(query, current_url="https://academy.towardsai.net/")
    )

    assert any(expected_url_fragment in source["url"] for source in sources), sources


def test_helper_catalog_routes_specialized_enterprise_queries() -> None:
    coding_agents = sources_from_pages(
        retrieve("We need Claude Code and Codex training for our engineering team")
    )
    developer_conversion = sources_from_pages(
        retrieve("Convert our software developers into AI engineers")
    )
    consulting = sources_from_pages(
        retrieve("We need AI deployment and value creation consulting")
    )

    assert coding_agents[0]["url"].endswith("/agentic-developer-conversion/")
    assert developer_conversion[0]["url"].endswith(
        "/software-developer-to-ai-engineer/"
    )
    assert consulting[0]["url"] == "https://towardsai.com/valuecreation/"


def test_helper_config_and_widget_are_served_from_shared_app() -> None:
    config = client.get("/api/helper/config")
    widget = client.get("/helper-widget.js")

    assert config.status_code == 200
    payload = config.json()
    assert payload["name"] == "Towards AI Helper"
    assert FIRST_PROMPT in payload["forcedPrompts"]
    assert "towardsai.com" in payload["allowedHosts"]
    assert "towardsai.com" in payload["siteWideHosts"]
    assert (
        "/academy/agent-engineering"
        in payload["allowedPathsByHost"]["towardsai.com"]
    )
    assert (
        "/courses/agent-engineering"
        in payload["allowedPathsByHost"]["academy.towardsai.net"]
    )
    assert payload["rateLimits"] == {
        "perMinute": 8,
        "perDay": 50,
        "ipPerMinute": 60,
        "ipPerDay": 300,
    }
    assert widget.status_code == 200
    assert "Towards AI Helper" in widget.text
    assert "Choose a starter prompt" in widget.text
    assert "isSignedIn" in widget.text
    assert "payload.sources" not in widget.text
    assert "sourceWrap" not in widget.text
    assert "data-reset" in widget.text
    assert "Restart conversation" in widget.text
    assert "function resetConversation()" in widget.text
    assert 'state.threadId = "";' in widget.text
    assert "state.messages = [];" in widget.text
    assert "state.firstMessageSent = false;" in widget.text
    assert 'event.key === "Enter"' in widget.text
    assert "!event.shiftKey" in widget.text
    assert 'form.dispatchEvent(new Event("submit"' in widget.text
    assert "quick breather" in widget.text
    assert "siteWideHosts" in widget.text
    assert "wp-admin" in widget.text


def test_helper_cors_preflight_accepts_towardsai_com() -> None:
    response = client.options(
        "/api/helper/chat",
        headers={
            "Origin": "https://towardsai.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://towardsai.com"


def test_helper_chat_requires_origin_public_page_signed_out_and_first_prompt() -> None:
    reset_helper_limiters()

    assert client.post("/api/helper/chat", json=helper_payload()).status_code == 403
    assert (
        client.post(
            "/api/helper/chat",
            json=helper_payload(
                url="https://towardsai.com/wp-admin/edit.php",
            ),
            headers=HEADERS,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/helper/chat",
            json=helper_payload(signed_in=True),
            headers=HEADERS,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/helper/chat",
            json=helper_payload(query="Can I type first?"),
            headers=HEADERS,
        ).status_code
        == 400
    )


def test_helper_chat_calls_llm_with_retrieved_sources(monkeypatch) -> None:
    reset_helper_limiters()
    prompts = []

    def fake_generate_grounded_answer(
        prompt: str, selected_pages: list[dict]
    ) -> GroundingResult:
        prompts.append(prompt)
        cited = EvidenceChunk(
            chunk_id=str(selected_pages[0]["chunk_id"]),
            title=str(selected_pages[0]["title"]),
            url=str(selected_pages[0]["url"]),
            kind=str(selected_pages[0]["kind"]),
            headings=tuple(selected_pages[0].get("headings", [])),
            text=str(selected_pages[0]["text"]),
        )
        return GroundingResult(
            valid=True,
            status="answered",
            answer="Tell me your coding background and goal.",
            cited_chunks=(cited,),
            usage={
                "input_tokens": 10,
                "output_tokens": 8,
                "total_tokens": 18,
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
            },
            latency_ms=123,
            provider="deepseek",
            model="deepseek-v4-flash",
        )

    monkeypatch.setattr(
        helper_router.llm,
        "generate_grounded_answer",
        fake_generate_grounded_answer,
    )

    response = client.post("/api/helper/chat", json=helper_payload(), headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Tell me your coding background and goal."
    assert data["threadId"]
    assert data["sources"]
    assert data["usage"]["total_tokens"] == 18
    assert "Agent Engineering" in prompts[0]
    assert "EVIDENCE_CHUNKS" in prompts[0]
    assert "return not_found" in prompts[0]


def test_helper_chat_still_accepts_legacy_net_origin(monkeypatch) -> None:
    reset_helper_limiters()
    monkeypatch.setattr(
        helper_router.llm,
        "generate_grounded_answer",
        lambda _prompt, selected: GroundingResult(
            valid=True,
            status="answered",
            answer="Supported answer.",
            cited_chunks=(
                EvidenceChunk(
                    chunk_id=str(selected[0]["chunk_id"]),
                    title=str(selected[0]["title"]),
                    url=str(selected[0]["url"]),
                    kind=str(selected[0]["kind"]),
                    headings=tuple(selected[0].get("headings", [])),
                    text=str(selected[0]["text"]),
                ),
            ),
        ),
    )

    response = client.post(
        "/api/helper/chat",
        json=helper_payload(url="https://towardsai.net/b2b"),
        headers={"Origin": "https://towardsai.net"},
    )

    assert response.status_code == 200


def test_helper_chat_keeps_course_choice_context_on_followup(monkeypatch) -> None:
    reset_helper_limiters()
    prompts = []

    def fake_generate_grounded_answer(
        prompt: str, selected_pages: list[dict]
    ) -> GroundingResult:
        prompts.append(prompt)
        cited = EvidenceChunk(
            chunk_id=str(selected_pages[0]["chunk_id"]),
            title=str(selected_pages[0]["title"]),
            url=str(selected_pages[0]["url"]),
            kind=str(selected_pages[0]["kind"]),
            headings=tuple(selected_pages[0].get("headings", [])),
            text=str(selected_pages[0]["text"]),
        )
        return GroundingResult(
            valid=True,
            status="answered",
            answer=(
                "Full Stack AI Engineering is designed for developers building "
                "production AI systems."
            ),
            cited_chunks=(cited,),
        )

    monkeypatch.setattr(
        helper_router.llm,
        "generate_grounded_answer",
        fake_generate_grounded_answer,
    )
    payload = helper_payload(
        query="I'm a developer interested in Full Stack AI Engineering"
    )
    payload["selectedPrompt"] = FIRST_PROMPT
    payload["history"] = [
        {"role": "user", "content": FIRST_PROMPT},
        {
            "role": "assistant",
            "content": "What is your coding experience and goal?",
        },
    ]

    response = client.post("/api/helper/chat", json=payload, headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    source_urls = [source["url"] for source in data["sources"]]
    assert any("full-stack-ai-engineering" in url for url in source_urls)
    assert "Full Stack AI" in prompts[0]
    assert data["answer"].endswith("systems.")


def test_helper_chat_refuses_unrelated_followup_after_valid_start(monkeypatch) -> None:
    reset_helper_limiters()

    def unexpected_generate_answer(_prompt: str) -> LLMResult:
        raise AssertionError("model should not be called for out-of-scope questions")

    monkeypatch.setattr(
        helper_router.llm, "generate_answer", unexpected_generate_answer
    )
    payload = helper_payload(query="Who won the World Cup?")
    payload["selectedPrompt"] = FIRST_PROMPT
    payload["history"] = [
        {"role": "user", "content": FIRST_PROMPT},
        {"role": "assistant", "content": "What is your background?"},
    ]

    response = client.post("/api/helper/chat", json=payload, headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["answer"].startswith("I can only help with choosing")


def test_helper_coupon_answer_is_deterministic(monkeypatch) -> None:
    reset_helper_limiters()

    def unexpected_generate_answer(*_args) -> GroundingResult:
        raise AssertionError("model should not be called for coupon intent")

    monkeypatch.setattr(
        helper_router.llm, "generate_grounded_answer", unexpected_generate_answer
    )
    first = helper_payload(query="Do you have a coupon code?")
    first["selectedPrompt"] = FIRST_PROMPT
    first["history"] = [{"role": "user", "content": FIRST_PROMPT}]
    second = helper_payload(query="Please I really need a coupon code")
    second["selectedPrompt"] = FIRST_PROMPT
    second["history"] = [
        {"role": "user", "content": FIRST_PROMPT},
        {"role": "assistant", "content": "I can't provide a coupon code here."},
    ]

    first_response = client.post("/api/helper/chat", json=first, headers=HEADERS)
    second_response = client.post("/api/helper/chat", json=second, headers=HEADERS)

    assert first_response.status_code == 200
    assert "louis@towardsai.net" in first_response.json()["answer"]
    assert first_response.json()["status"] == "policy"
    assert second_response.status_code == 200
    assert "louis@towardsai.net" in second_response.json()["answer"]


def test_helper_rate_limit_is_hard(monkeypatch) -> None:
    helper_router.helper_visitor_limiter = FixedWindowRateLimiter(
        (RateLimit("helper_per_minute", 1, 60),)
    )
    helper_router.helper_ip_limiter = FixedWindowRateLimiter(
        (RateLimit("helper_ip_per_minute", 100, 60),)
    )
    helper_router.helper_global_limiter = FixedWindowRateLimiter(
        (RateLimit("helper_global_per_minute", 100, 60),)
    )
    scheduled_monitors = []

    monkeypatch.setattr(
        helper_router.llm,
        "generate_answer",
        lambda _prompt: LLMResult(answer="ok"),
    )
    monkeypatch.setattr(
        helper_router,
        "_schedule_monitor",
        lambda monitor: scheduled_monitors.append(monitor),
    )

    first = client.post("/api/helper/chat", json=helper_payload(), headers=HEADERS)
    scheduled_monitors.clear()
    second = client.post("/api/helper/chat", json=helper_payload(), headers=HEADERS)

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0
    assert len(scheduled_monitors) == 1
    assert scheduled_monitors[0].limit_name == "helper_per_minute"
    assert scheduled_monitors[0].scope == "visitor"
    assert scheduled_monitors[0].visitor_key == "visitor:test-visitor"


def test_helper_llm_uses_deepseek_primary(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "model": "deepseek-v4-flash",
                "choices": [
                    {"message": {"content": "Start with the Agent Engineering course."}}
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 7,
                    "total_tokens": 27,
                },
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(helper_llm.requests, "post", fake_post)
    monkeypatch.setattr(
        helper_llm,
        "helper_settings",
        SimpleNamespace(
            deepseek_api_key="test-deepseek-key",
            deepseek_base_url="https://api.deepseek.com",
            gemini_api_key="",
            model_name="deepseek:deepseek-v4-flash",
            fallback_model_name="gemini-2.5-flash",
            max_output_tokens=420,
            request_timeout_seconds=45,
        ),
    )

    result = helper_llm.generate_answer("prompt")

    assert result.answer == "Start with the Agent Engineering course."
    assert result.provider == "deepseek"
    assert result.model == "deepseek-v4-flash"
    assert result.usage["total_tokens"] == 27
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-deepseek-key"
    assert captured["json"]["model"] == "deepseek-v4-flash"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert "Towards AI Helper" in captured["json"]["messages"][0]["content"]
    assert captured["json"]["messages"][1] == {"role": "user", "content": "prompt"}
    assert captured["json"]["thinking"] == {"type": "disabled"}
    assert captured["json"]["max_tokens"] == 420
    assert captured["timeout"] == 45


def test_helper_llm_falls_back_to_gemini_when_deepseek_fails(monkeypatch) -> None:
    captured = {}

    class FakeDeepSeekResponse:
        status_code = 503

        def json(self):
            return {"error": {"message": "upstream unavailable"}}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                text="Gemini fallback answer.",
                usage_metadata=SimpleNamespace(
                    prompt_token_count=11,
                    candidates_token_count=5,
                    total_token_count=16,
                ),
            )

    class FakeClient:
        def __init__(self, *, api_key: str) -> None:
            captured["api_key"] = api_key
            self.models = FakeModels()

    monkeypatch.setattr(
        helper_llm.requests,
        "post",
        lambda *_args, **_kwargs: FakeDeepSeekResponse(),
    )
    monkeypatch.setattr(helper_llm.genai, "Client", FakeClient)
    monkeypatch.setattr(
        helper_llm,
        "helper_settings",
        SimpleNamespace(
            deepseek_api_key="test-deepseek-key",
            deepseek_base_url="https://api.deepseek.com",
            gemini_api_key="test-gemini-key",
            model_name="deepseek:deepseek-v4-flash",
            fallback_model_name="gemini-2.5-flash",
            max_output_tokens=420,
            request_timeout_seconds=45,
        ),
    )

    result = helper_llm.generate_answer("prompt")

    assert result.answer == "Gemini fallback answer."
    assert result.provider == "google_genai"
    assert result.model == "gemini-2.5-flash"
    assert result.usage["total_tokens"] == 16
    assert captured["api_key"] == "test-gemini-key"
    assert captured["model"] == "gemini-2.5-flash"
    assert captured["config"]["thinking_config"] == {"thinking_budget": 0}


def test_helper_llm_disables_thinking_to_preserve_visible_output(monkeypatch) -> None:
    captured = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                text="A complete concise recommendation.",
                usage_metadata=SimpleNamespace(
                    prompt_token_count=12,
                    candidates_token_count=6,
                    total_token_count=18,
                ),
            )

    class FakeClient:
        def __init__(self, *, api_key: str) -> None:
            captured["api_key"] = api_key
            self.models = FakeModels()

    monkeypatch.setattr(helper_llm.genai, "Client", FakeClient)
    monkeypatch.setattr(
        helper_llm,
        "helper_settings",
        SimpleNamespace(
            gemini_api_key="test-gemini-key",
            model_name="gemini-2.5-flash",
            max_output_tokens=420,
        ),
    )

    result = helper_llm.generate_answer("prompt")

    assert result.answer == "A complete concise recommendation."
    assert result.usage["total_tokens"] == 18
    assert captured["api_key"] == "test-gemini-key"
    assert captured["model"] == "gemini-2.5-flash"
    assert captured["config"]["thinking_config"] == {"thinking_budget": 0}
    assert captured["config"]["max_output_tokens"] == 420
