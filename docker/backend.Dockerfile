# syntax=docker/dockerfile:1.7
# docker/backend.Dockerfile
# requirements-based install (local/CI/image aligned)

ARG PYTHON_IMAGE=python:3.11-slim@sha256:db27ce7778e5f581d5d97812ee577a01a9fffbfa612c47fc521fa684e3389c9b

FROM ${PYTHON_IMAGE} AS builder
WORKDIR /build

ARG REQUIREMENTS=requirements_api.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --upgrade pip

# Copy requirements (build context = repo root)
COPY ${REQUIREMENTS} /build/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir /wheels -r /build/requirements.txt

FROM ${PYTHON_IMAGE} AS runtime
WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --upgrade pip

RUN useradd -m -u 10001 appuser

COPY --from=builder /wheels /wheels
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy backend only
COPY backend/ /app

# backend.* import compatibility layer (symlink)
RUN mkdir -p /app/backend /app/_work /app/uploads && \
    ln -s /app/app /app/backend/app && \
    touch /app/backend/__init__.py && \
    chown -R appuser:appuser /app/_work /app/uploads
ENV PYTHONPATH=/app

EXPOSE 8000
USER appuser

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
