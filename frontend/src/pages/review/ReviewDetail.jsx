import { useState, useContext, useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ReviewContext } from "../../context/ReviewContext";
import { MemberContext } from "../../context/MemberContext";
import { MetaAPI } from "../../api/metaApi";
import styles from "./ReviewDetailPage.module.css";

// ========== Utility Functions ==========
function normalizeReview(raw) {
  if (!raw) return null;

  // 백엔드/프론트 필드명 흔들려도 최대한 안전하게 매핑
  const title = raw.review_title ?? raw.title ?? raw.subject ?? "";
  const content = raw.review_content ?? raw.content ?? raw.body ?? "";
  const rating = raw.rating ?? raw.star ?? raw.score ?? null;

  // 작성일
  const createdAt =
    raw.review_create ?? raw.created_at ?? raw.createdAt ?? raw.created ?? null;

  // 이미지
  const images = Array.isArray(raw.image_urls)
    ? raw.image_urls
    : Array.isArray(raw.images)
      ? raw.images.map((x) => (typeof x === "string" ? x : x?.url)).filter(Boolean)
      : [];

  // menu_name
  const menuName = raw.menu_name ?? raw.menuName ?? raw.menu ?? "";

  // review_items: "3,7,12" | [3,7,12] | null  -> number[]
  const itemIds = (() => {
    const v = raw.review_items ?? raw.reviewItems ?? raw.item_ids ?? raw.itemIds;
    if (!v) return [];
    if (Array.isArray(v)) return v.map((x) => Number(x)).filter(Number.isFinite);
    if (typeof v === "string") {
      return v
        .split(",")
        .map((s) => Number(String(s).trim()))
        .filter(Number.isFinite);
    }
    return [];
  })();

  return {
    id: raw.id ?? raw.review_id ?? raw.reviewId ?? null,
    title,
    content,
    rating,
    createdAt,
    images,
    itemIds,
    menuName,
    raw,
  };
}

function formatDate(v) {
  if (!v) return "-";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleString();
}

function renderStars(rating) {
  const n = Number(rating);
  if (!Number.isFinite(n)) return "-";
  const clamped = Math.max(0, Math.min(5, Math.round(n)));
  return "★".repeat(clamped) + "☆".repeat(5 - clamped);
}

// ========== Main Component ==========
export default function ReviewDetailPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const { stateReview, reviewActions } = useContext(ReviewContext);
  const { stateMember } = useContext(MemberContext);
  const [categories, setCategories] = useState([]);

  // Fetch review detail
  useEffect(() => {
    if (!id) return;
    reviewActions.fetchDetail(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Load categories for restriction/allergy items
  useEffect(() => {
    loadCategories();
  }, []);

  const loadCategories = async () => {
    try {
      const response = await MetaAPI.getActiveRestrictions();
      const list = response.data?.data || response.data || [];
      setCategories(list);
    } catch (e) {
      console.error("Failed to load category:", e);
    }
  };

  const review = useMemo(
    () => normalizeReview(stateReview.detail),
    [stateReview.detail]
  );

  // 컨텐츠에 사용 중인지 확인
  const isUsedInContent = review?.raw?.used_in_content || false;

  // 권한 체크: 현재 사용자가 리뷰 작성자인지 확인
  const reviewMemberId = Number(review?.raw?.member_id);
  const loginMemberId = Number(stateMember.me?.member_id);
  const isOwner = loginMemberId > 0 && reviewMemberId > 0 && loginMemberId === reviewMemberId;

  const handleEdit = () => {
    nav(`/review/${id}/edit`);
  };

  // review_items를 배열로 변환
  const reviewItemIds = review?.itemIds || [];

  // 리뷰에 포함된 아이템 정보만 추출
  const reviewItems = [];
  categories.forEach(cat => {
    (cat.items || []).forEach(item => {
      if (reviewItemIds.includes(item.item_id)) {
        reviewItems.push({
          id: item.item_id,
          label: item.item_label_en || item.item_label_ko || `Item #${item.item_id}`
        });
      }
    });
  });

  // menuName 파싱
  const parsedMenus = (() => {
    const menuName = review?.menuName;
    if (!menuName) return [];

    let parsedMenus = [];
    if (Array.isArray(menuName)) {
      parsedMenus = menuName;
    } else if (typeof menuName === 'string') {
      const trimmed = menuName.trim();
      if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
        try {
          parsedMenus = JSON.parse(trimmed);
        } catch (e) {
          console.error("JSON parse error:", e);
          parsedMenus = [trimmed];
        }
      } else {
        parsedMenus = trimmed.split(',');
      }
    }

    return parsedMenus
      .map(m => String(m).trim())
      .filter(m => m.length > 0);
  })();

  // ========== Render ==========
  return (
    <div className={styles.pageContainer}>
      {/* Page Header */}
      <div className={styles.pageHeader}>
        <h2 className={styles.pageTitle}>Review Details</h2>
        <button onClick={() => nav("/review")} className={styles.backButton}>
          List
        </button>
      </div>

      {/* Error State */}
      {stateReview.error && (
        <div className={styles.error}>
          {stateReview.error}
        </div>
      )}

      {/* Loading State */}
      {stateReview.loading && (
        <div className={styles.loading}>
          Loading...
        </div>
      )}

      {/* Review Detail Content */}
      {!stateReview.loading && review && (
        <div className={styles.detailContainer}>
          {/* Header: 제목과 수정 버튼 */}
          <div className={styles.detailHeader}>
            <div className={styles.headerContent}>
              <h1 className={styles.reviewTitle}>
                {review.title || "(No title)"}
              </h1>
              <div className={styles.meta}>
                <span>Date of creation: {formatDate(review.createdAt)}</span>
                {review.location ? <span className={styles.location}>📍 {review.location}</span> : null}
              </div>
            </div>

            {/* 수정 버튼 */}
            {!isUsedInContent && isOwner && (
              <button onClick={handleEdit} className={styles.editButton}>
                Edit
              </button>
            )}

            {/* 컨텐츠에 사용 중일 때 수정 불가 메시지 */}
            {isUsedInContent && (
              <div className={styles.usedInContentBadge}>
                In use with content (non-modifiable)
              </div>
            )}
          </div>

          {/* 별점 */}
          <div className={styles.ratingSection}>
            <strong className={styles.ratingLabel}>Rating:</strong>
            <span className={styles.stars}>{renderStars(review.rating)}</span>
            {review.rating != null ? (
              <span className={styles.ratingValue}>({review.rating}/5)</span>
            ) : null}
          </div>

          {/* 이미지 */}
          {review.images?.length > 0 && (
            <div className={styles.imagesSection}>
              <div
                className={`${styles.imageGrid} ${
                  review.images.length === 1 ? styles.single :
                  review.images.length === 2 ? styles.double :
                  styles.triple
                }`}
              >
                {review.images.slice(0, 3).map((src, idx) => (
                  <div key={`${src}-${idx}`} className={styles.imageWrapper}>
                    <img
                      src={src}
                      alt={`review-${idx}`}
                      className={styles.image}
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 아이템 정보 (카테고리 없이 아이템만 표시) */}
          {reviewItems.length > 0 && (
            <div className={styles.itemsSection}>
              <strong className={styles.sectionTitle}>
                Restrictions / Allergy Information
              </strong>
              <div className={styles.itemTags}>
                {reviewItems.map((item) => (
                  <span key={item.id} className={styles.itemTag}>
                    {item.label}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 메뉴명(영수증 디텍트 결과) */}
          {parsedMenus.length > 0 && (
            <div className={styles.menuSection}>
              <strong className={styles.sectionTitle}>
                Menu
              </strong>
              <div className={styles.menuTags}>
                {parsedMenus.map((menu, idx) => (
                  <div key={idx} className={styles.menuTag}>
                    🍴 {menu}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 리뷰 내용 */}
          <div className={styles.contentSection}>
            <strong className={styles.sectionTitle}>
              Content
            </strong>
            <div className={styles.contentBox}>
              {review.content || "-"}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}