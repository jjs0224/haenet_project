import uuid
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.app.core.security.deps import get_current_member
from backend.app.common.utils.debug import log_exception
from backend.app.common.service.file_upload_service import (
    build_temp_prefix,
    delete_prefix,
    ensure_local_path,
    upload_input_file,
)
from backend.app.features.menu.schemas import MenuUploadResponse
from backend.app.features.menu.service import run_menu_ai
from backend.app.core.database import get_db
from sqlalchemy.orm import Session
from backend.app.common.service.ai_member_info import build_user_profile_payload

router = APIRouter(prefix="/menu", tags=["menu"])


@router.post("/upload", response_model=MenuUploadResponse)
async def upload_menu(
    db: Session = Depends(get_db),
    type: str = Form("menu"),
    file: UploadFile = File(...),
    current=Depends(get_current_member)):

    if (type or "").lower().strip() != "menu":
        raise HTTPException(status_code=400, detail="type must be 'menu'")

    job_id = uuid.uuid4().hex
    tmp_prefix = build_temp_prefix(upload_type="menu", scope_id=job_id)

    try:
        obj = await upload_input_file(
            upload_type="menu",
            member_id=current.member_id,
            upload=file,
            scope_id=job_id,
            is_temp=True,
        )
    except Exception as e:
        log_exception("menu.upload_input", e)
        raise HTTPException(status_code=400, detail=f"upload failed: {e}")

    local_path, cleanup = ensure_local_path(obj)

    # runs_root는 기존 그대로 유지
    runs_root = Path(tmp_prefix) / "ai_runs"

    # user_profile_json도 tmp_prefix 아래에 생성 (정책 유지: 끝나면 temp 삭제)
    user_profile_json_path = Path(tmp_prefix) / "user_profile.json"

    try:

        # 현 위치 알레르기 정보 넘겨주면 끝
        payload = build_user_profile_payload(db, current.member_id)

        user_profile_json_path.parent.mkdir(parents=True, exist_ok=True)
        user_profile_json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        user_profile_json = str(user_profile_json_path)


        # --- (A) current에서 가능한 정보만 뽑아서 user_profile.json 생성 ---
        # 필드명은 프로젝트마다 다르니, 있는 것만 가져오게 방어적으로 구성
        # allergy_tags = getattr(current, "allergy_tags", None) #
        # avoid_foods = getattr(current, "avoid_foods", None) # dislike
        # religion = getattr(current, "religion", None) #
        #
        # print("allergy_tags :: ", allergy_tags)
        # print("avoid_foods :: ", avoid_foods)
        # print("religion :: ", religion)
        #
        # # 어떤 백엔드는 current.profile 같은 중첩 구조일 수 있어서 한 번 더 시도
        # profile = getattr(current, "profile", None)
        # if profile is not None:
        #     if allergy_tags is None:
        #         allergy_tags = getattr(profile, "allergy_tags", None)
        #     if avoid_foods is None:
        #         avoid_foods = getattr(profile, "avoid_foods", None)
        #     if religion is None:
        #         religion = getattr(profile, "religion", None)
        #
        # # 값이 하나라도 있으면 파일을 생성해서 Step5에 전달
        # user_profile_json = None
        # if allergy_tags or avoid_foods or religion:
        #     payload = {
        #         "allergy_tags": list(allergy_tags or []),
        #         "avoid_foods": list(avoid_foods or []),
        #         "religion": religion,
        #     }
        #     # tmp_prefix가 local 모드에서 로컬 경로라는 전제 하에 저장됨
        #     user_profile_json_path.parent.mkdir(parents=True, exist_ok=True)
        #     user_profile_json_path.write_text(
        #         json.dumps(payload, ensure_ascii=False, indent=2),
        #         encoding="utf-8",
        #     )
        #     user_profile_json = str(user_profile_json_path)





        # --- (B) pipeline 실행 ---
        result = run_menu_ai(
            image_path=local_path,
            runs_root=runs_root,
            run_id=job_id,
            user_profile_json=user_profile_json,
        )
        return MenuUploadResponse(job_id=job_id, upload_type="menu", result=result)

    except Exception as e:
        log_exception("menu.ai_failed", e)
        import builtins
        raise HTTPException(status_code=500, detail=f"menu ai failed: {builtins.type(e).__name__}: {e}")

    finally:
        cleanup()
        # delete_prefix(prefix_key=tmp_prefix)



# import uuid
# from pathlib import Path
#
# from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
#
# from backend.app.core import config
# from backend.app.core.security.deps import get_current_member
# from backend.app.common.utils.debug import log_exception
# from backend.app.common.service.file_upload_service import (
#     build_temp_prefix,
#     delete_prefix,
#     ensure_local_path,
#     upload_input_file,
# )
# from backend.app.features.menu.schemas import MenuUploadResponse
#
# from backend.app.features.menu.service import run_menu_ai
#
# router = APIRouter(prefix="/menu", tags=["menu"])
#
#
# @router.post("/upload", response_model=MenuUploadResponse)
# async def upload_menu(
#     type: str = Form("menu"),
#     file: UploadFile = File(...),
#     current=Depends(get_current_member),
# ):
#     if (type or "").lower().strip() != "menu":
#         raise HTTPException(status_code=400, detail="type must be 'menu'")
#
#     job_id = uuid.uuid4().hex
#     tmp_prefix = build_temp_prefix(upload_type="menu", scope_id=job_id)
#
#     try:
#         obj = await upload_input_file(
#             upload_type="menu",
#             member_id=current.member_id,
#             upload=file,
#             scope_id=job_id,
#             is_temp=True,
#         )
#     except Exception as e:
#         log_exception("menu.upload_input", e)
#         raise HTTPException(status_code=400, detail=f"upload failed: {e}")
#
#     local_path, cleanup = ensure_local_path(obj)
#
#     try:
#         #  runs_root는 temp 아래로 두어도 됨(디버그 목적)
#         runs_root = Path(tmp_prefix) / "ai_runs"
#
#         result = run_menu_ai(image_path=local_path, runs_root=runs_root, run_id=job_id)
#         return MenuUploadResponse(job_id=job_id, upload_type="menu", result=result)
#
#     except Exception as e:
#         log_exception("menu.ai_failed", e)
#         raise HTTPException(status_code=500, detail=f"menu ai failed: {type(e).__name__}: {e}")
#
#     finally:
#         cleanup()
#         #  menu 정책: 작업 끝나면 temp 삭제
#         # delete_prefix(prefix_key=tmp_prefix)
