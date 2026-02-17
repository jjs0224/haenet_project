from sqlalchemy.orm import Session
from sqlalchemy import select, delete, update, func
from fastapi import HTTPException
from typing import Any, Dict, Optional, List

from backend.app.models.community import Community
from backend.app.models.img_file import ImgFile
from backend.app.models.comment import Comment
from backend.app.models.member import Member
from backend.app.models.community_recommend import CommunityRecommend

from backend.app.features.review.service import list_reviews_by_ids
from backend.app.features.member.service import get_member
from backend.app.common.service.ai_member_info import build_user_profile_payload

from backend.app.common.service.file_upload_service import save_permanent_bytes, delete_prefix, build_perm_prefix

# private S3이면 storage_path -> presigned url 변환
from backend.app.common.utils.util import resolve_asset_urls


# ---------------------------------------------------------------------
# 등록 Step1 (API에서 실행: 검증 + payload 구성)
# ---------------------------------------------------------------------
def create_step1(db: Session, payload, member_id: int) -> Dict[str, Any]:
    template_id = int(payload.template_id)

    if template_id not in (1, 2):
        raise HTTPException(status_code=422, detail="template_id must be 1 or 2")

    review_ids = list(payload.review_ids or [])
    review_ids = [int(x) for x in review_ids if str(x).strip().isdigit()]

    if template_id == 1:
        if len(review_ids) != 3:
            raise HTTPException(status_code=422, detail="temp1 requires exactly 3 review_ids")
    else:
        if len(review_ids) < 3:
            raise HTTPException(status_code=422, detail="temp2 requires 3+ review_ids")

    reviews = list_reviews_by_ids(db, review_ids, member_id=member_id)

    if len(reviews) != len(set(review_ids)):
        raise HTTPException(status_code=403, detail="invalid review_ids (not found or not owned)")

    if template_id == 1:
        def is_active(r):
            v = r.get("available")
            return v is True or v == 1 or v == "1"
        if any(not is_active(r) for r in reviews):
            raise HTTPException(status_code=422, detail="temp1 allows ACTIVE reviews only")

    member_data = get_member(db, member_id)
    category_items = build_user_profile_payload(db, member_id)

    return {
        "member_id": member_id,
        "template_id": template_id,
        "reviews": reviews,
        "member": member_data,
        "allergy_tags": category_items,
    }


# ---------------------------------------------------------------------
# (추가) Worker가 호출할 Step2 Persist
# - AI가 생성한 image_bytes를 받아서 DB + S3 + ImgFile 저장까지 수행
# - commit/rollback은 "호출자(worker)"가 한다 (리뷰 available 처리까지 한 트랜잭션으로)
# ---------------------------------------------------------------------
async def persist_step2_from_image_bytes(db: Session, total_data: Dict[str, Any], image_bytes: bytes) -> Dict[str, Any]:
    # nickname
    nickname = (total_data.get("member") or {}).get("nickname") or ""

    template_id = int(total_data.get("template_id") or 0)
    community_type = "journal" if template_id == 1 else ("map" if template_id == 2 else None)

    # 1) community upsert (map이면 기존 row 재사용)
    community = None
    if community_type == "map":
        community = db.execute(
            select(Community)
            .where(Community.member_id == int(total_data["member_id"]))
            .where(Community.community_type == "map")
            .order_by(Community.community_id.desc())
        ).scalar_one_or_none()

    if community is None:
        community = Community(
            member_id=int(total_data["member_id"]),
            community_active=True,
            recommend=0,
            community_type=community_type,
        )
        db.add(community)
        db.flush()
    else:
        if community.community_type != community_type:
            community.community_type = community_type
        community.update_at = func.now()
        db.flush()

    community_id = community.community_id

    # 2) 기존 이미지 제거 후 새 이미지 저장
    stored = None
    perm_prefix = build_perm_prefix(owner_type="community", owner_id=community_id)

    try:
        try:
            delete_prefix(prefix_key=perm_prefix)
        except Exception:
            pass

        db.execute(
            delete(ImgFile)
            .where(ImgFile.owner_type == "community")
            .where(ImgFile.community_id == community_id)
        )
        db.flush()

        stored = await save_permanent_bytes(
            owner_type="community",
            owner_id=community_id,
            member_id=int(total_data["member_id"]),
            data=image_bytes,
            origin_name="community.png",
            mime_type="image/png",
            sort_order=0,
        )

        img = ImgFile(
            origin_name=stored.org_file_name,
            storage_key=stored.stored_file_name,
            storage_path=stored.storage_path,
            mime_type=stored.mime_type,
            file_size=stored.size_bytes,
            sort_order=stored.sort_order,
            owner_type="community",
            member_id=int(total_data["member_id"]),
            community_id=community_id,
            review_id=None,
        )
        db.add(img)
        db.flush()
        db.refresh(community)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Community image persist failed: {type(e).__name__}: {e}")

    return {
        "community_id": community_id,
        "member_id": community.member_id,
        "nickname": nickname,
        "community_active": bool(community.community_active),
        "recommend": int(community.recommend or 0),
        # presigned 변환해서 반환 (private S3 대응)
        "image_urls": resolve_asset_urls([stored.storage_path] if stored else []),
        "template_id": total_data.get("template_id"),
        "reviews": total_data.get("reviews", []),
        "community_type": community.community_type,
    }


# ---------------------------------------------------------------------
# list / detail (presigned 적용)
# ---------------------------------------------------------------------
def list_community(
    db: Session,
    *,
    member_id: Optional[int] = None,
    active_only: Optional[bool] = True,
) -> List[Dict[str, Any]]:

    latest_comment_text_sq = (
        select(Comment.content)
        .where(Comment.community_id == Community.community_id)
        .order_by(Comment.comment_id.desc())
        .limit(1)
        .scalar_subquery()
    )

    stmt = (
        select(Community, Member.nickname, latest_comment_text_sq)
        .join(Member, Member.member_id == Community.member_id)
    )

    if member_id is not None:
        stmt = stmt.where(Community.member_id == member_id)

    if active_only is True:
        stmt = stmt.where(Community.community_active.is_(True))
    elif active_only is False:
        stmt = stmt.where(Community.community_active.is_(False))

    rows = db.execute(stmt.order_by(Community.community_id.desc())).all()
    if not rows:
        return []

    community_ids = [row[0].community_id for row in rows]

    imgs = db.execute(
        select(ImgFile)
        .where(ImgFile.owner_type == "community")
        .where(ImgFile.community_id.in_(community_ids))
        .order_by(ImgFile.community_id.asc(), ImgFile.sort_order.asc())
    ).scalars().all()

    img_map: Dict[int, List[str]] = {}
    for img in imgs:
        img_map.setdefault(img.community_id, []).append(img.storage_path)

    out: List[Dict[str, Any]] = []
    for c, nickname, latest_comment_text in rows:
        out.append({
            "community_id": c.community_id,
            "member_id": c.member_id,
            "nickname": nickname,
            "community_active": bool(c.community_active),
            "recommend": int(c.recommend or 0),
            "created_at": c.create_at.isoformat() if getattr(c, "create_at", None) else None,
            "updated_at": c.update_at.isoformat() if getattr(c, "update_at", None) else None,
            "image_urls": resolve_asset_urls(img_map.get(c.community_id, [])),
            "latest_comment_text": latest_comment_text,
            "community_type": c.community_type,
        })
    return out


def get_community_detail(db: Session, community_id: int, *, member_id: Optional[int] = None) -> Dict[str, Any]:
    latest_comment_text_sq = (
        select(Comment.content)
        .where(Comment.community_id == Community.community_id)
        .order_by(Comment.comment_id.desc())
        .limit(1)
        .scalar_subquery()
    )

    row = db.execute(
        select(Community, Member.nickname, latest_comment_text_sq)
        .join(Member, Member.member_id == Community.member_id)
        .where(Community.community_id == int(community_id))
    ).first()

    if not row:
        raise HTTPException(status_code=404, detail="Community not found")

    c, nickname, latest_comment_text = row

    imgs = db.execute(
        select(ImgFile)
        .where(ImgFile.community_id == community_id)
        .where(ImgFile.owner_type == "community")
        .order_by(ImgFile.sort_order.asc())
    ).scalars().all()

    liked = False
    if member_id is not None:
        liked_row = db.execute(
            select(CommunityRecommend.recommend_id).where(
                CommunityRecommend.community_id == int(community_id),
                CommunityRecommend.member_id == int(member_id),
            )
        ).scalar_one_or_none()
        liked = liked_row is not None

    return {
        "community_id": c.community_id,
        "member_id": c.member_id,
        "nickname": nickname,
        "community_active": bool(c.community_active),
        "recommend": int(c.recommend or 0),
        "liked": liked,
        "created_at": c.create_at.isoformat() if getattr(c, "create_at", None) else None,
        "updated_at": c.update_at.isoformat() if getattr(c, "update_at", None) else None,
        "image_urls": resolve_asset_urls([img.storage_path for img in imgs]),
        "latest_comment_text": latest_comment_text,
    }


def toggle_recommend(db: Session, *, community_id: int, member_id: int) -> Dict[str, Any]:
    c = db.get(Community, int(community_id))
    if not c:
        raise HTTPException(status_code=404, detail="Community not found")

    exists = db.execute(
        select(CommunityRecommend.recommend_id).where(
            CommunityRecommend.community_id == int(community_id),
            CommunityRecommend.member_id == int(member_id),
        )
    ).scalar_one_or_none()

    original_update_at = c.update_at

    if exists is None:
        db.add(CommunityRecommend(community_id=int(community_id), member_id=int(member_id)))
        db.flush()
        db.execute(
            update(Community)
            .where(Community.community_id == int(community_id))
            .values(recommend=Community.recommend + 1, update_at=original_update_at)
        )
        db.flush()
        db.refresh(c)
        return {"recommended": True, "recommend": int(c.recommend or 0)}
    else:
        db.execute(
            delete(CommunityRecommend).where(
                CommunityRecommend.community_id == int(community_id),
                CommunityRecommend.member_id == int(member_id),
            )
        )
        db.execute(
            update(Community)
            .where(Community.community_id == int(community_id), Community.recommend > 0)
            .values(recommend=Community.recommend - 1, update_at=original_update_at)
        )
        db.flush()
        db.refresh(c)
        return {"recommended": False, "recommend": int(c.recommend or 0)}


def toggle_active(db: Session, *, community_id: int, member_id: int) -> Dict[str, Any]:
    c = db.get(Community, int(community_id))
    if not c:
        raise HTTPException(status_code=404, detail="Community not found")

    if c.member_id != int(member_id):
        raise HTTPException(status_code=403, detail="본인 게시글만 변경할 수 있습니다")

    original_update_at = c.update_at

    new_active = not c.community_active
    db.execute(
        update(Community)
        .where(Community.community_id == int(community_id))
        .values(community_active=new_active, update_at=original_update_at)
    )
    db.flush()
    db.refresh(c)

    return {"community_id": c.community_id, "community_active": bool(c.community_active)}

# 0217 jk 추가
def create_pending_community(db: Session, total_data: Dict[str, Any]) -> Dict[str, Any]:
    template_id = int(total_data.get("template_id") or 0)
    community_type = "journal" if template_id == 1 else ("map" if template_id == 2 else None)

    community: Optional[Community] = None
    if community_type == "map":
        community = db.execute(
            select(Community)
            .where(Community.member_id == int(total_data["member_id"]))
            .where(Community.community_type == "map")
            .order_by(Community.community_id.desc())
        ).scalar_one_or_none()

    if community is None:
        community = Community(
            member_id=int(total_data["member_id"]),
            community_active=True,
            recommend=0,
            community_type=community_type,
        )
        db.add(community)
        db.flush()
    else:
        if community.community_type != community_type:
            community.community_type = community_type
        community.update_at = func.now()
        db.flush()

    return {
        "community_id": community.community_id,
        "community_type": community.community_type,
    }

# 0217 jk 추가
def finalize_from_worker_result(
    db: Session,
    *,
    total_data: Dict[str, Any],
    community_id: int,
    stored: Dict[str, Any],
    template_id: int,
    review_ids: List[int],
) -> Dict[str, Any]:
    nickname = (total_data.get("member") or {}).get("nickname") or ""

    community = db.execute(
        select(Community).where(Community.community_id == int(community_id))
    ).scalar_one_or_none()
    if community is None:
        raise HTTPException(status_code=404, detail="community not found")

    # community는 이미지 1장 유니크라서 기존 레코드 정리 필요
    db.execute(
        delete(ImgFile)
        .where(ImgFile.owner_type == "community")
        .where(ImgFile.community_id == int(community_id))
    )
    db.flush()

    img = ImgFile(
        origin_name=str(stored.get("org_file_name") or stored.get("origin_name") or "community.png"),
        storage_key=str(stored.get("stored_file_name") or stored.get("storage_key") or ""),
        storage_path=str(stored.get("storage_path") or ""),
        mime_type=str(stored.get("mime_type") or "image/png"),
        file_size=int(stored.get("size_bytes") or stored.get("file_size") or 0),
        sort_order=int(stored.get("sort_order") or 0),
        owner_type="community",
        member_id=int(total_data["member_id"]),
        community_id=int(community_id),
        review_id=None,
    )
    db.add(img)

    if int(template_id) == 1:
        from backend.app.features.review.service import availavble_review
        ok = availavble_review(db, review_ids)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to update review availability")

    db.flush()
    db.refresh(community)

    return {
        "community_id": int(community_id),
        "member_id": community.member_id,
        "nickname": nickname,
        "community_active": bool(community.community_active),
        "recommend": int(community.recommend or 0),
        "image_urls": resolve_asset_urls([str(stored.get("storage_path") or "")]),
        "template_id": int(template_id),
        "reviews": total_data.get("reviews", []),
        "community_type": community.community_type,
        "storage_path": str(stored.get("storage_path") or ""),
    }



# from sqlalchemy.orm import Session
# from sqlalchemy import select, delete, update, func
# from fastapi import HTTPException
# from typing import Any, Dict, Optional, List
#
# from starlette.concurrency import run_in_threadpool
#
# from backend.app.models.community import Community
# # from backend.app.models.community_like import CommunityLike
# from backend.app.models.img_file import ImgFile
# from backend.app.models.comment import Comment  # 댓글
#
# # review 로직
# from backend.app.features.review.service import list_reviews_by_ids
#
# # member 로직
# from backend.app.features.member.service import get_member
# from backend.app.models.member import Member
# # category, item 조회
# from backend.app.common.service.ai_member_info import build_user_profile_payload
#
# # community_recommend
# from backend.app.models.community_recommend import CommunityRecommend
#
# # file upload helpers
# from backend.app.common.service.file_upload_service import save_permanent_bytes, delete_prefix, build_perm_prefix
#
# # s3
# from backend.app.common.utils.util import resolve_asset_urls
#
# # ---------------------------------------------------------------------
# # 등록 Step1
# # ---------------------------------------------------------------------
# def create_step1(db: Session, payload, member_id: int) -> Dict[str, Any]:
#     # 1) template_id 검증
#     template_id = int(payload.template_id)
#
#     if template_id not in (1, 2):
#         raise HTTPException(status_code=422, detail="template_id must be 1 or 2")
#
#     # 2) review ids 정리
#     review_ids = list(payload.review_ids or [])
#     review_ids = [int(x) for x in review_ids if str(x).strip().isdigit()]
#
#     # 3) template별 최소 조건 체크
#     if template_id == 1:
#         # temp1: 정확히 3개
#         if len(review_ids) != 3:
#             raise HTTPException(status_code=422, detail="temp1 requires exactly 3 review_ids")
#     else:
#         # temp2: 3개 이상
#         if len(review_ids) < 3:
#             raise HTTPException(status_code=422, detail="temp2 requires 3+ review_ids")
#
#     # 4) 리뷰 조회 (내것만 + template 규칙 반영)
#     reviews = list_reviews_by_ids(
#         db,
#         review_ids,
#         member_id=member_id,
#         # include_inactive=include_inactive,
#     )
#
#     # 5) 소유/존재 검증 (중복 방지 포함)
#     # - reviews는 "조회된 것만" 오므로, 개수가 안 맞으면 누락/남의것/없는id
#     if len(reviews) != len(set(review_ids)):
#         raise HTTPException(status_code=403, detail="invalid review_ids (not found or not owned)")
#
#     # 6) temp1 추가 검증: 모두 active인지 (안전망)
#     if template_id == 1:
#         # available이 1/true인 것만 통과
#         def is_active(r):
#             v = r.get("available")
#             return v is True or v == 1 or v == "1"
#
#         if any(not is_active(r) for r in reviews):
#             raise HTTPException(status_code=422, detail="temp1 allows ACTIVE reviews only")
#
#     member_data = get_member(db, member_id)
#     category_items = build_user_profile_payload(db, member_id)
#
#     return {
#         "member_id": member_id,
#         "template_id": template_id,
#         "reviews": reviews,
#         "member": member_data,
#         "allergy_tags": category_items,
#     }
#
#
# # ---------------------------------------------------------------------
# # 등록 Step2 (map이면 community 유지 + 이미지 교체)
# # ---------------------------------------------------------------------
# async def create_step2(db: Session, total_data: Dict[str, Any]) -> Dict[str, Any]:
#     ai_payload = {
#         "template": {
#             "template_id": total_data.get("template_id"),
#             "template_type": total_data.get("template_id"),
#         },
#         "member_id": total_data.get("member_id"),
#         "member": total_data.get("member"),
#         "allergy_tags": total_data.get("allergy_tags"),
#         "reviews": total_data.get("reviews"),
#     }
#
#     # nickname 안전하게 뽑기
#     nickname = (total_data.get("member") or {}).get("nickname") or ""
#
#     # community_type 매핑 (review 제외, community 구분만)
#     template_id = int(total_data.get("template_id") or 0)
#     community_type = "journal" if template_id == 1 else ("map" if template_id == 2 else None)
#
#     # 1) AI 호출 (이벤트루프 안막도록 threadpool)
#     try:
#         # Lazy import to avoid crashing API pod when AI code is not in the API image.
#         from AI.journal_assistant.pipeline.orchestrator import run_orchestrator
#         image_bytes: bytes = await run_in_threadpool(run_orchestrator, ai_payload)
#         if not image_bytes:
#             raise RuntimeError("AI returned empty bytes")
#     except ModuleNotFoundError as e:
#         raise HTTPException(
#             status_code=503,
#             detail="AI module not available in API image (journal_assistant)."
#         ) from e
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"AI generation failed: {type(e).__name__}: {e}")
#
#     # 2) community 생성 or 재사용
#     try:
#         community = None
#
#         # map이면 기존 map community 재사용 (community row 삭제 X)
#         if community_type == "map":
#             community = db.execute(
#                 select(Community)
#                 .where(Community.member_id == int(total_data["member_id"]))
#                 .where(Community.community_type == "map")
#                 .order_by(Community.community_id.desc())
#             ).scalar_one_or_none()
#
#         if community is None:
#             # 없으면 새로 생성
#             community = Community(
#                 member_id=int(total_data["member_id"]),
#                 community_active=True,
#                 recommend=0,  # 새 글일 때만 0
#                 community_type=community_type,
#             )
#             db.add(community)
#             db.flush()
#         else:
#             # 기존 글이면 type 보정 + update_at 갱신 (recommend/댓글 유지)
#             if community.community_type != community_type:
#                 community.community_type = community_type
#             # 이미지 덮어쓰기이므로 update_at 명시적 갱신
#             community.update_at = func.now()
#             db.flush()
#
#         community_id = community.community_id
#
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Community upsert failed: {type(e).__name__}: {e}")
#
#     stored = None
#     perm_prefix = build_perm_prefix(owner_type="community", owner_id=community_id)
#
#     try:
#         # (중요) 기존 이미지/ImgFile 제거 후 새 이미지 저장
#         # 1) 기존 파일 전체 삭제(community/{community_id} 아래)
#         #    - map 덮어쓰기는 "이미지 1장 유지"라 prefix 날리는게 가장 단순/안전
#         try:
#             delete_prefix(prefix_key=perm_prefix)
#         except Exception:
#             pass
#
#         # 2) 기존 ImgFile row 삭제
#         db.execute(
#             delete(ImgFile)
#             .where(ImgFile.owner_type == "community")
#             .where(ImgFile.community_id == community_id)
#         )
#         db.flush()
#
#         # 3) 새 파일 저장
#         stored = await save_permanent_bytes(
#             owner_type="community",
#             owner_id=community_id,
#             member_id=int(total_data["member_id"]),
#             data=image_bytes,
#             origin_name="community.png",
#             mime_type="image/png",
#             sort_order=0,
#         )
#
#         # 4) 새 ImgFile row insert
#         img = ImgFile(
#             origin_name=stored.org_file_name,
#             storage_key=stored.stored_file_name,
#             storage_path=stored.storage_path,
#             mime_type=stored.mime_type,
#             file_size=stored.size_bytes,
#             sort_order=stored.sort_order,
#             owner_type="community",
#             member_id=int(total_data["member_id"]),
#             community_id=community_id,
#             review_id=None,
#         )
#         db.add(img)
#         db.flush()
#         db.refresh(community)
#
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Community image replace failed: {type(e).__name__}: {e}")
#
#     return {
#         "community_id": community_id,
#         "member_id": community.member_id,
#         "nickname": nickname,
#         "community_active": bool(community.community_active),
#         "recommend": int(community.recommend or 0),  # 기존 글이면 추천 유지됨
#         "image_urls": resolve_asset_urls([stored.storage_path] if stored else []), # s3 변경
#         # "image_urls": [stored.storage_path] if stored else [],
#         "template_id": total_data.get("template_id"),
#         "reviews": total_data.get("reviews", []),
#         "community_type": community.community_type,  # 필요하면 프론트에서 구분 가능
#     }
#
# # ---------------------------------------------------------------------
# # 전체 조회 / 본인 조회 공용
# # ---------------------------------------------------------------------
# def list_community(
#     db: Session,
#     *,
#     member_id: Optional[int] = None,
#     active_only: Optional[bool] = True,   # Optional로 변경
# ) -> List[Dict[str, Any]]:
#
#     # 최신 댓글 1개 프리뷰
#     latest_comment_text_sq = (
#         select(Comment.content)
#         .where(Comment.community_id == Community.community_id)
#         .order_by(Comment.comment_id.desc())
#         .limit(1)
#         .scalar_subquery()
#     )
#
#     stmt = (
#         select(Community, Member.nickname, latest_comment_text_sq)
#         .join(Member, Member.member_id == Community.member_id)
#     )
#
#     if member_id is not None:
#         stmt = stmt.where(Community.member_id == member_id)
#
#     if active_only is True:
#         stmt = stmt.where(Community.community_active.is_(True))
#     elif active_only is False:
#         stmt = stmt.where(Community.community_active.is_(False))
#     # None이면 필터 없음
#
#     rows = db.execute(stmt.order_by(Community.community_id.desc())).all()
#     if not rows:
#         return []
#
#     # communities = [c for c, _ in rows]
#     communities = [row[0] for row in rows]
#     community_ids = [c.community_id for c in communities]
#
#     # 이미지 붙이기(기존 방식 유지)
#     imgs = db.execute(
#         select(ImgFile)
#         .where(ImgFile.owner_type == "community")
#         .where(ImgFile.community_id.in_(community_ids))
#         .order_by(ImgFile.community_id.asc(), ImgFile.sort_order.asc())
#     ).scalars().all()
#
#     img_map: Dict[int, List[str]] = {}
#     for img in imgs:
#         img_map.setdefault(img.community_id, []).append(img.storage_path)
#
#     out: List[Dict[str, Any]] = []
#     for c, nickname, latest_comment_text in rows:
#         out.append({
#             "community_id": c.community_id,
#             "member_id": c.member_id,
#             "nickname": nickname,
#             "community_active": bool(c.community_active),
#             "recommend": int(c.recommend or 0),
#             "created_at": c.create_at.isoformat() if getattr(c, "create_at", None) else None,
#             "updated_at": c.update_at.isoformat() if getattr(c, "update_at", None) else None,
#             "image_urls": resolve_asset_urls(img_map.get(c.community_id, [])), # s3 변경
#             # "image_urls": img_map.get(c.community_id, []),
#             "latest_comment_text": latest_comment_text,  # 댓글
#             "community_type": c.community_type,
#         })
#     return out
#
#
# # ---------------------------------------------------------------------
# # 상세
# # ---------------------------------------------------------------------
# def get_community_detail(db: Session, community_id: int, *, member_id: Optional[int] = None) -> Dict[str, Any]:
#
#     latest_comment_text_sq = (
#         select(Comment.content)
#         .where(Comment.community_id == Community.community_id)
#         .order_by(Comment.comment_id.desc())
#         .limit(1)
#         .scalar_subquery()
#     )
#
#     row = db.execute(
#         select(Community, Member.nickname, latest_comment_text_sq)
#         .join(Member, Member.member_id == Community.member_id)
#         .where(Community.community_id == int(community_id))
#     ).first()
#
#     if not row:
#         raise HTTPException(status_code=404, detail="Community not found")
#
#     c, nickname, latest_comment_text = row
#
#     imgs = db.execute(
#         select(ImgFile)
#         .where(ImgFile.community_id == community_id)
#         .where(ImgFile.owner_type == "community")
#         .order_by(ImgFile.sort_order.asc())
#     ).scalars().all()
#
#     # 현재 사용자가 좋아요 했는지 확인
#     liked = False
#     if member_id is not None:
#         liked_row = db.execute(
#             select(CommunityRecommend.recommend_id).where(
#                 CommunityRecommend.community_id == int(community_id),
#                 CommunityRecommend.member_id == int(member_id),
#             )
#         ).scalar_one_or_none()
#         liked = liked_row is not None
#
#     return {
#         "community_id": c.community_id,
#         "member_id": c.member_id,
#         "nickname": nickname,
#         "community_active": bool(c.community_active),
#         "recommend": int(c.recommend or 0),
#         "liked": liked,
#         "created_at": c.create_at.isoformat() if getattr(c, "create_at", None) else None,
#         "updated_at": c.update_at.isoformat() if getattr(c, "update_at", None) else None,
#         "image_urls": resolve_asset_urls([img.storage_path for img in imgs]), # s3 변경
#         # "image_urls": [img.storage_path for img in imgs],
#         "latest_comment_text": latest_comment_text,  # 댓글
#     }
#
#
# """
# community / recommend 실제 좋아요 수
#
# community_recommend community_id 당 1개의 좋아요 1 row
# 커뮤니티 1개의 글에 좋아요 5개 발생 시
# row 5개 생성
#
# 최종 recommend == row의 수
# """
# # community recommend 로직
# def toggle_recommend(db: Session, *, community_id: int, member_id: int) -> Dict[str, Any]:
#     c = db.get(Community, int(community_id))
#     if not c:
#         raise HTTPException(status_code=404, detail="Community not found")
#
#     exists = db.execute(
#         select(CommunityRecommend.recommend_id).where(
#             CommunityRecommend.community_id == int(community_id),
#             CommunityRecommend.member_id == int(member_id),
#         )
#     ).scalar_one_or_none()
#
#     # update_at 보존: 좋아요는 정렬 기준에 영향주지 않도록
#     original_update_at = c.update_at
#
#     if exists is None:
#         # 좋아요 추가(1 row 생성)
#         db.add(CommunityRecommend(community_id=int(community_id), member_id=int(member_id)))
#         db.flush()
#
#         # 카운트 +1 (update_at 원래 값 유지)
#         db.execute(
#             update(Community)
#             .where(Community.community_id == int(community_id))
#             .values(recommend=Community.recommend + 1, update_at=original_update_at)
#         )
#         db.flush()
#         db.refresh(c)
#
#         return {"recommended": True, "recommend": int(c.recommend or 0)}
#     else:
#         # 좋아요 취소(row 삭제)
#         db.execute(
#             delete(CommunityRecommend).where(
#                 CommunityRecommend.community_id == int(community_id),
#                 CommunityRecommend.member_id == int(member_id),
#             )
#         )
#
#         # 카운트 -1 (0 아래 방지, update_at 원래 값 유지)
#         db.execute(
#             update(Community)
#             .where(Community.community_id == int(community_id), Community.recommend > 0)
#             .values(recommend=Community.recommend - 1, update_at=original_update_at)
#         )
#         db.flush()
#         db.refresh(c)
#
#         return {"recommended": False, "recommend": int(c.recommend or 0)}
#
#
# # ---------------------------------------------------------------------
# # 공개 설정 토글 (community_active)
# # ---------------------------------------------------------------------
# def toggle_active(db: Session, *, community_id: int, member_id: int) -> Dict[str, Any]:
#     c = db.get(Community, int(community_id))
#     if not c:
#         raise HTTPException(status_code=404, detail="Community not found")
#
#     if c.member_id != int(member_id):
#         raise HTTPException(status_code=403, detail="본인 게시글만 변경할 수 있습니다")
#
#     # update_at 보존: 공개 토글은 정렬 기준에 영향주지 않도록
#     original_update_at = c.update_at
#
#     new_active = not c.community_active
#     db.execute(
#         update(Community)
#         .where(Community.community_id == int(community_id))
#         .values(community_active=new_active, update_at=original_update_at)
#     )
#     db.flush()
#     db.refresh(c)
#
#     return {"community_id": c.community_id, "community_active": bool(c.community_active)}