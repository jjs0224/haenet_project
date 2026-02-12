# syntax=docker/dockerfile:1.7
# docker/base.backend.Dockerfile
# Backend용 베이스 이미지: Python 의존성만 포함 (애플리케이션 코드 제외)
# requirements_api.txt가 변경될 때만 재빌드 필요

ARG PYTHON_IMAGE=python:3.11-slim@sha256:db27ce7778e5f581d5d97812ee577a01a9fffbfa612c47fc521fa684e3389c9b

# ═══════════════════════════════════════════════════════════
# Stage 1: 의존성 빌드 (wheel 파일 생성)
# ═══════════════════════════════════════════════════════════
FROM ${PYTHON_IMAGE} AS builder
WORKDIR /build

# 컴파일 도구 설치 (C 확장이 있는 패키지를 위해)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --upgrade pip

# requirements 파일만 복사 (빌드 컨텍스트는 프로젝트 루트)
COPY requirements_api.txt /build/requirements.txt

# pip wheel: 패키지를 미리 컴파일해서 .whl 파일로 만듦
# BuildKit 캐시 마운트로 pip 캐시 재사용
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir /wheels -r /build/requirements.txt

# ═══════════════════════════════════════════════════════════
# Stage 2: 런타임 이미지 (실제 실행 환경)
# ═══════════════════════════════════════════════════════════
FROM ${PYTHON_IMAGE} AS runtime
WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --upgrade pip

# 보안을 위한 non-root 유저 생성
RUN useradd -m -u 10001 appuser

# builder 스테이지에서 컴파일된 wheel 파일들 복사
COPY --from=builder /wheels /wheels

# wheel 파일들을 설치 (컴파일 불필요 → 빠름)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /wheels/* && rm -rf /wheels

# 여기까지가 베이스 이미지!
# 애플리케이션 코드는 포함하지 않음
# 이 이미지를 ECR에 푸시하고 애플리케이션 Dockerfile에서 재사용
