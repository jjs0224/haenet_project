import json
import uuid
import redis
from datetime import datetime, timezone
from typing import Any, Dict

from backend.app.core.config import REDIS_DB, REDIS_HOST, REDIS_PORT, REDIS_URL


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def _normalize_redis_url() -> str:
    raw = (REDIS_URL or "").strip()

    if raw.startswith(("redis://", "rediss://", "unix://")):
        return raw

    if raw.startswith("tcp://"):
        return "redis://" + raw[len("tcp://"):]

    if not raw:
        return f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

    return raw if raw.startswith("redis://") else f"redis://{raw}"

def connect_redis() -> redis.Redis:
    url = _normalize_redis_url()
    r = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)
    r.ping()
    return r

# def connect_redis() -> redis.Redis:
#     r = redis.Redis.from_url(
#         REDIS_URL,
#         decode_responses=True,
#         socket_connect_timeout=5,
#         socket_timeout=5,
#     )
#     r.ping()
#     return r


def _job_key(job_id: str) -> str:
    return f"cicdex:job:{job_id}"


def _queue_for_task(task: str) -> str:
    if task.startswith("menu_assistant_"):
        return "cicdex:jobs:menu_assistant"
    if task.startswith("journal_"):
        return "cicdex:jobs:journal"
    if task.startswith("review_"):
        return "cicdex:jobs:review"
    return "cicdex:jobs"


def enqueue_task(r: redis.Redis, task: str, payload: Dict[str, Any], job_id: str | None = None) -> str:
    job_id = job_id or str(uuid.uuid4())
    queued_at = utc_now_iso()

    data = {
        "job_id": job_id,
        "status": "PENDING",
        "updated_at": queued_at,
        "task": task,
        "queued_at": queued_at,
    }
    r.hset(_job_key(job_id), mapping=data)

    msg = {
        "job_id": job_id,
        "task": task,
        "payload": payload,
        "queued_at": queued_at,
    }
    r.lpush(_queue_for_task(task), json.dumps(msg, ensure_ascii=False))
    return job_id
