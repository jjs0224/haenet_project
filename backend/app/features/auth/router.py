from fastapi import APIRouter, Depends, Response, Cookie, HTTPException
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security.deps import get_current_member, oauth2_scheme
from backend.app.features.auth import service, schemas

from backend.app.core.security import jwt

router = APIRouter(prefix="/auth", tags=["auth"])

# front 확인 할 Cookie
COOKIE_NAME = "refresh_token"

@router.post("/login", response_model=schemas.AccessTokenResponse)
def login(
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    access, refresh = service.login_issue_tokens(db, email=form.username, password=form.password)

    decode_refresh = jwt.decode_token(refresh)
    ttl = jwt.exp_seconds_left(decode_refresh)

    response.set_cookie(
        key=COOKIE_NAME,
        value=refresh,
        httponly=True,
        secure=False,   # https 배포면 True
        samesite="lax",
        path="/",
        max_age=ttl,
    )
    return {"access_token": access, "token_type": "bearer"}


@router.post("/refresh", response_model=schemas.AccessTokenResponse)
def refresh(
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh cookie")

    new_access, new_refresh = service.refresh_rotate_tokens(db, refresh_token)

    new_refresh_payload = jwt.decode_token(new_refresh)
    ttl = jwt.exp_seconds_left(new_refresh_payload)

    response.set_cookie(
        key=COOKIE_NAME,
        value=new_refresh,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
        max_age=ttl,
    )
    return {"access_token": new_access, "token_type": "bearer"}


@router.post("/logout")
def logout(
    response: Response,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    service.logout(db, token)

    # refresh cookie 삭제
    response.delete_cookie(key=COOKIE_NAME, path="/")
    response.delete_cookie(key=COOKIE_NAME, path="/auth")
    return {"ok": True}


@router.get("/me")
def me(current=Depends(get_current_member)):
    return {
        "member_id": current.member_id,
        "email": current.email,
        "nickname": current.nickname,
    }