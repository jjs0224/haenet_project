"""
Worker entry point (queue consumer).
Wire your task queue here (Celery/RQ/etc.).
"""

import json
import os
import signal
import time
import uuid
from pathlib import Path
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


def _get_s3_client():
    try:
        import boto3  # type: ignore
    except Exception as e:
        _log(f"[worker] warning: boto3 not available for S3 upload: {type(e).__name__}: {e}")
        return None

    region = os.getenv("S3_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    try:
        return boto3.client("s3", region_name=region) if region else boto3.client("s3")
    except Exception as e:
        _log(f"[worker] warning: failed to create s3 client: {type(e).__name__}: {e}")
        return None


def _upload_rectified_image(run_dir: Path, run_id: str) -> Optional[Dict[str, Any]]:
    bucket = os.getenv("S3_BUCKET") or ""
    if not bucket:
        _log("[worker] S3_BUCKET not set; skip rectified image upload")
        return None

    rectified_path = run_dir / "rectify" / "rectified.jpg"
    if not rectified_path.exists():
        _log(f"[worker] rectified image not found: {rectified_path}")
        return None

    client = _get_s3_client()
    if client is None:
        return None

    prefix = os.getenv("MENU_ASSISTANT_IMAGE_S3_PREFIX") or os.getenv("S3_PREFIX") or "upload"
    prefix = prefix.strip("/")
    key = f"{prefix}/menu_assistant/rectified/{run_id}/rectified.jpg"

    try:
        client.upload_file(str(rectified_path), bucket, key, ExtraArgs={"ContentType": "image/jpeg"})
    except Exception as e:
        _log(f"[worker] rectified image upload failed: {type(e).__name__}: {e}")
        return None

    expires_in = int(os.getenv("MENU_ASSISTANT_IMAGE_URL_TTL", "3600"))
    presigned_url = ""
    try:
        presigned_url = client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
    except Exception as e:
        _log(f"[worker] presign failed for rectified image: {type(e).__name__}: {e}")

    return {
        "bucket": bucket,
        "key": key,
        "s3_uri": f"s3://{bucket}/{key}",
        "presigned_url": presigned_url,
        "expires_in": expires_in,
    }


def _render_result_overlay(run_dir: Path, result: Any) -> Optional[Path]:
    rectified_path = run_dir / "rectify" / "rectified.jpg"
    if not rectified_path.exists():
        _log(f"[worker] rectified image not found for overlay: {rectified_path}")
        return None

    items = None
    if isinstance(result, dict):
        items = result.get("items")
    elif isinstance(result, list):
        items = result

    if not isinstance(items, list) or not items:
        _log("[worker] overlay skipped: no items with poly")
        return None

    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception as e:
        _log(f"[worker] overlay skipped: missing cv2/numpy: {type(e).__name__}: {e}")
        return None

    img = cv2.imread(str(rectified_path), cv2.IMREAD_COLOR)
    if img is None:
        _log(f"[worker] overlay skipped: failed to read {rectified_path}")
        return None

    def _label_from_item(it: Dict[str, Any]) -> str:
        for key in ("menu_name_en", "menu_name_ko", "menu_name"):
            val = it.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return ""

    used = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        poly = item.get("poly")
        if not isinstance(poly, list) or len(poly) < 4:
            continue
        try:
            pts = np.array(poly, dtype=np.int32).reshape((-1, 1, 2))
        except Exception:
            continue
        if pts.size == 0:
            continue

        rd = item.get("risk_difficulty")
        if rd == 0:
            color = (0, 255, 0)       # green  — SAFE
        elif rd == 1:
            color = (0, 255, 255)     # yellow — LOW RISK
        elif rd == 2:
            color = (0, 128, 255)     # orange — HIGH RISK
        else:
            color = (128, 128, 128)   # gray   — UNKNOWN

        cv2.polylines(img, [pts], True, color, 2)
        label = _label_from_item(item)
        if label:
            x, y = int(pts[0][0][0]), int(pts[0][0][1])
            y = max(15, y - 6)
            cv2.putText(img, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
        used += 1

    if used == 0:
        _log("[worker] overlay skipped: no valid polygons")
        return None

    out_dir = run_dir / "final"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "result.jpg"
    ok = cv2.imwrite(str(out_path), img)
    if not ok:
        _log(f"[worker] overlay write failed: {out_path}")
        return None

    return out_path


def _upload_result_image(run_id: str, overlay_path: Optional[Path]) -> Optional[Dict[str, Any]]:
    bucket = os.getenv("S3_BUCKET") or ""
    if not bucket:
        _log("[worker] S3_BUCKET not set; skip result image upload")
        return None

    if overlay_path is None:
        return None

    client = _get_s3_client()
    if client is None:
        return None

    prefix = os.getenv("MENU_ASSISTANT_IMAGE_S3_PREFIX") or os.getenv("S3_PREFIX") or "upload"
    prefix = prefix.strip("/")
    key = f"{prefix}/menu_assistant/result/{run_id}/result.jpg"

    try:
        client.upload_file(str(overlay_path), bucket, key, ExtraArgs={"ContentType": "image/jpeg"})
    except Exception as e:
        _log(f"[worker] result image upload failed: {type(e).__name__}: {e}")
        return None

    expires_in = int(os.getenv("MENU_ASSISTANT_IMAGE_URL_TTL", "3600"))
    presigned_url = ""
    try:
        presigned_url = client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
    except Exception as e:
        _log(f"[worker] presign failed for result image: {type(e).__name__}: {e}")

    return {
        "bucket": bucket,
        "key": key,
        "s3_uri": f"s3://{bucket}/{key}",
        "presigned_url": presigned_url,
        "expires_in": expires_in,
    }


def _ensure_chroma_dir() -> None:
    """Download ChromaDB tarball from S3 at worker startup if not already present locally."""
    local = os.environ.get("MENU_ASSISTANT_CHROMA_DIR", "").strip()
    if local:
        p = Path(local)
        if p.exists() and any(p.iterdir()):
            _log(f"[worker] chroma_dir already present: {local}")
            return

    s3_prefix = os.environ.get("MENU_ASSISTANT_CHROMA_S3_PREFIX", "").strip()
    if not s3_prefix:
        _log("[worker] MENU_ASSISTANT_CHROMA_S3_PREFIX not set; skip chroma download.")
        return

    s3_uri = s3_prefix.rstrip("/")
    if s3_uri.startswith("s3://"):
        rest = s3_uri[5:]
    else:
        rest = s3_uri
    parts = rest.split("/", 1)
    bucket = parts[0]
    key_prefix = parts[1] if len(parts) > 1 else ""
    tarball_key = f"{key_prefix}/chroma.tar.gz" if key_prefix else "chroma.tar.gz"

    local_chroma_dir = Path("/tmp/chroma")
    tarball_path = Path("/tmp/chroma.tar.gz")

    _log(f"[worker] Downloading chroma from s3://{bucket}/{tarball_key} ...")
    try:
        import boto3  # type: ignore
    except ImportError:
        _log("[worker] boto3 not available; cannot download chroma from S3.")
        return

    try:
        region = (
            os.environ.get("S3_REGION")
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
        )
        client = boto3.client("s3", region_name=region) if region else boto3.client("s3")
        client.download_file(bucket, tarball_key, str(tarball_path))
    except Exception as e:
        _log(f"[worker] chroma download failed: {type(e).__name__}: {e}")
        return

    _log(f"[worker] Extracting {tarball_path} -> {local_chroma_dir.parent} ...")
    try:
        import tarfile
        with tarfile.open(str(tarball_path), "r:gz") as tar:
            tar.extractall(str(local_chroma_dir.parent))
    except Exception as e:
        _log(f"[worker] chroma extract failed: {type(e).__name__}: {e}")
        return
    finally:
        try:
            tarball_path.unlink()
        except Exception:
            pass

    os.environ["MENU_ASSISTANT_CHROMA_DIR"] = str(local_chroma_dir)
    _log(f"[worker] MENU_ASSISTANT_CHROMA_DIR set to: {local_chroma_dir}")


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
        from AI.menu_assistant.worker.worker_app.pipeline.orchestrator import (
            PipelineOrchestrator,
            Step5Options,
            _default_runs_root,
        )

        run_id = str(payload.get("run_id") or "").strip() or None
        run_step4 = bool(payload.get("run_step4", True))
        run_step5 = bool(payload.get("run_step5", True))
        run_step6 = bool(payload.get("run_step6", True))

        runs_root = Path(payload.get("runs_root") or _default_runs_root()).expanduser().resolve()
        tmp_dir = runs_root / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

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

        user_profile = payload.get("user_profile")
        user_profile_json = payload.get("user_profile_json")
        if user_profile and not user_profile_json:
            profile_path = tmp_dir / f"user_profile_{run_id or uuid.uuid4().hex}.json"
            profile_path.write_text(_json.dumps(user_profile, ensure_ascii=False), encoding="utf-8")
            user_profile_json = str(profile_path)

        step5 = Step5Options(user_profile_json=user_profile_json)

        orch = PipelineOrchestrator(runs_root)
        run_dir = orch.run(
            image_path=image_path,
            run_id=run_id,
            step5=step5,
            run_step4=run_step4,
            run_step5=run_step5,
            run_step6=run_step6,
            do_check=False,
        )

        result_path = run_dir / "final" / ("final_translated.json" if run_step6 else "final.json")
        if not result_path.exists():
            raise FileNotFoundError(f"Menu assistant result not found: {result_path}")
        result = _json.loads(result_path.read_text(encoding="utf-8"))
        if isinstance(result, dict):
            resolved_run_id = str(run_id or result.get("run_id") or run_dir.name)

            # --- S3 upload (rectified image) ---
            upload_info = _upload_rectified_image(run_dir, resolved_run_id)
            if upload_info:
                artifacts = result.get("artifacts")
                if not isinstance(artifacts, dict):
                    artifacts = {}
                artifacts["rectified_image"] = upload_info
                result["artifacts"] = artifacts
                if upload_info.get("presigned_url"):
                    result["rectified_image_url"] = upload_info["presigned_url"]

            # render overlay once — reused by both S3 upload and base64 fallback
            result_overlay_path = _render_result_overlay(run_dir, result)

            # --- S3 upload (result overlay image) ---
            result_upload = _upload_result_image(resolved_run_id, result_overlay_path)
            if result_upload:
                artifacts = result.get("artifacts")
                if not isinstance(artifacts, dict):
                    artifacts = {}
                artifacts["result_image"] = result_upload
                result["artifacts"] = artifacts
                if result_upload.get("presigned_url"):
                    result["result_image_url"] = result_upload["presigned_url"]

            # --- base64 fallback: S3 업로드 실패 시 rectified 이미지를 base64로 포함 ---
            if not result.get("rectified_image_url"):
                rectified_path = run_dir / "rectify" / "rectified.jpg"
                if rectified_path.exists():
                    _log("[worker] S3 unavailable; embedding rectified image as base64")
                    img_b64 = base64.b64encode(rectified_path.read_bytes()).decode("ascii")
                    result["rectified_image"] = {
                        "mime": "image/jpeg",
                        "base64": img_b64,
                    }

            # --- base64 fallback: S3 업로드 실패 시 result overlay를 base64로 포함 ---
            if not result.get("result_image_url"):
                if result_overlay_path and result_overlay_path.exists():
                    _log("[worker] S3 unavailable; embedding result image as base64")
                    img_b64 = base64.b64encode(result_overlay_path.read_bytes()).decode("ascii")
                    result["result_image"] = {
                        "mime": "image/jpeg",
                        "base64": img_b64,
                    }

        return result

    raise ValueError(f"Unsupported task: {task}")


def main() -> None:
    _load_secret_from_file("OPENAI_API_KEY")
    _load_secret_from_file("DB_PASSWORD")
    _load_secret_from_file("JWT_SECRET_KEY")

    _ensure_chroma_dir()

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
