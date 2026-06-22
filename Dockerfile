FROM python:3.13-slim

ARG AI_TUTOR_APP_REPO=https://github.com/towardsai/ai-tutor-app.git
ARG AI_TUTOR_APP_REF=main

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AI_TUTOR_APP_PATH=/opt/ai-tutor-app \
    AI_TUTOR_API_HOST=0.0.0.0 \
    PORT=7860

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ripgrep curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${AI_TUTOR_APP_REF}" "${AI_TUTOR_APP_REPO}" /opt/ai-tutor-app \
    || git clone --depth 1 "${AI_TUTOR_APP_REPO}" /opt/ai-tutor-app

WORKDIR /opt/thinkific-tutor-api

COPY pyproject.toml README.md ./
COPY thinkific_tutor ./thinkific_tutor
COPY static ./static

RUN pip install --no-cache-dir uv \
    && uv pip install --system -e .

EXPOSE 7860

CMD ["uvicorn", "thinkific_tutor.api:app", "--host", "0.0.0.0", "--port", "7860"]
