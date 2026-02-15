import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from sqlalchemy import select, update

from backend.app.core import config
from backend.app.common.utils.debug import log_exception
from backend.app.common.utils.util import ensure_list, dumps_json, parse_ids

# s3
from backend.app.common.utils.util import resolve_asset_urls

def parse_menu_name(menu_name_raw: Optional[str]) -> List[str]:
    """
    menu_name 문자열을 파싱하여 리스트로 반환
    - None/빈 문자열 -> []
    - JSON 배열 문자열 -> 파싱된 리스트
    - 일반 문자열 -> [문자열]
    """
    if not menu_name_raw:
        return []

    menu_name_raw = menu_name_raw.strip()

    # JSON 배열 문자열인 경우
    if menu_name_raw.startswith('[') and menu_name_raw.endswith(']'):
        try:
            parsed = json.loads(menu_name_raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if item]
        except (json.JSONDecodeError, ValueError):
            pass

    # 쉼표로 구분된 문자열
    if ',' in menu_name_raw:
        return [item.strip() for item in menu_name_raw.split(',') if item.strip()]

    # 단일 문자열
    return [menu_name_raw]
from backend.app.common.service.file_upload_service import (
    build_temp_prefix,
    ensure_local_path,
    upload_input_file,
    save_permanent_asset,
)

from backend.app.common.service.receipt_session_service import ReceiptSessionService
from backend.app.features.review.schemas import ReviewContentUpdate
from backend.app.models.img_file import ImgFile
from backend.app.models.review import Review
from backend.app.models.restrictions.item import Item
from backend.app.models.restrictions.category import Category
from backend.app.models.restrictions import MemberRestrictions
from backend.app.models.member import Member

def run_receipt_ai_step5(*, image_path: str, receipt_id: str, base_dir: Path) -> Dict[str, Any]:
    """
     Receipt: step5까지 전부 수행 (OCR 포함)
     결과물(run_dir, final json 등)은 base_dir 아래로 떨어지게 설정
    """
    from AI.review.app.pipeline.orchestrator import PipelineConfig, run_pipeline

    print("ai 진입(receipt full pipeline)")

    # base_dir 예: <PROJECT_ROOT>/uploads/tmp/receipt/<receipt_id>/runs_root
    base_dir.mkdir(parents=True, exist_ok=True)

    cfg = PipelineConfig(
        mode="prod",
        test_base_dir=base_dir,
        run_name=receipt_id,
        gemini_api_key=config.GEMINI_API_KEY,
        naver_cfg={
            "NAVER_CLIENT_ID": config.NAVER_CLIENT_ID,
            "NAVER_CLIENT_SECRET": config.NAVER_CLIENT_SECRET,
        },
    )

    return run_pipeline(input_image_path=image_path, cfg=cfg)


async def verify_receipt(*, member_id: int, file: UploadFile, receipt_id: str) -> Dict[str, Any]:
    """
     verify 단계에서 step5까지 수행
     최상위 uploads/tmp 밑에 결과(run_dir, json) 유지
    """
    # 업로드 temp prefix (폴더)
    tmp_prefix = build_temp_prefix(upload_type="receipt", scope_id=receipt_id)
    # run 결과를 tmp_prefix 안에 넣는다 (프론트가 이후 읽을 수 있도록)
    runs_root = Path(tmp_prefix) / "runs"

    print("검증 service 입장 :: tmp_prefix =", tmp_prefix)

    # 1) input 저장
    try:
        obj = await upload_input_file(
            upload_type="receipt",
            member_id=member_id,
            upload=file,
            scope_id=receipt_id,
            is_temp=True,
        )
    except Exception as e:
        log_exception("receipt.upload_reject", e)
        raise HTTPException(status_code=400, detail=str(e))

    print("obj :: ", obj)

    # 2) 로컬 경로 확보
    local_path, cleanup = ensure_local_path(obj)

    try:
        # 3) AI step5까지 수행
        ai_out = run_receipt_ai_step5(image_path=local_path, receipt_id=receipt_id, base_dir=runs_root)

        # 4) 프론트 재사용을 위해 redis/session에 “최종 결과”도 저장 가능
        # run_pipeline 리턴 형식이 {"run_dir": "...", "final": ...} 이니까 final을 저장
        final_payload = ai_out.get("final") or {}
        ReceiptSessionService.put(receipt_id=receipt_id, member_id=member_id, payload=final_payload)

        #  그리고 temp 폴더에도 최종 파일을 하나 더 “고정 파일명”으로 만들어두면 프론트가 접근 편함
        try:
            out_path = Path(tmp_prefix) / "receipt_final.json"
            out_path.write_text(json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        return {
            "receipt_id": receipt_id,
            "final": final_payload,
            "tmp_prefix": tmp_prefix,   # 디버그용(원하면 프론트엔 숨겨)
        }

    except Exception as e:
        log_exception("receipt.ai_failed", e)
        raise HTTPException(status_code=500, detail=f"receipt ai failed: {type(e).__name__}: {e}")

    finally:
        cleanup()
        #  정책: receipt는 결과를 temp에 담아둘 것이므로 prefix 삭제하지 않는다.
        # delete_prefix(prefix_key=tmp_prefix)  # 하면 안됨`


async def create_review_from_receipt(
    *,
    db: Session,
    member_id: int,
    receipt_id: str,
    title: str,
    content: str,
    rating: int,
    menu_name_override: Optional[str] = None,
    images: List[UploadFile],
) -> Dict[str, Any]:
    session = ReceiptSessionService.get(receipt_id=receipt_id)
    if not session:
        raise HTTPException(status_code=400, detail="receipt expired (verify again)")
    if int(session.get("member_id") or 0) != int(member_id):
        raise HTTPException(status_code=403, detail="forbidden")

    # 동시 생성 방지 락
    lock_token = ReceiptSessionService.acquire_create_lock(receipt_id=receipt_id)
    if not lock_token:
        raise HTTPException(status_code=409, detail="receipt is being processed (try again)")

    try:
        # 락 잡은 뒤 다시 확인(중간에 만료/삭제 가능)
        session = ReceiptSessionService.get(receipt_id=receipt_id)
        if not session:
            raise HTTPException(status_code=400, detail="receipt expired (verify again)")
        if int(session.get("member_id") or 0) != int(member_id):
            raise HTTPException(status_code=403, detail="forbidden")

        final_payload = session.get("payload") or {}

        coords = final_payload.get("coords") or {}
        x = coords.get("x")
        y = coords.get("y")
        location_list = [x, y] if (x is not None and y is not None) else []

        # 프론트에서 삭제한 메뉴가 반영된 menu_name_override 우선 사용
        if menu_name_override:
            try:
                parsed = json.loads(menu_name_override)
                menu_en_list = parsed if isinstance(parsed, list) else [parsed]
            except (ValueError, TypeError):
                menu_en_list = ensure_list(menu_name_override)
        else:
            raw = final_payload.get("menu_name")
            menu_en_list = ensure_list(raw) if raw else []

        member_item_ids = db.execute(
            select(MemberRestrictions.item_id)
            .join(Item, Item.item_id == MemberRestrictions.item_id)
            .join(Category, Category.category_id == Item.category_id)
            .where(MemberRestrictions.member_id == member_id)
            .where(Item.item_active == 1)
            .where(Category.category_active == 1)
        ).scalars().all()

        if rating < 1 or rating > 5:
            raise HTTPException(status_code=400, detail="rating must be 1~5")
        if len(images) > 3:
            raise HTTPException(status_code=400, detail="images max 3")

        review = Review(
            review_title=title,
            review_content=content,
            rating=rating,
            location=dumps_json(location_list),
            menu_name=dumps_json(menu_en_list),
            member_id=member_id,
            available=True,
            review_items=dumps_json(member_item_ids),
        )
        db.add(review)
        db.flush()

        image_urls: List[str] = []

        for idx, img in enumerate(images):
            stored = await save_permanent_asset(
                owner_type="review",
                owner_id=review.review_id,
                member_id=member_id,
                upload=img,
                sort_order=idx,
            )

            db.add(
                ImgFile(
                    origin_name=stored.org_file_name,
                    storage_key=stored.stored_file_name,
                    storage_path=stored.storage_path,
                    mime_type=stored.mime_type,
                    file_size=stored.size_bytes,
                    sort_order=idx,
                    owner_type="review",
                    member_id=member_id,
                    review_id=review.review_id,
                    community_id=None,
                )
            )
            image_urls.append(stored.storage_path)

        db.commit()

        # 성공한 경우에만 세션 삭제
        ReceiptSessionService.delete(receipt_id=receipt_id)
        
        # s3 변경
        return {"review_id": review.review_id, "image_urls": resolve_asset_urls(image_urls)}

    finally:
        ReceiptSessionService.release_create_lock(receipt_id=receipt_id, token=lock_token)


# 전체 조회 / 본인 리스트 조회 한번에 처리
# def list_reviews(db: Session, *, member_id: Optional[int] = None, active_only: bool = True,) -> List[Dict[str, Any]]:
def list_reviews(db: Session, *, member_id: Optional[int] = None) -> List[
        Dict[str, Any]]:
    stmt = (
        select(Review, Member.nickname)
        .join(Member, Member.member_id == Review.member_id)
    )

    # member_id
    if member_id is not None:
        stmt = stmt.where(Review.member_id == member_id)

    # active
    # if active_only:
    #     stmt = stmt.where(Review.available == True)

    # 최신순
    reviews = db.execute(
        stmt.order_by(Review.review_id.desc())
    ).all()

    if not reviews:
        return []

    # 이미지: review_id 기준으로 묶기
    imgs = db.execute(
        select(ImgFile)
        .where(ImgFile.owner_type == "review")
        .order_by(ImgFile.review_id.asc(), ImgFile.sort_order.asc())
    ).scalars().all()

    img_map: Dict[int, List[str]] = {}
    for img in imgs:
        img_map.setdefault(img.review_id, []).append(img.storage_path)

    out: List[Dict[str, Any]] = []
    for r, nickname in reviews:
        print("r :: ", r.review_items)

        out.append({
            "review_id": r.review_id,
            "member_id": r.member_id,
            "nickname": nickname,
            "review_title": r.review_title,
            "review_content": r.review_content,
            "rating": r.rating,
            "location": r.location,
            "available": r.available,
            "menu_name": parse_menu_name(r.menu_name),
            "review_items": parse_ids(r.review_items),
            # 프론트가 created_at/updated_at 키를 기대해서 맞춰줌
            "created_at": r.create_at.isoformat() if getattr(r, "create_at", None) else None,
            "updated_at": r.update_at.isoformat() if getattr(r, "update_at", None) else None,
            "image_urls": resolve_asset_urls(img_map.get(r.review_id, [])), # s3 변경
            # "image_urls": img_map.get(r.review_id, []),
        })

    print("out :: ", out)

    return out


def get_review_detail(db: Session, review_id: int) -> Dict[str, Any]:

    row = db.execute(
        select(Review, Member.nickname)
        .join(Member, Member.member_id == Review.member_id)
        .where(Review.review_id == int(review_id))
    ).first()

    if not row:
        raise HTTPException(status_code=404, detail="Review not found")

    r, nickname = row

    imgs = db.execute(
        select(ImgFile)
        .where(ImgFile.review_id == review_id)
        .where(ImgFile.owner_type == "review")
        .order_by(ImgFile.sort_order.asc())
    ).scalars().all()


    return {
        "review_id": r.review_id,
        "member_id": r.member_id,
        "review_title": r.review_title,
        "review_content": r.review_content,
        "nickname": nickname,
        "rating": r.rating,
        "location": r.location,
        "available": r.available,
        "menu_name": parse_menu_name(r.menu_name),
        "review_items": parse_ids(r.review_items),
        "created_at": r.create_at.isoformat() if getattr(r, "create_at", None) else None,
        "updated_at": r.update_at.isoformat() if getattr(r, "update_at", None) else None,
        "image_urls": resolve_asset_urls([img.storage_path for img in imgs]), # s3 변경
        # "image_urls": [img.storage_path for img in imgs],
    }


def update_review_content_only(
    db: Session,
    *,
    review_id: int,
    current_member_id: int,
    current_role: str | None,
    new_content: str,
) -> Dict[str, Any]:
    r = db.get(Review, review_id)
    print("수정 review :: ", r.available)


    if not r:
        raise HTTPException(status_code=404, detail="Review not found")

    # available == 0 이면 수정 불가
    if int(getattr(r, "available", 0)) != 1:
        raise HTTPException(
            status_code=409,
            detail="이미 커뮤니티 생성에 사용된 리뷰이므로 변경할 수 없습니다."
        )

    #  본인만 수정 (ADMIN 예외 허용)
    is_admin = (current_role or "").upper() == "ADMIN"
    if (r.member_id != current_member_id) and (not is_admin):
        raise HTTPException(status_code=403, detail="Not allowed")

    r.review_content = new_content
    db.add(r)
    db.commit()
    db.refresh(r)

    return {
        "review_id": r.review_id,
        "review_content": r.review_content,
        "updated_at": r.update_at.isoformat() if getattr(r, "update_at", None) else None,
    }

# community review 조회
def list_reviews_by_ids(
    db: Session,
    review_ids: List[int],
    *,
    member_id: Optional[int] = None,          # 내 리뷰만 허용하려면 넣기
    # include_inactive: bool = True,            # available(False)도 포함할지
) -> List[Dict[str, Any]]:
    """
    review_ids([4,2,1])로 리뷰를 한번에 조회해서
    이미지까지 포함한 dict 리스트로 반환한다.
    - IN 조회 1번 + 이미지 조회 1번 (총 2번 쿼리)
    - review_ids의 원래 순서([4,2,1]) 유지
    """

    if not review_ids:
        return []

    # 1) Review 한번에 조회
    q = select(Review).where(Review.review_id.in_(review_ids))

    if member_id is not None:
        q = q.where(Review.member_id == member_id)

    # if not include_inactive:
    #     q = q.where(Review.available == True)

    reviews = db.execute(q).scalars().all()

    if not reviews:
        return []

    # 2) 이미지도 한번에 조회 (review_id IN)
    imgs = db.execute(
        select(ImgFile)
        .where(ImgFile.owner_type == "review")
        .where(ImgFile.review_id.in_(review_ids))
        .order_by(ImgFile.review_id.asc(), ImgFile.sort_order.asc())
    ).scalars().all()

    img_map: Dict[int, List[str]] = {}
    for img in imgs:
        img_map.setdefault(img.review_id, []).append(img.storage_path)

    # 3) 응답 dict 생성 (기존 list_reviews 형식과 최대한 동일하게)
    by_id: Dict[int, Dict[str, Any]] = {}

    for r in reviews:
        by_id[r.review_id] = {
            "review_id": r.review_id,
            "member_id": r.member_id,
            "review_title": r.review_title,
            "review_content": r.review_content,
            "rating": r.rating,
            "location": r.location,
            "available": r.available,
            "menu_name": parse_menu_name(r.menu_name),
            "review_items": parse_ids(r.review_items),
            "created_at": r.create_at.isoformat() if getattr(r, "create_at", None) else None,
            "updated_at": r.update_at.isoformat() if getattr(r, "update_at", None) else None,
            "image_urls": resolve_asset_urls(img_map.get(r.review_id, [])), # s3 변경
            # "image_urls": img_map.get(r.review_id, []),
        }

    # 4) 요청한 review_ids 순서대로 정렬해서 반환
    return [by_id[i] for i in review_ids if i in by_id]


def availavble_review(db: Session, review_ids: List[int]):

    print("available :: ", review_ids)

    ids = [int(x) for x in (review_ids or [])]
    # 중복 제거(순서 유지)
    ids = list(dict.fromkeys(ids))

    if not ids:
        return True

    try:
        # available 컬럼 타입에 맞게 둘 중 하나만 사용
        # 1) bool 컬럼이면:
        # res = db.execute(
        #     update(Review)
        #     .where(Review.review_id.in_(ids))
        #     .values(available=False)
        # )

        # 테스트 진행 후 int 넘길 예정이면 사용
        # 2) int(0/1) 컬럼이면:
        res = db.execute(
            update(Review)
            .where(Review.review_id.in_(ids))
            .values(available=0)
        )

        # ids 개수와 업데이트 rowcount가 다르면 누락된 id가 있거나 조건이 안 맞는 상황
        if res.rowcount is not None and res.rowcount != len(ids):
            return False

        return True

    except Exception:
        # rollback은 라우터에서 통합 처리
        return False
