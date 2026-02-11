import React, { useContext, useEffect, useState, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ReviewContext } from "../../context/ReviewContext";
import { AuthContext } from "../../context/AuthContext";
import ReviewItem from "../../components/review/ReviewCard";
import { MetaAPI } from "../../api/metaApi";
import styles from "./ReviewList.module.css";

export default function ReviewList() {
  const { stateReview, reviewActions } = useContext(ReviewContext);
  const { stateAuth } = useContext(AuthContext);
  const [searchParams, setSearchParams] = useSearchParams();

  const [categories, setCategories] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [selectedItemIds, setSelectedItemIds] = useState([]); // 선택된 아이템 ID 배열
  // 로그인 안된 상태에서 ?mine=true 이면 무시
  const [showMyOnly, setShowMyOnly] = useState(() =>
    searchParams.get("mine") === "true" && stateAuth.accessToken ? true : false
  );
  const [loginGuide, setLoginGuide] = useState(false); // "로그인을 해주세요" 안내 표시 플래그

  // 카테고리 및 리뷰 목록 로드
  useEffect(() => {
    if (showMyOnly) {
      reviewActions.fetchMyList();
    } else {
      reviewActions.fetchList();
    }
    loadCategories();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showMyOnly]);

  const loadCategories = async () => {
    try {
      const response = await MetaAPI.getActiveRestrictions();
      // 응답 형식: { etag: "...", data: [...] }
      const list = response.data?.data || response.data || [];
      setCategories(list);
    } catch (e) {
      console.error("카테고리 로드 실패:", e);
    }
  };

  // 아이템 선택/해제 토글
  const toggleItem = (itemId) => {
    setSelectedItemIds(prev => {
      if (prev.includes(itemId)) {
        return prev.filter(id => id !== itemId);
      } else {
        return [...prev, itemId];
      }
    });
  };

  // "내 리뷰만" 토글
  const toggleMyOnly = () => {
    // 현재 활성 상태가 아닌 경우(켜려는 경우) 로그인 체크
    if (!showMyOnly && !stateAuth.accessToken) {
      setLoginGuide(true); // 안내문구 표시
      return;
    }
    setLoginGuide(false);
    setShowMyOnly(prev => {
      const next = !prev;
      if (next) {
        setSearchParams({ mine: "true" });
      } else {
        setSearchParams({});
      }
      return next;
    });
    // 카테고리/아이템 필터 초기화
    setSelectedCategory(null);
    setSelectedItemIds([]);
  };

  // 필터 초기화
  const clearFilters = () => {
    setSelectedCategory(null);
    setSelectedItemIds([]);
    setLoginGuide(false);
    if (showMyOnly) {
      setShowMyOnly(false);
      setSearchParams({});
    }
  };

  // 선택된 카테고리 또는 아이템으로 필터링된 리뷰 목록
  const filteredReviews = useMemo(() => {
    return stateReview.list.filter((review) => {
      const reviewItems = review.review_items || [];

      // review_items가 문자열인 경우 배열로 변환
      const reviewItemIds = typeof reviewItems === 'string'
        ? reviewItems.split(',').map(id => Number(id.trim()))
        : Array.isArray(reviewItems)
        ? reviewItems.map(id => Number(id))
        : [];

      // 특정 아이템이 선택되었으면 선택된 모든 아이템이 포함된 리뷰만 표시
      if (selectedItemIds.length > 0) {
        return selectedItemIds.every(itemId => reviewItemIds.includes(itemId));
      }

      // 아이템이 선택되지 않고 카테고리만 선택되었으면 해당 카테고리의 아이템 중 하나라도 포함된 리뷰 표시
      // if (selectedCategory) {
      //   const categoryItems = selectedCategory.items || [];
      //   return categoryItems.some(catItem =>
      //     reviewItemIds.includes(catItem.item_id)
      //   );
      // }

      // 필터가 없으면 전체 표시
      return true;
    });
  }, [stateReview.list, selectedItemIds]);

  const displayList = filteredReviews;
  const displayLoading = stateReview.loading;
  const displayError = stateReview.error;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>Review List</h1>
        <Link to="/review/new" className={styles.createButton}>
          + New Review
        </Link>
      </div>

      {/* 필터링 섹션 */}
      {categories.length > 0 && (
        <div className={styles.filterSection}>
          {/* 헤더 */}
          <div className={styles.filterHeader}>
            <div className={styles.filterTitle}>Filter</div>
            <div className={styles.filterHeaderButtons}>
              <button
                onClick={toggleMyOnly}
                className={`${styles.myOnlyButton} ${showMyOnly ? styles.myOnlyActive : ''}`}
              >
                My Reviews
              </button>
              {(selectedCategory || selectedItemIds.length > 0 || showMyOnly) && (
                <button onClick={clearFilters} className={styles.clearButton}>
                  Filter reset
                </button>
              )}
            </div>
          </div>

          {/* 카테고리 선택 */}
          <div className={styles.categorySection}>
            <div className={styles.categoryButtons}>
              <button
                onClick={() => setSelectedCategory(null)}
                className={`${styles.categoryButton} ${!selectedCategory ? styles.active : ''}`}
              >
                All
              </button>
              {categories.map((category) => (
                <button
                  key={category.category_id}
                  onClick={() => setSelectedCategory(category)}
                  className={`${styles.categoryButton} ${selectedCategory?.category_id === category.category_id ? styles.active : ''}`}
                >
                  {category.category_label_en || category.category_label_ko || `Category #${category.category_id}`}
                </button>
              ))}
            </div>
          </div>

          {/* 선택된 아이템 표시 (다른 카테고리에서 선택한 것들) */}
          {/* {selectedItemIds.length > 0 && (
            <div className={styles.itemSection}>
              <div className={styles.itemLabel}>Selected ({selectedItemIds.length})</div>
              <div className={styles.itemButtons}>
                {categories.flatMap(cat => cat.items || [])
                  .filter(item => selectedItemIds.includes(item.item_id))
                  .map((item) => (
                    <button
                      key={item.item_id}
                      onClick={() => toggleItem(item.item_id)}
                      className={`${styles.itemButton} ${styles.selected}`}
                    >
                      ✓ {item.item_label_ko || item.item_label_en || `Item #${item.item_id}`}
                    </button>
                  ))}
              </div>
            </div>
          )} */}

          {/* 아이템 선택 (카테고리가 선택되었을 때만 표시) */}
          {selectedCategory && selectedCategory.items && selectedCategory.items.length > 0 && (
            <div className={styles.itemSection}>
              <div className={styles.itemLabel}>
                {selectedCategory.category_label_en || selectedCategory.category_label_ko} Detail Items
              </div>
              <div className={styles.itemButtons}>
                {selectedCategory.items.map((item) => {
                  const isSelected = selectedItemIds.includes(item.item_id);
                  return (
                    <button
                      key={item.item_id}
                      onClick={() => toggleItem(item.item_id)}
                      className={`${styles.itemButton} ${isSelected ? styles.selected : ''}`}
                    >
                      {isSelected && "✓ "}
                      {item.item_label_en || item.item_label_ko || `Item #${item.item_id}`}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* 필터 상태 표시 */}
          {(selectedCategory || selectedItemIds.length > 0 || showMyOnly) && (
            <div className={styles.filterStatus}>
              {showMyOnly && (
                <span>Showing my reviews only</span>
              )}
              {showMyOnly && (selectedItemIds.length > 0 || selectedCategory) && (
                <span> · </span>
              )}
              {selectedItemIds.length > 0 ? (
                <>
                  <strong>{selectedItemIds.length} </strong> Displaying selected Details
                </>
              ) : selectedCategory ? (
                <>
                  "<strong>{selectedCategory.category_label_en || selectedCategory.category_label_ko}</strong>" Displaying reviews in this category
                </>
              ) : null}
            </div>
          )}
        </div>
      )}

      {/* 로그인 안내문구 (내 리뷰만 클릭 시 로그인 안된 경우) */}
      {loginGuide && (
        <div className={styles.loginGuideBox}>
          Please Sign in
        </div>
      )}

      {displayError && (
        <div className={styles.errorBox}>
          {displayError.includes("No access token after refresh")
            ? "Please Sign in"
            : <><strong>Error:</strong> {displayError}</>
          }
        </div>
      )}

      {displayLoading && (
        <div className={styles.loadingContainer}>
          <div className={styles.spinner}></div>
          <div className={styles.loadingText}>Loading...</div>
        </div>
      )}

      {!displayLoading && displayList.length === 0 && (
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>📝</div>
          <div className={styles.emptyTitle}>No reviews yet</div>
          <div className={styles.emptyDescription}>Create your first review!</div>
        </div>
      )}

      <div className={styles.reviewGrid}>
        {displayList.map((review) => (
          <ReviewItem
            key={review.review_id || review.id}
            review={review}
            categories={categories}
          />
        ))}
      </div>
    </div>
  );
}
