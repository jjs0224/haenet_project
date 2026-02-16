from fastapi import APIRouter

from backend.app.features.member.router import router as member_router
from backend.app.features.auth.router import router as auth_router
from backend.app.features.debug.router import router as debug_router
from backend.app.features.restrictions.router import router as restrictions_router
from backend.app.features.restrictions.admin_router import router as restrictions_admin
from backend.app.features.menu.router import router as menu_router
from backend.app.features.review.router import router as review_router
from backend.app.features.meta.router import router as meta_router
from backend.app.features.community.router import router as community_router
from backend.app.features.comment.router import router as comment_router
from backend.app.features.jobs.router import router as jobs_router
from backend.app.features.journal.router import router as journal_router

# router 전체 관리
api_router = APIRouter()

api_router.include_router(member_router)
api_router.include_router(auth_router)
api_router.include_router(debug_router)
api_router.include_router(restrictions_router)
api_router.include_router(restrictions_admin)
api_router.include_router(menu_router)
api_router.include_router(review_router)
api_router.include_router(meta_router)
api_router.include_router(community_router)
api_router.include_router(comment_router)
api_router.include_router(jobs_router)
api_router.include_router(journal_router)