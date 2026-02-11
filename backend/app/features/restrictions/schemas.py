from pydantic import BaseModel, Field

# category, item 전체 조회 --- start
class RestrictionItemRead(BaseModel):
    item_id: int
    item_label_ko: str
    item_label_en: str
    item_active : bool
    category_id: int

class CategoryItemRead(BaseModel):
    category_id: int
    category_label_ko: str
    category_label_en: str
    category_active : bool
    items: list[RestrictionItemRead] = []
# category, item 전체 조회 --- end

# Category, Item 등록 --- start
class ItemCreate(BaseModel):
    item_label_ko: str
    item_label_en: str
    item_active: bool = True

class CategoryCreate(BaseModel):
    category_label_ko: str
    category_label_en: str
    category_active: bool = True
    items: list[ItemCreate] = Field(default_factory=list)

class CategoriesBatchCreate(BaseModel):
    categories: list[CategoryCreate]
# Category, Item 등록 --- end

# Category, Item 수정 --- start
class CategoryUpdate(BaseModel):
    category_label_ko: str
    category_label_en: str
    category_active: bool

class ItemUpdate(BaseModel):
    item_label_ko: str
    item_label_en: str
    item_active: bool
# Category, Item 수정 --- end

# Category에 Item 추가 --- start
class ItemAddToCategory(BaseModel):
    item_label_ko: str
    item_label_en: str
    item_active: bool = True
# Category에 Item 추가 --- end