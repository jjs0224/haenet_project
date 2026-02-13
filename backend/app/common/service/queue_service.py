import json
import os
import uuid
from typing import Any, Dict, Optional

from backend.app.core.cache.redis import redis_client

# 워커가 읽는 큐 이름과 반드시 동일해야 함
QUEUE_NAME = os.getenv("QUEUE_NAME", "cicdex:jobs")


def enqueue(task: str, payload: Dict[str, Any]) -> str:
    """
    워커가 기대하는 표준 메시지 포맷으로만 큐에 넣는다.

    msg = {
      "job_id": "<uuid-hex>",
      "task": "<task name>",
      "payload": { ... }
    }
    """
    job_id = uuid.uuid4().hex
    msg = {"job_id": job_id, "task": task, "payload": payload}
    redis_client.lpush(QUEUE_NAME, json.dumps(msg, ensure_ascii=False))
    return job_id


def job_key(job_id: str) -> str:
    """
    워커가 결과를 저장하는 Redis 해시 키와 동일한 형태로 맞춘다.
    (worker: _job_key(job_id) == f"cicdex:job:{job_id}")
    """
    return f"cicdex:job:{job_id}"


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """
    워커가 저장한 job 상태/결과 조회.
    """
    key = job_key(job_id)
    if redis_client.exists(key) != 1:
        return None
    data = redis_client.hgetall(key)  # decode_responses=True면 str로 들어옴
    return dict(data)
