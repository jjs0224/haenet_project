import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security.deps import get_current_member

from backend.app.features.community.schemas import (
    CommunityCreate,
    CommunityRead,
    CommunityListRead,
    CommunityEnqueueResponse,
    CommunityJobResponse,
)
from backend.app.features.community import service

from backend.app.core.job_queue import connect_redis, enqueue_task, utc_now_iso

router = APIRouter(prefix="/community", tags=["community"])


def _parse_json(v: Optional[str]):
    if not v:
        return None
    try:
        return json.loads(v)
    except Exception:
        return None


@router.post("", response_model=CommunityEnqueueResponse)
def create_community(payload: CommunityCreate, db: Session = Depends(get_db), current=Depends(get_current_member)):
    # 1) 검증 + total_data 구성
    total_data = service.create_step1(db, payload, member_id=current.member_id)

    # 2) (B안 핵심) DB에서 community row 먼저 만들고 community_id 확보
    pending = service.create_pending_community(db, total_data)
    community_id = int(pending["community_id"])
    community_type = pending.get("community_type")

    # 3) 워커로 넘길 ai_payload
    ai_payload: Dict[str, Any] = {
        "template": {
            "template_id": total_data.get("template_id"),
            "template_type": total_data.get("template_id"),
        },
        "member_id": total_data.get("member_id"),
        "member": total_data.get("member"),
        "allergy_tags": total_data.get("allergy_tags"),
        "reviews": total_data.get("reviews"),
    }

    # 4) redis 연결
    try:
        r = connect_redis()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"redis unavailable: {type(e).__name__}: {e}")

    # 5) (B안 핵심) worker는 DB를 만지지 않음 → 업로드만 하게 필요한 값만 넣음
    task_payload = {
        "ai_payload": ai_payload,
        "total_data": total_data,          # member_id 등 (DB는 안 쓰지만 업로드에 필요)
        "community_id": community_id,      # ✅ 업로드 prefix용
        "community_type": community_type,
        "template_id": int(total_data.get("template_id") or 0),
        "review_ids": list(payload.review_ids or []),
        "member_id": current.member_id,
    }

    try:
        job_id = enqueue_task(r, task="journal_generate_community", payload=task_payload)

        # ✅ polling 시 backend가 finalize 할 수 있게 job hash에 메타 저장
        r.hset(
            f"cicdex:job:{job_id}",
            mapping={
                "member_id": str(current.member_id),
                "community_id": str(community_id),
                "template_id": str(int(total_data.get("template_id") or 0)),
                "review_ids": json.dumps(list(payload.review_ids or []), ensure_ascii=False),
                "finalized": "0",
            },
        )
        db.commit()  # community_id 선생성 확정
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"community enqueue failed: {type(e).__name__}: {e}")

    return CommunityEnqueueResponse(job_id=job_id, status="PENDING", queued_at=utc_now_iso())


@router.get("/job/{job_id}", response_model=CommunityJobResponse)
def community_job_status(job_id: str, db: Session = Depends(get_db), current=Depends(get_current_member)):
    try:
        r = connect_redis()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"redis unavailable: {type(e).__name__}: {e}")

    data = r.hgetall(f"cicdex:job:{job_id}")
    if not data:
        raise HTTPException(status_code=404, detail="job not found")

    status = data.get("status", "PENDING")
    result = _parse_json(data.get("result"))
    error = _parse_json(data.get("error"))

    # ✅ (B안 핵심) worker가 DONE이면 backend가 DB finalize(ImgFile + review available)
    if status == "DONE" and result and data.get("finalized") != "1":
        try:
            community_id = int(data.get("community_id") or (result.get("community_id") or 0))
            template_id = int(data.get("template_id") or (result.get("template_id") or 0))
            review_ids = _parse_json(data.get("review_ids")) or []
            stored = result.get("stored") or {}

            # total_data는 polling 시점에 없으니 최소 dict로 진행(필수: member_id)
            total_data = {"member_id": int(data.get("member_id") or current.member_id), "member": {}, "reviews": []}

            final = service.finalize_from_worker_result(
                db,
                total_data=total_data,
                community_id=community_id,
                stored=stored,
                template_id=template_id,
                review_ids=[int(x) for x in (review_ids or []) if str(x).strip().isdigit()],
            )
            db.commit()

            # job result를 최종 응답 형태로 덮어써서 이후 폴링은 바로 DONE 결과 받게 함
            r.hset(
                f"cicdex:job:{job_id}",
                mapping={"finalized": "1", "result": json.dumps(final, ensure_ascii=False)},
            )
            result = final

        except Exception as e:
            db.rollback()
            err = {"type": type(e).__name__, "message": str(e)}
            r.hset(
                f"cicdex:job:{job_id}",
                mapping={
                    "status": "FAILED",
                    "error": json.dumps(err, ensure_ascii=False),
                    "updated_at": utc_now_iso(),
                },
            )
            status = "FAILED"
            error = err
            result = None

    return CommunityJobResponse(
        job_id=job_id,
        status=status,
        result=result if status == "DONE" else None,
        error=error if status == "FAILED" else None,
        queued_at=data.get("queued_at"),
        updated_at=data.get("updated_at"),
    )


@router.get("", response_model=list[CommunityListRead])
def community_list(db: Session = Depends(get_db)):
    return service.list_community(db, member_id=None, active_only=True)


@router.get("/me", response_model=list[CommunityListRead])
def community_my_list(db: Session = Depends(get_db), current=Depends(get_current_member)):
    return service.list_community(db, member_id=current.member_id, active_only=None)


@router.get("/{community_id}", response_model=CommunityRead)
def get_community(community_id: int, db: Session = Depends(get_db), current=Depends(get_current_member)):
    return service.get_community_detail(db, community_id, member_id=current.member_id)


@router.post("/{community_id}/recommend")
def recommend_toggle(community_id: int, db: Session = Depends(get_db), current=Depends(get_current_member)):
    out = service.toggle_recommend(db, community_id=community_id, member_id=current.member_id)
    db.commit()
    return out


@router.patch("/{community_id}/active")
def toggle_active(community_id: int, db: Session = Depends(get_db), current=Depends(get_current_member)):
    out = service.toggle_active(db, community_id=community_id, member_id=current.member_id)
    db.commit()
    return out


# import json
# from typing import Any, Dict, Optional
#
# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy.orm import Session
#
# from backend.app.core.database import get_db
# from backend.app.core.security.deps import get_current_member
#
# from backend.app.features.community.schemas import (
#     CommunityCreate,
#     CommunityRead,
#     CommunityListRead,
#     CommunityEnqueueResponse,
#     CommunityJobResponse,
# )
# from backend.app.features.community import service
#
# # job queue (review와 동일)
# from backend.app.core.job_queue import connect_redis, enqueue_task, utc_now_iso
#
# router = APIRouter(prefix="/community", tags=["community"])
#
#
# def _parse_json(v: Optional[str]):
#     if not v:
#         return None
#     try:
#         return json.loads(v)
#     except Exception:
#         return None
#
#
# @router.post("", response_model=CommunityEnqueueResponse)
# def create_community(payload: CommunityCreate, db: Session = Depends(get_db), current=Depends(get_current_member)):
#     # 1) step1: 검증 + total_data 구성 (동기)
#     total_data = service.create_step1(db, payload, member_id=current.member_id)
#
#     # 2) worker로 넘길 ai_payload 구성 (기존 create_step2가 만들던 형태 그대로)
#     ai_payload: Dict[str, Any] = {
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
#     # 3) enqueue (journal_* => cicdex:jobs:journal 로 라우팅됨)
#     try:
#         r = connect_redis()
#     except Exception as e:
#         raise HTTPException(status_code=503, detail=f"redis unavailable: {type(e).__name__}: {e}")
#
#     # worker가 DB/리뷰available까지 처리하도록 payload에 필요한 값 넣기
#     task_payload = {
#         "ai_payload": ai_payload,
#         "total_data": total_data,
#         "template_id": int(total_data.get("template_id") or 0),
#         "review_ids": list(payload.review_ids or []),
#         "member_id": current.member_id,
#     }
#
#     try:
#         job_id = enqueue_task(r, task="journal_generate_community", payload=task_payload)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"community enqueue failed: {type(e).__name__}: {e}")
#
#     return CommunityEnqueueResponse(job_id=job_id, status="PENDING", queued_at=utc_now_iso())
#
#
# @router.get("/job/{job_id}", response_model=CommunityJobResponse)
# def community_job_status(job_id: str, current=Depends(get_current_member)):
#     try:
#         r = connect_redis()
#     except Exception as e:
#         raise HTTPException(status_code=503, detail=f"redis unavailable: {type(e).__name__}: {e}")
#
#     data = r.hgetall(f"cicdex:job:{job_id}")
#     if not data:
#         raise HTTPException(status_code=404, detail="job not found")
#
#     status = data.get("status", "PENDING")
#     result = _parse_json(data.get("result"))
#     error = _parse_json(data.get("error"))
#
#     return CommunityJobResponse(
#         job_id=job_id,
#         status=status,
#         result=result if status == "DONE" else None,
#         error=error if status == "FAILED" else None,
#         queued_at=data.get("queued_at"),
#         updated_at=data.get("updated_at"),
#     )
#
#
# @router.get("", response_model=list[CommunityListRead])
# def community_list(db: Session = Depends(get_db)):
#     return service.list_community(db, member_id=None, active_only=True)
#
#
# @router.get("/me", response_model=list[CommunityListRead])
# def community_my_list(db: Session = Depends(get_db), current=Depends(get_current_member)):
#     return service.list_community(db, member_id=current.member_id, active_only=None)
#
#
# @router.get("/{community_id}", response_model=CommunityRead)
# def get_community(community_id: int, db: Session = Depends(get_db), current=Depends(get_current_member)):
#     return service.get_community_detail(db, community_id, member_id=current.member_id)
#
#
# @router.post("/{community_id}/recommend")
# def recommend_toggle(community_id: int, db: Session = Depends(get_db), current=Depends(get_current_member)):
#     out = service.toggle_recommend(db, community_id=community_id, member_id=current.member_id)
#     db.commit()
#     return out
#
#
# @router.patch("/{community_id}/active")
# def toggle_active(community_id: int, db: Session = Depends(get_db), current=Depends(get_current_member)):
#     out = service.toggle_active(db, community_id=community_id, member_id=current.member_id)
#     db.commit()
#     return out
#
#
# # import uuid
# # import json
# # from typing import List
# # from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
# # from sqlalchemy.orm import Session
# #
# # from backend.app.core.database import get_db
# # from backend.app.core.security.deps import get_current_member
# # # from backend.app.common.utils.debug import log_exception
# # from backend.app.features.community.schemas import CommunityUpdate, CommunityCreate, CommunityRead, CommunityListRead
# # from backend.app.features.community import service
# # from backend.app.models.community import Community
# # from backend.app.features.review.service import availavble_review
# #
# #
# # router = APIRouter(prefix="/community", tags=["community"])
# #
# # @router.post("", response_model=CommunityListRead)
# # async def create_community(payload: CommunityCreate, db: Session = Depends(get_db), current=Depends(get_current_member)):
# #
# #     # 1. 넘겨 받은 데이터 조회 및 조합
# #     total_data = service.create_step1(db, payload, member_id=current.member_id)
# #     print("router data :: ", total_data)
# #
# #
# #     try:
# #         # 2. AI 로직 시작 (예외 가능성 제일 큼)
# #         result = await service.create_step2(db, total_data)
# #         print("result :: ", result)
# #
# #         # 3. AI 성공 후 TEMP1만 REVIEW available 처리
# #         if int(payload.template_id) == 1:
# #             ok = availavble_review(db, payload.review_ids)
# #             if not ok:
# #                 raise HTTPException(status_code=500, detail="Failed to update review availability")
# #
# #         # # 3. AI 성공 후 REVIEW available 처리
# #         # print("AI 처리 후 REVIEW AVAILABLE ", payload.review_ids)
# #         # ok = availavble_review(db, payload.review_ids)
# #         # if not ok:
# #         #     # 여기서 실패하면 절대 성공 리턴하면 안됨(데이터 정합성 깨짐)
# #         #     raise HTTPException(status_code=500, detail="Failed to update review availability")
# #
# #         # step1/step2에서 DB write가 있었다면 여기서 한 번에 커밋
# #         # step2 commit 주석처리 완
# #         db.commit()
# #
# #         return result
# #
# #     except HTTPException:
# #         db.rollback()
# #         raise
# #
# #     except Exception as e:
# #         db.rollback()
# #         raise HTTPException(status_code=500, detail=f"Community create failed: {type(e).__name__}: {e}")
# #
# #
# #
# #     # # 2. 넘겨 받은 데이터 AI 로직 시작
# #     # result = await service.create_step2(db, total_data)
# #     #
# #     # print("result :: ", result)
# #     #
# #     # # 3. AI 생성 후 완료되면 REVIEW available F or 0 수정 처리
# #     #
# #     # print("AI 처리 후 REVIEW AVAILABLE ", payload.review_ids)
# #     # availavble_review(db, payload.review_ids)
# #     #
# #     # return result
# #     # return CommunityListRead(community_id=result["community_id"], image_urls=result['image_urls'], member_id=result["member_id"])
# #
# #
# # @router.get("", response_model=list[CommunityListRead])
# # def community_list(db: Session = Depends(get_db)):
# #     print("community list 전체 조회중")
# #     return service.list_community(db, member_id=None, active_only=True)
# #
# # # active 상관없이 내것 전부
# # @router.get("/me", response_model=list[CommunityListRead])
# # def community_my_list(db: Session = Depends(get_db), current=Depends(get_current_member)):
# #     print("community list 내것만 조회중")
# #     return service.list_community(db, member_id=current.member_id, active_only=None)
# #
# # @router.get("/{community_id}", response_model=CommunityRead)
# # def get_community(community_id: int, db: Session = Depends(get_db), current=Depends(get_current_member)):
# #
# #     print("community 상세 조회 :: ", current.member_id)
# #
# #     return service.get_community_detail(db, community_id, member_id=current.member_id)
# #
# # # 좋아요 로직
# # @router.post("/{community_id}/recommend")
# # def recommend_toggle(community_id: int, db: Session = Depends(get_db), current=Depends(get_current_member)):
# #     out = service.toggle_recommend(db, community_id=community_id, member_id=current.member_id)
# #     db.commit()
# #     return out
# #
# # # 공개 설정 토글
# # @router.patch("/{community_id}/active")
# # def toggle_active(community_id: int, db: Session = Depends(get_db), current=Depends(get_current_member)):
# #     out = service.toggle_active(db, community_id=community_id, member_id=current.member_id)
# #     db.commit()
# #     return out