from __future__ import annotations

from fastapi.testclient import TestClient

from thinkific_tutor import api, helper_router
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
from thinkific_tutor.helper_llm import LLMResult
from thinkific_tutor.rate_limiter import FixedWindowRateLimiter, RateLimit

client = TestClient(api.app)
HEADERS = {"Origin": "https://academy.towardsai.net"}
PUBLIC_URL = "https://academy.towardsai.net/courses/agent-engineering"
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
    assert not page_is_allowed(
        "https://academy.towardsai.net/courses/take/agent-engineering/lessons/x"
    )
    assert "/b2b" in allowed_paths_by_host()["www.towardsai.net"]

    mentorship = sources_from_pages(retrieve("I want to find mentors"))
    b2b = sources_from_pages(retrieve("I want training inside my company"))
    bundle = sources_from_pages(retrieve("What is the best value bundle?"))

    assert any("tai-mentorship" in source["url"] for source in mentorship)
    assert any("towardsai.net/b2b" in source["url"] for source in b2b)
    assert any("get-it-all" in source["url"] for source in bundle)
    assert in_scope("Which course is best for learning agents?")
    assert not in_scope("Who won the world cup?")
    assert coupon_intent("Do you have a coupon code?")
    assert coupon_followup("Please I really need a discount code", ["coupon?"])


def test_helper_config_and_widget_are_served_from_shared_app() -> None:
    config = client.get("/api/helper/config")
    widget = client.get("/helper-widget.js")

    assert config.status_code == 200
    payload = config.json()
    assert payload["name"] == "Towards AI Helper"
    assert FIRST_PROMPT in payload["forcedPrompts"]
    assert "/courses/agent-engineering" in payload["allowedPathsByHost"][
        "academy.towardsai.net"
    ]
    assert widget.status_code == 200
    assert "Towards AI Helper" in widget.text
    assert "Choose a starter prompt" in widget.text
    assert "isSignedIn" in widget.text


def test_helper_chat_requires_origin_public_page_signed_out_and_first_prompt() -> None:
    reset_helper_limiters()

    assert client.post("/api/helper/chat", json=helper_payload()).status_code == 403
    assert (
        client.post(
            "/api/helper/chat",
            json=helper_payload(
                url="https://academy.towardsai.net/courses/take/x",
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


def test_helper_chat_calls_gemini_with_retrieved_sources(monkeypatch) -> None:
    reset_helper_limiters()
    prompts = []

    def fake_generate_answer(prompt: str) -> LLMResult:
        prompts.append(prompt)
        return LLMResult(
            answer="Tell me your coding background and goal.",
            usage={"input_tokens": 10, "output_tokens": 8, "total_tokens": 18},
            latency_ms=123,
        )

    monkeypatch.setattr(helper_router.llm, "generate_answer", fake_generate_answer)

    response = client.post("/api/helper/chat", json=helper_payload(), headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Tell me your coding background and goal."
    assert data["threadId"]
    assert data["sources"]
    assert data["usage"]["total_tokens"] == 18
    assert "Agent Engineering" in prompts[0]


def test_helper_coupon_answer_is_deterministic(monkeypatch) -> None:
    reset_helper_limiters()

    def unexpected_generate_answer(_prompt: str) -> LLMResult:
        raise AssertionError("model should not be called for coupon intent")

    monkeypatch.setattr(helper_router.llm, "generate_answer", unexpected_generate_answer)
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
    assert "Get it all bundle" in first_response.json()["answer"]
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

    monkeypatch.setattr(
        helper_router.llm,
        "generate_answer",
        lambda _prompt: LLMResult(answer="ok"),
    )

    first = client.post("/api/helper/chat", json=helper_payload(), headers=HEADERS)
    second = client.post("/api/helper/chat", json=helper_payload(), headers=HEADERS)

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0
