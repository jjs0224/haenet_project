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
    r = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=None,
        retry_on_timeout=True,
    )
    r.ping()
    return r


def _run_async(coro):
    import asyncio
    return asyncio.run(coro)


def _handle_task(task: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if task == "ping":
        return {"message": "pong", "echo": payload}

    if task == "sleep":
        sec = int(payload.get("seconds", 1))
        time.sleep(max(0, sec))
        return {"slept": sec}

    if task == "journal_generate":
        from AI.journal_assistant.pipeline.orchestrator import run_orchestrator

        image_bytes = run_orchestrator(payload)
        if not image_bytes:
            raise ValueError("Journal generation returned empty image")

        import base64
        encoded = base64.b64encode(image_bytes).decode("ascii")

        journal_type = str(payload.get("journal_type") or payload.get("template_type") or "journal").strip().lower()
        return {"image_base64": encoded, "journal_type": journal_type}

    # ✅ (B안) 커뮤니티 생성: AI + 업로드만
    if task == "journal_generate_community":
        ai_payload = payload.get("ai_payload") or {}
        total_data = payload.get("total_data") or {}
        template_id = int(payload.get("template_id") or (total_data.get("template_id") or 0))
        community_id = int(payload.get("community_id") or 0)

        if community_id <= 0:
            raise ValueError("community_id is required for async community generation")

        from AI.journal_assistant.pipeline.orchestrator import run_orchestrator
        image_bytes: bytes = run_orchestrator(ai_payload)
        if not image_bytes:
            raise ValueError("AI returned empty image bytes")

        # ✅ DB 접근 제거 / 스토리지 업로드만 수행
        from backend.app.common.service.file_upload_service import save_permanent_bytes, delete_prefix, build_perm_prefix

        try:
            perm_prefix = build_perm_prefix(owner_type="community", owner_id=community_id)
            delete_prefix(prefix_key=perm_prefix)
        except Exception:
            pass

        stored = _run_async(
            save_permanent_bytes(
                owner_type="community",
                owner_id=community_id,
                member_id=int(total_data.get("member_id") or payload.get("member_id") or 0),
                data=image_bytes,
                origin_name="community.png",
                mime_type="image/png",
                sort_order=0,
            )
        )

        return {
            "community_id": community_id,
            "template_id": template_id,
            "stored": {
                "storage_path": getattr(stored, "storage_path", None),
                "stored_file_name": getattr(stored, "stored_file_name", None),
                "org_file_name": getattr(stored, "org_file_name", None),
                "mime_type": getattr(stored, "mime_type", None),
                "size_bytes": getattr(stored, "size_bytes", None),
                "sort_order": getattr(stored, "sort_order", 0),
                "file_key": getattr(stored, "file_key", None),
            },
        }

    raise ValueError(f"Unsupported task: {task}")


def main() -> None:
    _load_secret_from_file("GEMINI_API_KEY")
    _load_secret_from_file("DB_PASSWORD")
    _load_secret_from_file("JWT_SECRET_KEY")
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
                import traceback
                tb = traceback.format_exc()
                _set_job(
                    r,
                    job_id,
                    "FAILED",
                    finished_at=_utc_now_iso(),
                    error={
                        "type": type(e).__name__,
                        "message": str(e),
                        "traceback": tb,  # ✅ 여기!
                    },
                )
                _log(f"[worker:{worker_id}] FAILED job_id={job_id} err={type(e).__name__}: {e}")
                _log(tb)
                # _set_job(
                #     r,
                #     job_id,
                #     "FAILED",
                #     finished_at=_utc_now_iso(),
                #     error={"type": type(e).__name__, "message": str(e)},
                # )
                # _log(f"[worker:{worker_id}] FAILED job_id={job_id} err={type(e).__name__}: {e}")

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


# """
# Worker entry point (queue consumer).
# Wire your task queue here (Celery/RQ/etc.).
# """
#
# import json
# import os
# import signal
# import time
# import uuid
# from datetime import datetime, timezone
# from typing import Any, Dict, Optional
#
# import redis
#
#
# def _utc_now_iso() -> str:
#     return datetime.now(timezone.utc).isoformat()
#
#
# def _log(msg: str) -> None:
#     print(msg, flush=True)
#
#
# def _load_secret_from_file(env_name: str) -> None:
#     file_path = os.getenv(f"{env_name}_FILE")
#     if not file_path or os.getenv(env_name):
#         return
#     try:
#         with open(file_path, "r", encoding="utf-8") as f:
#             os.environ[env_name] = f.read().strip()
#     except Exception as e:
#         _log(f"[worker] warning: failed to read {env_name}_FILE: {type(e).__name__}: {e}")
#
#
# def _job_key(job_id: str) -> str:
#     return f"cicdex:job:{job_id}"
#
#
# def _set_job(r: redis.Redis, job_id: str, status: str, **fields: Any) -> None:
#     data: Dict[str, str] = {
#         "job_id": job_id,
#         "status": status,
#         "updated_at": _utc_now_iso(),
#     }
#     for k, v in fields.items():
#         if isinstance(v, (dict, list)):
#             data[k] = json.dumps(v, ensure_ascii=False)
#         else:
#             data[k] = str(v)
#     r.hset(_job_key(job_id), mapping=data)
#
#
# def _connect(redis_url: str) -> redis.Redis:
#     """
#     중요:
#     - BRPOPLPUSH 같은 블로킹 명령을 쓰면 socket_timeout은 None이어야 정상 대기 중 TimeoutError가 안 남.
#     - connect timeout만 짧게 유지.
#     """
#     r = redis.Redis.from_url(
#         redis_url,
#         decode_responses=True,
#         socket_connect_timeout=5,
#         socket_timeout=None,
#         retry_on_timeout=True,
#     )
#     r.ping()
#     return r
#
#
# def _run_async(coro):
#     import asyncio
#     return asyncio.run(coro)
#
#
# def _handle_task(task: str, payload: Dict[str, Any]) -> Dict[str, Any]:
#     """
#     실제 AI 처리 로직 연결 지점.
#     """
#     if task == "ping":
#         return {"message": "pong", "echo": payload}
#
#     if task == "sleep":
#         sec = int(payload.get("seconds", 1))
#         time.sleep(max(0, sec))
#         return {"slept": sec}
#
#     # 저널 생성 - orchestrator 사용 (템플릿 라우팅 지원)
#     if task == "journal_generate":
#         from AI.journal_assistant.pipeline.orchestrator import run_orchestrator
#
#         # orchestrator가 template_type 또는 template_id로 자동 라우팅
#         image_bytes = run_orchestrator(payload)
#         if not image_bytes:
#             raise ValueError("Journal generation returned empty image")
#
#         import base64
#         encoded = base64.b64encode(image_bytes).decode("ascii")
#
#         # journal_type은 payload에서 추출 (backward compatibility)
#         journal_type = str(payload.get("journal_type") or payload.get("template_type") or "journal").strip().lower()
#         return {"image_base64": encoded, "journal_type": journal_type}
#
#     # 추가: 커뮤니티 생성 (AI 이미지 생성 + S3 저장 + RDS 반영까지 worker가 수행)
#     if task == "journal_generate_community":
#         # payload는 API에서 enqueue할 때 넣어준 값
#         ai_payload = payload.get("ai_payload") or {}
#         total_data = payload.get("total_data") or {}
#         template_id = int(payload.get("template_id") or (total_data.get("template_id") or 0))
#         review_ids = payload.get("review_ids") or []
#
#         # 1) AI 이미지 생성 (저널/지도 템플릿 오케스트레이터)
#         from AI.journal_assistant.pipeline.orchestrator import run_orchestrator
#         image_bytes: bytes = run_orchestrator(ai_payload)
#         if not image_bytes:
#             raise ValueError("AI returned empty image bytes")
#
#         # 2) DB/S3 저장은 backend 로직 재사용
#         #    (⚠️ worker 이미지 안에 backend 코드가 포함되어 있어야 import 가능)
#         from backend.app.core.database import SessionLocal
#         from backend.app.features.community.service import persist_step2_from_image_bytes
#         from backend.app.features.review.service import availavble_review
#
#         db = SessionLocal()
#         try:
#             # community upsert + ImgFile + S3 업로드
#             result = _run_async(persist_step2_from_image_bytes(db, total_data, image_bytes))
#
#             # template1이면 리뷰 available=0 처리
#             if template_id == 1:
#                 ok = availavble_review(db, review_ids)
#                 if not ok:
#                     raise RuntimeError("Failed to update review availability")
#
#             db.commit()
#             return result
#
#         except Exception:
#             db.rollback()
#             raise
#         finally:
#             db.close()
#
#     raise ValueError(f"Unsupported task: {task}")
#
#
# def main() -> None:
#     _load_secret_from_file("GEMINI_API_KEY")
#     _load_secret_from_file("DB_PASSWORD")
#     _load_secret_from_file("JWT_SECRET_KEY")
#     _load_secret_from_file("NAVER_CLIENT_ID")
#     _load_secret_from_file("NAVER_CLIENT_SECRET")
#
#     # S3/DB/REDIS 관련 env는 기존 worker처럼 주입되어 있어야 함
#     redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
#     queue_name = os.getenv("QUEUE_NAME", "cicdex:jobs")
#     processing_name = os.getenv("QUEUE_PROCESSING_NAME", f"{queue_name}:processing")
#     brpop_timeout = int(os.getenv("BRPOP_TIMEOUT_SEC", "10"))
#
#     worker_id = os.getenv("WORKER_ID", str(uuid.uuid4())[:8])
#
#     _log(f"[worker:{worker_id}] starting")
#     _log(f"[worker:{worker_id}] REDIS_URL={redis_url}")
#     _log(f"[worker:{worker_id}] QUEUE_NAME={queue_name}")
#     _log(f"[worker:{worker_id}] PROCESSING_NAME={processing_name}")
#
#     try:
#         r = _connect(redis_url)
#     except Exception as e:
#         _log(f"[worker:{worker_id}] FATAL: redis connect failed: {type(e).__name__}: {e}")
#         raise SystemExit(2)
#
#     stop = {"flag": False}
#
#     def _on_signal(signum, _frame):
#         stop["flag"] = True
#         _log(f"[worker:{worker_id}] signal received={signum}, stopping...")
#
#     signal.signal(signal.SIGTERM, _on_signal)
#     signal.signal(signal.SIGINT, _on_signal)
#
#     _log(f"[worker:{worker_id}] ready; waiting for messages...")
#
#     while not stop["flag"]:
#         try:
#             raw: Optional[str] = r.brpoplpush(queue_name, processing_name, timeout=brpop_timeout)
#             if raw is None:
#                 continue
#
#             try:
#                 msg = json.loads(raw)
#             except Exception:
#                 _log(f"[worker:{worker_id}] invalid json: {raw!r}")
#                 r.lrem(processing_name, 1, raw)
#                 continue
#
#             job_id = str(msg.get("job_id") or "").strip()
#             task = str(msg.get("task") or "").strip()
#             payload = msg.get("payload") or {}
#
#             if not job_id or not task:
#                 _log(f"[worker:{worker_id}] invalid message (missing job_id/task): {msg}")
#                 r.lrem(processing_name, 1, raw)
#                 continue
#
#             if not isinstance(payload, dict):
#                 payload = {"payload": payload}
#
#             _set_job(r, job_id, "RUNNING", worker_id=worker_id, task=task, started_at=_utc_now_iso())
#             _log(f"[worker:{worker_id}] RUNNING job_id={job_id} task={task}")
#
#             try:
#                 result = _handle_task(task, payload)
#                 _set_job(r, job_id, "DONE", finished_at=_utc_now_iso(), result=result)
#                 _log(f"[worker:{worker_id}] DONE job_id={job_id}")
#             except Exception as e:
#                 _set_job(
#                     r,
#                     job_id,
#                     "FAILED",
#                     finished_at=_utc_now_iso(),
#                     error={"type": type(e).__name__, "message": str(e)},
#                 )
#                 _log(f"[worker:{worker_id}] FAILED job_id={job_id} err={type(e).__name__}: {e}")
#
#             r.lrem(processing_name, 1, raw)
#
#         except redis.exceptions.ConnectionError as e:
#             _log(f"[worker:{worker_id}] redis connection error: {e} (retry in 2s)")
#             time.sleep(2)
#             try:
#                 r = _connect(redis_url)
#             except Exception:
#                 continue
#         except Exception as e:
#             _log(f"[worker:{worker_id}] unexpected error: {type(e).__name__}: {e}")
#             time.sleep(1)
#
#     _log(f"[worker:{worker_id}] stopped")
#
#
# if __name__ == "__main__":
#     main()
#
#
#
# # """
# # Worker entry point (queue consumer).
# # """
# #
# # import json
# # import os
# # import signal
# # import time
# # import uuid
# # from datetime import datetime, timezone
# # from typing import Any, Dict, Optional
# #
# # import redis
# #
# #
# # def _utc_now_iso() -> str:
# #     return datetime.now(timezone.utc).isoformat()
# #
# #
# # def _log(msg: str) -> None:
# #     print(msg, flush=True)
# #
# #
# # def _load_secret_from_file(env_name: str) -> None:
# #     file_path = os.getenv(f"{env_name}_FILE")
# #     if not file_path or os.getenv(env_name):
# #         return
# #     try:
# #         with open(file_path, "r", encoding="utf-8") as f:
# #             os.environ[env_name] = f.read().strip()
# #     except Exception as e:
# #         _log(f"[worker] warning: failed to read {env_name}_FILE: {type(e).__name__}: {e}")
# #
# #
# # def _job_key(job_id: str) -> str:
# #     return f"cicdex:job:{job_id}"
# #
# #
# # def _set_job(r: redis.Redis, job_id: str, status: str, **fields: Any) -> None:
# #     data: Dict[str, str] = {
# #         "job_id": job_id,
# #         "status": status,
# #         "updated_at": _utc_now_iso(),
# #     }
# #     for k, v in fields.items():
# #         if isinstance(v, (dict, list)):
# #             data[k] = json.dumps(v, ensure_ascii=False)
# #         else:
# #             data[k] = str(v)
# #     r.hset(_job_key(job_id), mapping=data)
# #
# #
# # def _connect(redis_url: str) -> redis.Redis:
# #     r = redis.Redis.from_url(
# #         redis_url,
# #         decode_responses=True,
# #         socket_connect_timeout=5,
# #         socket_timeout=None,
# #         retry_on_timeout=True,
# #     )
# #     r.ping()
# #     return r
# #
# #
# # def _run_async(coro):
# #     # worker는 기본 sync 루프이므로 asyncio.run으로 실행
# #     import asyncio
# #     return asyncio.run(coro)
# #
# #
# # def _handle_task(task: str, payload: Dict[str, Any]) -> Dict[str, Any]:
# #     if task == "ping":
# #         return {"message": "pong", "echo": payload}
# #
# #     if task == "sleep":
# #         sec = int(payload.get("seconds", 1))
# #         time.sleep(max(0, sec))
# #         return {"slept": sec}
# #
# #     # (추가) 커뮤니티 생성: AI + DB/S3 저장까지 worker가 처리
# #     if task == "journal_generate_community":
# #         # 1) AI 이미지 생성
# #         ai_payload = payload.get("ai_payload") or {}
# #         total_data = payload.get("total_data") or {}
# #         template_id = int(payload.get("template_id") or (total_data.get("template_id") or 0))
# #         review_ids = payload.get("review_ids") or []
# #
# #         from AI.journal_assistant.pipeline.orchestrator import run_orchestrator
# #         image_bytes = run_orchestrator(ai_payload)
# #         if not image_bytes:
# #             raise ValueError("AI returned empty image bytes")
# #
# #         # 2) DB/S3 저장 (backend 코드를 그대로 재사용)
# #         from backend.app.core.database import SessionLocal
# #         from backend.app.features.community.service import persist_step2_from_image_bytes
# #         from backend.app.features.review.service import availavble_review
# #
# #         db = SessionLocal()
# #         try:
# #             result = _run_async(persist_step2_from_image_bytes(db, total_data, image_bytes))
# #
# #             # 3) template1이면 review available=0 처리 (기존 API 라우터가 하던걸 worker로 이동)
# #             if template_id == 1:
# #                 ok = availavble_review(db, review_ids)
# #                 if not ok:
# #                     raise RuntimeError("Failed to update review availability")
# #
# #             db.commit()
# #             return result
# #
# #         except Exception:
# #             db.rollback()
# #             raise
# #         finally:
# #             db.close()
# #
# #     raise ValueError(f"Unsupported task: {task}")
# #
# #
# # def main() -> None:
# #     _load_secret_from_file("GEMINI_API_KEY")
# #     _load_secret_from_file("DB_PASSWORD")
# #     _load_secret_from_file("JWT_SECRET_KEY")
# #     _load_secret_from_file("NAVER_CLIENT_ID")
# #     _load_secret_from_file("NAVER_CLIENT_SECRET")
# #
# #     redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
# #     queue_name = os.getenv("QUEUE_NAME", "cicdex:jobs")
# #     processing_name = os.getenv("QUEUE_PROCESSING_NAME", f"{queue_name}:processing")
# #     brpop_timeout = int(os.getenv("BRPOP_TIMEOUT_SEC", "10"))
# #
# #     worker_id = os.getenv("WORKER_ID", str(uuid.uuid4())[:8])
# #
# #     _log(f"[worker:{worker_id}] starting")
# #     _log(f"[worker:{worker_id}] REDIS_URL={redis_url}")
# #     _log(f"[worker:{worker_id}] QUEUE_NAME={queue_name}")
# #     _log(f"[worker:{worker_id}] PROCESSING_NAME={processing_name}")
# #
# #     try:
# #         r = _connect(redis_url)
# #     except Exception as e:
# #         _log(f"[worker:{worker_id}] FATAL: redis connect failed: {type(e).__name__}: {e}")
# #         raise SystemExit(2)
# #
# #     stop = {"flag": False}
# #
# #     def _on_signal(signum, _frame):
# #         stop["flag"] = True
# #         _log(f"[worker:{worker_id}] signal received={signum}, stopping...")
# #
# #     signal.signal(signal.SIGTERM, _on_signal)
# #     signal.signal(signal.SIGINT, _on_signal)
# #
# #     _log(f"[worker:{worker_id}] ready; waiting for messages...")
# #
# #     while not stop["flag"]:
# #         try:
# #             raw: Optional[str] = r.brpoplpush(queue_name, processing_name, timeout=brpop_timeout)
# #             if raw is None:
# #                 continue
# #
# #             try:
# #                 msg = json.loads(raw)
# #             except Exception:
# #                 _log(f"[worker:{worker_id}] invalid json: {raw!r}")
# #                 r.lrem(processing_name, 1, raw)
# #                 continue
# #
# #             job_id = str(msg.get("job_id") or "").strip()
# #             task = str(msg.get("task") or "").strip()
# #             payload = msg.get("payload") or {}
# #
# #             if not job_id or not task:
# #                 _log(f"[worker:{worker_id}] invalid message (missing job_id/task): {msg}")
# #                 r.lrem(processing_name, 1, raw)
# #                 continue
# #
# #             if not isinstance(payload, dict):
# #                 payload = {"payload": payload}
# #
# #             _set_job(r, job_id, "RUNNING", worker_id=worker_id, task=task, started_at=_utc_now_iso())
# #             _log(f"[worker:{worker_id}] RUNNING job_id={job_id} task={task}")
# #
# #             try:
# #                 result = _handle_task(task, payload)
# #                 _set_job(r, job_id, "DONE", finished_at=_utc_now_iso(), result=result)
# #                 _log(f"[worker:{worker_id}] DONE job_id={job_id}")
# #             except Exception as e:
# #                 _set_job(
# #                     r,
# #                     job_id,
# #                     "FAILED",
# #                     finished_at=_utc_now_iso(),
# #                     error={"type": type(e).__name__, "message": str(e)},
# #                 )
# #                 _log(f"[worker:{worker_id}] FAILED job_id={job_id} err={type(e).__name__}: {e}")
# #
# #             r.lrem(processing_name, 1, raw)
# #
# #         except redis.exceptions.ConnectionError as e:
# #             _log(f"[worker:{worker_id}] redis connection error: {e} (retry in 2s)")
# #             time.sleep(2)
# #             try:
# #                 r = _connect(redis_url)
# #             except Exception:
# #                 continue
# #         except Exception as e:
# #             _log(f"[worker:{worker_id}] unexpected error: {type(e).__name__}: {e}")
# #             time.sleep(1)
# #
# #     _log(f"[worker:{worker_id}] stopped")
# #
# #
# # if __name__ == "__main__":
# #     main()
# #
# #
# #
# # # """
# # # Worker entry point (queue consumer).
# # # Wire your task queue here (Celery/RQ/etc.).
# # # """
# # #
# # # import json
# # # import os
# # # import signal
# # # import time
# # # import uuid
# # # from datetime import datetime, timezone
# # # from typing import Any, Dict, Optional
# # #
# # # import redis
# # #
# # #
# # # def _utc_now_iso() -> str:
# # #     return datetime.now(timezone.utc).isoformat()
# # #
# # #
# # # def _log(msg: str) -> None:
# # #     print(msg, flush=True)
# # #
# # #
# # # def _load_secret_from_file(env_name: str) -> None:
# # #     file_path = os.getenv(f"{env_name}_FILE")
# # #     if not file_path or os.getenv(env_name):
# # #         return
# # #     try:
# # #         with open(file_path, "r", encoding="utf-8") as f:
# # #             os.environ[env_name] = f.read().strip()
# # #     except Exception as e:
# # #         _log(f"[worker] warning: failed to read {env_name}_FILE: {type(e).__name__}: {e}")
# # #
# # #
# # # def _job_key(job_id: str) -> str:
# # #     return f"cicdex:job:{job_id}"
# # #
# # #
# # # def _set_job(r: redis.Redis, job_id: str, status: str, **fields: Any) -> None:
# # #     data: Dict[str, str] = {
# # #         "job_id": job_id,
# # #         "status": status,
# # #         "updated_at": _utc_now_iso(),
# # #     }
# # #     for k, v in fields.items():
# # #         if isinstance(v, (dict, list)):
# # #             data[k] = json.dumps(v, ensure_ascii=False)
# # #         else:
# # #             data[k] = str(v)
# # #     r.hset(_job_key(job_id), mapping=data)
# # #
# # #
# # # def _connect(redis_url: str) -> redis.Redis:
# # #     """
# # #     중요:
# # #     - BRPOPLPUSH 같은 블로킹 명령을 쓰면 socket_timeout은 None이어야 정상 대기 중 TimeoutError가 안 남.
# # #     - connect timeout만 짧게 유지.
# # #     """
# # #     r = redis.Redis.from_url(
# # #         redis_url,
# # #         decode_responses=True,
# # #         socket_connect_timeout=5,
# # #         socket_timeout=None,  # <-- 핵심 수정
# # #         retry_on_timeout=True,
# # #     )
# # #     r.ping()
# # #     return r
# # #
# # #
# # # def _handle_task(task: str, payload: Dict[str, Any]) -> Dict[str, Any]:
# # #     """
# # #     실제 AI 처리 로직 연결 지점.
# # #     - 지금은 E2E 검증을 위해 기본 task 제공
# # #     """
# # #     if task == "ping":
# # #         return {"message": "pong", "echo": payload}
# # #
# # #     if task == "sleep":
# # #         sec = int(payload.get("seconds", 1))
# # #         time.sleep(max(0, sec))
# # #         return {"slept": sec}
# # #     if task == "journal_generate":
# # #         from AI.journal_assistant.pipeline import journal as journal_module
# # #
# # #         journal_type = str(payload.get("journal_type") or "journal").strip().lower()
# # #         if journal_type not in ("journal", "culture"):
# # #             raise ValueError("journal_type must be 'journal' or 'culture'")
# # #
# # #         if journal_type == "culture":
# # #             prompt = journal_module.culture_journal(payload)
# # #         else:
# # #             prompt = journal_module.journal_prompt(payload)
# # #
# # #         image_bytes = journal_module.generate_journal(prompt)
# # #         if not image_bytes:
# # #             raise ValueError("Journal generation returned empty image")
# # #
# # #         import base64
# # #         encoded = base64.b64encode(image_bytes).decode("ascii")
# # #         return {"image_base64": encoded, "journal_type": journal_type}
# # #
# # #     raise ValueError(f"Unsupported task: {task}")
# # #
# # #
# # # def main() -> None:
# # #     _load_secret_from_file("GEMINI_API_KEY")
# # #     _load_secret_from_file("DB_PASSWORD")
# # #     _load_secret_from_file("JWT_SECRET_KEY")
# # #
# # #     redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
# # #     queue_name = os.getenv("QUEUE_NAME", "cicdex:jobs")
# # #     processing_name = os.getenv("QUEUE_PROCESSING_NAME", f"{queue_name}:processing")
# # #     brpop_timeout = int(os.getenv("BRPOP_TIMEOUT_SEC", "10"))
# # #
# # #     worker_id = os.getenv("WORKER_ID", str(uuid.uuid4())[:8])
# # #
# # #     _log(f"[worker:{worker_id}] starting")
# # #     _log(f"[worker:{worker_id}] REDIS_URL={redis_url}")
# # #     _log(f"[worker:{worker_id}] QUEUE_NAME={queue_name}")
# # #     _log(f"[worker:{worker_id}] PROCESSING_NAME={processing_name}")
# # #
# # #     try:
# # #         r = _connect(redis_url)
# # #     except Exception as e:
# # #         _log(f"[worker:{worker_id}] FATAL: redis connect failed: {type(e).__name__}: {e}")
# # #         raise SystemExit(2)
# # #
# # #     stop = {"flag": False}
# # #
# # #     def _on_signal(signum, _frame):
# # #         stop["flag"] = True
# # #         _log(f"[worker:{worker_id}] signal received={signum}, stopping...")
# # #
# # #     signal.signal(signal.SIGTERM, _on_signal)
# # #     signal.signal(signal.SIGINT, _on_signal)
# # #
# # #     _log(f"[worker:{worker_id}] ready; waiting for messages...")
# # #
# # #     while not stop["flag"]:
# # #         try:
# # #             raw: Optional[str] = r.brpoplpush(queue_name, processing_name, timeout=brpop_timeout)
# # #             if raw is None:
# # #                 continue
# # #
# # #             try:
# # #                 msg = json.loads(raw)
# # #             except Exception:
# # #                 _log(f"[worker:{worker_id}] invalid json: {raw!r}")
# # #                 r.lrem(processing_name, 1, raw)
# # #                 continue
# # #
# # #             job_id = str(msg.get("job_id") or "").strip()
# # #             task = str(msg.get("task") or "").strip()
# # #             payload = msg.get("payload") or {}
# # #
# # #             if not job_id or not task:
# # #                 _log(f"[worker:{worker_id}] invalid message (missing job_id/task): {msg}")
# # #                 r.lrem(processing_name, 1, raw)
# # #                 continue
# # #
# # #             if not isinstance(payload, dict):
# # #                 payload = {"payload": payload}
# # #
# # #             _set_job(r, job_id, "RUNNING", worker_id=worker_id, task=task, started_at=_utc_now_iso())
# # #             _log(f"[worker:{worker_id}] RUNNING job_id={job_id} task={task}")
# # #
# # #             try:
# # #                 result = _handle_task(task, payload)
# # #                 _set_job(r, job_id, "DONE", finished_at=_utc_now_iso(), result=result)
# # #                 _log(f"[worker:{worker_id}] DONE job_id={job_id}")
# # #             except Exception as e:
# # #                 _set_job(
# # #                     r,
# # #                     job_id,
# # #                     "FAILED",
# # #                     finished_at=_utc_now_iso(),
# # #                     error={"type": type(e).__name__, "message": str(e)},
# # #                 )
# # #                 _log(f"[worker:{worker_id}] FAILED job_id={job_id} err={type(e).__name__}: {e}")
# # #
# # #             r.lrem(processing_name, 1, raw)
# # #
# # #         except redis.exceptions.ConnectionError as e:
# # #             _log(f"[worker:{worker_id}] redis connection error: {e} (retry in 2s)")
# # #             time.sleep(2)
# # #             try:
# # #                 r = _connect(redis_url)
# # #             except Exception:
# # #                 continue
# # #         except Exception as e:
# # #             _log(f"[worker:{worker_id}] unexpected error: {type(e).__name__}: {e}")
# # #             time.sleep(1)
# # #
# # #     _log(f"[worker:{worker_id}] stopped")
# # #
# # #
# # # if __name__ == "__main__":
# # #     main()
