# syntax=docker/dockerfile:1.7
# docker/base.worker.Dockerfile
# Worker용 베이스 이미지: Python 의존성 + 시스템 라이브러리 포함 (애플리케이션 코드 제외)
# requirements_cpu.txt가 변경될 때만 재빌드 필요

ARG PYTHON_IMAGE=python:3.11-slim@sha256:db27ce7778e5f581d5d97812ee577a01a9fffbfa612c47fc521fa684e3389c9b

# ═══════════════════════════════════════════════════════════
# Stage 1: 의존성 빌드 (wheel 파일 생성)
# ═══════════════════════════════════════════════════════════
FROM ${PYTHON_IMAGE} AS builder
WORKDIR /build

# 컴파일 도구 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# GPU 버전 requirements 사용 (CI/CD와 일치시킴)
ARG WORKER_REQUIREMENTS=requirements_cu.txt
ARG PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cu126

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
# Stage 2: 런타임 이미지
# ═══════════════════════════════════════════════════════════
FROM ${PYTHON_IMAGE} AS runtime
WORKDIR /app

# OpenCV와 이미지 처리를 위한 시스템 라이브러리 설치
# 이것들도 베이스 이미지에 포함되어 매번 설치하지 않음
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
 && rm -rf /var/lib/apt/lists/*

ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# 보안을 위한 non-root 유저 생성
RUN useradd -m -u 10001 appuser

# builder 스테이지에서 컴파일된 wheel 파일들 복사
COPY --from=builder /wheels /wheels

# wheel 파일들을 설치
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /wheels/* && rm -rf /wheels

# 여기까지가 베이스 이미지!
# 애플리케이션 코드는 포함하지 않음
