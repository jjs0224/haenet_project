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
from pathlib import Path
from typing import Any, Dict, Optional

import redis


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    print(msg, flush=True)


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"invalid s3 uri: {uri}")
    parts = uri[5:].split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    return bucket, key


def _load_profile_from_file_key(file_key: str) -> Optional[Dict[str, Any]]:
    key = (file_key or "").strip()
    if not key:
        return None

    # 1) local path
    p = Path(key)
    if p.exists():
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else None
        except Exception as e:
            _log(f"[worker] warning: failed to read local profile json: {type(e).__name__}: {e}")
            return None

    # 2) s3://bucket/key
    if key.startswith("s3://"):
        try:
            import boto3

            bucket, s3_key = _parse_s3_uri(key)
            resp = boto3.client("s3").get_object(Bucket=bucket, Key=s3_key)
            body = resp["Body"].read().decode("utf-8")
            obj = json.loads(body)
            return obj if isinstance(obj, dict) else None
        except Exception as e:
            _log(f"[worker] warning: failed to read profile json from s3 uri: {type(e).__name__}: {e}")
            return None

    # 3) plain s3 object key (bucket from env)
    try:
        import boto3

        bucket = (os.getenv("S3_BUCKET") or "").strip()
        if not bucket:
            _log("[worker] warning: S3_BUCKET is empty; cannot load user_profile_file_key")
            return None
        resp = boto3.client("s3").get_object(Bucket=bucket, Key=key)
        body = resp["Body"].read().decode("utf-8")
        obj = json.loads(body)
        return obj if isinstance(obj, dict) else None
    except Exception as e:
        _log(f"[worker] warning: failed to read profile json from s3 key: {type(e).__name__}: {e}")
        return None


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
    if task == "menu_assistant_pipeline":
        import base64
        import json as _json
        from dataclasses import asdict, is_dataclass
        from pathlib import Path

        # NOTE: keep import path unchanged (project layout)
        from AI.menu_assistant.worker.worker_app.pipeline.orchestrator import (
            PipelineOrchestrator,
            Step1Options,
            Step2Options,
            Step3Options,
            Step4Options,
            Step5Options,
            Step6Options,
            _default_runs_root,
        )

        def _coerce_bool(v: Any, default: bool) -> bool:
            if v is None:
                return default
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return bool(v)
            s = str(v).strip().lower()
            if s in ("1", "true", "t", "yes", "y", "on"):
                return True
            if s in ("0", "false", "f", "no", "n", "off"):
                return False
            return default

        def _load_opts(cls, data: Any):
            """
            Build orchestrator option dataclass from dict (unknown keys ignored).
            Also accepts an already-constructed instance.
            """
            if data is None:
                return None
            if is_dataclass(data):
                return data
            if not isinstance(data, dict):
                return None

            # allow both snake_case keys and older flat keys; ignore unknowns
            allowed = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
            kwargs = {k: v for k, v in data.items() if k in allowed}
            return cls(**kwargs)

        run_id = str(payload.get("run_id") or "").strip() or None

        # Execution flags (default: run step4~6)
        run_step4 = _coerce_bool(payload.get("run_step4"), True)
        run_step5 = _coerce_bool(payload.get("run_step5"), True)
        run_step6 = _coerce_bool(payload.get("run_step6"), True)

        # Paths
        runs_root = Path(payload.get("runs_root") or _default_runs_root()).expanduser().resolve()
        data_dir = payload.get("data_dir")
        data_dir_path = Path(data_dir).expanduser().resolve() if data_dir else None

        tmp_dir = runs_root / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # Image input: prefer image_path; fallback to image_base64
        image_path = payload.get("image_path")
        if image_path:
            image_path = Path(image_path).expanduser().resolve()
        else:
            encoded = payload.get("image_base64")
            if not encoded:
                raise ValueError("Missing 'image_base64' or 'image_path' in payload")
            img_bytes = base64.b64decode(encoded)
            image_path = tmp_dir / f"menu_{run_id or uuid.uuid4().hex}.jpg"
            image_path.write_bytes(img_bytes)

        # User profile (supports dict -> temp json, or explicit json path)
        user_profile = payload.get("user_profile")
        user_profile_json = payload.get("user_profile_json")
        user_profile_file_key = payload.get("user_profile_file_key")

        # Fallback: if profile object is not provided, load from saved key/path.
        if not user_profile and user_profile_file_key:
            loaded_profile = _load_profile_from_file_key(str(user_profile_file_key))
            if loaded_profile:
                user_profile = loaded_profile

        if user_profile and not user_profile_json:
            profile_path = tmp_dir / f"user_profile_{run_id or uuid.uuid4().hex}.json"
            profile_path.write_text(_json.dumps(user_profile, ensure_ascii=False), encoding="utf-8")
            user_profile_json = str(profile_path)

        # Options: allow nested dicts: step1..step6
        step1 = _load_opts(Step1Options, payload.get("step1"))
        step2 = _load_opts(Step2Options, payload.get("step2"))
        step3 = _load_opts(Step3Options, payload.get("step3"))
        step4 = _load_opts(Step4Options, payload.get("step4"))
        step5 = _load_opts(Step5Options, payload.get("step5")) or Step5Options()
        step6 = _load_opts(Step6Options, payload.get("step6"))

        # Backward-compatible Step5 flat keys (if provided)
        if user_profile_json:
            step5.user_profile_json = user_profile_json

        if "include_debug" in payload:
            step5.include_debug = _coerce_bool(payload.get("include_debug"), step5.include_debug)
        if "require_poly" in payload:
            step5.require_poly = _coerce_bool(payload.get("require_poly"), step5.require_poly)
        if "max_retries" in payload and payload.get("max_retries") is not None:
            step5.max_retries = int(payload.get("max_retries"))

        # speed patch (optional)
        if payload.get("chunk_size") is not None:
            step5.chunk_size = int(payload.get("chunk_size"))
        if payload.get("workers") is not None:
            step5.workers = int(payload.get("workers"))
        if payload.get("use_cache") is not None:
            step5.use_cache = _coerce_bool(payload.get("use_cache"), step5.use_cache)

        orch = PipelineOrchestrator(runs_root, data_dir=data_dir_path)
        run_dir = orch.run(
            image_path=image_path,
            run_id=run_id,
            step1=step1,
            step2=step2,
            step3=step3,
            step4=step4,
            step5=step5,
            step6=step6,
            run_step4=run_step4,
            run_step5=run_step5,
            run_step6=run_step6,
            do_check=False,
        )

        # Preferred entrypoint when Step06 ran: final/final_output.json -> final/final_translated.json
        final_output_path = run_dir / "final" / "final_output.json"
        if run_step6 and final_output_path.exists():
            meta = _json.loads(final_output_path.read_text(encoding="utf-8"))
            rel = (((meta.get("final_output") or {}).get("relative_path")) or "").strip()
            result_path = (run_dir / rel).resolve() if rel else (run_dir / "final" / "final_translated.json")
        else:
            result_path = run_dir / "final" / ("final_translated.json" if run_step6 else "final.json")

        if not result_path.exists():
            raise FileNotFoundError(f"Menu assistant result not found: {result_path}")

        final_obj = _json.loads(result_path.read_text(encoding="utf-8"))

        rectified_path = run_dir / "rectify" / "rectified.jpg"
        rectified_image = None
        if rectified_path.exists():
            img_b64 = base64.b64encode(rectified_path.read_bytes()).decode("ascii")
            rectified_image = {
                "mime": "image/jpeg",
                "base64": img_b64,
            }

        return {
            "final": final_obj,
            "rectified_image": rectified_image,
            "run_id": run_id,
            "run_dir": str(run_dir),
            "result_path": str(result_path),
            "final_output_path": str(final_output_path) if final_output_path.exists() else None,
        }

    raise ValueError(f"Unsupported task: {task}")


def main() -> None:
    _load_secret_from_file("OPENAI_API_KEY")
    _load_secret_from_file("DB_PASSWORD")
    _load_secret_from_file("JWT_SECRET_KEY")

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
