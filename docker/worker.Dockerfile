# syntax=docker/dockerfile:1.7
# docker/worker.Dockerfile
# Worker 애플리케이션 이미지 (베이스 이미지 사용)

# BASE_IMAGE가 제공되면 베이스 이미지 사용, 아니면 멀티스테이지 빌드로 폴백
ARG BASE_IMAGE
ARG PYTHON_IMAGE=python:3.11-slim@sha256:db27ce7778e5f581d5d97812ee577a01a9fffbfa612c47fc521fa684e3389c9b

# ═══════════════════════════════════════════════════════════
# 폴백: 베이스 이미지가 없을 때 사용할 빌더 스테이지
# ═══════════════════════════════════════════════════════════
FROM ${PYTHON_IMAGE} AS builder
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ARG WORKER_REQUIREMENTS=requirements_cpu.txt
ARG PIP_EXTRA_INDEX_URL=""

COPY ${WORKER_REQUIREMENTS} /build/requirements.txt

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    if [ -n "$PIP_EXTRA_INDEX_URL" ]; then \
      pip wheel --wheel-dir /wheels -r /build/requirements.txt --extra-index-url "$PIP_EXTRA_INDEX_URL"; \
    else \
      pip wheel --wheel-dir /wheels -r /build/requirements.txt; \
    fi

# ═══════════════════════════════════════════════════════════
# 폴백: 베이스 이미지가 없을 때 사용할 런타임 스테이지
# ═══════════════════════════════════════════════════════════
FROM ${PYTHON_IMAGE} AS fallback-runtime
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
 && rm -rf /var/lib/apt/lists/*

ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd -m -u 10001 appuser

COPY --from=builder /wheels /wheels
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /wheels/* && rm -rf /wheels

# ═══════════════════════════════════════════════════════════
# 최종 스테이지: 베이스 이미지 또는 폴백 사용
# ═══════════════════════════════════════════════════════════
FROM ${BASE_IMAGE:-fallback-runtime} AS runtime
WORKDIR /app

COPY . /app
ARG BUILD_CHROMA_INDEX=0
ARG CHROMA_DATASET_PATH=/app/AI/menu_assistant/data/datasets/raw/menu_seed.json
ARG CHROMA_DIR=/app/AI/menu_assistant/data/chroma
ARG CHROMA_COLLECTION=menu_index
ARG CHROMA_EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

RUN if [ "$BUILD_CHROMA_INDEX" = "1" ]; then \
      python /app/AI/menu_assistant/worker/scripts/build_chroma_index.py \
        --dataset "$CHROMA_DATASET_PATH" \
        --chroma_dir "$CHROMA_DIR" \
        --collection "$CHROMA_COLLECTION" \
        --embed_model "$CHROMA_EMBED_MODEL"; \
      chown -R 10001:10001 "$CHROMA_DIR" || true; \
    fi

ENV PYTHONPATH=/app
USER appuser

# Default command; overridden by Helm values (worker.command/args)
CMD ["python", "-m", "AI.menu_assistant.worker.worker_app.main"]
