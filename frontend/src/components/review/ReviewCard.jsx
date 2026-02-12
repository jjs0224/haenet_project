import styles from './ReviewCard.module.css';
import { useNavigate } from "react-router-dom";
import { useContext, useMemo, useState } from "react";
import { MetaContext } from "../../context/MetaContext";
import { MemberContext } from "../../context/MemberContext";

function ReviewItem({ review, categories }) {
  const nav = useNavigate();
  const { stateMeta } = useContext(MetaContext);
  const { stateMember } = useContext(MemberContext);
  const [currentImageIndex, setCurrentImageIndex] = useState(0);

  // categories prop이 있으면 사용, 없으면 MetaContext 사용 - useMemo로 최적화
  const restrictionsData = useMemo(
    () => categories || stateMeta?.restrictions || [],
    [categories, stateMeta?.restrictions]
  );

  // 데이터 정규화 (API 응답 형식이 다를 수 있으므로)
  const reviewId = review.review_id || review.id;
  const title = review.review_title || review.title || review.subject || "(No title)";
  const content = review.review_content || review.content || "";
  const rating = review.rating || 0;
  const imageUrls = review.image_urls || (review.image_url ? [review.image_url] : []);

  // menu_name이 배열이면 join, 문자열이면 그대로, 없으면 빈 문자열
  const createdAt = review.created_at || review.create_at || "";

  // 작성자 닉네임 결정:
  // 1) API 응답에 nickname 필드가 있으면 사용
  // 2) 없으면 본인 리뷰일 때만 현재 로그인 유저의 닉네임 사용
  const authorNickname = useMemo(() => {
    if (review.nickname || review.author_nickname || review.member_nickname) {
      return review.nickname || review.author_nickname || review.member_nickname;
    }
    // 본인 리뷰 체크: member_id 비교
    const reviewMemberId = Number(review.member_id);
    const myMemberId = Number(stateMember?.me?.member_id);
    if (reviewMemberId > 0 && myMemberId > 0 && reviewMemberId === myMemberId) {
      return stateMember.me.nickname || null;
    }
    return null;
  }, [review.nickname, review.author_nickname, review.member_nickname, review.member_id, stateMember?.me]);

  // 아이템 ID → 라벨 리스트 (카테고리 구분 없이 flat)
  const itemLabels = useMemo(() => {
    const reviewItems = review.review_items || [];
    const itemIds = typeof reviewItems === 'string'
      ? reviewItems.split(',').map(id => Number(id.trim()))
      : Array.isArray(reviewItems)
      ? reviewItems.map(id => Number(id))
      : [];

    if (!itemIds.length || !restrictionsData.length) return [];

    const allItems = restrictionsData.flatMap(cat => cat.items || []);
    const labels = itemIds
      .map(id => {
        const item = allItems.find(it => it.item_id === id);
        return item ? (item.item_label_en || item.item_label_ko || `Item #${id}`) : null;
      })
      .filter(Boolean);

    return labels;
  }, [review.review_items, restrictionsData]);

  const handleClick = () => {
      // console.log("클릭 reviewId :: ", {reviewId})
      nav(`/review/${reviewId}`);
  };

  const handlePrevImage = (e) => {
    e.stopPropagation();
    setCurrentImageIndex((prev) => (prev === 0 ? imageUrls.length - 1 : prev - 1));
  };

  const handleNextImage = (e) => {
    e.stopPropagation();
    setCurrentImageIndex((prev) => (prev === imageUrls.length - 1 ? 0 : prev + 1));
  };

  // 별점 렌더링 함수
  const renderStars = (rating) => {
    const stars = [];
    for (let i = 1; i <= 5; i++) {
      stars.push(
        <span key={i} className={i <= rating ? styles.starActive : styles.starInactive}>
          ★
        </span>
      );
    }
    return stars;
  };

  return (
    <div onClick={handleClick} className={styles.reviewCard}>
        {/* 작성자의 식습관 영역 */}
        {(authorNickname || itemLabels.length > 0) && (
          <div className={styles.habitHeader}>
            {authorNickname && (
              <div className={styles.habitTitle}>
                <span className={styles.habitNickname}>{authorNickname}</span>'s dietary restriction
              </div>
            )}
            {itemLabels.length > 0 && (
              <div className={styles.habitItemTags}>
                {itemLabels.map((label, idx) => (
                  <span key={idx} className={styles.habitItemTag}>{label}</span>
                ))}
              </div>
            )}
          </div>
        )}

      {imageUrls.length > 0 ? (
        <div className={styles.reviewCardImageContainer}>
          <img
            src={imageUrls[currentImageIndex]}
            alt={title}
            className={styles.reviewCardImage}
          />
          {imageUrls.length > 1 && (
            <>
              <button
                onClick={handlePrevImage}
                className={`${styles.imageNavBtn} ${styles.prev}`}
              >
                ‹
              </button>
              <button
                onClick={handleNextImage}
                className={`${styles.imageNavBtn} ${styles.next}`}
              >
                ›
              </button>
              <div className={styles.imageIndicator}>
                {currentImageIndex + 1} / {imageUrls.length}
              </div>
            </>
          )}
        </div>
      ) : (
        <div className={styles.reviewCardNoImage}>
          🍽️
        </div>
      )}

      <div className={styles.reviewCardContent}>
        {/* 메뉴 이름 */}
        {/* {menuName && (
          <div className={styles.menuNamesContainer}>
            {menuName.split(',').map((menu, idx) => (
              <div key={idx} className={styles.menuNameTag}>
                🍽️ {menu.replace(/["[\]]/g, '').trim()}
              </div>
            ))}
          </div>
        )} */}

        {/* 제목 */}
        <h3 className={styles.reviewCardTitle}>
          {title}
        </h3>

        {/* 별점 */}
        {rating > 0 && (
          <div className={styles.reviewCardRating}>
            {renderStars(rating)}
            <span className={styles.ratingText}>
              ({rating}.0)
            </span>
          </div>
        )}

        {/* 내용 미리보기 */}
        {content && (
          <p className={styles.reviewCardPreview}>
            {content}
          </p>
        )}


        {/* 작성일 */}
        {createdAt && (
          <div className={styles.reviewCardDate}>
            {new Date(createdAt).toLocaleDateString('en-KR')}
          </div>
        )}
      </div>
    </div>
  );
}

export default ReviewItem;
