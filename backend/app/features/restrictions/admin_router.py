from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.app.core.security.deps import require_admin
from backend.app.core.database import get_db
from . import schemas, service


# Admin 관리자 Category, Item 초기 등록, 사용중 Update API
router = APIRouter(prefix="/admin", tags=["admin"])

# Category, Item 전체 등록
@router.post("/restrictions/batch", dependencies=[Depends(require_admin)],)
def create_categories_batch(payload: schemas.CategoriesBatchCreate, db: Session = Depends(get_db)):
    print("전체 등록으로 들어왔다!")


    print("payload :: ", payload)
    return service.create_categories_batch(db, payload)

# Category 수정
@router.put("/restrictions/category/{category_id}", response_model=dict, dependencies=[Depends(require_admin)],)
def update_category(category_id: int, payload: schemas.CategoryUpdate, db: Session = Depends(get_db)):
    print("category id :: ", category_id)
    print("payload :: ", payload)
    return service.update_category(db, category_id, payload)

# Item 수정
@router.put("/restrictions/item/{item_id}", response_model=dict, dependencies=[Depends(require_admin)], )
def update_item(item_id: int, payload: schemas.ItemUpdate, db: Session = Depends(get_db)):
    return service.update_item(db, item_id, payload)

# 기존 Category에 Item 추가
@router.post("/restrictions/category/{category_id}/item", response_model=dict, dependencies=[Depends(require_admin)])
def add_item_to_category(category_id: int, payload: schemas.ItemAddToCategory, db: Session = Depends(get_db)):
    return service.add_item_to_category(db, category_id, payload)