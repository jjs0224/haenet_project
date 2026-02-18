import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

import asyncio
import os
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api_router import api_router
from backend.app.core import config


from backend.app.common.utils.tmp_cleanup import cleanup_receipt_tmp
from backend.app.common.utils.redis_lock import acquire_lock, release_lock

from backend.app.core.cache.redis import redis_client

app = FastAPI()

if config.STORAGE_BACKEND == "local":
    config.LOCAL_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(config.LOCAL_UPLOAD_ROOT)), name="static")


class ForceUTF8Middleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        ct = response.headers.get("content-type", "")
        if ct.startswith("application/json") and "charset=" not in ct:
            response.headers["content-type"] = "application/json; charset=utf-8"
        return response

def _parse_cors_origins():
    raw = os.getenv("CORS_ORIGINS", "")
    return [o.strip() for o in raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://foodray.net",
        "https://www.foodray.net",
        # "http://localhost:5173",
        # "http://127.0.0.1:5173",
    ] + _parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)

app.include_router(api_router)


# clear
async def _tmp_cleanup_loop():
    """
    uploads/tmp/receipt 하위 TTL 지난 폴더 주기 삭제
    - redis lock으로 멀티 워커 중복 실행 방지
    """
    lock_key = "lock:cleanup:receipt_tmp"
    lock_ttl = max(30, config.TMP_CLEAN_INTERVAL_SECONDS - 1)

    while True:
        token = None
        try:
            # token 방식 락
            token = acquire_lock(redis_client, lock_key, lock_ttl)
            if token:
                cleanup_receipt_tmp(config.LOCAL_TMP_ROOT, config.TMP_TTL_SECONDS)
        except Exception:
            pass
        finally:
            if token:
                release_lock(redis_client, lock_key, token)

        await asyncio.sleep(config.TMP_CLEAN_INTERVAL_SECONDS)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_tmp_cleanup_loop())

#수정7