import os
from pathlib import Path
from dotenv import load_dotenv

# backend/app/core/config.py 기준:
# .../backend/app/core/config.py
# parents[3] -> .../backend
ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(ENV_PATH)

# ---- DB ----
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "final_project")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

# ---- JWT ----
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME__PLEASE_SET_ENV")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "14"))

# ---- Auth Cookies ----
_cookie_domain = os.getenv("COOKIE_DOMAIN", "").strip()
COOKIE_DOMAIN = _cookie_domain if _cookie_domain else None
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() in ("1", "true", "yes", "y")
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "none").strip().lower()
if COOKIE_SAMESITE not in ("lax", "strict", "none"):
    COOKIE_SAMESITE = "lax"

# ---- Redis ----
REDIS_URL = os.getenv("REDIS_URL", "").strip()
if REDIS_URL:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(REDIS_URL)
        if parsed.scheme in ("redis", "rediss"):
            REDIS_HOST = parsed.hostname or "127.0.0.1"
            REDIS_PORT = parsed.port or 6379
            REDIS_DB = int(parsed.path.lstrip("/") or 0)
        else:
            raise ValueError(f"Unsupported REDIS_URL scheme: {parsed.scheme}")
    except Exception:
        # Fallback to explicit env vars if parsing fails
        REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
        port_raw = os.getenv("REDIS_PORT", "6379")
        if port_raw.startswith("tcp://"):
            port_raw = port_raw.rsplit(":", 1)[-1]
        REDIS_PORT = int(port_raw)
        REDIS_DB = int(os.getenv("REDIS_DB", "0"))
else:
    REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
    port_raw = os.getenv("REDIS_PORT", "6379")
    if port_raw.startswith("tcp://"):
        port_raw = port_raw.rsplit(":", 1)[-1]
    REDIS_PORT = int(port_raw)
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# ---- Project Root ----
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# ---- Storage ----
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")  # local | s3

# 로컬 업로드 루트 (기본: <PROJECT_ROOT>/uploads)
LOCAL_UPLOAD_ROOT = Path(os.getenv("LOCAL_UPLOAD_ROOT", str(PROJECT_ROOT / "uploads"))).resolve()
LOCAL_TMP_ROOT = (LOCAL_UPLOAD_ROOT / "tmp").resolve()
LOCAL_PERM_ROOT = (LOCAL_UPLOAD_ROOT / "perm").resolve()

TMP_TTL_SECONDS = int(os.getenv("TMP_TTL_SECONDS", "1800"))  # 30분
TMP_CLEAN_INTERVAL_SECONDS = int(os.getenv("TMP_CLEAN_INTERVAL_SECONDS", "600"))  # 10분마다

# S3
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_PREFIX_TMP = os.getenv("S3_PREFIX_TMP", "tmp").strip("/")
S3_PREFIX_PERM = os.getenv("S3_PREFIX_PERM", "perm").strip("/")

# gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
