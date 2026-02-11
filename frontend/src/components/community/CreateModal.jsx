import { useContext, useEffect, useMemo, useState } from "react";
import Modal from "../common/Modal";
import styles from "../../styles/CreateModal.module.css";
import templateStyles from "../../styles/TemplateRadioCard.module.css";
import TemplateRadioCard from "./TemplateRadioCard";

import { MemberContext } from "../../context/MemberContext";

export default function CreateModal({
  isOpen,
  onClose,
  stateReview,
  reviewActions,
  onConfirm,
  saving = false,
}) {
  // 로그인 사용자 정보
  const { stateMember } = useContext(MemberContext);
  const myMemberId = stateMember?.me?.member_id;

  const [templateId, setTemplateId] = useState(1);
  const [selectedIds, setSelectedIds] = useState([]);

  // 여기서부터 list로 사용 (서버에서 내것만 내려줌)
  const myReviews = useMemo(() => stateReview.list ?? [], [stateReview.list]);
  // console.log("community :: ", myReviews)

  // 0/1, true/false, "1"/"0" 등 다 커버
  const toBool = (v) => v === true || v === 1 || v === "1" || v === "true";

  // temp1 - 함수를 useMemo 밖에서 정의
  const isReviewActive = (r) =>
    toBool(r.available ?? r.is_active ?? r.isActive) === true;

  // temp2
  const allIds = useMemo(() => {
    return myReviews
      .map((r) => r.review_id ?? r.id)
      .filter((v) => v !== null && v !== undefined);
  }, [myReviews]);

  // active도 내 리뷰(myList) 기준 temp1사용
  const activeReviews = useMemo(() => myReviews.filter(isReviewActive), [myReviews, isReviewActive]);

  useEffect(() => {
    if (!isOpen) return;

    // 로그인 안 됐으면 호출하지 않음
    if (!myMemberId) {
      setTemplateId(1);
      setSelectedIds([]);
      return;
    }

    // ✅ 모달이 열릴 때마다 /review/me 호출 (다른 유저 리뷰가 list에 남아있을 수 있으므로)
    if (!stateReview.loading) {
      reviewActions.fetchMyList();
    }

    setTemplateId(1);
    setSelectedIds([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, myMemberId]);

  // allIds를 string으로 변환하여 의존성으로 사용
  const allIdsKey = allIds.join(",");

  useEffect(() => {
    if (!isOpen) return;

    if (templateId === 2) {
        setSelectedIds(allIds);
    } else {
        setSelectedIds([]);
    }
  }, [templateId, allIdsKey, isOpen, allIds]);

  const toggleSelect = (id, isActive) => {
    if (!isActive) return;
    if (templateId === 2) return;

    setSelectedIds((prev) => {
      const has = prev.includes(id);
      if (has) return prev.filter((v) => v !== id);
      if (prev.length >= 3) return prev;
      return [...prev, id];
    });
  };

  const canSubmit =
    templateId === 1
      ? activeReviews.length >= 3 && selectedIds.length === 3
      : allIds.length >= 3;

  const handleConfirm = () => {

      // console.log("나 버튼 눌렀다.")

    if (!canSubmit || saving) return;

    const reviewIds = templateId === 2 ? allIds : selectedIds;
    // console.log("버튼 클릭 :: ", reviewIds)
    onConfirm?.({ templateId, reviewIds });
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="AI 이미지 생성">
      <p className={styles.desc}>Choose a template</p>

      <div className={templateStyles.templateGrid}>
        <TemplateRadioCard
          value={1}
          checked={templateId === 1}
          onChange={setTemplateId}
          imgSrc="/template1.png"
          title="Template 1 (Journal)"
          description="Select exactly 3 ACTIVE reviews"
        />

        <TemplateRadioCard
          value={2}
          checked={templateId === 2}
          onChange={setTemplateId}
          imgSrc="/template2.png"
          title="Template 2 (Map)"
          description="Uses ALL ACTIVE reviews"
        />
      </div>

      <div className={styles.section} style={{ marginTop: 12 }}>
        <div className={styles.sectionTitle}>
          Total reviews ({myReviews.length}) / ACTIVE ({activeReviews.length})
        </div>

        {!myMemberId && (
          <div className={styles.empty}>로그인이 필요합니다.</div>
        )}

        {myMemberId && stateReview.loading && (
          <div className={styles.loading}>리뷰 불러오는 중...</div>
        )}

        {myMemberId && !stateReview.loading && myReviews.length === 0 && (
          <div className={styles.empty}>리뷰가 없습니다.</div>
        )}

        {myMemberId && !stateReview.loading && myReviews.length > 0 && (
          <>
            {templateId === 1 && (
              <>
                <div className={styles.hint}>
                  Chosen 3 reviews will be used ({selectedIds.length}/3)
                </div>

                <ul className={styles.reviewList}>
                  {myReviews.map((r) => {
                    const id = r.review_id ?? r.id;
                    const title = r.review_title ?? r.title ?? "(no title)";
                    const isActive = isReviewActive(r);
                    const checked = selectedIds.includes(id);

                    return (
                      <li
                        key={id}
                        className={`${styles.reviewItem} ${
                          !isActive ? styles.inactive : ""
                        }`}
                      >
                        <label className={styles.checkboxRow}>
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={!isActive}
                            onChange={() => toggleSelect(id, isActive)}
                          />
                          <span className={styles.reviewTitle}>
                            {title}
                            {!isActive && (
                              <span className={styles.inactiveTag}> (INACTIVE)</span>
                            )}
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </>
            )}

            {templateId === 2 && (
              <div className={styles.hint}>
                Template 2 uses the location of ALL ACTIVE reviews to create a roadmap.
              </div>
            )}
          </>
        )}
      </div>

      <div className={styles.actions}>
        <button type="button" onClick={onClose} className={styles.btnGhost}>
          Cancel
        </button>

        <button
          type="button"
          onClick={handleConfirm}
          disabled={!canSubmit || saving}
          className={styles.btnPrimary}
        >
          {saving ? "Creating..." : "Create"}
        </button>
      </div>
    </Modal>
  );
}