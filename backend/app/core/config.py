import os
from pathlib import Path
from dotenv import load_dotenv

# backend/app/core/config.py 기준:
# .../backend/app/core/config.py
# parents[3] -> .../backend
ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(ENV_PATH)


def _env(name: str, default: str = "") -> str:
    """
    1) env 값을 우선 사용
    2) 없거나 빈 문자열이면 <NAME>_FILE(파일 마운트)에서 읽기
    - ExternalSecrets/CSI/SecretsManager file mount 환경 대응
    """
    v = os.getenv(name)
    if v is not None and str(v).strip() != "":
        return str(v).strip()

    file_path = os.getenv(f"{name}_FILE")
    if file_path:
        try:
            return Path(file_path).read_text(encoding="utf-8").strip()
        except Exception:
            pass

    return default


# ---- DB ----
DB_HOST = _env("DB_HOST")
DB_PORT = (_env("DB_PORT", "3306") or "3306").strip()
DB_NAME = _env("DB_NAME")
DB_USER = _env("DB_USER")
DB_PASSWORD = _env("DB_PASSWORD")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

# ---- JWT ----
JWT_SECRET_KEY = _env("JWT_SECRET_KEY", "CHANGE_ME__PLEASE_SET_ENV")
JWT_ALGORITHM = _env("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(_env("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(_env("REFRESH_TOKEN_EXPIRE_DAYS", "14"))

# ---- Auth Cookies ----
_cookie_domain = _env("COOKIE_DOMAIN", "").strip()
COOKIE_DOMAIN = _cookie_domain if _cookie_domain else None
COOKIE_SECURE = _env("COOKIE_SECURE", "true").strip().lower() in ("1", "true", "yes", "y")
COOKIE_SAMESITE = _env("COOKIE_SAMESITE", "none").strip().lower()
if COOKIE_SAMESITE not in ("lax", "strict", "none"):
    COOKIE_SAMESITE = "lax"

# ---- Redis ----
REDIS_URL = _env("REDIS_URL", "").strip()
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
        REDIS_HOST = _env("REDIS_HOST", "127.0.0.1")
        port_raw = _env("REDIS_PORT", "6379")
        if port_raw.startswith("tcp://"):
            port_raw = port_raw.rsplit(":", 1)[-1]
        REDIS_PORT = int(port_raw)
        REDIS_DB = int(_env("REDIS_DB", "0"))
else:
    REDIS_HOST = _env("REDIS_HOST", "127.0.0.1")
    port_raw = _env("REDIS_PORT", "6379")
    if port_raw.startswith("tcp://"):
        port_raw = port_raw.rsplit(":", 1)[-1]
    REDIS_PORT = int(port_raw)
    REDIS_DB = int(_env("REDIS_DB", "0"))

# ---- Project Root ----
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# ---- Storage ----
STORAGE_BACKEND = _env("STORAGE_BACKEND", "s3")  # local | s3

LOCAL_UPLOAD_ROOT = Path(_env("LOCAL_UPLOAD_ROOT", str(PROJECT_ROOT / "uploads"))).resolve()
LOCAL_TMP_ROOT = (LOCAL_UPLOAD_ROOT / "tmp").resolve()
LOCAL_PERM_ROOT = (LOCAL_UPLOAD_ROOT / "perm").resolve()

TMP_TTL_SECONDS = int(_env("TMP_TTL_SECONDS", "1800"))
TMP_CLEAN_INTERVAL_SECONDS = int(_env("TMP_CLEAN_INTERVAL_SECONDS", "600"))

S3_BUCKET = _env("S3_BUCKET", "")
S3_PREFIX_TMP = _env("S3_PREFIX_TMP", "tmp").strip("/")
S3_PREFIX_PERM = _env("S3_PREFIX_PERM", "perm").strip("/")

GEMINI_API_KEY = _env("GEMINI_API_KEY", "")
NAVER_CLIENT_ID = _env("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = _env("NAVER_CLIENT_SECRET", "")


# import os
# from pathlib import Path
# from dotenv import load_dotenv
#
# # backend/app/core/config.py 기준:
# # .../backend/app/core/config.py
# # parents[3] -> .../backend
# ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
# load_dotenv(ENV_PATH)
#
# # ---- DB ----
# DB_HOST = os.getenv("DB_HOST", "")
# DB_PORT = os.getenv("DB_PORT", "")
# DB_NAME = os.getenv("DB_NAME", "")
# DB_USER = os.getenv("DB_USER", "")
# DB_PASSWORD = os.getenv("DB_PASSWORD", "")
#
# DATABASE_URL = (
#     f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
#     "?charset=utf8mb4"
# )
#
# # ---- JWT ----
# JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME__PLEASE_SET_ENV")
# JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
# ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
# REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "14"))
#
# # ---- Auth Cookies ----
# _cookie_domain = os.getenv("COOKIE_DOMAIN", "").strip()
# COOKIE_DOMAIN = _cookie_domain if _cookie_domain else None
# COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() in ("1", "true", "yes", "y")
# COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "none").strip().lower()
# if COOKIE_SAMESITE not in ("lax", "strict", "none"):
#     COOKIE_SAMESITE = "lax"
#
# # ---- Redis ----
# REDIS_URL = os.getenv("REDIS_URL", "").strip()
# if REDIS_URL:
#     try:
#         from urllib.parse import urlparse
#
#         parsed = urlparse(REDIS_URL)
#         if parsed.scheme in ("redis", "rediss"):
#             REDIS_HOST = parsed.hostname or "127.0.0.1"
#             REDIS_PORT = parsed.port or 6379
#             REDIS_DB = int(parsed.path.lstrip("/") or 0)
#         else:
#             raise ValueError(f"Unsupported REDIS_URL scheme: {parsed.scheme}")
#     except Exception:
#         # Fallback to explicit env vars if parsing fails
#         REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
#         port_raw = os.getenv("REDIS_PORT", "6379")
#         if port_raw.startswith("tcp://"):
#             port_raw = port_raw.rsplit(":", 1)[-1]
#         REDIS_PORT = int(port_raw)
#         REDIS_DB = int(os.getenv("REDIS_DB", "0"))
# else:
#     REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
#     port_raw = os.getenv("REDIS_PORT", "6379")
#     if port_raw.startswith("tcp://"):
#         port_raw = port_raw.rsplit(":", 1)[-1]
#     REDIS_PORT = int(port_raw)
#     REDIS_DB = int(os.getenv("REDIS_DB", "0"))
#
# # ---- Project Root ----
# PROJECT_ROOT = Path(__file__).resolve().parents[3]
#
# # ---- Storage ----
# STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "s3")  # local | s3
#
# # 로컬 업로드 루트 (기본: <PROJECT_ROOT>/uploads)
# LOCAL_UPLOAD_ROOT = Path(os.getenv("LOCAL_UPLOAD_ROOT", str(PROJECT_ROOT / "uploads"))).resolve()
# LOCAL_TMP_ROOT = (LOCAL_UPLOAD_ROOT / "tmp").resolve()
# LOCAL_PERM_ROOT = (LOCAL_UPLOAD_ROOT / "perm").resolve()
#
# TMP_TTL_SECONDS = int(os.getenv("TMP_TTL_SECONDS", "1800"))  # 30분
# TMP_CLEAN_INTERVAL_SECONDS = int(os.getenv("TMP_CLEAN_INTERVAL_SECONDS", "600"))  # 10분마다
#
# # S3
# S3_BUCKET = os.getenv("S3_BUCKET", "")
# S3_PREFIX_TMP = os.getenv("S3_PREFIX_TMP", "tmp").strip("/")
# S3_PREFIX_PERM = os.getenv("S3_PREFIX_PERM", "perm").strip("/")
#
# # gemini
# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
# NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
