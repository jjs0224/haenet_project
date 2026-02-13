# backend/Dockerfile
# requirements.txt 없이: pyproject.toml 기반으로 설치 (PEP 517/518)

FROM python:3.11-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

# 의존성 메타데이터만 먼저 복사 (캐시 최적화)
COPY pyproject.toml ./

# (중요) lock 파일은 없어도 되므로 여기서는 복사하지 않습니다.
# lock이 있다면 나중에 캐시 최적화를 위해 별도로 추가할 수 있습니다.

# 의존성 wheel 생성 (pyproject의 의존성을 읽어 wheel로 만듦)
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

# 앱 소스 복사
COPY . /app

FROM python:3.11-slim AS runtime
WORKDIR /app

RUN useradd -m -u 10001 appuser

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY --from=builder /app /app

# --- backend.* import 호환 레이어 (symlink) ---
RUN mkdir -p /app/backend && \
    ln -s /app/app /app/backend/app && \
    touch /app/backend/__init__.py
ENV PYTHONPATH=/app
# --------------------------------------------

EXPOSE 8000
USER appuser

# 이제 코드가 기대하는 네임스페이스로 실행(가장 일관됨)
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]