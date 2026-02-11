import React, { useState } from "react";

export default function RestrictionsAdminList({
  data = [],
  loading = false,
  onChangeCategory,
  onChangeItem,
  onSaveCategory,
  onSaveItem,
  onAddItem,
}) {
  const [addingItemForCategory, setAddingItemForCategory] = useState(null);
  const [newItemKo, setNewItemKo] = useState("");
  const [newItemEn, setNewItemEn] = useState("");
  if (!data.length) {
    return (
      <div className="admin-list-panel">
        <div className="empty-list-message">
          표시할 데이터가 없습니다. (왼쪽에서 먼저 등록하세요)
        </div>
      </div>
    );
  }

  return (
    <div className="admin-list-panel">
      <h3>전체 리스트 (active 포함)</h3>

      {data.map((c) => (
        <div key={c.category_id} className="category-item-box">
          <div className="category-header">
            <strong>Category #{c.category_id}</strong>

            <input
              type="text"
              value={c.category_label_ko || ""}
              onChange={(e) => onChangeCategory(c.category_id, { category_label_ko: e.target.value })}
              placeholder="category_label_ko"
            />
            <input
              type="text"
              value={c.category_label_en || ""}
              onChange={(e) => onChangeCategory(c.category_id, { category_label_en: e.target.value })}
              placeholder="category_label_en"
            />

            <label>
              <input
                type="checkbox"
                checked={!!c.category_active}
                onChange={(e) => onChangeCategory(c.category_id, { category_active: e.target.checked })}
              />
              active
            </label>

            <button onClick={() => onSaveCategory(c)} disabled={loading} className="save-button">
              저장
            </button>
          </div>

          <div className="items-list">
            {(c.items || []).map((it) => (
              <div key={it.item_id} className="item-row">
                <span>Item #{it.item_id}</span>

                <input
                  type="text"
                  value={it.item_label_ko || ""}
                  onChange={(e) => onChangeItem(c.category_id, it.item_id, { item_label_ko: e.target.value })}
                  placeholder="item_label_ko"
                />
                <input
                  type="text"
                  value={it.item_label_en || ""}
                  onChange={(e) => onChangeItem(c.category_id, it.item_id, { item_label_en: e.target.value })}
                  placeholder="item_label_en"
                />

                <label>
                  <input
                    type="checkbox"
                    checked={!!it.item_active}
                    onChange={(e) => onChangeItem(c.category_id, it.item_id, { item_active: e.target.checked })}
                  />
                  active
                </label>

                <button onClick={() => onSaveItem(c.category_id, it)} disabled={loading} className="save-button-item">
                  저장
                </button>
              </div>
            ))}

            {/* 새로운 아이템 추가 폼 */}
            {addingItemForCategory === c.category_id ? (
              <div className="add-item-form">
                <div className="add-item-inputs">
                  <input
                    type="text"
                    value={newItemKo}
                    onChange={(e) => setNewItemKo(e.target.value)}
                    placeholder="item_label_ko"
                    autoFocus
                  />
                  <input
                    type="text"
                    value={newItemEn}
                    onChange={(e) => setNewItemEn(e.target.value)}
                    placeholder="item_label_en"
                  />
                </div>
                <div className="add-item-actions">
                  <button
                    onClick={async () => {
                      if (!newItemKo.trim() || !newItemEn.trim()) {
                        alert("한글명과 영문명을 모두 입력해주세요.");
                        return;
                      }
                      await onAddItem(c.category_id, {
                        item_label_ko: newItemKo.trim(),
                        item_label_en: newItemEn.trim(),
                      });
                      setNewItemKo("");
                      setNewItemEn("");
                      setAddingItemForCategory(null);
                    }}
                    disabled={loading}
                    className="save-button"
                  >
                    저장
                  </button>
                  <button
                    onClick={() => {
                      setNewItemKo("");
                      setNewItemEn("");
                      setAddingItemForCategory(null);
                    }}
                    className="cancel-button"
                  >
                    취소
                  </button>
                </div>
              </div>
            ) : (
              <div className="add-item-row">
                <button
                  onClick={() => setAddingItemForCategory(c.category_id)}
                  disabled={loading}
                  className="add-item-to-category-button"
                >
                  + Item 추가
                </button>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
