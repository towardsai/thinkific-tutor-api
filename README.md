---
title: Towards AI Thinkific Tutor API
sdk: docker
app_port: 7860
pinned: false
---

# Towards AI Thinkific Tutor API

Thin Thinkific integration layer for the existing
[`towardsai/ai-tutor-app`](https://github.com/towardsai/ai-tutor-app) backend.

This repo does not fork the tutor/RAG logic. It imports the existing tutor core,
derives the course source from Thinkific course/lesson context, applies rate
limits, and serves a small chat bubble widget for Thinkific Course Player pages.

## Why not iframe the Hugging Face app?

An iframe of the public HF app is fast, but it is not the best long-term
integration:

- The HF UI exposes course/source selection that Thinkific should not expose.
- Thinkific lesson context needs to be passed into the request.
- Course filtering must be enforced server-side, not trusted from iframe state.
- Rate limits and allowed origins belong at the integration API layer.
- You would still need postMessage plumbing between Thinkific and the iframe.

This adapter keeps one tutor backend while replacing only the public surface:

```text
Thinkific Course Player
  -> /widget.js
  -> /api/thinkific/chat
  -> ai-tutor-app stream_chat(...)
  -> course-only Chroma/Cohere retrieval
  -> Gemini 2.5 Flash
```

## Public Sales Helper

This same deployment also serves a separate signed-out sales helper for public
academy/TowardsAI.net pages:

```html
<script
  src="https://towardsai-tutors-thinkific-tutor-api.hf.space/helper-widget.js"
  data-api-base="https://towardsai-tutors-thinkific-tutor-api.hf.space"
  defer
></script>
```

It uses `/api/helper/config` and `/api/helper/chat`, not the lesson-tutor
routes. The helper:

- Shows only on public sitemap-discoverable pages.
- Hides when a visitor appears signed in.
- Forces the first message to one of the configured starter prompts.
- Answers only course, bundle, mentorship, free-resource, book, or B2B training
  questions.
- Refuses coupon codes and redirects persistent discount requests to
  `louis@towardsai.net`.
- Uses Gemini 2.5 Flash, hard public rate limits, and Opik project
  `towards-ai-helper`.

## Local setup

```bash
cd /Users/louis/Documents/Codex/thinkific-tutor-api
uv sync
cp .env.example .env
```

Set `AI_TUTOR_APP_PATH` to your existing checkout, for example:

```bash
AI_TUTOR_APP_PATH=/Users/louis/Documents/GitHub/ai-tutor-app
```

You do not need to copy secrets. On startup the adapter loads its own `.env`
first, then fills missing keys from `AI_TUTOR_APP_PATH/.env`.

Run the API:

```bash
uv run uvicorn thinkific_tutor.api:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/healthz
```

## Thinkific install snippet

Add this to Thinkific **Settings -> Code & Analytics -> Site Footer Code**:

```html
<script
  src="https://YOUR-DEPLOYED-API/widget.js"
  data-api-base="https://YOUR-DEPLOYED-API"
  defer
></script>
```

For public signed-out pages, add the helper snippet too:

```html
<script
  src="https://YOUR-DEPLOYED-API/helper-widget.js"
  data-api-base="https://YOUR-DEPLOYED-API"
  defer
></script>
```

The widget stays hidden unless it detects Thinkific `CoursePlayerV2` lesson
events and the API confirms the course maps to one of the tutor course sources.
It minimizes back to the bottom-right bubble when the student closes the panel.
The helper widget has separate signed-out/public-page gating.

## Course mapping

By default, URL mapping is derived from `ai-tutor-app`:

| Course source | Academy URL |
| --- | --- |
| `full_stack_ai_engineering` | `https://academy.towardsai.net/courses/beginner-to-advanced-llm-dev` |
| `beginner_python_for_ai_engineering` | `https://academy.towardsai.net/courses/python-for-genai` |
| `master_ai_for_work` | `https://academy.towardsai.net/courses/ai-business-professionals` |
| `agentic_ai_engineering` | `https://academy.towardsai.net/courses/agent-engineering` |

When you have Thinkific course ids, add them for stronger routing:

```bash
THINKIFIC_COURSE_ID_SOURCE_MAP='{
  "123456": "full_stack_ai_engineering",
  "234567": "agentic_ai_engineering"
}'
```

You can add custom URL mappings:

```bash
THINKIFIC_COURSE_URL_SOURCE_MAP='{
  "https://academy.towardsai.net/courses/custom-slug": "full_stack_ai_engineering"
}'
```

## API behavior

`POST /api/thinkific/resolve`

Checks whether a browser context is a mapped Thinkific lesson. The widget uses
this before showing the bubble.

`POST /api/thinkific/chat`

Streams the same AI SDK UI-message SSE protocol as the main tutor app. The
request is accepted only when:

- The current URL host is in `THINKIFIC_ALLOWED_HOSTS`.
- Thinkific logged-in user or enrollment context is present.
- A lesson id/title is present.
- The lesson does not look like a quiz, exam, or assessment.
- The course maps to one course source.

The adapter sends exactly one `source_key` to the tutor core, so retrieval is
course-scoped even if a browser user edits the request.

The sales page and course landing pages are rejected because they do not emit
Course Player lesson context. Quiz-like pages are rejected by default via:

```bash
THINKIFIC_REQUIRE_LOGGED_IN_USER=true
THINKIFIC_BLOCKED_LESSON_KEYWORDS=quiz,quizz,exam,assessment
```

## Cost controls

Defaults:

```bash
THINKIFIC_TUTOR_MODEL=google-genai:gemini-2.5-flash
THINKIFIC_ENABLED_TOOLS=
THINKIFIC_DISABLE_KB=true
THINKIFIC_RETRIEVAL_BUDGET=24000
THINKIFIC_RATE_LIMIT_PER_MINUTE=6
THINKIFIC_RATE_LIMIT_PER_DAY=120
```

Public helper defaults:

```bash
HELPER_MODEL=gemini-2.5-flash
HELPER_RATE_LIMIT_PER_MINUTE=8
HELPER_RATE_LIMIT_PER_DAY=50
HELPER_IP_RATE_LIMIT_PER_MINUTE=60
HELPER_IP_RATE_LIMIT_PER_DAY=300
HELPER_GLOBAL_RATE_LIMIT_PER_MINUTE=120
HELPER_OPIK_PROJECT_NAME=towards-ai-helper
```

`THINKIFIC_DISABLE_KB=true` keeps only vector/BM25 retrieval enabled and removes
the local KB browsing tool from the agent. Turn it off if you want deeper lesson
file inspection at the cost of larger prompts.

The built-in rate limiter is in-memory. For multi-replica production, replace
`FixedWindowRateLimiter` with Redis or put a gateway rate limit in front.

## Monitoring

The repo has two layers of monitoring:

- GitHub Actions pings the Hugging Face Space every 12 hours so the free CPU
  Space stays warm, and scheduled live smoke tests check health/widget/course
  resolution.
- Optional Opik tracing records each completed chat turn with course, lesson,
  student id, model, token usage, estimated cost, latency, and answer status.
  Rate-limit rejections are tracked too: filter for the `rate-limit` tag or
  span names `thinkific_tutor_rate_limit` and `towards_ai_helper_rate_limit`.
  Their metadata includes `limit_name`, `scope`, `retry_after_seconds`, and
  either `student_id` or `visitor_key`.

Enable Opik with:

```bash
OPIK_ENABLED=true
OPIK_API_KEY=...
OPIK_WORKSPACE=...
OPIK_PROJECT_NAME=towards-ai-thinkific-tutor
```

The trace intentionally does not copy full Thinkific page text into Opik. It
records the student's question, the answer, and operational metadata.

## Deployment

Build with Docker:

```bash
docker build -t thinkific-tutor-api .
docker run --env-file .env -p 7860:7860 thinkific-tutor-api
```

Deploy targets that work well:

- Hugging Face Space with Docker SDK
- Render/Fly.io/Railway
- Any container host that can keep the vector DB bundle on disk between restarts

Required secrets:

```bash
GEMINI_API_KEY
COHERE_API_KEY
HF_TOKEN
OPIK_API_KEY              # optional, for monitoring
OPIK_WORKSPACE            # optional, for monitoring
```

## Future single-repo path

Best future state: move this adapter into `ai-tutor-app` under a
`integrations/thinkific` package, or extract the existing tutor backend into a
small shared Python package that both the HF UI and Thinkific API import.

For now, this repo is deliberately thin so the duplicate maintenance surface is
small: course mapping, rate limits, and the widget.
