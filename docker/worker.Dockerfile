# syntax=docker/dockerfile:1.7
# docker/worker.Dockerfile

ARG PYTHON_IMAGE=python:3.11-slim@sha256:db27ce7778e5f581d5d97812ee577a01a9fffbfa612c47fc521fa684e3389c9b

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

FROM ${PYTHON_IMAGE} AS runtime
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

COPY . /app
ENV PYTHONPATH=/app
USER appuser

# Default command; overridden by Helm values (worker.command/args)
CMD ["python", "-m", "AI.menu_assistant.worker.worker_app.main"]
