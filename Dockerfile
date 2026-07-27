FROM python:3.13-slim

ARG AI_TUTOR_APP_REPO=https://github.com/towardsai/ai-tutor-app.git
ARG AI_TUTOR_APP_REF=c8c398a75e76154cb6e7140a169f684ece5f6ac7

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AI_TUTOR_APP_PATH=/opt/ai-tutor-app \
    AI_TUTOR_API_HOST=0.0.0.0 \
    PATH=/opt/thinkific-tutor-api/.venv/bin:$PATH \
    PORT=7860

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ripgrep curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git init /opt/ai-tutor-app \
    && git -C /opt/ai-tutor-app remote add origin "${AI_TUTOR_APP_REPO}" \
    && git -C /opt/ai-tutor-app fetch --depth 1 origin "${AI_TUTOR_APP_REF}" \
    && git -C /opt/ai-tutor-app checkout --detach FETCH_HEAD

WORKDIR /opt/thinkific-tutor-api

COPY pyproject.toml uv.lock README.md ./
COPY thinkific_tutor ./thinkific_tutor
COPY static ./static

RUN pip install --no-cache-dir uv \
    && uv sync --locked --no-dev

EXPOSE 7860

CMD ["uvicorn", "thinkific_tutor.api:app", "--host", "0.0.0.0", "--port", "7860"]
