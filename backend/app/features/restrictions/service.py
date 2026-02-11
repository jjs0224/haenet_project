from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.app.models.restrictions.category import Category
from backend.app.models.restrictions.item import Item
from backend.app.features.restrictions.schemas import CategoriesBatchCreate

# Category_Item 전체 조회
def get_categories_with_items(db: Session):
    print("service db ::", db)
    cats = db.query(Category).order_by(Category.category_id).all()

    result = []
    for c in cats:
        items = db.query(Item).filter(Item.category_id == c.category_id).order_by(Item.item_id).all()

        result.append({
            "category_id": c.category_id,
            "category_label_ko": c.category_label_ko,
            "category_label_en": c.category_label_en,
            "category_active": c.category_active,
            "items": [
                {
                    "item_id": it.item_id,
                    "item_label_ko": it.item_label_ko,
                    "item_label_en": it.item_label_en,
                    "item_active": it.item_active,
                    "category_id": it.category_id,
                }
                for it in items
            ],
        })

    return result



# Category_Item 등록
def create_categories_batch(db: Session, payload: CategoriesBatchCreate):
    created = []
    categories = payload.categories  # list[CategoryCreate]
    print("categories :: ", categories)
    if not categories:
        raise HTTPException(status_code=400, detail="categories가 비어있습니다.")

    try:
        for c in categories:

            category = Category(
                category_label_ko=c.category_label_ko,
                category_label_en=c.category_label_en,
                category_active=c.category_active,
            )
            db.add(category)
            db.flush()

            print("category :: ", category)

            items_created = []
            for it in c.items:
                item = Item(
                    category_id=category.category_id,
                    item_label_ko=it.item_label_ko,
                    item_label_en=it.item_label_en,
                    item_active=it.item_active,
                )

                print("item :: ", it)

                db.add(item)
                db.flush()
                items_created.append({
                    "item_id": item.item_id,
                    "item_label_ko": item.item_label_ko,
                    "item_label_en": item.item_label_en,
                    "item_active": bool(item.item_active),
                    "category_id": item.category_id,
                })

            created.append({
                "category_id": category.category_id,
                "category_label_ko": category.category_label_ko,
                "category_label_en": category.category_label_en,
                "category_active": bool(category.category_active),
                "items": items_created,
            })
        print("db 커밋 했다.")
        db.commit()
        return created

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate value (unique constraint).")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# Category 수정
def update_category(db: Session, category_id: int, payload):
    print("payload :: ", payload)

    c = db.get(Category, category_id)
    if not c:
        raise HTTPException(status_code=404, detail="Category not found")

    c.category_label_ko = payload.category_label_ko
    c.category_label_en = payload.category_label_en
    c.category_active = payload.category_active

    try:
        db.commit()
        return {
            "category_id": c.category_id,
            "category_label_ko": c.category_label_ko,
            "category_label_en": c.category_label_en,
            "category_active": bool(c.category_active),
        }
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate value (unique constraint).")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# Item 수정
def update_item(db: Session, item_id: int, payload):
    it = db.get(Item, item_id)
    if not it:
        raise HTTPException(status_code=404, detail="Item not found")

    it.item_label_ko = payload.item_label_ko
    it.item_label_en = payload.item_label_en
    it.item_active = payload.item_active

    try:
        db.commit()
        return {
            "item_id": it.item_id,
            "item_label_ko": it.item_label_ko,
            "item_label_en": it.item_label_en,
            "item_active": bool(it.item_active),
            "category_id": it.category_id,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# Category에 Item 추가
def add_item_to_category(db: Session, category_id: int, payload):
    # 먼저 category가 존재하는지 확인
    c = db.get(Category, category_id)
    if not c:
        raise HTTPException(status_code=404, detail="Category not found")

    try:
        # 새 item 생성
        item = Item(
            category_id=category_id,
            item_label_ko=payload.item_label_ko,
            item_label_en=payload.item_label_en,
            item_active=payload.item_active,
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        return {
            "item_id": item.item_id,
            "item_label_ko": item.item_label_ko,
            "item_label_en": item.item_label_en,
            "item_active": bool(item.item_active),
            "category_id": item.category_id,
        }
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate value (unique constraint).")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))