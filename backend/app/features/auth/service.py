from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import hashlib

from backend.app.models.member import Member
from backend.app.core.security.password import verify_password
from backend.app.core.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    exp_seconds_left,
)
from backend.app.features.auth import token_store
from backend.app.models.refresh_token import RefreshToken

from backend.app.core.cache.redis import redis_client
from backend.app.common.utils.redis_lock import acquire_lock, release_lock


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _exp_to_dt(exp) -> datetime:
    if isinstance(exp, int):
        return datetime.fromtimestamp(exp, tz=timezone.utc)
    return exp

def _upsert_refresh_db(db: Session, member_id: int, refresh_token: str, refresh_payload: dict) -> None:
    row = db.get(RefreshToken, member_id)
    if not row:
        row = RefreshToken(member_id=member_id)
        db.add(row)

    row.jti = refresh_payload["jti"]
    row.token_hash = _hash(refresh_token)
    row.expires_at = _exp_to_dt(refresh_payload["exp"])
    row.revoked_at = None


def authenticate_member(db: Session, email: str, password: str) -> Member:
    member = db.query(Member).filter(Member.email == email).first()
    if not member or not verify_password(password, member.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return member


def login_issue_tokens(db: Session, email: str, password: str) -> tuple[str, str]:
    member = authenticate_member(db, email, password)

    access = create_access_token(subject=str(member.member_id), role=member.role)
    refresh = create_refresh_token(subject=str(member.member_id))
    refresh_payload = decode_token(refresh)

    # Redis 저장
    token_store.save_refresh_jti(
        member.member_id,
        refresh_payload["jti"],
        exp_seconds_left(refresh_payload),
    )

    # DB 저장
    _upsert_refresh_db(db, member.member_id, refresh, refresh_payload)
    db.commit()

    return access, refresh


def refresh_rotate_tokens(db: Session, refresh_token: str) -> tuple[str, str]:
    # 1) refresh token 자체 검증
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("not refresh token")
        member_id = int(payload["sub"])
        refresh_jti = payload["jti"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # 2) 동시 refresh 방지: member 단위 락
    lock_key = f"lock:auth:refresh:{member_id}"
    lock_token = acquire_lock(redis_client, lock_key, ttl_seconds=10)
    if not lock_token:
        raise HTTPException(status_code=429, detail="Too many refresh requests (try again)")

    try:
        # 3) redis jti 비교
        saved_jti = token_store.get_refresh_jti(member_id)
        if not saved_jti or saved_jti != refresh_jti:
            token_store.delete_refresh(member_id)
            raise HTTPException(status_code=401, detail="Refresh token revoked")

        # 4) DB hash/jti 비교
        row = db.get(RefreshToken, member_id)
        if (not row) or (row.revoked_at is not None):
            raise HTTPException(status_code=401, detail="Refresh token revoked")

        if row.jti != refresh_jti or row.token_hash != _hash(refresh_token):
            row.revoked_at = datetime.now(timezone.utc)
            db.commit()
            token_store.delete_refresh(member_id)
            raise HTTPException(status_code=401, detail="Refresh token reused")

        # 5) 새 토큰 발급
        member = db.get(Member, member_id)
        if not member:
            raise HTTPException(status_code=401, detail="Member not found")

        new_access = create_access_token(subject=str(member_id), role=member.role)
        new_refresh = create_refresh_token(subject=str(member_id))
        new_refresh_payload = decode_token(new_refresh)

        # 6) rotate 저장
        token_store.save_refresh_jti(
            member_id,
            new_refresh_payload["jti"],
            exp_seconds_left(new_refresh_payload),
        )
        _upsert_refresh_db(db, member_id, new_refresh, new_refresh_payload)
        db.commit()

        return new_access, new_refresh

    finally:
        release_lock(redis_client, lock_key, lock_token)


def logout(db: Session, access_token: str) -> None:
    """
    logout도 refresh와 같은 member 락을 잡아두면
    - refresh 도중 logout
    - logout 도중 refresh
    의 경쟁조건이 줄어듦
    """
    try:
        payload = decode_token(access_token)
        if payload.get("type") != "access":
            raise ValueError("not access token")
        jti = payload["jti"]
        member_id = int(payload["sub"])
        ttl = exp_seconds_left(payload)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid access token")

    lock_key = f"lock:auth:refresh:{member_id}"
    lock_token = acquire_lock(redis_client, lock_key, ttl_seconds=10)
    if not lock_token:
        # logout은 강제성 높으니까 409로 안내(재시도 유도)
        raise HTTPException(status_code=409, detail="Logout in progress (try again)")

    try:
        # redis: access blacklist
        token_store.add_to_blacklist(jti, ttl)

        # redis: refresh 제거
        token_store.delete_refresh(member_id)

        # db: refresh revoke
        row = db.get(RefreshToken, member_id)
        if row and row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            db.commit()

    finally:
        release_lock(redis_client, lock_key, lock_token)
