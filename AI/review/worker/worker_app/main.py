"""
Worker entry point (queue consumer).
Wire your task queue here (Celery/RQ/etc.).
"""

import json
import os
import signal
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import redis


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    print(msg, flush=True)


def _load_secret_from_file(env_name: str) -> None:
    file_path = os.getenv(f"{env_name}_FILE")
    if not file_path or os.getenv(env_name):
        return
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            os.environ[env_name] = f.read().strip()
    except Exception as e:
        _log(f"[worker] warning: failed to read {env_name}_FILE: {type(e).__name__}: {e}")


def _job_key(job_id: str) -> str:
    return f"cicdex:job:{job_id}"


def _set_job(r: redis.Redis, job_id: str, status: str, **fields: Any) -> None:
    data: Dict[str, str] = {
        "job_id": job_id,
        "status": status,
        "updated_at": _utc_now_iso(),
    }
    for k, v in fields.items():
        if isinstance(v, (dict, list)):
            data[k] = json.dumps(v, ensure_ascii=False)
        else:
            data[k] = str(v)
    r.hset(_job_key(job_id), mapping=data)


def _connect(redis_url: str) -> redis.Redis:
    """
    중요:
    - BRPOPLPUSH 같은 블로킹 명령을 쓰면 socket_timeout은 None이어야 정상 대기 중 TimeoutError가 안 남.
    - connect timeout만 짧게 유지.
    """
    r = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=None,  # <-- 핵심 수정
        retry_on_timeout=True,
    )
    r.ping()
    return r


def _handle_task(task: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    실제 AI 처리 로직 연결 지점.
    - 지금은 E2E 검증을 위해 기본 task 제공
    """
    if task == "ping":
        return {"message": "pong", "echo": payload}

    if task == "sleep":
        sec = int(payload.get("seconds", 1))
        time.sleep(max(0, sec))
        return {"slept": sec}

    if task == "review_receipt_ocr":
        import base64
        import os
        from pathlib import Path
        from AI.review.app.pipeline.orchestrator import PipelineConfig, run_pipeline

        encoded = payload.get("image_base64")
        if not encoded:
            raise ValueError("Missing 'image_base64' in payload")

        receipt_id = str(payload.get("receipt_id") or "").strip() or None
        runs_root = Path(payload.get("runs_root") or "/tmp/ai_runs").expanduser().resolve()
        tmp_dir = runs_root / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        img_bytes = base64.b64decode(encoded)
        image_path = tmp_dir / f"receipt_{receipt_id or uuid.uuid4().hex}.jpg"
        image_path.write_bytes(img_bytes)

        gemini_key = os.getenv("GEMINI_API_KEY") or None
        naver_cfg = {
            "NAVER_CLIENT_ID": os.getenv("NAVER_CLIENT_ID", ""),
            "NAVER_CLIENT_SECRET": os.getenv("NAVER_CLIENT_SECRET", ""),
        }

        cfg = PipelineConfig(
            mode="prod",
            test_base_dir=runs_root,
            run_name=receipt_id,
            gemini_api_key=gemini_key,
            naver_cfg=naver_cfg,
        )

        result = run_pipeline(input_image_path=str(image_path), cfg=cfg)
        return result.get("final") or result

    raise ValueError(f"Unsupported task: {task}")


def main() -> None:
    _load_secret_from_file("GEMINI_API_KEY")
    _load_secret_from_file("DB_PASSWORD")
    _load_secret_from_file("JWT_SECRET_KEY")

    # ✅ 추가 (FILE 기반 시크릿이면 필수)
    _load_secret_from_file("NAVER_CLIENT_ID")
    _load_secret_from_file("NAVER_CLIENT_SECRET")

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    queue_name = os.getenv("QUEUE_NAME", "cicdex:jobs")
    processing_name = os.getenv("QUEUE_PROCESSING_NAME", f"{queue_name}:processing")
    brpop_timeout = int(os.getenv("BRPOP_TIMEOUT_SEC", "10"))

    worker_id = os.getenv("WORKER_ID", str(uuid.uuid4())[:8])

    _log(f"[worker:{worker_id}] starting")
    _log(f"[worker:{worker_id}] REDIS_URL={redis_url}")
    _log(f"[worker:{worker_id}] QUEUE_NAME={queue_name}")
    _log(f"[worker:{worker_id}] PROCESSING_NAME={processing_name}")


    try:
        r = _connect(redis_url)
    except Exception as e:
        _log(f"[worker:{worker_id}] FATAL: redis connect failed: {type(e).__name__}: {e}")
        raise SystemExit(2)

    stop = {"flag": False}

    def _on_signal(signum, _frame):
        stop["flag"] = True
        _log(f"[worker:{worker_id}] signal received={signum}, stopping...")

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    _log(f"[worker:{worker_id}] ready; waiting for messages...")

    while not stop["flag"]:
        try:
            raw: Optional[str] = r.brpoplpush(queue_name, processing_name, timeout=brpop_timeout)
            if raw is None:
                continue

            try:
                msg = json.loads(raw)
            except Exception:
                _log(f"[worker:{worker_id}] invalid json: {raw!r}")
                r.lrem(processing_name, 1, raw)
                continue

            job_id = str(msg.get("job_id") or "").strip()
            task = str(msg.get("task") or "").strip()
            payload = msg.get("payload") or {}

            if not job_id or not task:
                _log(f"[worker:{worker_id}] invalid message (missing job_id/task): {msg}")
                r.lrem(processing_name, 1, raw)
                continue

            if not isinstance(payload, dict):
                payload = {"payload": payload}

            _set_job(r, job_id, "RUNNING", worker_id=worker_id, task=task, started_at=_utc_now_iso())
            _log(f"[worker:{worker_id}] RUNNING job_id={job_id} task={task}")

            try:
                result = _handle_task(task, payload)
                _set_job(r, job_id, "DONE", finished_at=_utc_now_iso(), result=result)
                _log(f"[worker:{worker_id}] DONE job_id={job_id}")
            except Exception as e:
                _set_job(
                    r,
                    job_id,
                    "FAILED",
                    finished_at=_utc_now_iso(),
                    error={"type": type(e).__name__, "message": str(e)},
                )
                _log(f"[worker:{worker_id}] FAILED job_id={job_id} err={type(e).__name__}: {e}")

            r.lrem(processing_name, 1, raw)

        except redis.exceptions.ConnectionError as e:
            _log(f"[worker:{worker_id}] redis connection error: {e} (retry in 2s)")
            time.sleep(2)
            try:
                r = _connect(redis_url)
            except Exception:
                continue
        except Exception as e:
            _log(f"[worker:{worker_id}] unexpected error: {type(e).__name__}: {e}")
            time.sleep(1)

    _log(f"[worker:{worker_id}] stopped")


if __name__ == "__main__":
    main()
