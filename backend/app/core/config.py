import os
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

def getenv_secret(name: str, default: str = "") -> str:
    """
    AWS/ECS/도커 secrets 지원: NAME 또는 NAME_FILE
    - NAME이 있으면 그 값 사용
    - 없으면 NAME_FILE이 가리키는 파일 내용을 읽어서 사용
    """
    v = os.getenv(name)
    if v is not None and str(v).strip() != "":
        return v

    fp = os.getenv(f"{name}_FILE")
    if fp:
        try:
            return Path(fp).read_text(encoding="utf-8").strip()
        except Exception:
            return default

    return default


# ---- DB ----
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "final_project")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = getenv_secret("DB_PASSWORD", "")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

# ---- JWT ----
JWT_SECRET_KEY = getenv_secret("JWT_SECRET_KEY", "CHANGE_ME__PLEASE_SET_ENV")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "14"))

# ---- Cookies ----
_cookie_domain = os.getenv("COOKIE_DOMAIN", "").strip()
COOKIE_DOMAIN = _cookie_domain if _cookie_domain else None
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() in ("1", "true", "yes", "y")
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "none").strip().lower()
if COOKIE_SAMESITE not in ("lax", "strict", "none"):
    COOKIE_SAMESITE = "lax"

# ---- External APIs ----
GEMINI_API_KEY = getenv_secret("GEMINI_API_KEY", "")

# NAVER 통일
NAVER_CLIENT_ID = getenv_secret("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = getenv_secret("NAVER_CLIENT_SECRET", "")
