from sqlalchemy.orm import Session, aliased
from sqlalchemy import select, delete, update, func, true
from fastapi import HTTPException
from typing import Any, Dict, Optional, List

from starlette.concurrency import run_in_threadpool

from backend.app.models.community import Community
from backend.app.models.img_file import ImgFile
from backend.app.models.comment import Comment  # 댓글

# review 로직
from backend.app.features.review.service import list_reviews_by_ids

# member 로직
from backend.app.features.member.service import get_member
from backend.app.models.member import Member

# category, item 조회
from backend.app.common.service.ai_member_info import build_user_profile_payload
from backend.app.common.utils.util import resolve_asset_urls

# community_recommend
from backend.app.models.community_recommend import CommunityRecommend

# 파일 저장(공통)
from backend.app.common.service.file_upload_service import (
    save_permanent_bytes,
    delete_prefix,
    build_perm_prefix,
)


# ---------------------------------------------------------------------
# 등록 Step1
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

    reviews = list_reviews_by_ids(
        db,
        review_ids,
        member_id=member_id,
    )

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
# pending community (async worker)
# ---------------------------------------------------------------------
def create_pending_community(db: Session, total_data: Dict[str, Any]) -> Dict[str, Any]:
    member_id = int(total_data.get("member_id") or 0)
    if not member_id:
        raise HTTPException(status_code=422, detail="member_id is required")

    template_id = int(total_data.get("template_id") or 0)
    community_type = "journal" if template_id == 1 else ("map" if template_id == 2 else None)

    community: Community | None = None
    if community_type == "map":
        community = db.execute(
            select(Community)
            .where(Community.member_id == member_id)
            .where(Community.community_type == "map")
            .order_by(Community.community_id.desc())
        ).scalar_one_or_none()

    if community is None:
        community = Community(
            member_id=member_id,
            community_active=True,
            recommend=0,
            community_type=community_type,
        )
        db.add(community)
        db.flush()
    elif community_type and community.community_type != community_type:
        community.community_type = community_type
        db.add(community)
        db.flush()

    return {
        "community_id": int(community.community_id),
        "community_type": community.community_type,
    }


# ---------------------------------------------------------------------
# common persist from image bytes (worker / sync)
# ---------------------------------------------------------------------
async def persist_step2_from_image_bytes(db: Session, total_data: Dict[str, Any], image_bytes: bytes) -> Dict[str, Any]:
    """
    Common helper for community creation from image bytes.
    - upload image bytes to storage
    - insert ImgFile row
    - create or reuse community row
    """
    if not image_bytes:
        raise ValueError("empty image_bytes")

    member_id = int(total_data.get("member_id") or 0)
    if not member_id:
        raise ValueError("member_id is required in total_data")

    template_id = int(total_data.get("template_id") or 0)
    community_type = "journal" if template_id == 1 else ("map" if template_id == 2 else None)

    community_id = int(total_data.get("community_id") or 0)
    community: Community | None = None
    if community_id:
        community = db.get(Community, community_id)
        if community is None:
            raise ValueError(f"community not found: {community_id}")
        if int(community.member_id) != member_id:
            raise ValueError("community member mismatch")
    elif community_type == "map":
        community = db.execute(
            select(Community)
            .where(Community.member_id == member_id)
            .where(Community.community_type == "map")
            .order_by(Community.community_id.desc())
        ).scalar_one_or_none()

    if community is None:
        community = Community(
            member_id=member_id,
            community_active=True,
            recommend=0,
            community_type=community_type,
        )
        db.add(community)
        db.flush()
    elif community_type and community.community_type != community_type:
        community.community_type = community_type
        db.add(community)
        db.flush()

    community_id = int(community.community_id)

    # map: delete existing objects (best-effort)
    if community_type == "map":
        try:
            perm_prefix = build_perm_prefix(owner_type="community", owner_id=community_id)
            delete_prefix(prefix_key=perm_prefix)
        except Exception:
            pass

    # delete existing ImgFile row (unique constraint)
    db.execute(
        delete(ImgFile)
        .where(ImgFile.owner_type == "community")
        .where(ImgFile.community_id == community_id)
    )
    db.flush()

    stored = await save_permanent_bytes(
        owner_type="community",
        owner_id=community_id,
        member_id=member_id,
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
        member_id=member_id,
        community_id=community_id,
        review_id=None,
    )
    db.add(img)
    db.flush()
    db.refresh(community)

    return {
        "community_id": community_id,
        "image_urls": resolve_asset_urls([stored.storage_path] if stored else []),
        "template_id": template_id,
        "reviews": total_data.get("reviews", []),
        "community_type": community.community_type,
    }


# ---------------------------------------------------------------------
# finalize job result (when worker only uploaded to storage)
# ---------------------------------------------------------------------
def finalize_from_worker_result(
    db: Session,
    *,
    total_data: Dict[str, Any],
    community_id: int,
    stored: Dict[str, Any],
    template_id: int,
    review_ids: List[int],
) -> Dict[str, Any]:
    if not community_id:
        raise HTTPException(status_code=422, detail="community_id is required")

    community = db.get(Community, int(community_id))
    if community is None:
        raise HTTPException(status_code=404, detail="community not found")

    member_id = int(total_data.get("member_id") or community.member_id or 0)
    if not member_id:
        raise HTTPException(status_code=422, detail="member_id is required")

    community_type = "journal" if int(template_id) == 1 else ("map" if int(template_id) == 2 else None)
    if community_type and community.community_type != community_type:
        community.community_type = community_type
        db.add(community)
        db.flush()

    storage_path = stored.get("storage_path")
    if not storage_path:
        raise HTTPException(status_code=422, detail="stored.storage_path is required")

    db.execute(
        delete(ImgFile)
        .where(ImgFile.owner_type == "community")
        .where(ImgFile.community_id == int(community_id))
    )
    db.flush()

    img = ImgFile(
        origin_name=stored.get("org_file_name") or "community.png",
        storage_key=stored.get("stored_file_name") or stored.get("file_key") or storage_path,
        storage_path=storage_path,
        mime_type=stored.get("mime_type") or "image/png",
        file_size=stored.get("size_bytes"),
        sort_order=int(stored.get("sort_order") or 0),
        owner_type="community",
        member_id=member_id,
        community_id=int(community_id),
        review_id=None,
    )
    db.add(img)
    db.flush()

    if int(template_id) == 1 and review_ids:
        from backend.app.features.review.service import availavble_review

        ok = availavble_review(db, review_ids)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to update review availability")

    return {
        "community_id": int(community_id),
        "image_urls": resolve_asset_urls([storage_path]),
        "template_id": int(template_id),
        "reviews": total_data.get("reviews", []),
        "community_type": community.community_type,
    }

# ---------------------------------------------------------------------
# 등록 Step2 (기존 동기 생성 경로도 공용함수 사용하도록 정리)
# ---------------------------------------------------------------------
async def create_step2(db: Session, total_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from AI.journal_assistant.pipeline.orchestrator import run_orchestrator
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI module unavailable: {type(e).__name__}: {e}")

    ai_payload = {
        "template": {
            "template_id": total_data.get("template_id"),
            "template_type": total_data.get("template_id"),
        },
        "member_id": total_data.get("member_id"),
        "member": total_data.get("member"),
        "allergy_tags": total_data.get("allergy_tags"),
        "reviews": total_data.get("reviews"),
    }

    # 1) AI 호출
    try:
        image_bytes: bytes = await run_in_threadpool(run_orchestrator, ai_payload)
        if not image_bytes:
            raise RuntimeError("AI returned empty bytes")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {type(e).__name__}: {e}")

    # 2) 저장 + DB 반영
    try:
        return await persist_step2_from_image_bytes(db, total_data, image_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"community persist failed: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------
# 전체 조회 / 본인 조회 공용
# ---------------------------------------------------------------------
def list_community(
    db: Session,
    *,
    member_id: Optional[int] = None,
    active_only: Optional[bool] = True,
) -> List[Dict[str, Any]]:
    PostAuthor = aliased(Member)

    latest_comment_text_sq = (
        select(Comment.content)
        .where(Comment.community_id == Community.community_id)
        .order_by(Comment.comment_id.desc())
        .limit(1)
        .scalar_subquery()
    )

    latest_comment_nickname_sq = (
        select(Member.nickname)
        .join(Comment, Comment.member_id == Member.member_id)
        .where(Comment.community_id == Community.community_id)
        .order_by(Comment.comment_id.desc())
        .limit(1)
        .scalar_subquery()
    )

    stmt = (
        select(
            Community,
            PostAuthor.nickname.label("post_nickname"),
            latest_comment_text_sq.label("latest_comment_text"),
            latest_comment_nickname_sq.label("latest_comment_nickname"),
        )
        .join(PostAuthor, PostAuthor.member_id == Community.member_id)
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

    communities = [row[0] for row in rows]
    community_ids = [c.community_id for c in communities]

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
    for c, post_nickname, latest_comment_text, latest_comment_nickname in rows:
        out.append({
            "community_id": c.community_id,
            "member_id": c.member_id,
            "nickname": post_nickname,
            "community_active": bool(c.community_active),
            "recommend": int(c.recommend or 0),
            "created_at": c.create_at.isoformat() if getattr(c, "create_at", None) else None,
            "updated_at": c.update_at.isoformat() if getattr(c, "update_at", None) else None,
            "image_urls": resolve_asset_urls(img_map.get(c.community_id, [])),
            "latest_comment_text": latest_comment_text,
            "latest_comment_nickname": latest_comment_nickname,
            "community_type": c.community_type,
        })
    return out


# ---------------------------------------------------------------------
# 상세
# ---------------------------------------------------------------------
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
        raise HTTPException(status_code=404, detail="community not found")

    c, nickname, latest_comment_text = row

    img_rows = db.execute(
        select(ImgFile)
        .where(ImgFile.owner_type == "community")
        .where(ImgFile.community_id == int(community_id))
        .order_by(ImgFile.sort_order.asc())
    ).scalars().all()

    image_urls = resolve_asset_urls([img.storage_path for img in img_rows])

    return {
        "community_id": c.community_id,
        "member_id": c.member_id,
        "nickname": nickname,
        "community_active": bool(c.community_active),
        "recommend": int(c.recommend or 0),
        "liked": False,
        "created_at": c.create_at.isoformat() if getattr(c, "create_at", None) else None,
        "updated_at": c.update_at.isoformat() if getattr(c, "update_at", None) else None,
        "image_urls": image_urls,
        "latest_comment_text": latest_comment_text,
    }

"""
community / recommend 실제 좋아요 수

community_recommend community_id 당 1개의 좋아요 1 row
커뮤니티 1개의 글에 좋아요 5개 발생 시 
row 5개 생성

최종 recommend == row의 수
"""
# community recommend 로직
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

    # update_at 보존: 좋아요는 정렬 기준에 영향주지 않도록
    original_update_at = c.update_at

    if exists is None:
        # 좋아요 추가(1 row 생성)
        db.add(CommunityRecommend(community_id=int(community_id), member_id=int(member_id)))
        db.flush()

        # 카운트 +1 (update_at 원래 값 유지)
        db.execute(
            update(Community)
            .where(Community.community_id == int(community_id))
            .values(recommend=Community.recommend + 1, update_at=original_update_at)
        )
        db.flush()
        db.refresh(c)

        return {"recommended": True, "recommend": int(c.recommend or 0)}
    else:
        # 좋아요 취소(row 삭제)
        db.execute(
            delete(CommunityRecommend).where(
                CommunityRecommend.community_id == int(community_id),
                CommunityRecommend.member_id == int(member_id),
            )
        )

        # 카운트 -1 (0 아래 방지, update_at 원래 값 유지)
        db.execute(
            update(Community)
            .where(Community.community_id == int(community_id), Community.recommend > 0)
            .values(recommend=Community.recommend - 1, update_at=original_update_at)
        )
        db.flush()
        db.refresh(c)

        return {"recommended": False, "recommend": int(c.recommend or 0)}


# ---------------------------------------------------------------------
# 공개 설정 토글 (community_active)
# ---------------------------------------------------------------------
def toggle_active(db: Session, *, community_id: int, member_id: int) -> Dict[str, Any]:
    c = db.get(Community, int(community_id))
    if not c:
        raise HTTPException(status_code=404, detail="Community not found")

    if c.member_id != int(member_id):
        raise HTTPException(status_code=403, detail="본인 게시글만 변경할 수 있습니다")

    # update_at 보존: 공개 토글은 정렬 기준에 영향주지 않도록
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